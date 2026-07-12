"""S3 utilities: parse s3 URIs, list keys, download, upload, generate presigned URLs."""

import io
from dataclasses import dataclass
from typing import Iterator

import boto3


@dataclass
class S3Uri:
    bucket: str
    key: str

    @classmethod
    def parse(cls, uri: str) -> "S3Uri":
        if not uri.startswith("s3://"):
            raise ValueError(f"not an s3 uri: {uri}")
        rest = uri[len("s3://"):]
        bucket, _, key = rest.partition("/")
        return cls(bucket=bucket, key=key)

    def __str__(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def _client():
    return boto3.client("s3")


def list_keys(prefix_uri: str) -> Iterator[str]:
    """List all object keys under a prefix (skips directory markers)."""
    u = S3Uri.parse(prefix_uri)
    paginator = _client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=u.bucket, Prefix=u.key):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            yield key


def download_to(prefix_uri: str, key: str, dest_path: str) -> None:
    u = S3Uri.parse(prefix_uri)
    _client().download_file(u.bucket, key, dest_path)


def read_text(uri: str) -> str:
    u = S3Uri.parse(uri)
    buf = io.BytesIO()
    _client().download_fileobj(u.bucket, u.key, buf)
    return buf.getvalue().decode("utf-8")


def upload_bytes(data: bytes, dest_uri: str, content_type: str = "text/csv") -> None:
    u = S3Uri.parse(dest_uri)
    _client().put_object(Bucket=u.bucket, Key=u.key, Body=data, ContentType=content_type)


def presigned_url(uri: str, expires_seconds: int = 7 * 24 * 3600) -> str:
    u = S3Uri.parse(uri)
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": u.bucket, "Key": u.key},
        ExpiresIn=expires_seconds,
    )
