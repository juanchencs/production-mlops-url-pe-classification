# Design Document

## Goals

1. Serve two pre-built ML models (URL classifier, PE malware classifier) via reliable, monitored REST APIs
2. Support batch workloads (hundreds of URLs, thousands of PE files) without blocking the HTTP connection
3. Enable safe, zero-downtime deployments triggered by code merges
4. Eliminate long-lived credentials from CI and runtime environments
5. Manage all AWS infrastructure as code (Terraform)
6. Keep the app layer thin — the ML SDK and model weights live in the base image

## Non-Goals

- Real-time streaming results (a simple CSV download is sufficient)
- Multi-tenant isolation (single internal deployment)
- Horizontal auto-scaling (single replica is adequate for current workload)

---

## Service Design

### Async Job Pattern

Long-running batch jobs (PE scanning hundreds of files) cannot complete within an HTTP timeout. The services use a fire-and-poll pattern:

```
POST /pe/scan        → 200 {"job_id": "uuid", "status": "running", "total": 120}
GET  /pe/jobs/{id}   → 200 {"status": "running", "processed": 45}
GET  /pe/jobs/{id}   → 200 {"status": "done", "output_s3": "s3://...", "download_url": "..."}
```

The background task runs in FastAPI's `BackgroundTasks` (a thread pool, not async). This matches the ML SDK which uses blocking I/O and is not asyncio-compatible.

### Job Store

`app/common/jobs.py` implements an in-memory `JobStore` using a `dict` protected by a `threading.Lock`. This is sufficient for a single-replica deployment. For multi-replica, replace with DynamoDB or ElastiCache.

Job lifecycle: `running` → `done` | `error`. Jobs are never evicted (container restarts clean them automatically).

### Authentication

`app/common/auth.py` provides a FastAPI dependency `require_api_key`. The API key is fetched from AWS Secrets Manager on the first request and cached in-process. Health check endpoints (`/*/healthz`) are exempt — required by ALB target group health checks.

---

## Model Adapter Design

Both model adapters follow the same interface:
```python
score_url(url: str) -> int          # 0-100
score_pe(pe_path: str) -> int       # 0-100
```

### Real Mode

`MODEL_MODE=real` — the ML SDK is imported on first call using double-checked locking. The singleton pattern avoids re-loading multi-GB model weights on each request.

```python
_model_initialized = False
_model_lock = threading.Lock()

def _ensure_model():
    if _model_initialized:   # fast path (no lock)
        return
    with _model_lock:        # slow path (one thread initializes)
        if _model_initialized:
            return
        # ... ML SDK imports ...
        _model_initialized = True
```

### Stub Mode

`MODEL_MODE=stub` — no ML SDK imports, no model weights required. Score is a deterministic function of the input (SHA-256 hash modulo 100). Used for:
- CI pipeline smoke tests (no GPU or model license required)
- Integration tests of the API layer
- Local development

### Pydantic Version Compatibility

The PE ML SDK requires pydantic v1. The URL ML SDK is compatible with pydantic v2. The `requirements.txt` files differ accordingly:

| Service | pydantic | fastapi |
|---------|----------|---------|
| url | 2.10.4 | 0.115.6 |
| pe | 1.10.21 | 0.103.2 (last pydantic-v1-compatible release) |

**Root cause**: The PE base image runs as a non-root user. `pip install` without `--target` goes to `~/.local/lib/python3.9/site-packages/` which takes precedence over `/usr/local/lib`. Installing pydantic v2 from `requirements.txt` would shadow the system pydantic v1 that the ML SDK depends on.

---

## Docker Image Layering

```
ML model base image
├── Python 3.9 + system libs
├── ML SDK (dsml_api)
├── Model weight files (/usr/src/app/*.dat)
└── WORKDIR /usr/src/app         ← weight paths resolve here

App image (built in CI on every merge)
├── FROM <base>
├── WORKDIR /srv
├── pip install requirements.txt → /srv (or ~/.local for non-root user)
├── COPY common/ url/ or pe/
├── ENV PYTHONPATH=/srv           ← lets uvicorn find our modules
└── CMD cd /usr/src/app && uvicorn main:app ...
    ↑ changes CWD back so relative weight paths in config.ini resolve
```

The `cd /usr/src/app` in CMD is the critical fix. Without it, the ML SDK's `weight_file_path = model.dat` (relative) would resolve against `/srv` (our WORKDIR) and fail.

---

## Infrastructure as Code (Terraform)

All AWS resources are defined in `terraform/`. Key design choices:

- **S3 backend**: Terraform state is stored in S3 for team sharing and auditability
- **`lifecycle { ignore_changes = [container_definitions] }`** on task definitions: prevents Terraform from reverting image tags that CI has updated between `terraform apply` runs
- **`lifecycle { ignore_changes = [task_definition] }`** on services: same reason — CI updates the active revision, Terraform doesn't roll it back
- **Data sources for pre-existing resources**: `ecsTaskExecutionRole` and the GitHub OIDC provider are referenced as data sources, not recreated; `terraform destroy` will not delete them

---

## Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Long-lived CI credentials | GitHub OIDC — no `AWS_ACCESS_KEY_ID` stored |
| Container image integrity | ECR image tag immutability enabled |
| API access control | API key via Secrets Manager; rotatable without redeployment |
| S3 output access | 7-day presigned URL; no public bucket policy |
| Least-privilege IAM | `mlscan-task-role` scoped to specific bucket and secret ARNs |
| No public ingress | ALB is internal; no internet gateway on ECS subnets |
