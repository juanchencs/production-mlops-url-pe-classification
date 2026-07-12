"""API-key authentication via AWS Secrets Manager.

The secret is read once on first request using the ECS task IAM role
and cached for the container's lifetime. Clients pass the same key in
the X-API-Key request header.

Environment variables:
    API_KEY_SECRET_NAME   Secret name in Secrets Manager, e.g. mlscan/api-key
    API_KEY               (optional) plaintext key for local testing — skips Secrets Manager
    AWS_REGION            AWS region (default: us-east-1)
"""

import functools
import json
import os

import boto3
from fastapi import Header, HTTPException, status


@functools.lru_cache(maxsize=1)
def _expected_key() -> str:
    plain = os.getenv("API_KEY")
    if plain:
        return plain.strip()

    secret_name = os.environ["API_KEY_SECRET_NAME"]
    region = os.getenv("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_name)
    value = resp["SecretString"].strip()
    if value.startswith("{"):
        value = json.loads(value)["api_key"]
    return value.strip()


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """FastAPI dependency: validate the X-API-Key header."""
    if not x_api_key or x_api_key.strip() != _expected_key():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
