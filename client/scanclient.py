"""HTTP client for the ML scan services (URL and PE).

Both services follow the same async job pattern:
  POST /url/scan  or  POST /pe/scan  →  {"job_id": "...", "status": "running"}
  GET  /url/jobs/{id}               →  {"status": "done", "download_url": "..."}
"""

import time
from typing import Optional

import requests


class ScanClient:
    """Thin wrapper around the scan service REST API."""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        if "://" not in base_url:
            base_url = "http://" + base_url
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        if api_key:
            self._session.headers["X-API-Key"] = api_key

    # ------------------------------------------------------------------
    # URL scan
    # ------------------------------------------------------------------

    def submit_url_scan(self, urls: list[str]) -> str:
        """Submit a list of URLs; returns job_id."""
        resp = self._session.post(f"{self.base_url}/url/scan", json={"urls": urls}, timeout=30)
        resp.raise_for_status()
        return resp.json()["job_id"]

    def get_url_job(self, job_id: str) -> dict:
        resp = self._session.get(f"{self.base_url}/url/jobs/{job_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def wait_url_job(self, job_id: str, poll_interval: float = 3.0, timeout: float = 600) -> dict:
        """Poll until the URL job finishes; raises TimeoutError on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get_url_job(job_id)
            if job["status"] in ("done", "error"):
                return job
            time.sleep(poll_interval)
        raise TimeoutError(f"URL job {job_id} did not finish within {timeout}s")

    # ------------------------------------------------------------------
    # PE scan
    # ------------------------------------------------------------------

    def submit_pe_scan(self, s3_input: Optional[str] = None) -> str:
        """Submit PE scan from an S3 prefix; returns job_id."""
        body = {}
        if s3_input:
            body["s3_input"] = s3_input
        resp = self._session.post(f"{self.base_url}/pe/scan", json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()["job_id"]

    def get_pe_job(self, job_id: str) -> dict:
        resp = self._session.get(f"{self.base_url}/pe/jobs/{job_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def wait_pe_job(self, job_id: str, poll_interval: float = 5.0, timeout: float = 900) -> dict:
        """Poll until the PE job finishes; raises TimeoutError on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get_pe_job(job_id)
            if job["status"] in ("done", "error"):
                return job
            time.sleep(poll_interval)
        raise TimeoutError(f"PE job {job_id} did not finish within {timeout}s")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def healthz(self, kind: str = "url") -> dict:
        resp = self._session.get(f"{self.base_url}/{kind}/healthz", timeout=5)
        resp.raise_for_status()
        return resp.json()
