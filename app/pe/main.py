"""PE file classification service (FastAPI).

Endpoints:
    POST /pe/scan        Submit an S3 prefix of PE files for async batch scoring
    GET  /pe/jobs/{id}   Poll job status; returns S3 URI + presigned download URL when done
    GET  /pe/healthz     ALB health check (no auth)

Input:
    s3_input  S3 prefix containing PE binary files (e.g. s3://bucket/input/pe/)

Output: CSV written to S3 with columns: filename, score, malicious
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

from common import s3util
from common.auth import require_api_key
from common.jobs import STORE, Job
from model_adapter import score_pe

DEFAULT_INPUT = os.getenv("DEFAULT_INPUT", "s3://<YOUR_S3_BUCKET>/mlmodels/data/input_data/pe")
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "s3://<YOUR_S3_BUCKET>/mlmodels/data/output_data/pe")
THRESHOLD = float(os.getenv("THRESHOLD", "30"))

app = FastAPI(title="pe-scan-service", version=os.getenv("APP_VERSION", "dev"))


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
        raise HTTPException(400, f"no objects found under {s3_input}")

    job = STORE.create()
    STORE.update(job.id, total=len(keys))
    background.add_task(_run, job.id, s3_input, keys)
    return {"job_id": job.id, "status": "running", "total": len(keys)}


@app.get("/pe/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str):
    job: Optional[Job] = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


def _run(job_id: str, s3_input: str, keys: list[str]) -> None:
    try:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["filename", "score", "malicious"])
        with tempfile.TemporaryDirectory() as tmp:
            for i, key in enumerate(keys, 1):
                filename = key.rsplit("/", 1)[-1]
                local = os.path.join(tmp, filename)
                s3util.download_to(s3_input, key, local)
                score = score_pe(local)
                writer.writerow([filename, score, int(score >= THRESHOLD)])
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
    except Exception as exc:  # noqa: BLE001
        STORE.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            finished_at=time.time(),
        )
