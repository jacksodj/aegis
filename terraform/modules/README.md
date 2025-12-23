# Terraform Modules for Serverless Durable Agent Orchestration

This directory contains reusable Terraform modules for deploying the serverless durable agent orchestration platform.

## Module Structure

```
modules/
├── lambda/          # Reusable Lambda function module
│   ├── main.tf      # Lambda resources
│   ├── variables.tf # Input variables
│   ├── outputs.tf   # Output values
│   └── README.md    # Module documentation
│
└── agent/           # Reusable containerized agent module
    ├── main.tf      # ECR and Docker build resources
    ├── variables.tf # Input variables
    ├── outputs.tf   # Output values
    ├── build.sh     # Docker build and push script
    └── README.md    # Module documentation
```

## Available Modules

### Lambda Module

Creates AWS Lambda functions with:
- Automatic IAM role creation
- CloudWatch logging
- Function URLs
- Scheduled invocations
- VPC configuration
- Multi-architecture support (x86_64, ARM64)

**Use cases:**
- Controller Lambda
- Callback handlers
- State management functions
- API endpoints

[Full Documentation](./lambda/README.md)

### Agent Module

Creates containerized agents with:
- ECR repository
- Automated Docker builds
- Multi-platform support (ARM64/Graviton)
- IAM roles
- CloudWatch logging
- Lifecycle policies

**Use cases:**
- Coordinator agent
- Analyst agent
- Research agent
- Execution agent
- Custom specialized agents

[Full Documentation](./agent/README.md)

## Quick Start

### Using the Lambda Module

```hcl
module "controller" {
  source = "./modules/lambda"

  function_name = "aegis-controller"
  handler       = "main.lambda_handler"
  runtime       = "python3.12"
  memory_size   = 512
  timeout       = 300

  source_dir = "${path.module}/../controller/src"

  environment_variables = {
    STATE_TABLE = aws_dynamodb_table.state.name
    TASK_QUEUE  = aws_sqs_queue.tasks.url
  }

  policy_arns = [
    aws_iam_policy.controller_policy.arn
  ]
}
```

### Using the Agent Module

```hcl
module "coordinator_agent" {
  source = "./modules/agent"

  agent_name = "coordinator-agent"
  source_dir = "${path.module}/../agents/coordinator"
  platform   = "linux/arm64"

  create_iam_role  = true
  create_log_group = true
}
```

### Deploying Multiple Agents

```hcl
locals {
  agents = ["coordinator", "analyst", "research", "execution"]
}

module "agents" {
  for_each = toset(local.agents)
  source   = "./modules/agent"

  agent_name = "${each.key}-agent"
  source_dir = "${path.module}/../agents/${each.key}"
  platform   = "linux/arm64"  # Graviton for cost savings

  tags = {
    Environment = var.environment
    Agent       = each.key
  }
}
```

## Module Best Practices

### 1. Version Pinning

Always pin module versions in production:

```hcl
module "my_lambda" {
  source = "git::https://github.com/org/repo.git//modules/lambda?ref=v1.0.0"
  # ... configuration
}
```

### 2. Variable Validation

Both modules include input validation to catch errors early:

```hcl
variable "memory_size" {
  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240
    error_message = "Memory size must be between 128 MB and 10240 MB."
  }
}
```

### 3. Tag Standardization

Use consistent tagging across all modules:

```hcl
locals {
  common_tags = {
    Project     = "aegis"
    Environment = var.environment
    ManagedBy   = "terraform"
    CostCenter  = "engineering"
  }
}

module "example" {
  source = "./modules/lambda"
  tags   = local.common_tags
  # ...
}
```

### 4. Output Composition

Chain module outputs as inputs:

```hcl
module "agent" {
  source = "./modules/agent"
  # ...
}

module "lambda" {
  source = "./modules/lambda"

  environment_variables = {
    AGENT_IMAGE = module.agent.image_uri
  }
}
```

### 5. Conditional Resources

Use variables to toggle optional features:

```hcl
module "lambda" {
  source = "./modules/lambda"

  enable_function_url = var.environment == "production" ? false : true
  tracing_mode       = var.environment == "production" ? "Active" : "PassThrough"
}
```

## Architecture Considerations

### Lambda vs Container Agents

**Use Lambda when:**
- Execution time < 15 minutes
- Stateless operations
- Event-driven workflows
- Low to medium memory requirements

**Use Container Agents when:**
- Long-running tasks (> 15 minutes)
- Complex dependencies
- Custom runtimes
- High memory requirements
- Stateful operations

### Cost Optimization

1. **Use ARM64/Graviton**: 20% cost savings
   ```hcl
   architectures = ["arm64"]  # Lambda
   platform = "linux/arm64"    # Agents
   ```

2. **Right-size memory**: Monitor and adjust
3. **Enable lifecycle policies**: Clean up old images
4. **Use reserved concurrency**: Prevent runaway costs
5. **Optimize cold starts**: Use provisioned concurrency for critical paths

### Security Best Practices

1. **Least Privilege IAM**: Only grant necessary permissions
2. **Enable Encryption**: Use KMS for ECR repositories
3. **Image Scanning**: Enable vulnerability scanning
4. **Network Isolation**: Use VPC when accessing private resources
5. **Secrets Management**: Use AWS Secrets Manager, not env vars

## Testing Modules

### Validate Configuration

```bash
cd terraform
terraform init
terraform validate
terraform plan
```

### Test Lambda Module

```bash
# Create test function
terraform apply -target=module.test_lambda

# Invoke function
aws lambda invoke \
  --function-name test-lambda \
  --payload '{"test": "data"}' \
  response.json
```

### Test Agent Module

```bash
# Build and push image
terraform apply -target=module.test_agent

# Verify image exists
aws ecr describe-images \
  --repository-name test-agent \
  --query 'imageDetails[0]'
```

## Troubleshooting

### Common Issues

**Lambda Package Too Large**
- Use layers for dependencies
- Exclude test files and documentation
- Consider container images for large packages

**Docker Build Fails**
- Check Dockerfile syntax
- Verify Docker daemon is running
- Ensure AWS credentials are configured
- Check disk space for builds

**ECR Push Permission Denied**
- Verify IAM permissions for ECR
- Check ECR repository exists
- Confirm AWS region is correct

**Terraform State Locked**
- Check for running operations
- Use `terraform force-unlock` if needed
- Consider using remote state locking

## Contributing

When creating new modules:

1. Follow the same structure (main.tf, variables.tf, outputs.tf)
2. Include comprehensive variable validation
3. Add detailed README with examples
4. Use consistent naming conventions
5. Tag all resources appropriately
6. Include lifecycle management
7. Document all inputs and outputs

## Resources

- [Terraform AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [ECR Best Practices](https://docs.aws.amazon.com/AmazonECR/latest/userguide/best-practices.html)
- [AWS Graviton](https://aws.amazon.com/ec2/graviton/)
