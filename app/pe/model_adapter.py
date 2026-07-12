"""PE model adapter.

Thin interface between the FastAPI service and the vendor-provided ML model.
The base Docker image ships the model and its Python SDK; this adapter
lazy-loads the SDK on first request (thread-safe) and reuses it for all files.

MODEL_MODE env var:
    stub  →  deterministic fake score for pipeline smoke-testing
    real  →  vendor ML SDK (requires SAI_API_CONFIG_PATH=/usr/src/app/config.ini)
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
    """Deterministic fake score — only for smoke-testing the pipeline."""
    h = hashlib.sha256()
    with open(pe_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return round(int(h.hexdigest()[:4], 16) / 0xFFFF * 100)


def _ensure_model() -> None:
    """Lazy-initialize the vendor ML SDK (called only on first real request)."""
    global _model_initialized, _analyze, _MultipartMLAnalysesBase
    global _BytesSample, _InputType, _Source, _DataFormat, _Filters

    if _model_initialized:
        return

    with _model_lock:
        if _model_initialized:
            return

        # Vendor ML SDK — bundled in the model base image.
        # Importing triggers model weight loading (~10-30 s).
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


def _extract_score(report: dict) -> int:
    """Extract 0-100 maliciousness score from the PE model report.

    PE model report structure:
    {
      "black_box": {
        "benign": {"score": <int 0-100>, "raw": <float>},
        "verdict": "Malicious" | "Likely clean" | ...
      },
      "random_forest": {...},
      ...
    }
    Higher score = more malicious; threshold 30 = malicious.
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


def _score_real(pe_path: str) -> int:
    """Score a PE file via the vendor ML SDK. Returns 0–100."""
    _ensure_model()
    with open(pe_path, "rb") as f:
        file_bytes = f.read()
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    samples = [_BytesSample(sample_id=sha256_hash, data=file_bytes)]
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
    """Return a maliciousness score 0–100 (≥30 → malicious)."""
    if os.getenv("MODEL_MODE", "stub") == "real":
        return _score_real(pe_path)
    return _score_stub(pe_path)
