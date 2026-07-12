#!/usr/bin/env bash
# Push a vendor-provided ML model base image to ECR.
# Usage: ./scripts/push_base.sh <url|pe> <local-image-tag>
# Example: ./scripts/push_base.sh url vendor-url-model:20250301
#
# Prerequisites:
#   aws ecr get-login-password ... | docker login   (or use aws-cli v2 helper)
#   ECR_REPO and AWS_REGION set as env vars, or set defaults below

set -euo pipefail

MODEL_KIND="${1:?usage: push_base.sh <url|pe> <local-image-tag>}"
LOCAL_TAG="${2:?usage: push_base.sh <url|pe> <local-image-tag>}"

ECR_REPO="${ECR_REPO:-<YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/mlscan-models}"
AWS_REGION="${AWS_REGION:-us-east-1}"
REMOTE_TAG="${ECR_REPO}:base-${MODEL_KIND}-$(date +%Y%m%d)"

echo "Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REPO"

echo "Tagging ${LOCAL_TAG} → ${REMOTE_TAG}"
docker tag "$LOCAL_TAG" "$REMOTE_TAG"
docker tag "$LOCAL_TAG" "${ECR_REPO}:base-${MODEL_KIND}-latest"

echo "Pushing..."
docker push "$REMOTE_TAG"
docker push "${ECR_REPO}:base-${MODEL_KIND}-latest"

echo "Done. Base image pushed:"
echo "  ${REMOTE_TAG}"
echo "  ${ECR_REPO}:base-${MODEL_KIND}-latest"
