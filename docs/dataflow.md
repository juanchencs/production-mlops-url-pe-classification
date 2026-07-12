# Data Flow

## URL Classification

### Input
A list of URLs submitted in the POST request body. No files are read from S3.

```json
POST /url/scan
{"urls": ["https://example.com", "http://suspicious.net/page"]}
```

### Processing

```mermaid
sequenceDiagram
    participant C as Client
    participant API as url-svc (FastAPI)
    participant BG as Background Thread
    participant SDK as ML SDK
    participant S3 as S3

    C->>API: POST /url/scan (urls list)
    API->>API: Create job (uuid)
    API->>BG: spawn background task
    API->>C: 200 {job_id, status: running}

    loop for each URL (batched)
        BG->>SDK: analyze(url)
        SDK->>BG: score 0-100
    end

    BG->>S3: upload url-scan-<ts>-<id>.csv
    BG->>BG: job.status = done

    C->>API: GET /url/jobs/{id}
    API->>C: {status: done, download_url: ...}
    C->>S3: GET presigned URL
    S3->>C: results.csv
```

### Output CSV

```
url,score,malicious
https://example.com,12,0
http://suspicious.net/page,67,1
```

---

## PE File Classification

### Input
An S3 prefix pointing to a directory of PE (Windows executable) binary files. Files are downloaded to a temporary local directory, scored, then deleted.

```json
POST /pe/scan
{"s3_input": "s3://<YOUR_S3_BUCKET>/data/input/pe/"}
```

### Processing

```mermaid
sequenceDiagram
    participant C as Client
    participant API as pe-svc (FastAPI)
    participant BG as Background Thread
    participant S3 as S3
    participant SDK as ML SDK

    C->>API: POST /pe/scan (s3_input prefix)
    API->>S3: list_objects (get all keys under prefix)
    API->>API: Create job
    API->>BG: spawn background task (job_id, key list)
    API->>C: 200 {job_id, status: running, total: N}

    loop for each PE file key
        BG->>S3: download to /tmp/
        BG->>SDK: analyze(file_bytes)
        SDK->>BG: score 0-100 (via black_box.benign.score)
        BG->>BG: append row to CSV buffer
        BG->>BG: delete local file
    end

    BG->>S3: upload pe-scan-<ts>-<id>.csv
    BG->>BG: job.status = done

    C->>API: GET /pe/jobs/{id}
    API->>C: {status: done, output_s3: ..., download_url: ...}
    C->>S3: GET presigned URL
    S3->>C: pe_results.csv
```

### Output CSV

```
filename,score,malicious
setup.exe,60,1
notepad.exe,6,0
calculator.dll,7,0
```

Score source in PE model report:
```
result[0].report.black_box.benign.score  →  0-100 integer
```
Higher score = more malicious. Threshold: **≥ 30 → malicious = 1**.

---

## S3 Object Layout

```
s3://<YOUR_S3_BUCKET>/
├── mlmodels/data/input_data/
│   ├── urls/         (optional: pre-loaded URL lists)
│   └── pe/           ← PE binary files scanned by pe-svc
└── mlmodels/data/output_data/
    ├── url/
    │   └── url-scan-20250301-120000-abc123.csv
    └── pe/
        └── pe-scan-20250301-120500-def456.csv
```

Output files are retained indefinitely in S3. Presigned download URLs expire after 7 days but the underlying S3 object remains. Add an S3 lifecycle rule to expire outputs after your desired retention period.

---

## Scoring Model

Both models use the same scoring convention:

| Value | Type | Range | Meaning |
|-------|------|-------|---------|
| `score` | int | 0–100 | Maliciousness probability (100 = certainly malicious) |
| `malicious` | int | 0 or 1 | 1 if score ≥ threshold (default 30) |

The `THRESHOLD` environment variable controls the cutoff and can be adjusted per deployment without rebuilding the image.

### Score Sources by Model

| Model | SDK result path |
|-------|----------------|
| URL | `result[0]["report"]["score"]` |
| PE | `result[0]["report"]["black_box"]["benign"]["score"]` |

Both are cast to `int(round(float(...)))` to normalize any floating-point representation returned by the SDK.
