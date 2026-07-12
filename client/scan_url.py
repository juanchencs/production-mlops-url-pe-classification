#!/usr/bin/env python3
"""URL scan client.

Two input modes:
  Local text file (one URL per line):
    python scan_url.py --api-url http://<alb-dns> --file urls.txt --out result.csv

  Text file on S3:
    python scan_url.py --api-url http://<alb-dns> \
        --s3-input s3://<bucket>/data/input/urls.txt

API key is read from SCAN_API_KEY env var, or pass --api-key.
"""

import argparse

from scanclient import ScanClient, download


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True, help="ALB address, e.g. http://xxx.elb.amazonaws.com")
    p.add_argument("--api-key")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="local text file path, one URL per line")
    g.add_argument("--s3-input", help="s3://... pointing to a text file")
    p.add_argument("--out", help="download result CSV to this local path")
    args = p.parse_args()

    client = ScanClient(args.api_url, args.api_key)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
        body = {"urls": urls}
    else:
        body = {"s3_input": args.s3_input}

    job_id = client.submit("/url", body)
    job = client.wait("/url", job_id)
    print("\nResult CSV (S3):", job["output_s3"])
    print("Download URL (valid 7 days):", job["download_url"])
    if args.out:
        download(job["download_url"], args.out)


if __name__ == "__main__":
    main()
