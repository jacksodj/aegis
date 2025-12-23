# Agent Module Outputs

output "repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.agent.repository_url
}

output "repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.agent.arn
}

output "repository_name" {
  description = "Name of the ECR repository"
  value       = aws_ecr_repository.agent.name
}

output "image_uri" {
  description = "Full URI of the Docker image (repository:tag)"
  value       = "${aws_ecr_repository.agent.repository_url}:${var.image_tag}"
}

output "image_tag" {
  description = "Tag of the Docker image"
  value       = var.image_tag
}

output "registry_id" {
  description = "Registry ID (AWS account ID)"
  value       = aws_ecr_repository.agent.registry_id
}

output "log_group_name" {
  description = "Name of the CloudWatch Log Group (if created)"
  value       = var.create_log_group ? aws_cloudwatch_log_group.agent[0].name : null
}

output "log_group_arn" {
  description = "ARN of the CloudWatch Log Group (if created)"
  value       = var.create_log_group ? aws_cloudwatch_log_group.agent[0].arn : null
}

output "role_arn" {
  description = "ARN of the IAM role (if created)"
  value       = var.create_iam_role ? aws_iam_role.agent[0].arn : null
}

output "role_name" {
  description = "Name of the IAM role (if created)"
  value       = var.create_iam_role ? aws_iam_role.agent[0].name : null
}

output "build_trigger_hash" {
  description = "Hash of build triggers (for detecting changes)"
  value       = sha256(jsonencode(local.build_trigger))
}

output "ecr_login_command" {
  description = "Command to login to ECR"
  value       = "aws ecr get-login-password --region ${data.aws_region.current.name} | docker login --username AWS --password-stdin ${local.ecr_url}"
  sensitive   = true
}
