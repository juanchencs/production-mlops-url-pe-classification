"""极简的内存任务表。

扫描是异步的：POST 提交后立刻返回 job_id，后台线程跑批，客户端轮询 /jobs/{id}。
任务状态存在内存里，所以每个 service 的 desiredCount 设为 1（本项目扫描一个月才几次，
单任务足够；如需多副本请换成 DynamoDB / Redis）。
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

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == "running")


STORE = JobStore()
