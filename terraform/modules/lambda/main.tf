# Lambda Function Module
# Reusable module for creating Lambda functions with IAM roles and CloudWatch logging

# Data source for AWS region and account
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Archive source code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.module}/.terraform/archive/${var.function_name}.zip"
  excludes    = var.exclude_files
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name = "${var.function_name}-logs"
    }
  )
}

# IAM Role for Lambda execution
resource "aws_iam_role" "lambda_role" {
  name = "${var.function_name}-role"

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
    var.tags,
    {
      Name = "${var.function_name}-role"
    }
  )
}

# Attach AWS managed policy for basic Lambda execution
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Attach additional custom policy ARNs
resource "aws_iam_role_policy_attachment" "lambda_additional_policies" {
  for_each = toset(var.policy_arns)

  role       = aws_iam_role.lambda_role.name
  policy_arn = each.value
}

# Inline IAM policy for custom permissions
resource "aws_iam_role_policy" "lambda_inline_policy" {
  count = var.inline_policy != null ? 1 : 0

  name   = "${var.function_name}-inline-policy"
  role   = aws_iam_role.lambda_role.id
  policy = var.inline_policy
}

# Lambda Function
resource "aws_lambda_function" "function" {
  function_name = var.function_name
  role          = aws_iam_role.lambda_role.arn
  handler       = var.handler
  runtime       = var.runtime
  timeout       = var.timeout
  memory_size   = var.memory_size

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = var.environment_variables
  }

  # VPC Configuration (optional)
  dynamic "vpc_config" {
    for_each = var.vpc_config != null ? [var.vpc_config] : []
    content {
      subnet_ids         = vpc_config.value.subnet_ids
      security_group_ids = vpc_config.value.security_group_ids
    }
  }

  # Dead Letter Queue configuration (optional)
  dynamic "dead_letter_config" {
    for_each = var.dead_letter_config != null ? [var.dead_letter_config] : []
    content {
      target_arn = dead_letter_config.value.target_arn
    }
  }

  # Ephemeral storage configuration
  ephemeral_storage {
    size = var.ephemeral_storage_size
  }

  # Reserved concurrent executions
  reserved_concurrent_executions = var.reserved_concurrent_executions

  # Tracing configuration
  tracing_config {
    mode = var.tracing_mode
  }

  # Architecture
  architectures = var.architectures

  # Layers
  layers = var.layers

  tags = merge(
    var.tags,
    {
      Name = var.function_name
    }
  )

  depends_on = [
    aws_cloudwatch_log_group.lambda_logs,
    aws_iam_role_policy_attachment.lambda_basic_execution
  ]

  lifecycle {
    create_before_destroy = true
  }
}

# Lambda Function URL (optional)
resource "aws_lambda_function_url" "function_url" {
  count = var.enable_function_url ? 1 : 0

  function_name      = aws_lambda_function.function.function_name
  authorization_type = var.function_url_auth_type

  dynamic "cors" {
    for_each = var.function_url_cors != null ? [var.function_url_cors] : []
    content {
      allow_credentials = cors.value.allow_credentials
      allow_headers     = cors.value.allow_headers
      allow_methods     = cors.value.allow_methods
      allow_origins     = cors.value.allow_origins
      expose_headers    = cors.value.expose_headers
      max_age           = cors.value.max_age
    }
  }
}

# CloudWatch Event Rule for scheduled invocations (optional)
resource "aws_cloudwatch_event_rule" "schedule" {
  count = var.schedule_expression != null ? 1 : 0

  name                = "${var.function_name}-schedule"
  description         = "Schedule for ${var.function_name}"
  schedule_expression = var.schedule_expression

  tags = merge(
    var.tags,
    {
      Name = "${var.function_name}-schedule"
    }
  )
}

# CloudWatch Event Target
resource "aws_cloudwatch_event_target" "lambda_target" {
  count = var.schedule_expression != null ? 1 : 0

  rule      = aws_cloudwatch_event_rule.schedule[0].name
  target_id = "lambda"
  arn       = aws_lambda_function.function.arn
}

# Lambda Permission for CloudWatch Events
resource "aws_lambda_permission" "allow_cloudwatch" {
  count = var.schedule_expression != null ? 1 : 0

  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}

# Lambda Alias (optional)
resource "aws_lambda_alias" "alias" {
  count = var.alias_name != null ? 1 : 0

  name             = var.alias_name
  description      = "Alias for ${var.function_name}"
  function_name    = aws_lambda_function.function.function_name
  function_version = var.alias_function_version

  lifecycle {
    ignore_changes = [function_version]
  }
}
