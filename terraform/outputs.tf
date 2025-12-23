# ============================================================================
# Terraform Outputs
# ============================================================================
# This file defines outputs that are useful for:
# - Deployment verification
# - Integration with other systems
# - CI/CD pipelines
# - Documentation and testing
# ============================================================================

# ============================================================================
# API Gateway Outputs
# ============================================================================

output "api_endpoint" {
  description = "API Gateway endpoint URL for workflow orchestration"
  value       = aws_apigatewayv2_stage.main.invoke_url
}

output "api_id" {
  description = "API Gateway API ID"
  value       = aws_apigatewayv2_api.main.id
}

output "api_stage_name" {
  description = "API Gateway stage name"
  value       = aws_apigatewayv2_stage.main.name
}

# ============================================================================
# S3 Outputs
# ============================================================================

output "artifact_bucket_name" {
  description = "S3 bucket name for workflow artifacts and reports"
  value       = aws_s3_bucket.artifacts.id
}

output "artifact_bucket_arn" {
  description = "S3 bucket ARN for artifact storage"
  value       = aws_s3_bucket.artifacts.arn
}

output "artifact_bucket_region" {
  description = "S3 bucket region"
  value       = aws_s3_bucket.artifacts.region
}

# ============================================================================
# DynamoDB Outputs
# ============================================================================

output "workflow_table_name" {
  description = "DynamoDB table name for workflow state"
  value       = aws_dynamodb_table.workflows.name
}

output "workflow_table_arn" {
  description = "DynamoDB table ARN for workflow state"
  value       = aws_dynamodb_table.workflows.arn
}

output "workflow_table_stream_arn" {
  description = "DynamoDB table stream ARN (if enabled)"
  value       = try(aws_dynamodb_table.workflows.stream_arn, null)
}

# ============================================================================
# Lambda Function Outputs
# ============================================================================

output "controller_function_name" {
  description = "Controller Lambda function name"
  value       = aws_lambda_function.controller.function_name
}

output "controller_function_arn" {
  description = "Controller Lambda function ARN"
  value       = aws_lambda_function.controller.arn
}

output "controller_function_invoke_arn" {
  description = "Controller Lambda function invoke ARN"
  value       = aws_lambda_function.controller.invoke_arn
}

output "callback_function_name" {
  description = "Callback Lambda function name"
  value       = aws_lambda_function.callback.function_name
}

output "callback_function_arn" {
  description = "Callback Lambda function ARN"
  value       = aws_lambda_function.callback.arn
}

output "callback_function_invoke_arn" {
  description = "Callback Lambda function invoke ARN"
  value       = aws_lambda_function.callback.invoke_arn
}

# ============================================================================
# ECR Repository Outputs
# ============================================================================

output "ecr_repository_urls" {
  description = "ECR repository URLs for each agent type"
  value = {
    for agent_type, repo in aws_ecr_repository.agents :
    agent_type => repo.repository_url
  }
}

output "ecr_repository_arns" {
  description = "ECR repository ARNs for each agent type"
  value = {
    for agent_type, repo in aws_ecr_repository.agents :
    agent_type => repo.arn
  }
}

output "ecr_repository_names" {
  description = "ECR repository names for each agent type"
  value = {
    for agent_type, repo in aws_ecr_repository.agents :
    agent_type => repo.name
  }
}

# ============================================================================
# IAM Role Outputs
# ============================================================================

output "controller_role_arn" {
  description = "IAM role ARN for controller Lambda function"
  value       = aws_iam_role.controller.arn
}

output "controller_role_name" {
  description = "IAM role name for controller Lambda function"
  value       = aws_iam_role.controller.name
}

output "callback_role_arn" {
  description = "IAM role ARN for callback Lambda function"
  value       = aws_iam_role.callback.arn
}

output "callback_role_name" {
  description = "IAM role name for callback Lambda function"
  value       = aws_iam_role.callback.name
}

# ============================================================================
# CloudWatch Log Group Outputs
# ============================================================================

output "controller_log_group_name" {
  description = "CloudWatch log group name for controller Lambda"
  value       = aws_cloudwatch_log_group.controller.name
}

output "callback_log_group_name" {
  description = "CloudWatch log group name for callback Lambda"
  value       = aws_cloudwatch_log_group.callback.name
}

output "api_gateway_log_group_name" {
  description = "CloudWatch log group name for API Gateway"
  value       = aws_cloudwatch_log_group.api_gateway.name
}

# ============================================================================
# Configuration Outputs
# ============================================================================

output "environment" {
  description = "Deployment environment"
  value       = var.environment
}

output "region" {
  description = "AWS region where resources are deployed"
  value       = data.aws_region.current.name
}

output "account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

# ============================================================================
# Workflow Configuration Outputs
# ============================================================================

output "approval_timeout_hours" {
  description = "Configured timeout for human approval callbacks (hours)"
  value       = var.approval_timeout_hours
}

output "workflow_state_retention_days" {
  description = "Number of days workflow state is retained in DynamoDB"
  value       = var.workflow_state_retention_days
}

# ============================================================================
# Quick Start Commands
# ============================================================================

output "quick_start_commands" {
  description = "Useful commands for getting started"
  value = {
    start_workflow = "curl -X POST ${aws_apigatewayv2_stage.main.invoke_url}/workflows -H 'Content-Type: application/json' -d '{\"topic\": \"Your research topic\", \"parameters\": {}}'"
    get_workflow   = "curl -X GET ${aws_apigatewayv2_stage.main.invoke_url}/workflows/{workflow_id}"
    view_logs      = "aws logs tail ${aws_cloudwatch_log_group.controller.name} --follow"
    list_images    = "aws ecr describe-images --repository-name ${aws_ecr_repository.agents["researcher"].name} --region ${data.aws_region.current.name}"
  }
}

# ============================================================================
# Testing Endpoints
# ============================================================================

output "test_endpoints" {
  description = "API endpoints for testing different operations"
  value = {
    create_workflow = "${aws_apigatewayv2_stage.main.invoke_url}/workflows"
    get_workflow    = "${aws_apigatewayv2_stage.main.invoke_url}/workflows/{workflow_id}"
    callback        = "${aws_apigatewayv2_stage.main.invoke_url}/callbacks/{workflow_id}"
    approve         = "${aws_apigatewayv2_stage.main.invoke_url}/approve/{workflow_id}"
  }
}

# ============================================================================
# Docker Build Commands
# ============================================================================

output "docker_build_commands" {
  description = "Commands to manually build and push agent Docker images"
  value = {
    for agent_type, repo in aws_ecr_repository.agents :
    agent_type => {
      ecr_login = "aws ecr get-login-password --region ${data.aws_region.current.name} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com"
      build     = "docker build -t ${repo.repository_url}:latest --platform linux/arm64 ../agents/${agent_type}"
      push      = "docker push ${repo.repository_url}:latest"
    }
  }
}

# ============================================================================
# Monitoring and Observability
# ============================================================================

output "monitoring_urls" {
  description = "AWS Console URLs for monitoring and observability"
  value = {
    controller_logs  = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#logsV2:log-groups/log-group/${replace(aws_cloudwatch_log_group.controller.name, "/", "$252F")}"
    callback_logs    = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#logsV2:log-groups/log-group/${replace(aws_cloudwatch_log_group.callback.name, "/", "$252F")}"
    api_gateway_logs = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#logsV2:log-groups/log-group/${replace(aws_cloudwatch_log_group.api_gateway.name, "/", "$252F")}"
    dynamodb_table   = "https://console.aws.amazon.com/dynamodbv2/home?region=${data.aws_region.current.name}#table?name=${aws_dynamodb_table.workflows.name}"
    s3_bucket        = "https://s3.console.aws.amazon.com/s3/buckets/${aws_s3_bucket.artifacts.id}?region=${data.aws_region.current.name}"
    xray_traces      = "https://console.aws.amazon.com/xray/home?region=${data.aws_region.current.name}#/traces"
  }
}

# ============================================================================
# Summary Output
# ============================================================================

output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    api_endpoint                = aws_apigatewayv2_stage.main.invoke_url
    artifact_bucket             = aws_s3_bucket.artifacts.id
    workflow_table              = aws_dynamodb_table.workflows.name
    controller_function         = aws_lambda_function.controller.function_name
    callback_function           = aws_lambda_function.callback.function_name
    agent_repositories          = [for repo in aws_ecr_repository.agents : repo.name]
    region                      = data.aws_region.current.name
    environment                 = var.environment
    xray_tracing_enabled        = var.enable_xray_tracing
    approval_timeout_hours      = var.approval_timeout_hours
  }
}
