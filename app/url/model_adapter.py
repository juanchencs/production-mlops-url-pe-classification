"""URL model adapter.

This file is the only interface between our FastAPI code and the ML SDK.
The container is built FROM the ML model base image, which bundles the SDK
and model weights. We call it by importing the dsml_api Python package —
the model is loaded once at startup and reused across all requests.

Set MODEL_MODE to switch behaviour:
    stub  →  deterministic hash-based score; no SDK loaded (pipeline smoke test)
    real  →  calls the ML SDK (requires SAI_API_CONFIG_PATH=/usr/src/app/config.ini)
"""

import os
import hashlib
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


def _score_stub(url: str) -> float:
    """Deterministic fake score based on SHA-256 hash — for pipeline testing only."""
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return round(int(h[:4], 16) / 0xFFFF * 100, 2)


def _ensure_model():
    """Lazy-load the ML SDK on first call (double-checked locking, ~5-10 s).
    Requires: SAI_API_CONFIG_PATH=/usr/src/app/config.ini
    """
    global _model_initialized, _analyze, _MultipartMLAnalysesBase
    global _BytesSample, _InputType, _Source, _DataFormat, _Filters

    if _model_initialized:
        return

    with _model_lock:
        if _model_initialized:
            return

        from dsml_api.initialization.analysis_init import dsml  # noqa: F401
        from dsml_api.app.common.analysis import analyze
        from dsml_api.app.common.pydantic_models.analysis_models import MultipartMLAnalysesBase
        from dsml_api.app.common.pydantic_models.samples import BytesSample
        from dsml_api.data_types import InputType, Source, DataFormat, Filters

        _analyze = analyze
        _MultipartMLAnalysesBase = MultipartMLAnalysesBase
        _BytesSample = BytesSample
        _InputType = InputType
        _Source = Source
        _DataFormat = DataFormat
        _Filters = Filters
        _model_initialized = True


def _score_batch_real(urls: List[str]) -> List[Tuple[str, float]]:
    """Batch-score URLs via the ML SDK. Returns [(url, score), ...], score 0-100."""
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
    """Return a 0–100 maliciousness score (≥30 = malicious)."""
    if os.getenv("MODEL_MODE", "stub") == "real":
        pairs = _score_batch_real([url])
        return pairs[0][1]
    return int(_score_stub(url))


def score_urls_batch(urls: List[str]) -> List[Tuple[str, int]]:
    """Batch scoring — more efficient than calling score_url() per URL."""
    if os.getenv("MODEL_MODE", "stub") == "real":
        return _score_batch_real(urls)
    return [(url, int(_score_stub(url))) for url in urls]
