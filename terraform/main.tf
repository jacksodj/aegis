# ============================================================================
# Main Terraform Configuration
# Serverless Durable Agent Orchestration Platform
# ============================================================================
# This configuration creates all resources needed for the platform:
# - S3 bucket for artifacts (versioned, encrypted)
# - DynamoDB table for workflow state (with GSI)
# - ECR repositories for agent containers
# - Lambda functions (controller, callback)
# - API Gateway for HTTP endpoints
# - IAM roles and policies
# - CloudWatch log groups
# - Docker image build and push automation
# ============================================================================

# ============================================================================
# Data Sources
# ============================================================================

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_partition" "current" {}

# ============================================================================
# S3 Bucket for Artifacts
# ============================================================================

resource "aws_s3_bucket" "artifacts" {
  bucket = local.artifact_bucket_name

  tags = merge(
    local.common_tags,
    {
      Name        = local.artifact_bucket_name
      Description = "Storage for workflow artifacts, reports, and large payloads"
    }
  )
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = var.artifact_bucket_versioning ? "Enabled" : "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "transition-old-artifacts"
    status = "Enabled"

    transition {
      days          = var.artifact_retention_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.artifact_retention_days * 2
      storage_class = "GLACIER"
    }

    expiration {
      days = var.artifact_retention_days * 4
    }

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# ============================================================================
# DynamoDB Table for Workflow State
# ============================================================================

resource "aws_dynamodb_table" "workflows" {
  name           = local.workflow_table_name
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "workflow_id"

  attribute {
    name = "workflow_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # Global Secondary Index for querying by status and creation time
  global_secondary_index {
    name            = local.workflow_gsi_status_created.name
    hash_key        = local.workflow_gsi_status_created.hash_key
    range_key       = local.workflow_gsi_status_created.range_key
    projection_type = local.workflow_gsi_status_created.projection_type
  }

  # TTL for automatic cleanup of old workflow records
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(
    local.common_tags,
    {
      Name        = local.workflow_table_name
      Description = "Workflow state and metadata storage"
    }
  )
}

# ============================================================================
# ECR Repositories for Agent Containers
# ============================================================================

resource "aws_ecr_repository" "agents" {
  for_each = local.agent_configs

  name                 = each.value.ecr_repository
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = var.enable_container_image_scanning
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(
    local.common_tags,
    {
      Name        = each.value.ecr_repository
      AgentType   = each.value.name
      Description = "${each.value.description} Agent Container Repository"
    }
  )
}

resource "aws_ecr_lifecycle_policy" "agents" {
  for_each = aws_ecr_repository.agents

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ============================================================================
# CloudWatch Log Groups
# ============================================================================

resource "aws_cloudwatch_log_group" "controller" {
  name              = local.controller_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = local.controller_log_group_name
    }
  )
}

resource "aws_cloudwatch_log_group" "callback" {
  name              = local.callback_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = local.callback_log_group_name
    }
  )
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = local.api_gateway_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = local.api_gateway_log_group_name
    }
  )
}

# ============================================================================
# IAM Role for Controller Lambda
# ============================================================================

resource "aws_iam_role" "controller" {
  name = "${local.name_prefix}-controller-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-controller-role"
    }
  )
}

# Attach basic execution policy
resource "aws_iam_role_policy_attachment" "controller_basic" {
  role       = aws_iam_role.controller.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Attach VPC execution policy if needed (for future VPC deployment)
# Commented out for now as we're not using VPC
# resource "aws_iam_role_policy_attachment" "controller_vpc" {
#   role       = aws_iam_role.controller.name
#   policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
# }

# Controller-specific IAM policy
resource "aws_iam_role_policy" "controller" {
  name = "${local.name_prefix}-controller-policy"
  role = aws_iam_role.controller.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Durable Execution permissions (for future use when SDK is available)
      {
        Sid    = "DurableExecutionPermissions"
        Effect = "Allow"
        Action = [
          "lambda:CheckpointDurableExecution",
          "lambda:GetDurableExecutionState",
          "lambda:ListDurableExecutions"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${local.controller_function_name}:*"
      },
      # AgentCore invocation permissions
      {
        Sid    = "AgentCoreInvocation"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:InvokeAgentRuntime",
          "bedrock-agentcore:GetAgentRuntime",
          "bedrock-agentcore:ListAgentRuntimes"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:agent-runtime/*"
      },
      # S3 artifact storage permissions
      {
        Sid    = "ArtifactStorage"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.artifacts.arn,
          "${aws_s3_bucket.artifacts.arn}/*"
        ]
      },
      # DynamoDB workflow state permissions
      {
        Sid    = "WorkflowMetadata"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.workflows.arn,
          "${aws_dynamodb_table.workflows.arn}/index/*"
        ]
      },
      # X-Ray tracing permissions
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      },
      # EventBridge permissions for workflow events
      {
        Sid    = "EventBridgeEvents"
        Effect = "Allow"
        Action = [
          "events:PutEvents"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:events:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:event-bus/default"
      },
      # SNS permissions for approval notifications
      {
        Sid    = "SNSNotifications"
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:sns:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${local.name_prefix}-*"
      }
    ]
  })
}

# ============================================================================
# IAM Role for Callback Lambda
# ============================================================================

resource "aws_iam_role" "callback" {
  name = "${local.name_prefix}-callback-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-callback-role"
    }
  )
}

resource "aws_iam_role_policy_attachment" "callback_basic" {
  role       = aws_iam_role.callback.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "callback" {
  name = "${local.name_prefix}-callback-policy"
  role = aws_iam_role.callback.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # DynamoDB permissions
      {
        Sid    = "WorkflowMetadata"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.workflows.arn,
          "${aws_dynamodb_table.workflows.arn}/index/*"
        ]
      },
      # S3 permissions for artifacts
      {
        Sid    = "ArtifactAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.artifacts.arn}/*"
      },
      # Lambda callback permissions (for durable execution)
      {
        Sid    = "DurableCallbackPermissions"
        Effect = "Allow"
        Action = [
          "lambda:SendDurableExecutionCallbackSuccess",
          "lambda:SendDurableExecutionCallbackFailure"
        ]
        Resource = "${aws_lambda_function.controller.arn}:*"
      },
      # X-Ray tracing
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================================
# Lambda Function Packaging
# ============================================================================

# Archive controller Lambda code
data "archive_file" "controller" {
  type        = "zip"
  source_dir  = local.controller_source_dir
  output_path = "${path.module}/.terraform/lambda_packages/controller.zip"
  excludes    = [
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    "tests",
    "test_*.py",
    "*.md",
    ".DS_Store"
  ]
}

# Archive callback Lambda code
data "archive_file" "callback" {
  type        = "zip"
  source_dir  = local.callback_source_dir
  output_path = "${path.module}/.terraform/lambda_packages/callback.zip"
  excludes    = [
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    "tests",
    "test_*.py",
    "*.md",
    ".DS_Store"
  ]
}

# ============================================================================
# Controller Lambda Function
# ============================================================================

resource "aws_lambda_function" "controller" {
  filename         = data.archive_file.controller.output_path
  function_name    = local.controller_function_name
  role            = aws_iam_role.controller.arn
  handler         = "handler.api_handler"
  source_code_hash = data.archive_file.controller.output_base64sha256
  runtime         = var.lambda_runtime
  architectures   = [var.lambda_architecture]
  memory_size     = var.controller_memory
  timeout         = var.controller_timeout

  environment {
    variables = local.controller_environment
  }

  tracing_config {
    mode = var.enable_xray_tracing ? "Active" : "PassThrough"
  }

  depends_on = [
    aws_cloudwatch_log_group.controller,
    aws_iam_role_policy.controller,
    aws_s3_bucket.artifacts,
    aws_dynamodb_table.workflows
  ]

  tags = merge(
    local.common_tags,
    {
      Name        = local.controller_function_name
      Description = "Durable workflow orchestration controller"
    }
  )
}

# ============================================================================
# Callback Lambda Function
# ============================================================================

resource "aws_lambda_function" "callback" {
  filename         = data.archive_file.callback.output_path
  function_name    = local.callback_function_name
  role            = aws_iam_role.callback.arn
  handler         = "handler.handler"
  source_code_hash = data.archive_file.callback.output_base64sha256
  runtime         = var.lambda_runtime
  architectures   = [var.lambda_architecture]
  memory_size     = var.callback_memory
  timeout         = var.callback_timeout

  environment {
    variables = local.callback_environment
  }

  tracing_config {
    mode = var.enable_xray_tracing ? "Active" : "PassThrough"
  }

  depends_on = [
    aws_cloudwatch_log_group.callback,
    aws_iam_role_policy.callback,
    aws_lambda_function.controller
  ]

  tags = merge(
    local.common_tags,
    {
      Name        = local.callback_function_name
      Description = "Handles callbacks from AgentCore agents"
    }
  )
}

# ============================================================================
# API Gateway HTTP API
# ============================================================================

resource "aws_apigatewayv2_api" "main" {
  name          = local.api_gateway_name
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = local.api_cors_configuration.allow_origins
    allow_methods = local.api_cors_configuration.allow_methods
    allow_headers = local.api_cors_configuration.allow_headers
    max_age       = local.api_cors_configuration.max_age
  }

  tags = merge(
    local.common_tags,
    {
      Name = local.api_gateway_name
    }
  )
}

# API Gateway Stage
resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
    })
  }

  tags = local.common_tags
}

# ============================================================================
# API Gateway Integrations
# ============================================================================

# Controller Lambda Integration
resource "aws_apigatewayv2_integration" "controller" {
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.controller.invoke_arn
  payload_format_version = "2.0"
}

# Callback Lambda Integration
resource "aws_apigatewayv2_integration" "callback" {
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.callback.invoke_arn
  payload_format_version = "2.0"
}

# ============================================================================
# API Gateway Routes
# ============================================================================

# POST /workflows - Start new workflow
resource "aws_apigatewayv2_route" "create_workflow" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /workflows"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
}

# GET /workflows/{workflow_id} - Get workflow status
resource "aws_apigatewayv2_route" "get_workflow" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /workflows/{workflow_id}"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
}

# POST /callbacks/{workflow_id} - Receive agent callbacks
resource "aws_apigatewayv2_route" "callback" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /callbacks/{workflow_id}"
  target    = "integrations/${aws_apigatewayv2_integration.callback.id}"
}

# POST /approve/{workflow_id} - Human approval endpoint
resource "aws_apigatewayv2_route" "approve" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /approve/{workflow_id}"
  target    = "integrations/${aws_apigatewayv2_integration.callback.id}"
}

# ============================================================================
# Lambda Permissions for API Gateway
# ============================================================================

resource "aws_lambda_permission" "api_gateway_controller" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.controller.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gateway_callback" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.callback.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ============================================================================
# Docker Image Build and Push Automation
# ============================================================================

# Null resource to build and push Docker images to ECR
resource "null_resource" "docker_build_push" {
  for_each = local.agent_configs

  triggers = {
    # Rebuild when Dockerfile or source code changes
    dockerfile_hash = filemd5("${local.agents_source_dir}/${each.key}/Dockerfile")
    source_hash     = sha256(join("", [for f in fileset("${local.agents_source_dir}/${each.key}", "**") : filesha256("${local.agents_source_dir}/${each.key}/${f}")]))
    ecr_repo_url    = aws_ecr_repository.agents[each.key].repository_url
  }

  provisioner "local-exec" {
    command = <<-EOT
      # Authenticate Docker to ECR
      aws ecr get-login-password --region ${data.aws_region.current.name} | \
        docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com

      # Build the Docker image
      docker build -t ${aws_ecr_repository.agents[each.key].repository_url}:latest \
        --platform linux/arm64 \
        ${local.agents_source_dir}/${each.key}

      # Tag with additional tags
      docker tag ${aws_ecr_repository.agents[each.key].repository_url}:latest \
        ${aws_ecr_repository.agents[each.key].repository_url}:${formatdate("YYYYMMDDhhmmss", timestamp())}

      # Push to ECR
      docker push ${aws_ecr_repository.agents[each.key].repository_url}:latest
      docker push ${aws_ecr_repository.agents[each.key].repository_url}:${formatdate("YYYYMMDDhhmmss", timestamp())}

      echo "Successfully built and pushed ${each.key} agent image"
    EOT

    working_dir = path.module
  }

  depends_on = [
    aws_ecr_repository.agents
  ]
}

# ============================================================================
# EventBridge Rule for Workflow Monitoring (Optional)
# ============================================================================

resource "aws_cloudwatch_event_rule" "workflow_events" {
  name        = "${local.name_prefix}-workflow-events"
  description = "Capture workflow state change events"

  event_pattern = jsonencode({
    source      = ["agent.orchestration"]
    detail-type = ["WorkflowStarted", "WorkflowCompleted", "WorkflowFailed", "ApprovalRequested"]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-workflow-events"
    }
  )
}

# CloudWatch Log Group target for workflow events
resource "aws_cloudwatch_log_group" "workflow_events" {
  name              = "/aws/events/${local.name_prefix}-workflow-events"
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = "/aws/events/${local.name_prefix}-workflow-events"
    }
  )
}

resource "aws_cloudwatch_event_target" "workflow_events_log" {
  rule      = aws_cloudwatch_event_rule.workflow_events.name
  target_id = "SendToCloudWatchLogs"
  arn       = aws_cloudwatch_log_group.workflow_events.arn
}

# IAM role for EventBridge to write to CloudWatch Logs
resource "aws_iam_role" "eventbridge_logs" {
  name = "${local.name_prefix}-eventbridge-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "eventbridge_logs" {
  name = "${local.name_prefix}-eventbridge-logs-policy"
  role = aws_iam_role.eventbridge_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.workflow_events.arn}:*"
      }
    ]
  })
}
