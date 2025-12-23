# Complete Deployment Example
# This example shows how to use both Lambda and Agent modules together
# to deploy a full serverless durable agent orchestration platform

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "aegis"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Variables
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "image_version" {
  description = "Version tag for agent images"
  type        = string
  default     = "latest"
}

# Local variables
locals {
  project_name = "aegis"

  # Agent configurations
  agents = {
    coordinator = {
      source_dir = "${path.module}/../../agents/coordinator"
      platform   = "linux/arm64"
      memory     = 2048
    }
    analyst = {
      source_dir = "${path.module}/../../agents/analyst"
      platform   = "linux/arm64"
      memory     = 4096
    }
    research = {
      source_dir = "${path.module}/../../agents/research"
      platform   = "linux/amd64"
      memory     = 2048
    }
    execution = {
      source_dir = "${path.module}/../../agents/execution"
      platform   = "linux/amd64"
      memory     = 1024
    }
  }

  common_tags = {
    Project     = local.project_name
    Environment = var.environment
    Terraform   = "true"
  }
}

# ============================================================================
# Agent Modules - Build and store container images in ECR
# ============================================================================

module "agents" {
  for_each = local.agents
  source   = "../modules/agent"

  agent_name = "${each.key}-agent"
  source_dir = each.value.source_dir
  platform   = each.value.platform
  image_tag  = var.image_version

  # Enable scanning and lifecycle management
  scan_on_push                    = true
  enable_default_lifecycle_policy = true
  max_image_count                 = 20
  untagged_image_days            = 7

  # Create IAM role for ECS execution
  create_iam_role = true
  iam_role_principals = [
    "ecs-tasks.amazonaws.com"
  ]

  # Create CloudWatch Log Group
  create_log_group   = true
  log_retention_days = 30

  tags = merge(local.common_tags, {
    Agent = each.key
  })
}

# ============================================================================
# Lambda Modules - Controller and Callback functions
# ============================================================================

# Controller Lambda - Orchestrates agent execution
module "controller_lambda" {
  source = "../modules/lambda"

  function_name = "${local.project_name}-controller"
  handler       = "main.lambda_handler"
  runtime       = "python3.12"
  memory_size   = 512
  timeout       = 300
  architectures = ["arm64"]  # Graviton for cost savings

  source_dir = "${path.module}/../../controller/src"

  environment_variables = {
    STATE_TABLE        = aws_dynamodb_table.agent_state.name
    TASK_QUEUE_URL     = aws_sqs_queue.task_queue.url
    CALLBACK_QUEUE_URL = aws_sqs_queue.callback_queue.url
    CLUSTER_ARN        = aws_ecs_cluster.agents.arn
    LOG_LEVEL          = "INFO"
    ENVIRONMENT        = var.environment
  }

  policy_arns = [
    aws_iam_policy.controller_policy.arn
  ]

  # Enable X-Ray tracing
  tracing_mode = "Active"

  log_retention_days = 30

  tags = merge(local.common_tags, {
    Component = "controller"
  })
}

# Callback Lambda - Handles agent completion callbacks
module "callback_lambda" {
  source = "../modules/lambda"

  function_name = "${local.project_name}-callback-handler"
  handler       = "handler.process_callback"
  runtime       = "python3.12"
  memory_size   = 256
  timeout       = 60
  architectures = ["arm64"]

  source_dir = "${path.module}/../../callback/src"

  environment_variables = {
    STATE_TABLE        = aws_dynamodb_table.agent_state.name
    CONTROLLER_ARN     = module.controller_lambda.function_arn
    LOG_LEVEL          = "INFO"
  }

  policy_arns = [
    aws_iam_policy.callback_policy.arn
  ]

  # Trigger from SQS
  # Note: SQS trigger would be configured separately via aws_lambda_event_source_mapping

  log_retention_days = 14

  tags = merge(local.common_tags, {
    Component = "callback"
  })
}

# State Checker Lambda - Monitors agent state
module "state_checker_lambda" {
  source = "../modules/lambda"

  function_name = "${local.project_name}-state-checker"
  handler       = "checker.check_state"
  runtime       = "python3.12"
  memory_size   = 256
  timeout       = 300
  architectures = ["arm64"]

  source_dir = "${path.module}/../../controller/state-checker"

  # Run every 5 minutes
  schedule_expression = "rate(5 minutes)"

  environment_variables = {
    STATE_TABLE    = aws_dynamodb_table.agent_state.name
    CLUSTER_ARN    = aws_ecs_cluster.agents.arn
    LOG_LEVEL      = "INFO"
  }

  policy_arns = [
    aws_iam_policy.state_checker_policy.arn
  ]

  log_retention_days = 7

  tags = merge(local.common_tags, {
    Component = "monitoring"
  })
}

# ============================================================================
# Supporting Infrastructure
# ============================================================================

# DynamoDB Table for Agent State
resource "aws_dynamodb_table" "agent_state" {
  name           = "${local.project_name}-agent-state"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "execution_id"
  range_key      = "timestamp"

  attribute {
    name = "execution_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  attribute {
    name = "status"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Component = "storage"
  })
}

# SQS Queue for Task Distribution
resource "aws_sqs_queue" "task_queue" {
  name                       = "${local.project_name}-task-queue"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 1209600  # 14 days
  receive_wait_time_seconds  = 20       # Long polling

  tags = merge(local.common_tags, {
    Component = "messaging"
  })
}

# SQS Queue for Callbacks
resource "aws_sqs_queue" "callback_queue" {
  name                       = "${local.project_name}-callback-queue"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400  # 1 day
  receive_wait_time_seconds  = 20

  tags = merge(local.common_tags, {
    Component = "messaging"
  })
}

# Dead Letter Queue
resource "aws_sqs_queue" "dlq" {
  name                      = "${local.project_name}-dlq"
  message_retention_seconds = 1209600  # 14 days

  tags = merge(local.common_tags, {
    Component = "messaging"
  })
}

# ECS Cluster for Agent Execution
resource "aws_ecs_cluster" "agents" {
  name = "${local.project_name}-agents"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(local.common_tags, {
    Component = "compute"
  })
}

# ============================================================================
# IAM Policies
# ============================================================================

# Controller Lambda Policy
resource "aws_iam_policy" "controller_policy" {
  name = "${local.project_name}-controller-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.agent_state.arn,
          "${aws_dynamodb_table.agent_state.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = [
          aws_sqs_queue.task_queue.arn,
          aws_sqs_queue.callback_queue.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:DescribeTasks",
          "ecs:StopTask"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = "*"
        Condition = {
          StringLike = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      }
    ]
  })
}

# Callback Lambda Policy
resource "aws_iam_policy" "callback_policy" {
  name = "${local.project_name}-callback-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem",
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.agent_state.arn
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = module.controller_lambda.function_arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.callback_queue.arn
      }
    ]
  })
}

# State Checker Policy
resource "aws_iam_policy" "state_checker_policy" {
  name = "${local.project_name}-state-checker-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.agent_state.arn,
          "${aws_dynamodb_table.agent_state.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeTasks",
          "ecs:ListTasks"
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================================
# Lambda Event Source Mappings
# ============================================================================

# Callback Queue -> Callback Lambda
resource "aws_lambda_event_source_mapping" "callback_queue" {
  event_source_arn = aws_sqs_queue.callback_queue.arn
  function_name    = module.callback_lambda.function_name
  batch_size       = 10
  enabled          = true
}

# ============================================================================
# Outputs
# ============================================================================

output "agent_images" {
  description = "Map of agent names to their ECR image URIs"
  value = {
    for k, v in module.agents : k => v.image_uri
  }
}

output "controller_function_arn" {
  description = "ARN of the controller Lambda function"
  value       = module.controller_lambda.function_arn
}

output "callback_function_arn" {
  description = "ARN of the callback Lambda function"
  value       = module.callback_lambda.function_arn
}

output "state_table_name" {
  description = "Name of the DynamoDB state table"
  value       = aws_dynamodb_table.agent_state.name
}

output "task_queue_url" {
  description = "URL of the task SQS queue"
  value       = aws_sqs_queue.task_queue.url
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.agents.name
}

output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    agents     = keys(module.agents)
    functions  = [
      module.controller_lambda.function_name,
      module.callback_lambda.function_name,
      module.state_checker_lambda.function_name
    ]
    region     = var.aws_region
    environment = var.environment
  }
}
