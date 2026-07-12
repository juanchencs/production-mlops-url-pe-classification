variable "aws_region" {
  description = "AWS region"
  default     = "eu-west-2"
}

variable "project" {
  description = "Project name prefix used in resource names"
  default     = "mlscan"
}

variable "s3_bucket" {
  description = "S3 bucket for ML model input/output data"
  default     = "your-s3-bucket"
}

variable "github_repo" {
  description = "GitHub repository in org/repo format used in OIDC trust condition"
  default     = "<YOUR_GITHUB_ORG>/<YOUR_REPO>"
}

variable "caller_sg_id" {
  description = "Security group ID of the EC2 instance(s) that call the ALB"
  default     = "<CALLER_EC2_SG_ID>"
}

variable "alb_subnet_ids" {
  description = "Subnet IDs for the ALB (at least 2 AZs)"
  type        = list(string)
  default     = ["<SUBNET_AZ1>", "<SUBNET_AZ2>"]
}

variable "ecs_subnet_ids" {
  description = "Subnet IDs for ECS Fargate tasks"
  type        = list(string)
  default     = ["<SUBNET_AZ1>", "<SUBNET_AZ2>", "<SUBNET_AZ3>"]
}

variable "task_cpu" {
  description = "ECS task CPU units (1024 = 1 vCPU)"
  default     = 2048
}

variable "task_memory" {
  description = "ECS task memory in MiB"
  default     = 4096
}

variable "api_key_secret_value" {
  description = "API key to store in Secrets Manager. Set via terraform.tfvars (not committed to git)."
  default     = ""
  sensitive   = true
}
