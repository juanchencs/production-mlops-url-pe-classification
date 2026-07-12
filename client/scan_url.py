#!/usr/bin/env python3
"""Submit URLs for classification and write results to a CSV file.

Usage:
    python3 client/scan_url.py --api-url http://<ALB_DNS> \
        --file client/test_urls.txt --out url_results.csv

    # with API key auth
    python3 client/scan_url.py --api-url http://<ALB_DNS> \
        --api-key secret --file client/test_urls.txt --out url_results.csv
"""

import argparse
import csv
import sys
import urllib.request

from scanclient import ScanClient

THRESHOLD = 30


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch URL scanner client")
    parser.add_argument("--api-url", required=True, help="Base URL of the scan service ALB")
    parser.add_argument("--api-key", default=None, help="X-API-Key header value (if required)")
    parser.add_argument("--file", required=True, help="File with one URL per line")
    parser.add_argument("--out", default="url_results.csv", help="Output CSV path")
    parser.add_argument("--batch-size", type=int, default=100, help="URLs per API call")
    args = parser.parse_args()

    with open(args.file) as f:
        urls = [u.strip() for u in f if u.strip() and not u.startswith("#")]

    if not urls:
        sys.exit("No URLs found in input file.")

    client = ScanClient(args.api_url, api_key=args.api_key)

    print(f"Checking service health...", end=" ")
    hc = client.healthz("url")
    print(hc)

    batches = [urls[i : i + args.batch_size] for i in range(0, len(urls), args.batch_size)]
    print(f"Submitting {len(urls)} URLs in {len(batches)} batch(es)...")

    all_rows: list[tuple[str, int, int]] = []
    for idx, batch in enumerate(batches, 1):
        job_id = client.submit_url_scan(batch)
        print(f"  Batch {idx}/{len(batches)}: job={job_id} ({len(batch)} URLs)")
        job = client.wait_url_job(job_id)
        if job["status"] == "error":
            print(f"  ERROR: {job.get('error')}", file=sys.stderr)
            continue
        # Download result CSV from presigned URL
        download_url = job["download_url"]
        with urllib.request.urlopen(download_url) as resp:
            content = resp.read().decode("utf-8")
        lines = content.splitlines()
        for row in lines[1:]:  # skip header
            parts = row.split(",", 2)
            if len(parts) >= 2:
                all_rows.append((parts[0], int(parts[1]), int(int(parts[1]) >= THRESHOLD)))

    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "score", "malicious"])
        writer.writerows(all_rows)

    malicious_count = sum(1 for _, _, m in all_rows if m)
    print(f"\nResults written to {args.out}")
    print(f"Total: {len(all_rows)} URLs | Malicious (score ≥ {THRESHOLD}): {malicious_count}")


if __name__ == "__main__":
    main()
