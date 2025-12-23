# Infrastructure

This project uses **Terraform** for infrastructure deployment.

See [`/terraform`](../terraform/) for the complete infrastructure configuration.

## Quick Start

```bash
cd ../terraform
./deploy.sh deploy
```

Or manually:

```bash
cd ../terraform
terraform init
terraform plan
terraform apply
```

## What's Deployed

- **S3 Bucket**: Artifact storage (versioned, encrypted)
- **DynamoDB Table**: Workflow state with GSI
- **ECR Repositories**: Container registries for agents
- **Lambda Functions**: Controller + Callback handler
- **API Gateway**: REST API for workflows
- **IAM Roles**: Least-privilege policies
- **CloudWatch**: Logging and monitoring

See [terraform/README.md](../terraform/README.md) for full details.
