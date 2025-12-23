# Terraform Deployment Guide
## Serverless Durable Agent Orchestration Platform

## What Was Created

This Terraform configuration provides a complete, production-ready infrastructure for the serverless durable agent orchestration platform. Here's what's included:

### Core Terraform Files

1. **versions.tf** (837 bytes)
   - Terraform version constraint: >= 1.5
   - AWS provider: >= 5.0
   - Archive provider for Lambda packaging
   - Null provider for Docker automation

2. **variables.tf** (6.3 KB)
   - 20+ configurable input variables
   - Comprehensive validation rules
   - Sensible defaults for all settings
   - Support for dev, staging, and prod environments

3. **locals.tf** (5.9 KB)
   - Computed naming conventions
   - Agent configurations (researcher, analyst, writer)
   - Lambda environment variables (auto-wired)
   - API Gateway and DynamoDB configurations
   - S3 lifecycle rules

4. **main.tf** (24 KB) - The comprehensive main configuration with:
   - **S3 Bucket**: Versioned, encrypted artifact storage with lifecycle policies
   - **DynamoDB Table**: Workflow state with GSI on status+created_at, TTL enabled
   - **ECR Repositories**: One per agent type with lifecycle policies
   - **Lambda Functions**: Controller (orchestration) and Callback (agent responses)
   - **API Gateway HTTP API**: REST endpoints with CORS configuration
   - **IAM Roles & Policies**: Least-privilege access for all components
   - **CloudWatch Log Groups**: Centralized logging with configurable retention
   - **EventBridge Rules**: Workflow event monitoring
   - **Docker Build Automation**: Automatic build and push to ECR
   - **~40+ AWS resources** in total

5. **outputs.tf** (11 KB)
   - API endpoints and resource identifiers
   - ECR repository URLs for all agents
   - CloudWatch log group names
   - AWS Console URLs for monitoring
   - Quick start commands
   - Docker build commands
   - Complete deployment summary

### Supporting Files

6. **README.md** (13 KB)
   - Comprehensive documentation
   - Prerequisites and setup instructions
   - Configuration variable reference
   - Testing and troubleshooting guides
   - Cost optimization tips
   - CI/CD integration examples

7. **terraform.tfvars.example** (6.8 KB)
   - Example configurations for dev/staging/prod
   - Detailed comments for each variable
   - Ready-to-use templates

8. **.gitignore** (1.2 KB)
   - Protects sensitive files (*.tfvars)
   - Excludes generated files
   - Standard Terraform exclusions

9. **deploy.sh** (executable)
   - Automated deployment script
   - Prerequisites checking
   - Guided deployment process
   - Plan summary and outputs

## Key Features

### 🚀 Production-Ready

- **Automated deployment**: Single `terraform apply` deploys everything
- **Zero manual ARN updates**: All resources auto-wired via environment variables
- **Proper ordering**: `depends_on` ensures correct resource creation sequence
- **Idempotent**: Safe to run multiple times

### 🔒 Security

- **Encryption at rest**: S3 (AES256), DynamoDB (enabled)
- **Encryption in transit**: TLS enforced on all endpoints
- **Least privilege IAM**: Minimal permissions for each component
- **Private access**: S3 public access blocked
- **Audit trail**: CloudWatch Logs for all operations

### 💰 Cost Optimized

- **Pay-per-request**: DynamoDB on-demand billing
- **ARM64 Lambda**: Lower costs vs x86_64
- **S3 lifecycle**: Auto-transition to cheaper storage classes
- **Log retention**: Configurable to control costs
- **ECR lifecycle**: Auto-cleanup of old images

### 📊 Observable

- **X-Ray tracing**: Distributed tracing across all components
- **Structured logging**: JSON logs with workflow_id correlation
- **EventBridge events**: Workflow state change notifications
- **CloudWatch dashboards**: Pre-configured monitoring URLs
- **API Gateway logging**: Full request/response logging

### 🔧 Configurable

- **Environment-specific**: Variables for dev/staging/prod
- **Flexible sizing**: Adjustable Lambda memory and timeout
- **Retention policies**: Configurable for logs and artifacts
- **Feature flags**: Enable/disable X-Ray, versioning, etc.
- **Tag inheritance**: Common tags on all resources

### 🐳 Docker Automation

- **Automatic builds**: Docker images built during `terraform apply`
- **ECR push**: Images automatically pushed to ECR
- **Change detection**: Rebuilds when Dockerfile or code changes
- **Multi-platform**: ARM64 support for cost savings
- **Versioning**: Both `latest` and timestamped tags

## Quick Start

### 1. Prerequisites Check

```bash
cd /home/user/aegis/terraform
./deploy.sh check
```

### 2. Customize Configuration (Optional)

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your preferences
```

### 3. Deploy Infrastructure

```bash
./deploy.sh deploy
```

Or manually:

```bash
terraform init
terraform plan
terraform apply
```

### 4. Test the Deployment

```bash
# Get API endpoint
API_ENDPOINT=$(terraform output -raw api_endpoint)

# Start a workflow
curl -X POST "$API_ENDPOINT/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Impact of quantum computing on cryptography",
    "parameters": {"depth": "comprehensive"}
  }'
```

### 5. Monitor Logs

```bash
# Controller logs
aws logs tail $(terraform output -raw controller_log_group_name) --follow

# Callback logs  
aws logs tail $(terraform output -raw callback_log_group_name) --follow
```

## What Gets Deployed

### Infrastructure Resources (~40+)

| Resource Type | Count | Purpose |
|--------------|-------|---------|
| S3 Buckets | 1 | Artifact and report storage |
| DynamoDB Tables | 1 | Workflow state management |
| ECR Repositories | 3 | Agent container images (researcher, analyst, writer) |
| Lambda Functions | 2 | Controller (orchestration) + Callback (responses) |
| IAM Roles | 3 | Lambda controller, callback, EventBridge logs |
| IAM Policies | 3 | Custom policies for each role |
| API Gateway APIs | 1 | HTTP API for workflow management |
| API Gateway Stages | 1 | $default stage with auto-deploy |
| API Gateway Routes | 4 | POST /workflows, GET /workflows/{id}, POST /callbacks/{id}, POST /approve/{id} |
| API Gateway Integrations | 2 | Controller and callback Lambda integrations |
| CloudWatch Log Groups | 4 | Controller, callback, API Gateway, EventBridge |
| EventBridge Rules | 1 | Workflow event monitoring |
| EventBridge Targets | 1 | CloudWatch Logs target |
| Lambda Permissions | 2 | API Gateway invoke permissions |
| Null Resources | 3 | Docker build and push automation |

### Estimated Monthly Costs (Dev Environment)

Based on moderate usage (100 workflows/month, 1GB artifacts):

- **Lambda**: ~$5 (pay per invocation)
- **API Gateway**: ~$1 (pay per request)
- **DynamoDB**: ~$1 (on-demand, low traffic)
- **S3**: ~$0.50 (storage + requests)
- **ECR**: ~$0.30 (image storage)
- **CloudWatch**: ~$2 (logs + metrics)
- **Data Transfer**: ~$1

**Total: ~$10-15/month for dev environment**

Production costs scale with usage but remain serverless (pay-per-use).

## Architecture

The deployed infrastructure follows this architecture:

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────┐
│      API Gateway (HTTP)         │
│  - POST /workflows              │
│  - GET /workflows/{id}          │
│  - POST /callbacks/{id}         │
│  - POST /approve/{id}           │
└────┬────────────────────┬───────┘
     │                    │
     ▼                    ▼
┌─────────────┐    ┌─────────────┐
│ Controller  │    │  Callback   │
│   Lambda    │    │   Lambda    │
└──────┬──────┘    └──────┬──────┘
       │                  │
       ├──────────────────┤
       │                  │
       ▼                  ▼
┌─────────────────────────────────┐
│         DynamoDB Table          │
│     (Workflow State + GSI)      │
└─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│          S3 Bucket              │
│    (Artifacts + Reports)        │
└─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│     CloudWatch Logs + X-Ray     │
│      (Observability Layer)      │
└─────────────────────────────────┘

Controller invokes ──▶ AgentCore Runtimes (ECR images)
                       ├─ Researcher
                       ├─ Analyst
                       └─ Writer
```

## Environment Variables Auto-Wired

The configuration automatically wires these environment variables to Lambda functions:

### Controller Lambda
- `ARTIFACT_BUCKET`: S3 bucket name
- `WORKFLOW_TABLE`: DynamoDB table name
- `RESEARCHER_AGENT_ARN`: Researcher agent ARN
- `ANALYST_AGENT_ARN`: Analyst agent ARN
- `WRITER_AGENT_ARN`: Writer agent ARN
- `CALLBACK_API_URL`: API Gateway invoke URL
- `APPROVAL_TIMEOUT_HOURS`: Configured timeout
- `ENVIRONMENT`: Current environment
- `LOG_LEVEL`: DEBUG (dev) or INFO (prod)

### Callback Lambda
- `WORKFLOW_TABLE`: DynamoDB table name
- `ARTIFACT_BUCKET`: S3 bucket name
- `CONTROLLER_FUNCTION_NAME`: Controller Lambda name
- `ENVIRONMENT`: Current environment
- `LOG_LEVEL`: DEBUG (dev) or INFO (prod)

**No manual updates needed!** All ARNs and resource names are automatically injected.

## Workflow

After deployment, workflows follow this pattern:

1. **Client** sends POST to `/workflows` with topic and parameters
2. **Controller Lambda** receives request and starts orchestration
3. **DynamoDB** stores workflow state
4. **Controller** invokes **Researcher Agent** (via AgentCore)
5. **Researcher** gathers information, stores in **S3**, sends callback
6. **Callback Lambda** receives result, updates **DynamoDB**
7. **Controller** invokes **Analyst Agent**
8. **Analyst** analyzes data, sends callback
9. **Controller** requests **human approval** via EventBridge
10. Human approves via `/approve/{id}` endpoint
11. **Controller** invokes **Writer Agent**
12. **Writer** generates report, stores in **S3**
13. **Controller** finalizes workflow, returns presigned URL

All steps are logged to **CloudWatch**, traced via **X-Ray**, and emit **EventBridge** events.

## Validation

The configuration includes:

- **Variable validation**: Type checks, range validation, enum validation
- **Terraform validation**: Runs `terraform validate` successfully
- **Syntax checking**: All HCL syntax is valid
- **Dependency ordering**: Proper `depends_on` relationships
- **IAM policy validation**: Correct ARN formats and actions

## Next Steps

1. **Deploy**: Run `./deploy.sh deploy`
2. **Test**: Use the quick start commands from outputs
3. **Monitor**: Access CloudWatch and X-Ray via monitoring URLs
4. **Scale**: Adjust variables in terraform.tfvars
5. **Iterate**: Modify and reapply as needed

## Support

- Main spec: `/home/user/aegis/serverless_durable_agent_orchestration_spec.md`
- Controller code: `/home/user/aegis/controller/`
- Callback code: `/home/user/aegis/callback/`
- Agent code: `/home/user/aegis/agents/`

## Clean Up

To destroy all resources:

```bash
./deploy.sh destroy
```

Or manually:

```bash
terraform destroy
```

**Warning**: This permanently deletes all workflow data and artifacts!
