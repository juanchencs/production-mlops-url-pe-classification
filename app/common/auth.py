"""API key authentication.

The key is stored in AWS Secrets Manager and fetched once on first request,
then cached in-process via lru_cache. Clients pass the same key in the
`X-API-Key` request header.

Environment variables:
    API_KEY_SECRET_NAME   Secrets Manager secret name, e.g. mlscan/api-key
    API_KEY               (optional) plaintext key for local testing — skips Secrets Manager
"""

import os
import functools

import boto3
from fastapi import Header, HTTPException, status


@functools.lru_cache(maxsize=1)
def _expected_key() -> str:
    plain = os.getenv("API_KEY")
    if plain:
        return plain.strip()

    secret_name = os.environ["API_KEY_SECRET_NAME"]
    region = os.getenv("AWS_REGION", "eu-west-2")
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_name)
    value = resp["SecretString"].strip()
    if value.startswith("{"):
        import json
        value = json.loads(value)["api_key"]
    return value.strip()


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """FastAPI dependency: validate the X-API-Key request header."""
    if not x_api_key or x_api_key.strip() != _expected_key():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
