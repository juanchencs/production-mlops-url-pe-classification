"""URL scan service (FastAPI).

- POST /url/scan   Submit a batch of URLs; returns job_id immediately
- GET  /url/jobs/{id}  Poll status; done → S3 path + presigned download URL
- GET  /url/healthz    ALB health check (no auth required)

Input (one of):
  urls:     list of URL strings in the request body
  s3_input: s3 URI pointing to a text file (one URL per line)

Output CSV: url,score,malicious,verdict — written to s3://<bucket>/mlmodels/data/output_data/url/
"""

import csv
import io
import os
import time
import traceback
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from common import metrics, s3util
from common.auth import require_api_key
from common.guardrails import Verdict, apply as guardrail_apply, classify as guardrail_classify
from common.jobs import STORE, Job
from model_adapter import score_url

OUTPUT_PREFIX = os.getenv(
    "OUTPUT_PREFIX", "s3://your-s3-bucket/mlmodels/data/output_data/url"
)
THRESHOLD = float(os.getenv("THRESHOLD", "30"))
SERVICE_KIND = os.getenv("SERVICE_KIND", "url")

app = FastAPI(title="mlscan url", version=os.getenv("APP_VERSION", "dev"))


class ScanRequest(BaseModel):
    urls: Optional[List[str]] = None
    s3_input: Optional[str] = None


@app.get("/url/healthz")
def healthz():
    return {"status": "ok", "kind": "url", "version": app.version}


@app.post("/url/scan", dependencies=[Depends(require_api_key)])
def scan_url(req: ScanRequest, background: BackgroundTasks):
    if req.s3_input:
        text = s3util.read_text(req.s3_input)
        urls = [line.strip() for line in text.splitlines() if line.strip()]
    elif req.urls:
        urls = [u.strip() for u in req.urls if u.strip()]
    else:
        raise HTTPException(400, "provide either 'urls' or 's3_input'")

    job = STORE.create()
    STORE.update(job.id, total=len(urls))
    metrics.emit_queue_depth(SERVICE_KIND, STORE.running_count())
    background.add_task(_run, job.id, urls)
    return {"job_id": job.id, "status": "running", "total": len(urls)}


@app.get("/url/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str):
    job: Optional[Job] = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


def _run(job_id: str, urls: list[str]) -> None:
    m = metrics.JobMetrics(SERVICE_KIND, THRESHOLD)
    try:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["url", "score", "malicious", "verdict"])
        for i, url in enumerate(urls, 1):
            t0 = time.perf_counter()
            score = score_url(url)
            m.record(score, (time.perf_counter() - t0) * 1000)
            verdict = guardrail_classify(score)
            guardrail_apply(verdict, url, score, SERVICE_KIND)
            writer.writerow([url, score, int(score >= THRESHOLD), verdict.value])
            if i % 100 == 0:
                STORE.update(job_id, processed=i)
        STORE.update(job_id, processed=len(urls))

        ts = time.strftime("%Y%m%d-%H%M%S")
        out_uri = f"{OUTPUT_PREFIX}/url-scan-{ts}-{job_id}.csv"
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
