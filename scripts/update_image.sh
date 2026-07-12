#!/usr/bin/env bash
# Build and deploy a new app image for a given service.
# Usage: ./scripts/update_image.sh <url|pe> <base-tag>
# Example: ./scripts/update_image.sh url base-url-20260601

set -euo pipefail

MODEL_KIND="${1:?usage: update_image.sh <url|pe> <base-tag>}"
BASE_TAG="${2:?usage: update_image.sh <url|pe> <base-tag>}"

ECR_REPO="${ECR_REPO:-<YOUR_ACCOUNT_ID>.dkr.ecr.eu-west-2.amazonaws.com/mlscan-models}"
AWS_REGION="${AWS_REGION:-eu-west-2}"
ECS_CLUSTER="${ECS_CLUSTER:-mlscan-cluster}"
ECS_SERVICE="${MODEL_KIND}-svc"
TASK_FAMILY="${MODEL_KIND}-task"

echo "Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REPO"

SHA_TAG="${MODEL_KIND}-$(git rev-parse --short HEAD)-manual"
BASE_IMAGE="$ECR_REPO:$BASE_TAG"
APP_IMAGE="$ECR_REPO:$SHA_TAG"

echo "Building ${APP_IMAGE} from base ${BASE_IMAGE}..."
docker build \
  --build-arg BASE_IMAGE="$BASE_IMAGE" \
  -t "$APP_IMAGE" \
  -f "app/${MODEL_KIND}/Dockerfile" app
docker push "$APP_IMAGE"

echo "Registering new task definition..."
NEW_TASK_DEF=$(aws ecs describe-task-definition \
  --task-definition "$TASK_FAMILY" --region "$AWS_REGION" \
  --query 'taskDefinition' --output json | \
  python3 -c "
import sys, json
td = json.load(sys.stdin)
for c in td['containerDefinitions']:
    if c['name'] == 'app':
        c['image'] = '$APP_IMAGE'
for f in ['taskDefinitionArn','revision','status','requiresAttributes',
          'placementConstraints','compatibilities','registeredAt','registeredBy']:
    td.pop(f, None)
print(json.dumps(td))
")
NEW_ARN=$(aws ecs register-task-definition \
  --region "$AWS_REGION" \
  --cli-input-json "$NEW_TASK_DEF" \
  --query 'taskDefinition.taskDefinitionArn' --output text)
echo "New task definition: $NEW_ARN"

echo "Deploying to ECS..."
aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --task-definition "$NEW_ARN" \
  --query 'service.{service:serviceName,status:status}' \
  --output table

echo "Waiting for service to stabilize..."
aws ecs wait services-stable \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE"

echo "Service ${ECS_SERVICE} is stable."
