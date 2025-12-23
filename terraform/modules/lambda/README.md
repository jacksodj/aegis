# Lambda Module

Reusable Terraform module for creating AWS Lambda functions with associated IAM roles, CloudWatch logging, and optional features like Function URLs, scheduled invocations, and VPC configuration.

## Features

- Lambda function with configurable runtime, memory, and timeout
- Automatic IAM role creation with customizable policies
- CloudWatch Log Group with configurable retention
- Support for VPC configuration
- Dead Letter Queue configuration
- Function URL support with CORS
- Scheduled invocations via CloudWatch Events
- Lambda aliases for versioning
- X-Ray tracing support
- Multi-architecture support (x86_64, ARM64/Graviton)
- Lambda Layers support
- Automatic source code packaging

## Usage

### Basic Lambda Function

```hcl
module "api_handler" {
  source = "./modules/lambda"

  function_name = "api-handler"
  handler       = "index.handler"
  runtime       = "nodejs20.x"
  memory_size   = 256
  timeout       = 30

  source_dir = "${path.module}/../src/api-handler"

  environment_variables = {
    NODE_ENV = "production"
    API_URL  = "https://api.example.com"
  }

  tags = {
    Environment = "production"
    Project     = "aegis"
  }
}
```

### Lambda with Custom IAM Policies

```hcl
module "data_processor" {
  source = "./modules/lambda"

  function_name = "data-processor"
  handler       = "main.lambda_handler"
  runtime       = "python3.12"
  memory_size   = 1024
  timeout       = 300

  source_dir = "${path.module}/../src/processor"

  # Attach AWS managed policies
  policy_arns = [
    "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
  ]

  # Add inline policy for specific permissions
  inline_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      }
    ]
  })

  environment_variables = {
    TABLE_NAME = "data-table"
    BUCKET_NAME = "data-bucket"
  }
}
```

### Lambda with Function URL

```hcl
module "webhook_handler" {
  source = "./modules/lambda"

  function_name = "webhook-handler"
  handler       = "app.handler"
  runtime       = "python3.11"

  source_dir = "${path.module}/../src/webhook"

  # Enable Function URL
  enable_function_url   = true
  function_url_auth_type = "NONE"

  # Configure CORS
  function_url_cors = {
    allow_origins     = ["https://example.com"]
    allow_methods     = ["POST", "GET"]
    allow_headers     = ["content-type", "x-api-key"]
    max_age           = 86400
  }
}

output "webhook_url" {
  value = module.webhook_handler.function_url
}
```

### Scheduled Lambda

```hcl
module "daily_report" {
  source = "./modules/lambda"

  function_name = "daily-report-generator"
  handler       = "report.generate"
  runtime       = "python3.12"
  timeout       = 600

  source_dir = "${path.module}/../src/reports"

  # Run every day at 9 AM UTC
  schedule_expression = "cron(0 9 * * ? *)"

  environment_variables = {
    REPORT_BUCKET = "reports-bucket"
  }
}
```

### Lambda with VPC Configuration

```hcl
module "db_migrator" {
  source = "./modules/lambda"

  function_name = "database-migrator"
  handler       = "migrate.handler"
  runtime       = "python3.11"
  timeout       = 900
  memory_size   = 512

  source_dir = "${path.module}/../src/migrator"

  # VPC configuration for database access
  vpc_config = {
    subnet_ids         = ["subnet-12345", "subnet-67890"]
    security_group_ids = ["sg-12345"]
  }

  policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
  ]
}
```

### ARM64/Graviton Lambda

```hcl
module "graviton_function" {
  source = "./modules/lambda"

  function_name = "graviton-processor"
  handler       = "index.handler"
  runtime       = "python3.12"
  memory_size   = 512

  source_dir = "${path.module}/../src/processor"

  # Use ARM64 architecture for better price-performance
  architectures = ["arm64"]
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| function_name | Name of the Lambda function | string | - | yes |
| handler | Lambda function handler | string | - | yes |
| runtime | Lambda runtime | string | - | yes |
| source_dir | Path to source code directory | string | - | yes |
| memory_size | Memory in MB | number | 128 | no |
| timeout | Timeout in seconds | number | 3 | no |
| environment_variables | Environment variables map | map(string) | {} | no |
| policy_arns | IAM policy ARNs to attach | list(string) | [] | no |
| inline_policy | Inline IAM policy JSON | string | null | no |
| log_retention_days | CloudWatch log retention | number | 7 | no |
| architectures | CPU architecture | list(string) | ["x86_64"] | no |
| enable_function_url | Enable Function URL | bool | false | no |
| schedule_expression | CloudWatch schedule expression | string | null | no |
| vpc_config | VPC configuration | object | null | no |
| tags | Resource tags | map(string) | {} | no |

## Outputs

| Name | Description |
|------|-------------|
| function_arn | ARN of the Lambda function |
| function_name | Name of the Lambda function |
| invoke_arn | Invoke ARN for API Gateway |
| role_arn | ARN of the execution role |
| log_group_name | CloudWatch Log Group name |
| function_url | Function URL (if enabled) |

## Best Practices

1. **Memory Sizing**: Start with lower memory and increase based on monitoring
2. **Timeout**: Set appropriate timeouts - avoid max unless necessary
3. **Environment Variables**: Use for configuration, not secrets
4. **IAM Permissions**: Follow least privilege principle
5. **Logging**: Keep reasonable retention periods
6. **Architecture**: Consider ARM64 for better price-performance
7. **VPC**: Only use VPC when accessing VPC resources

## Requirements

- Terraform >= 1.0
- AWS Provider >= 5.0
