resource "aws_secretsmanager_secret" "api_key" {
  name        = "mlscan/api-key"
  description = "API key for the ML scan service"
}

# Set the secret value by passing api_key_secret_value variable:
#   terraform apply -var='api_key_secret_value=<key>'
# or via terraform.tfvars (git-ignored).
# After initial set, subsequent applies won't overwrite a manually-rotated value.
resource "aws_secretsmanager_secret_version" "api_key" {
  count         = var.api_key_secret_value != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.api_key.id
  secret_string = var.api_key_secret_value

  lifecycle {
    ignore_changes = [secret_string]
  }
}
