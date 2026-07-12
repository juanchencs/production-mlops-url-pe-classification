#!/usr/bin/env bash
# Push a pre-built ML model base image to ECR.
# Usage: ./scripts/push_base.sh <url|pe> <local-image-tag>
# Example: ./scripts/push_base.sh url ml-url-model:20250301
#
# Prerequisites:
#   ECR_REPO and AWS_REGION set as env vars, or edit the defaults below.

set -euo pipefail

MODEL_KIND="${1:?usage: push_base.sh <url|pe> <local-image-tag>}"
LOCAL_TAG="${2:?usage: push_base.sh <url|pe> <local-image-tag>}"

ECR_REPO="${ECR_REPO:-<YOUR_ACCOUNT_ID>.dkr.ecr.eu-west-2.amazonaws.com/mlscan-models}"
AWS_REGION="${AWS_REGION:-eu-west-2}"
REMOTE_TAG="${ECR_REPO}:base-${MODEL_KIND}-$(date +%Y%m%d)"

echo "Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REPO"

echo "Tagging ${LOCAL_TAG} → ${REMOTE_TAG}"
docker tag "$LOCAL_TAG" "$REMOTE_TAG"

echo "Pushing..."
docker push "$REMOTE_TAG"

echo "Done. Base image pushed: ${REMOTE_TAG}"
