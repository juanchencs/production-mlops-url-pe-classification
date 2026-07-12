terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state stored in S3. Run `terraform init` once to initialise the backend.
  backend "s3" {
    bucket = "your-s3-bucket"
    key    = "terraform/mlscan/terraform.tfstate"
    region = "eu-west-2"
  }
}

provider "aws" {
  region = var.aws_region
}
