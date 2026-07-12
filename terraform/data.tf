data "aws_caller_identity" "current" {}

# Reference existing VPC — do not recreate.
data "aws_vpc" "main" {
  id = "<YOUR_VPC_ID>"
}

# Pre-existing ECS execution role — managed outside this project.
# Do not destroy it with terraform destroy.
data "aws_iam_role" "ecs_execution" {
  name = "ecsTaskExecutionRole"
}

# Pre-existing GitHub Actions OIDC provider for the account.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}
