# Lambda Module Outputs

output "function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.function.arn
}

output "function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.function.function_name
}

output "invoke_arn" {
  description = "Invoke ARN of the Lambda function (for API Gateway integration)"
  value       = aws_lambda_function.function.invoke_arn
}

output "qualified_arn" {
  description = "Qualified ARN of the Lambda function (includes version)"
  value       = aws_lambda_function.function.qualified_arn
}

output "version" {
  description = "Latest published version of the Lambda function"
  value       = aws_lambda_function.function.version
}

output "role_arn" {
  description = "ARN of the Lambda execution IAM role"
  value       = aws_iam_role.lambda_role.arn
}

output "role_name" {
  description = "Name of the Lambda execution IAM role"
  value       = aws_iam_role.lambda_role.name
}

output "log_group_name" {
  description = "Name of the CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "log_group_arn" {
  description = "ARN of the CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.lambda_logs.arn
}

output "source_code_hash" {
  description = "Base64-encoded SHA256 hash of the Lambda package"
  value       = aws_lambda_function.function.source_code_hash
}

output "function_url" {
  description = "URL of the Lambda Function URL (if enabled)"
  value       = var.enable_function_url ? aws_lambda_function_url.function_url[0].function_url : null
}

output "alias_arn" {
  description = "ARN of the Lambda alias (if created)"
  value       = var.alias_name != null ? aws_lambda_alias.alias[0].arn : null
}

output "alias_invoke_arn" {
  description = "Invoke ARN of the Lambda alias (if created)"
  value       = var.alias_name != null ? aws_lambda_alias.alias[0].invoke_arn : null
}

output "schedule_rule_arn" {
  description = "ARN of the CloudWatch Event Rule for scheduling (if created)"
  value       = var.schedule_expression != null ? aws_cloudwatch_event_rule.schedule[0].arn : null
}
