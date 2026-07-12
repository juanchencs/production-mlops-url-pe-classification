"""URL model adapter.

Thin interface between the FastAPI service and the pre-built ML model.
The base Docker image ships the model and its Python SDK; this adapter
lazy-loads the SDK on first request (thread-safe) and reuses it across calls.

MODEL_MODE env var:
    stub  →  deterministic fake score for pipeline smoke-testing
    real  →  ML SDK (requires SAI_API_CONFIG_PATH=/usr/src/app/config.ini)
"""

import hashlib
import os
import threading
from typing import List, Tuple

_model_initialized = False
_model_lock = threading.Lock()
_analyze = None
_MultipartMLAnalysesBase = None
_BytesSample = None
_InputType = None
_Source = None
_DataFormat = None
_Filters = None


def _score_stub(url: str) -> int:
    """Deterministic fake score — only for smoke-testing the pipeline."""
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return int(round(int(h[:4], 16) / 0xFFFF * 100))


def _ensure_model() -> None:
    """Lazy-initialize the ML SDK (called only on first real request)."""
    global _model_initialized, _analyze, _MultipartMLAnalysesBase
    global _BytesSample, _InputType, _Source, _DataFormat, _Filters

    if _model_initialized:
        return

    with _model_lock:
        if _model_initialized:
            return

        # ML SDK — bundled in the model base image.
        # Importing triggers model weight loading (~5-10 s).
        from dsml_api.initialization.analysis_init import dsml  # noqa: F401
        from dsml_api.app.common.analysis import analyze
        from dsml_api.app.common.pydantic_models.analysis_models import MultipartMLAnalysesBase
        from dsml_api.app.common.pydantic_models.samples import BytesSample
        from dsml_api.data_types import DataFormat, Filters, InputType, Source

        _analyze = analyze
        _MultipartMLAnalysesBase = MultipartMLAnalysesBase
        _BytesSample = BytesSample
        _InputType = InputType
        _Source = Source
        _DataFormat = DataFormat
        _Filters = Filters
        _model_initialized = True


def _score_batch_real(urls: List[str]) -> List[Tuple[str, int]]:
    """Batch-score URLs via the ML SDK. Returns [(url, score), ...]."""
    _ensure_model()
    samples = [
        _BytesSample(sample_id=f"s_{i}", data=url.encode())
        for i, url in enumerate(urls)
    ]
    fields = _MultipartMLAnalysesBase(
        source=_Source.inline,
        data_format=_DataFormat.raw,
        samples=samples,
    )
    result = _analyze(
        input_type=_InputType.sample,
        ml_analyses_fields=fields,
        response_filters=[_Filters.report],
    )
    score_map = {
        item["sample_id"]: int(round(float(item["report"]["score"])))
        for item in result["result"]
    }
    return [(url, score_map.get(f"s_{i}", -1)) for i, url in enumerate(urls)]


def score_url(url: str) -> int:
    """Return a maliciousness score 0–100 (≥30 → malicious)."""
    if os.getenv("MODEL_MODE", "stub") == "real":
        return _score_batch_real([url])[0][1]
    return _score_stub(url)


def score_urls_batch(urls: List[str]) -> List[Tuple[str, int]]:
    """Batch-score for efficiency. Returns [(url, score), ...]."""
    if os.getenv("MODEL_MODE", "stub") == "real":
        return _score_batch_real(urls)
    return [(url, _score_stub(url)) for url in urls]
