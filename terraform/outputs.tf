output "alb_dns_name" {
  description = "Internal ALB DNS — set as ALB env var on caller EC2"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URI — used in push_base.sh and CI workflows"
  value       = aws_ecr_repository.models.repository_url
}

output "alb_sg_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

output "ecs_task_sg_id" {
  value = aws_security_group.ecs_task.id
}

output "api_secret_arn" {
  description = "Secrets Manager ARN for the API key"
  value       = aws_secretsmanager_secret.api_key.arn
}

output "gha_deploy_role_arn" {
  description = "IAM role ARN for GitHub Actions — update workflows if this changes"
  value       = aws_iam_role.gha_deploy.arn
}
