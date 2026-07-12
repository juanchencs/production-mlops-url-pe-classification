"""CloudWatch custom metrics for the ML scan services.

Emits per-item and per-job metrics asynchronously (daemon threads) so
CloudWatch API latency never delays scan responses. Drops silently on error.

Namespace: MLScan   Dimension: Service=url | Service=pe

Metrics emitted:
  Score             – maliciousness score per item (0-100)
  ScanLatencyMs     – ms to score one item
  JobDuration       – wall-clock seconds for a completed job
  MaliciousPct      – % of items flagged malicious in a job (0-100)
  MeanScore         – mean score across a job
  JobItemsProcessed – item count for a completed job
  JobError          – 1 when a background job fails
  JobQueueDepth     – running jobs at the moment a new scan request arrives
"""

import os
import threading
import time
from typing import List

import boto3

NAMESPACE = "MLScan"
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
ENABLED = os.getenv("CLOUDWATCH_METRICS", "true").lower() == "true"

_cw = None
_cw_lock = threading.Lock()


def _client():
    global _cw
    if _cw is None:
        with _cw_lock:
            if _cw is None:
                _cw = boto3.client("cloudwatch", region_name=AWS_REGION)
    return _cw


def _put_async(metric_data: List[dict]) -> None:
    """Fire-and-forget: send metric_data to CloudWatch in a daemon thread."""
    if not ENABLED or not metric_data:
        return
    snapshot = metric_data[:]

    def _send():
        try:
            for i in range(0, len(snapshot), 150):  # CloudWatch max: 150 data points per call
                _client().put_metric_data(
                    Namespace=NAMESPACE,
                    MetricData=snapshot[i : i + 150],
                )
        except Exception:
            pass  # monitoring must never break the API

    threading.Thread(target=_send, daemon=True).start()


def _dims(service: str) -> List[dict]:
    return [{"Name": "Service", "Value": service}]


class JobMetrics:
    """Accumulates per-item metrics for one scan job.

    Usage:
        m = JobMetrics("url", threshold=30)
        for item in items:
            t0 = time.perf_counter()
            score = score_fn(item)
            m.record(score, (time.perf_counter() - t0) * 1000)
        m.finish()          # or m.finish_error() on exception
    """

    def __init__(self, service: str, threshold: float) -> None:
        self.service = service
        self.threshold = threshold
        self._dims = _dims(service)
        self._buf: List[dict] = []
        self._total = 0
        self._malicious = 0
        self._score_sum = 0.0
        self._t0 = time.perf_counter()

    def record(self, score: int, latency_ms: float) -> None:
        self._total += 1
        self._score_sum += score
        if score >= self.threshold:
            self._malicious += 1
        self._buf += [
            {"MetricName": "Score",         "Dimensions": self._dims, "Value": float(score), "Unit": "None"},
            {"MetricName": "ScanLatencyMs", "Dimensions": self._dims, "Value": latency_ms,   "Unit": "Milliseconds"},
        ]
        if len(self._buf) >= 100:
            _put_async(self._buf)
            self._buf = []

    def finish(self) -> None:
        """Flush remaining items and emit job-level summary metrics."""
        if self._buf:
            _put_async(self._buf)
            self._buf = []
        if self._total == 0:
            return
        duration = time.perf_counter() - self._t0
        _put_async([
            {"MetricName": "JobDuration",       "Dimensions": self._dims, "Value": duration,                                   "Unit": "Seconds"},
            {"MetricName": "MaliciousPct",      "Dimensions": self._dims, "Value": self._malicious / self._total * 100,        "Unit": "Percent"},
            {"MetricName": "MeanScore",         "Dimensions": self._dims, "Value": self._score_sum / self._total,              "Unit": "None"},
            {"MetricName": "JobItemsProcessed", "Dimensions": self._dims, "Value": float(self._total),                        "Unit": "Count"},
        ])

    def finish_error(self) -> None:
        """Flush any partial metrics and emit a JobError counter."""
        if self._buf:
            _put_async(self._buf)
            self._buf = []
        _put_async([{
            "MetricName": "JobError",
            "Dimensions": self._dims,
            "Value": 1.0,
            "Unit": "Count",
        }])


def emit_queue_depth(service: str, running_count: int) -> None:
    _put_async([{
        "MetricName": "JobQueueDepth",
        "Dimensions": _dims(service),
        "Value": float(running_count),
        "Unit": "Count",
    }])
