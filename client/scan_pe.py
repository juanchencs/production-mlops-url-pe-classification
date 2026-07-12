#!/usr/bin/env python3
"""PE scan client.

Input is an S3 prefix containing PE (Windows executable) binary files:
  python scan_pe.py --api-url http://<alb-dns> \
      --s3-input s3://<bucket>/data/input/pe --out result.csv

API key is read from SCAN_API_KEY env var, or pass --api-key.
"""

import argparse

from scanclient import ScanClient, download


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True, help="ALB address")
    p.add_argument("--api-key")
    p.add_argument(
        "--s3-input",
        default="s3://your-s3-bucket/mlmodels/data/input_data/pe",
        help="S3 prefix containing PE binary files",
    )
    p.add_argument("--out", help="download result CSV to this local path")
    p.add_argument("--poll", type=int, default=10, help="polling interval in seconds (default 10)")
    args = p.parse_args()

    client = ScanClient(args.api_url, args.api_key)
    job_id = client.submit("/pe", {"s3_input": args.s3_input})
    job = client.wait("/pe", job_id, poll_seconds=args.poll)
    print("\nResult CSV (S3):", job["output_s3"])
    print("Download URL (valid 7 days):", job["download_url"])
    if args.out:
        download(job["download_url"], args.out)


if __name__ == "__main__":
    main()
