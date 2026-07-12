"""Scan API client helper — used by scan_url.py and scan_pe.py.

Uses stdlib only (urllib) — no pip install required on client machines.
API base URL = ALB DNS, e.g. http://mlscan-alb-xxxx.eu-west-2.elb.amazonaws.com
API key priority: function argument > SCAN_API_KEY environment variable.
"""

import json
import os
import time
import urllib.request
import urllib.error


class ScanClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        if "://" not in base_url:
            base_url = "http://" + base_url
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ["SCAN_API_KEY"]

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("X-API-Key", self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise SystemExit(f"HTTP {e.code}: {e.read().decode()}") from e

    def submit(self, prefix: str, body: dict) -> str:
        """prefix is the service path prefix, e.g. '/url' or '/pe'."""
        resp = self._req("POST", f"{prefix}/scan", body)
        print(f"Submitted: job_id={resp['job_id']}  total={resp.get('total')}")
        return resp["job_id"]

    def wait(self, prefix: str, job_id: str, poll_seconds: int = 5) -> dict:
        while True:
            job = self._req("GET", f"{prefix}/jobs/{job_id}")
            st = job["status"]
            print(f"  [{st}] {job.get('processed', 0)}/{job.get('total', 0)}")
            if st == "done":
                return job
            if st == "error":
                raise SystemExit("Scan failed:\n" + (job.get("error") or ""))
            time.sleep(poll_seconds)


def download(url: str, dest: str) -> None:
    urllib.request.urlretrieve(url, dest)
    print(f"Downloaded result CSV -> {dest}")
