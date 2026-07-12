#!/usr/bin/env python3
"""Submit an S3 prefix of PE files for classification and download results.

Usage:
    python3 client/scan_pe.py \
        --api-url http://<ALB_DNS> \
        --s3-input s3://<YOUR_S3_BUCKET>/data/input/pe \
        --out pe_results.csv

    # with API key
    python3 client/scan_pe.py --api-url http://<ALB_DNS> \
        --api-key secret \
        --s3-input s3://<YOUR_S3_BUCKET>/data/input/pe \
        --out pe_results.csv
"""

import argparse
import sys
import urllib.request

from scanclient import ScanClient

THRESHOLD = 30


def main() -> None:
    parser = argparse.ArgumentParser(description="PE file scanner client")
    parser.add_argument("--api-url", required=True, help="Base URL of the scan service ALB")
    parser.add_argument("--api-key", default=None, help="X-API-Key header value (if required)")
    parser.add_argument("--s3-input", required=True, help="S3 prefix of PE files to scan")
    parser.add_argument("--out", default="pe_results.csv", help="Local path to save results CSV")
    args = parser.parse_args()

    client = ScanClient(args.api_url, api_key=args.api_key)

    print("Checking PE service health...", end=" ")
    hc = client.healthz("pe")
    print(hc)

    print(f"Submitting PE scan for {args.s3_input}...")
    job_id = client.submit_pe_scan(s3_input=args.s3_input)
    print(f"Job submitted: {job_id}  (polling...)")

    job = client.wait_pe_job(job_id, poll_interval=5.0, timeout=900)

    if job["status"] == "error":
        print(f"Scan failed: {job.get('error')}", file=sys.stderr)
        sys.exit(1)

    download_url = job["download_url"]
    print(f"Scan complete. Downloading results...")
    with urllib.request.urlopen(download_url) as resp:
        content = resp.read()

    with open(args.out, "wb") as f:
        f.write(content)

    lines = content.decode("utf-8").splitlines()
    total = len(lines) - 1  # exclude header
    malicious = sum(1 for line in lines[1:] if line.endswith(",1"))
    print(f"\nResults written to {args.out}")
    print(f"Total: {total} files | Malicious (score ≥ {THRESHOLD}): {malicious}")
    print(f"S3 output: {job['output_s3']}")


if __name__ == "__main__":
    main()
