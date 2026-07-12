#!/usr/bin/env bash
# Manually trigger a re-deploy of an ECS service by forcing a new deployment.
# This pulls the latest task definition and forces ECS to start new tasks.
# Useful for rolling back to the current task definition without a code change.
#
# Usage: ./scripts/update_image.sh <url|pe>

set -euo pipefail

MODEL_KIND="${1:?usage: update_image.sh <url|pe>}"
ECS_CLUSTER="${ECS_CLUSTER:-mlscan-cluster}"
ECS_SERVICE="${MODEL_KIND}-svc"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "Forcing new deployment for ${ECS_SERVICE} on cluster ${ECS_CLUSTER}..."
aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --force-new-deployment \
  --query 'service.{service:serviceName,status:status,running:runningCount,desired:desiredCount}' \
  --output table

echo "Waiting for service to stabilize..."
aws ecs wait services-stable \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE"

echo "Service ${ECS_SERVICE} is stable."
