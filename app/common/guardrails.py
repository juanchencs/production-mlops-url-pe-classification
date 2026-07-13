"""Decision guardrails — three-tier verdict routing.

Converts a 0-100 maliciousness score to a verdict and performs the
corresponding action. Logs structured JSON events to CloudWatch Logs
(via ECS awslogs log driver) and emits CloudWatch counter metrics.

Verdict tiers (probability = score / 100):

  QUARANTINE    prob >= 0.95  (score 95-100)  — high-confidence; auto-copy PE to quarantine prefix
  ALERT         0.75 <= prob < 0.95 (75-94)   — medium-confidence; security alert, no file action
  MANUAL_REVIEW 0.30 <= prob < 0.75 (30-74)   — low-confidence; flag for human review
  ALLOW         prob < 0.30   (score 0-29)    — clean; no action

Automatic quarantine is only triggered for >= 95% confidence to minimise
false-positive operational impact. Lower-confidence malicious detections
are routed to alert or manual review instead.
"""

import json
import logging
import os
import time
from enum import Enum
from typing import Optional

import boto3

from common import metrics

logger = logging.getLogger(__name__)
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")


class Verdict(str, Enum):
    ALLOW         = "ALLOW"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ALERT         = "ALERT"
    QUARANTINE    = "QUARANTINE"


def classify(score: int) -> Verdict:
    """Map a 0-100 maliciousness score to a guardrail verdict."""
    prob = score / 100.0
    if prob >= 0.95:
        return Verdict.QUARANTINE
    if prob >= 0.75:
        return Verdict.ALERT
    if prob >= 0.30:
        return Verdict.MANUAL_REVIEW
    return Verdict.ALLOW


def apply(
    verdict: Verdict,
    item_id: str,
    score: int,
    service: str,
    s3_bucket: Optional[str] = None,
    s3_key: Optional[str] = None,
) -> None:
    """Log a structured guardrail event, emit a counter metric, and
    quarantine PE files when verdict is QUARANTINE."""
    _log_event(verdict, item_id, score, service)
    _emit_metric(verdict, service)
    if verdict == Verdict.QUARANTINE and s3_bucket and s3_key:
        _quarantine_s3(s3_bucket, s3_key)


def _log_event(verdict: Verdict, item_id: str, score: int, service: str) -> None:
    """Emit structured JSON to CloudWatch Logs via the ECS awslogs driver."""
    event = json.dumps({
        "event":       "GUARDRAIL",
        "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service":     service,
        "verdict":     verdict.value,
        "score":       score,
        "probability": round(score / 100.0, 4),
        "item_id":     item_id,
    }, separators=(",", ":"))
    if verdict == Verdict.QUARANTINE:
        logger.critical(event)
    elif verdict == Verdict.ALERT:
        logger.warning(event)
    elif verdict == Verdict.MANUAL_REVIEW:
        logger.info(event)


def _emit_metric(verdict: Verdict, service: str) -> None:
    metric_name = {
        Verdict.QUARANTINE:    "Quarantine",
        Verdict.ALERT:         "SecurityAlert",
        Verdict.MANUAL_REVIEW: "ManualReview",
    }.get(verdict)
    if metric_name:
        metrics.emit_verdict(service, metric_name)


def _quarantine_s3(bucket: str, src_key: str) -> None:
    """Copy PE file to quarantine/pe/ prefix and tag it. Non-destructive: original stays in place."""
    try:
        filename = src_key.rsplit("/", 1)[-1]
        dest_key = f"quarantine/pe/{filename}"
        s3 = boto3.client("s3", region_name=AWS_REGION)
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": src_key},
            Key=dest_key,
            TaggingDirective="REPLACE",
            Tagging="status=quarantined&confidence=high",
        )
        logger.critical(json.dumps({
            "event": "QUARANTINE_COMPLETE",
            "src":   f"s3://{bucket}/{src_key}",
            "dest":  f"s3://{bucket}/{dest_key}",
        }, separators=(",", ":")))
    except Exception as exc:
        logger.error(json.dumps({
            "event":  "QUARANTINE_FAILED",
            "key":    src_key,
            "reason": str(exc),
        }, separators=(",", ":")))
