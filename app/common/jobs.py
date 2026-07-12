"""Minimal in-memory job store.

Scanning is async: POST returns a job_id immediately; a background thread
processes the batch; the client polls GET /jobs/{id} for progress.

Job state is held in memory, so ECS desired_count is set to 1 (single replica).
For multi-replica deployments, replace with DynamoDB or Redis.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error
    total: int = 0
    processed: int = 0
    output_s3: Optional[str] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(id=uuid.uuid4().hex[:12])
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for k, v in fields.items():
                setattr(job, k, v)


STORE = JobStore()
