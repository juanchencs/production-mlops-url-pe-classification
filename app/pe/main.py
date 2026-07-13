"""PE scan service (FastAPI).

- POST /pe/scan    Submit an S3 prefix of PE files; returns job_id immediately
- GET  /pe/jobs/{id}  Poll status; done → S3 path + presigned download URL
- GET  /pe/healthz    ALB health check (no auth required)

Input:  s3_input — S3 prefix containing PE (Windows executable) binary files
Output CSV: filename,score,malicious,verdict — written to s3://<bucket>/mlmodels/data/output_data/pe/
"""

import csv
import io
import os
import tempfile
import time
import traceback
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from common import metrics, s3util
from common.auth import require_api_key
from common.guardrails import apply as guardrail_apply, classify as guardrail_classify
from common.jobs import STORE, Job
from model_adapter import score_pe

DEFAULT_INPUT = os.getenv(
    "DEFAULT_INPUT", "s3://your-s3-bucket/mlmodels/data/input_data/pe"
)
OUTPUT_PREFIX = os.getenv(
    "OUTPUT_PREFIX", "s3://your-s3-bucket/mlmodels/data/output_data/pe"
)
THRESHOLD = float(os.getenv("THRESHOLD", "30"))
SERVICE_KIND = os.getenv("SERVICE_KIND", "pe")

app = FastAPI(title="mlscan pe", version=os.getenv("APP_VERSION", "dev"))


class ScanRequest(BaseModel):
    s3_input: Optional[str] = None


@app.get("/pe/healthz")
def healthz():
    return {"status": "ok", "kind": "pe", "version": app.version}


@app.post("/pe/scan", dependencies=[Depends(require_api_key)])
def scan_pe(req: ScanRequest, background: BackgroundTasks):
    s3_input = req.s3_input or DEFAULT_INPUT
    keys = list(s3util.list_keys(s3_input))
    if not keys:
        raise HTTPException(400, f"no objects under {s3_input}")

    job = STORE.create()
    STORE.update(job.id, total=len(keys))
    metrics.emit_queue_depth(SERVICE_KIND, STORE.running_count())
    background.add_task(_run, job.id, s3_input, keys)
    return {"job_id": job.id, "status": "running", "total": len(keys)}


@app.get("/pe/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str):
    job: Optional[Job] = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


def _run(job_id: str, s3_input: str, keys: list[str]) -> None:
    m = metrics.JobMetrics(SERVICE_KIND, THRESHOLD)
    bucket = s3_input.removeprefix("s3://").split("/")[0]
    try:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["filename", "score", "malicious", "verdict"])
        with tempfile.TemporaryDirectory() as tmp:
            for i, key in enumerate(keys, 1):
                filename = key.rsplit("/", 1)[-1]
                local = os.path.join(tmp, filename)
                s3util.download_to(s3_input, key, local)
                t0 = time.perf_counter()
                score = score_pe(local)
                m.record(score, (time.perf_counter() - t0) * 1000)
                verdict = guardrail_classify(score)
                guardrail_apply(verdict, filename, score, SERVICE_KIND, s3_bucket=bucket, s3_key=key)
                writer.writerow([filename, score, int(score >= THRESHOLD), verdict.value])
                os.remove(local)
                if i % 50 == 0:
                    STORE.update(job_id, processed=i)
        STORE.update(job_id, processed=len(keys))

        ts = time.strftime("%Y%m%d-%H%M%S")
        out_uri = f"{OUTPUT_PREFIX}/pe-scan-{ts}-{job_id}.csv"
        s3util.upload_bytes(buf.getvalue().encode("utf-8"), out_uri)
        STORE.update(
            job_id,
            status="done",
            output_s3=out_uri,
            download_url=s3util.presigned_url(out_uri),
            finished_at=time.time(),
        )
        m.finish()
    except Exception as exc:  # noqa: BLE001
        STORE.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            finished_at=time.time(),
        )
        m.finish_error()
