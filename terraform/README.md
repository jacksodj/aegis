# Terraform Configuration for Serverless Durable Agent Orchestration

This directory contains the complete Terraform infrastructure-as-code configuration for deploying the serverless durable agent orchestration platform on AWS.

## Overview

This Terraform configuration deploys:

- **S3 Bucket**: Versioned and encrypted storage for workflow artifacts and reports
- **DynamoDB Table**: Workflow state management with GSI for status-based queries
- **ECR Repositories**: Container registries for researcher, analyst, and writer agents
- **Lambda Functions**: Controller (orchestration) and callback (agent response) handlers
- **API Gateway**: HTTP API with endpoints for workflow management and callbacks
- **IAM Roles & Policies**: Least-privilege access for all components
- **CloudWatch Log Groups**: Centralized logging with configurable retention
- **EventBridge**: Workflow event monitoring and observability
- **Docker Build Automation**: Automated build and push of agent container images

## File Structure

```
terraform/
├── versions.tf      # Terraform and provider version constraints
├── variables.tf     # Input variables with defaults and validation
├── locals.tf        # Local values and computed configurations
├── main.tf          # Main resource definitions
├── outputs.tf       # Output values for integration and testing
└── README.md        # This file
```

## Prerequisites

### Required Tools

```bash
# Terraform 1.5 or later
terraform --version

# AWS CLI v2
aws --version

# Docker (for building agent images)
docker --version

# Valid AWS credentials
aws sts get-caller-identity
```

### AWS Permissions

Your AWS credentials need permissions to create:
- S3 buckets
- DynamoDB tables
- ECR repositories
- Lambda functions
- API Gateway APIs
- IAM roles and policies
- CloudWatch log groups
- EventBridge rules

## Quick Start

### 1. Initialize Terraform

```bash
cd terraform
terraform init
```

This downloads the required providers (AWS, archive, null).

### 2. Review Configuration

Review the default values in `variables.tf` and create a `terraform.tfvars` file if you want to override any:

```hcl
# terraform.tfvars (optional)
aws_region              = "us-east-1"
environment             = "dev"
project_name            = "agent-orchestration"
controller_memory       = 1024
controller_timeout      = 900
approval_timeout_hours  = 24
log_retention_days      = 7
```

### 3. Plan Deployment

```bash
terraform plan
```

Review the planned changes. You should see approximately 40+ resources to be created.

### 4. Deploy Infrastructure

```bash
terraform apply
```

Type `yes` when prompted. Deployment takes approximately 5-10 minutes.

**Note**: The Docker build automation will run during deployment, building and pushing agent images to ECR. This requires Docker to be running locally.

### 5. Verify Deployment

After successful deployment, Terraform outputs important values:

```bash
# View all outputs
terraform output

# View specific output
terraform output api_endpoint
terraform output artifact_bucket_name
terraform output ecr_repository_urls
```

## Testing the Deployment

### Start a Workflow

```bash
# Get the API endpoint
API_ENDPOINT=$(terraform output -raw api_endpoint)

# Start a new workflow
curl -X POST "${API_ENDPOINT}/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Impact of quantum computing on cryptography",
    "parameters": {
      "depth": "comprehensive",
      "sources": ["academic", "industry"]
    }
  }'
```

Response:
```json
{
  "status": "PENDING",
  "workflow_id": "wf-abc123...",
  "awaiting": "research_completion",
  "message": "Workflow suspended awaiting research completion"
}
```

### Check Workflow Status

```bash
# Get workflow status
WORKFLOW_ID="wf-abc123..."
curl -X GET "${API_ENDPOINT}/workflows/${WORKFLOW_ID}"
```

### View Logs

```bash
# Controller logs
aws logs tail $(terraform output -raw controller_log_group_name) --follow

# Callback logs
aws logs tail $(terraform output -raw callback_log_group_name) --follow
```

## Configuration Variables

### General Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `aws_region` | AWS region for deployment | `us-east-1` | No |
| `environment` | Environment name (dev, staging, prod) | `dev` | No |
| `project_name` | Project name for resource naming | `agent-orchestration` | No |

### Lambda Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `controller_memory` | Controller Lambda memory (MB) | `1024` | No |
| `controller_timeout` | Controller Lambda timeout (seconds) | `900` | No |
| `callback_memory` | Callback Lambda memory (MB) | `256` | No |
| `callback_timeout` | Callback Lambda timeout (seconds) | `30` | No |
| `lambda_architecture` | Lambda architecture (arm64/x86_64) | `arm64` | No |
| `lambda_runtime` | Python runtime version | `python3.12` | No |

### Workflow Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `approval_timeout_hours` | Human approval timeout (hours) | `24` | No |
| `workflow_state_retention_days` | DynamoDB TTL retention (days) | `14` | No |

### Storage Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `artifact_bucket_versioning` | Enable S3 versioning | `true` | No |
| `artifact_retention_days` | Days before artifact transition | `90` | No |

### Observability Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `enable_xray_tracing` | Enable AWS X-Ray tracing | `true` | No |
| `log_retention_days` | CloudWatch log retention (days) | `7` | No |
| `enable_api_access_logging` | Enable API Gateway access logs | `true` | No |

## Outputs

After deployment, the following outputs are available:

### API Endpoints
- `api_endpoint`: Base URL for API Gateway
- `test_endpoints`: Map of all available endpoints

### Resource Identifiers
- `artifact_bucket_name`: S3 bucket name
- `workflow_table_name`: DynamoDB table name
- `controller_function_name`: Controller Lambda name
- `callback_function_name`: Callback Lambda name
- `ecr_repository_urls`: Map of ECR repository URLs per agent type

### Monitoring
- `monitoring_urls`: AWS Console URLs for CloudWatch, X-Ray, etc.
- `controller_log_group_name`: CloudWatch log group for controller
- `callback_log_group_name`: CloudWatch log group for callback

### Quick Commands
- `quick_start_commands`: Ready-to-use CLI commands
- `docker_build_commands`: Commands to rebuild agent images

## Docker Image Management

### Automated Builds

The Terraform configuration automatically builds and pushes Docker images to ECR during deployment using `null_resource` provisioners. Images are rebuilt when:

- Dockerfile changes
- Source code changes
- ECR repository URL changes

### Manual Builds

To manually rebuild and push agent images:

```bash
# Get the build commands
terraform output -json docker_build_commands

# For a specific agent (e.g., researcher)
REGION=$(terraform output -raw region)
ACCOUNT_ID=$(terraform output -raw account_id)
REPO_URL=$(terraform output -json ecr_repository_urls | jq -r '.researcher')

# Login to ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Build and push
docker build -t $REPO_URL:latest --platform linux/arm64 ../agents/researcher
docker push $REPO_URL:latest
```

## Cost Optimization

### Development Environment

For development, consider these cost-saving measures:

```hcl
# terraform.tfvars
controller_memory           = 512          # Reduce from default 1024
log_retention_days          = 1            # Minimal retention
enable_xray_tracing         = false        # Disable tracing
artifact_bucket_versioning  = false        # Disable versioning
```

### Production Environment

For production, use:

```hcl
# terraform.tfvars
environment                 = "prod"
controller_memory           = 2048         # More memory for performance
log_retention_days          = 30           # Longer retention
enable_xray_tracing         = true         # Full observability
artifact_bucket_versioning  = true         # Data protection
```

## Monitoring and Observability

### CloudWatch Dashboards

Access pre-configured monitoring URLs:

```bash
terraform output -json monitoring_urls | jq
```

### X-Ray Tracing

When `enable_xray_tracing = true`, view distributed traces:

```bash
# Open X-Ray console URL
terraform output -json monitoring_urls | jq -r '.xray_traces'
```

### Structured Logging

All Lambda functions emit structured JSON logs. Query with CloudWatch Logs Insights:

```sql
fields @timestamp, workflow_id, step_name, @message
| filter event_type = "step_completed"
| sort @timestamp desc
| limit 20
```

## Troubleshooting

### Docker Build Failures

If Docker builds fail during `terraform apply`:

1. Ensure Docker daemon is running: `docker ps`
2. Check Docker authentication: `docker login` to ECR
3. Verify Dockerfiles exist in `../agents/*/Dockerfile`
4. Check build logs in Terraform output

To skip Docker builds:

```bash
# Comment out null_resource "docker_build_push" in main.tf
# Then apply
terraform apply
```

### Lambda Deployment Failures

If Lambda functions fail to deploy:

1. Check source directories exist:
   - `../controller/handler.py`
   - `../callback/handler.py`
2. Verify IAM permissions for Lambda creation
3. Check CloudWatch log groups for errors

### API Gateway 403 Errors

If API returns 403 Forbidden:

1. Check IAM authentication is configured correctly
2. Verify Lambda permissions allow API Gateway invocation
3. Check CORS configuration if calling from browser

## Cleanup

To destroy all resources:

```bash
# Preview what will be destroyed
terraform plan -destroy

# Destroy all resources
terraform destroy
```

**Warning**: This will permanently delete:
- All workflow data in DynamoDB
- All artifacts in S3 (if versioning is disabled)
- All Docker images in ECR
- All CloudWatch logs (within retention period)

To preserve data, export before destroying:

```bash
# Export DynamoDB table
aws dynamodb scan --table-name $(terraform output -raw workflow_table_name) > workflows_backup.json

# Download S3 artifacts
aws s3 sync s3://$(terraform output -raw artifact_bucket_name) ./artifacts_backup/
```

## Advanced Configuration

### Using a Custom VPC

To deploy Lambda functions in a VPC (not included by default):

1. Uncomment VPC-related resources in `main.tf`
2. Add VPC configuration to Lambda functions
3. Update security groups and subnets

### Enabling DynamoDB Streams

To enable streams for change data capture:

```hcl
# Add to DynamoDB table resource in main.tf
stream_enabled   = true
stream_view_type = "NEW_AND_OLD_IMAGES"
```

### Custom Domain Names

To use a custom domain with API Gateway:

1. Create ACM certificate
2. Add custom domain to API Gateway
3. Update DNS records

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Deploy Infrastructure

on:
  push:
    branches: [main]

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Terraform Init
        run: terraform init
        working-directory: terraform

      - name: Terraform Plan
        run: terraform plan
        working-directory: terraform

      - name: Terraform Apply
        run: terraform apply -auto-approve
        working-directory: terraform
```

## Security Considerations

### Secrets Management

This configuration does NOT include Secrets Manager for API keys. To add:

```hcl
resource "aws_secretsmanager_secret" "bedrock_api_key" {
  name = "${local.name_prefix}-bedrock-api-key"
}

# Add to Lambda environment
environment {
  variables = {
    BEDROCK_API_KEY_SECRET = aws_secretsmanager_secret.bedrock_api_key.arn
  }
}
```

### Network Security

For production:
- Deploy Lambda functions in private VPC subnets
- Use VPC endpoints for AWS services
- Implement API Gateway resource policies
- Enable AWS WAF for API Gateway

## Support

For issues, questions, or contributions:
- Review the main specification: `../serverless_durable_agent_orchestration_spec.md`
- Check implementation docs: `../controller/README.md`, `../callback/README.md`
- View architecture diagrams: `../docs/`

## License

See repository root for license information.
