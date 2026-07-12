"""PE model adapter.

This file is the only interface between our FastAPI code and the ML SDK.
The container is built FROM the ML model base image, which bundles the SDK
and model weights. We call it by importing the dsml_api Python package —
the model is loaded once on first call and reused for all subsequent files.

Set MODEL_MODE to switch behaviour:
    stub  →  deterministic hash-based score; no SDK loaded (pipeline smoke test)
    real  →  calls the ML SDK (requires SAI_API_CONFIG_PATH=/usr/src/app/config.ini)
"""

import hashlib
import os
import threading

_model_initialized = False
_model_lock = threading.Lock()
_analyze = None
_MultipartMLAnalysesBase = None
_BytesSample = None
_InputType = None
_Source = None
_DataFormat = None
_Filters = None


def _score_stub(pe_path: str) -> int:
    """Deterministic fake score based on file content hash — for pipeline testing only."""
    h = hashlib.sha256()
    with open(pe_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return round(int(h.hexdigest()[:4], 16) / 0xFFFF * 100)


def _ensure_model():
    """Lazy-load the ML SDK on first call (double-checked locking, ~10-30 s).
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


def _extract_score(report: dict) -> int:
    """Extract 0-100 score from PE model report dict (higher = more malicious).

    PE model report structure:
    {
      "black_box": {
        "benign": {"score": <int 0-100>, "raw": <float>},
        "pua":    {"score": <int 0-100>, "raw": <float>},
        "verdict": "Likely clean" | "Suspicious" | ...
      },
      ...
    }
    """
    if "black_box" in report:
        box = report["black_box"]
        if "benign" in box:
            return int(round(float(box["benign"]["score"])))
        if "score" in box:
            return int(round(float(box["score"])))
    if "benign" in report:
        return int(round(float(report["benign"]["score"])))
    if "score" in report:
        return int(round(float(report["score"])))
    return -1


def _score_real(pe_path: str) -> float:
    """Score a PE file via the ML SDK. Returns 0-100."""
    _ensure_model()
    with open(pe_path, "rb") as f:
        file_bytes = f.read()
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    samples = [
        _BytesSample(sample_id=sha256_hash, data=file_bytes)
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
    report = result["result"][0]["report"]
    return _extract_score(report)


def score_pe(pe_path: str) -> int:
    """Return a 0–100 maliciousness score (≥30 = malicious)."""
    if os.getenv("MODEL_MODE", "stub") == "real":
        return _score_real(pe_path)
    return _score_stub(pe_path)
