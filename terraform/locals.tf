# ============================================================================
# Local Values
# ============================================================================
# This file defines local values and computed configurations used throughout
# the Terraform configuration.
# ============================================================================

locals {
  # ============================================================================
  # Naming Conventions
  # ============================================================================

  name_prefix = "${var.project_name}-${var.environment}"

  # Resource names
  artifact_bucket_name        = "${local.name_prefix}-artifacts-${data.aws_caller_identity.current.account_id}"
  workflow_table_name         = "${local.name_prefix}-workflows"
  controller_function_name    = "${local.name_prefix}-controller"
  callback_function_name      = "${local.name_prefix}-callback"
  api_gateway_name            = "${local.name_prefix}-api"

  # Log group names
  controller_log_group_name   = "/aws/lambda/${local.controller_function_name}"
  callback_log_group_name     = "/aws/lambda/${local.callback_function_name}"
  api_gateway_log_group_name  = "/aws/apigateway/${local.api_gateway_name}"

  # ============================================================================
  # Common Tags
  # ============================================================================

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Repository  = "aegis"
      Component   = "agent-orchestration"
    },
    var.additional_tags
  )

  # ============================================================================
  # Agent Configuration
  # ============================================================================

  # Agent configurations with ECR repository names
  agent_configs = {
    for agent in var.agent_types : agent => {
      name           = agent
      ecr_repository = "${local.name_prefix}-${agent}-agent"
      description    = title(agent)
      # These would be populated after AgentCore deployment
      # In practice, you'd use outputs from a separate AgentCore deployment
      # or data sources to retrieve these ARNs
      agent_arn      = "arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:agent-runtime/${agent}"
    }
  }

  # ============================================================================
  # Lambda Environment Variables
  # ============================================================================

  # Controller Lambda environment variables
  controller_environment = {
    ARTIFACT_BUCKET          = aws_s3_bucket.artifacts.id
    WORKFLOW_TABLE           = aws_dynamodb_table.workflows.name
    RESEARCHER_AGENT_ARN     = lookup(local.agent_configs, "researcher", { agent_arn = "" }).agent_arn
    ANALYST_AGENT_ARN        = lookup(local.agent_configs, "analyst", { agent_arn = "" }).agent_arn
    WRITER_AGENT_ARN         = lookup(local.agent_configs, "writer", { agent_arn = "" }).agent_arn
    CALLBACK_API_URL         = aws_apigatewayv2_stage.main.invoke_url
    APPROVAL_TIMEOUT_HOURS   = tostring(var.approval_timeout_hours)
    ENVIRONMENT              = var.environment
    LOG_LEVEL                = var.environment == "prod" ? "INFO" : "DEBUG"
  }

  # Callback Lambda environment variables
  callback_environment = {
    WORKFLOW_TABLE           = aws_dynamodb_table.workflows.name
    ARTIFACT_BUCKET          = aws_s3_bucket.artifacts.id
    CONTROLLER_FUNCTION_NAME = aws_lambda_function.controller.function_name
    ENVIRONMENT              = var.environment
    LOG_LEVEL                = var.environment == "prod" ? "INFO" : "DEBUG"
  }

  # ============================================================================
  # Lambda Source Paths
  # ============================================================================

  controller_source_dir = "${path.module}/../controller"
  callback_source_dir   = "${path.module}/../callback"
  agents_source_dir     = "${path.module}/../agents"

  # ============================================================================
  # API Gateway Configuration
  # ============================================================================

  api_cors_configuration = {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"]
    max_age       = 300
  }

  # ============================================================================
  # DynamoDB Configuration
  # ============================================================================

  # Global Secondary Index configuration
  workflow_gsi_status_created = {
    name               = "status-created-index"
    hash_key           = "status"
    range_key          = "created_at"
    projection_type    = "ALL"
    read_capacity      = null  # On-demand billing
    write_capacity     = null  # On-demand billing
  }

  # ============================================================================
  # S3 Lifecycle Configuration
  # ============================================================================

  artifact_lifecycle_rules = [
    {
      id      = "transition-old-artifacts"
      enabled = true

      transition = [
        {
          days          = var.artifact_retention_days
          storage_class = "STANDARD_IA"
        },
        {
          days          = var.artifact_retention_days * 2
          storage_class = "GLACIER"
        }
      ]

      expiration = {
        days = var.artifact_retention_days * 4
      }

      noncurrent_version_transition = [
        {
          days          = 30
          storage_class = "GLACIER"
        }
      ]

      noncurrent_version_expiration = {
        days = 90
      }
    }
  ]
}
