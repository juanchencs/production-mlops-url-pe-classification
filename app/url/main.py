"""URL classification service (FastAPI).

Endpoints:
    POST /url/scan       Submit a batch of URLs for async scoring; returns job_id immediately
    GET  /url/jobs/{id}  Poll job status; returns S3 URI + presigned download URL when done
    GET  /url/healthz    ALB health check (no auth)

Input (choose one):
    urls      JSON list of URL strings in the request body
    s3_input  S3 URI of a plain-text file with one URL per line

Output: CSV written to S3 with columns: url, score, malicious
"""

import csv
import io
import os
import time
import traceback
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from common import s3util
from common.auth import require_api_key
from common.jobs import STORE, Job
from model_adapter import score_url

OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "s3://<YOUR_S3_BUCKET>/mlmodels/data/output_data/url")
THRESHOLD = float(os.getenv("THRESHOLD", "30"))

app = FastAPI(title="url-scan-service", version=os.getenv("APP_VERSION", "dev"))


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
    background.add_task(_run, job.id, urls)
    return {"job_id": job.id, "status": "running", "total": len(urls)}


@app.get("/url/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str):
    job: Optional[Job] = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


def _run(job_id: str, urls: list[str]) -> None:
    try:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["url", "score", "malicious"])
        for i, url in enumerate(urls, 1):
            score = score_url(url)
            writer.writerow([url, score, int(score >= THRESHOLD)])
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
    except Exception as exc:  # noqa: BLE001
        STORE.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            finished_at=time.time(),
        )
