# Agent Module

Reusable Terraform module for creating containerized agents with Amazon ECR repository, automated Docker builds, and optional IAM roles and CloudWatch logging.

## Features

- ECR repository with configurable lifecycle policies
- Automated Docker image build and push
- Multi-architecture support (ARM64/Graviton)
- Image scanning on push
- KMS encryption support
- Automatic lifecycle management
- Optional IAM role creation
- Optional CloudWatch Log Group
- Build information output
- Cross-account access support

## Usage

### Basic Agent

```hcl
module "analyst_agent" {
  source = "./modules/agent"

  agent_name = "analyst-agent"
  source_dir = "${path.module}/../agents/analyst"

  tags = {
    Environment = "production"
    Project     = "aegis"
  }
}

output "analyst_image" {
  value = module.analyst_agent.image_uri
}
```

### Agent with ARM64 Support (Graviton)

```hcl
module "coordinator_agent" {
  source = "./modules/agent"

  agent_name = "coordinator-agent"
  source_dir = "${path.module}/../agents/coordinator"

  # Build for ARM64 (AWS Graviton)
  platform = "linux/arm64"

  image_tag = "v1.0.0"
  additional_tags = "latest,stable"

  tags = {
    Environment = "production"
    Architecture = "arm64"
  }
}
```

### Agent with Custom Build Arguments

```hcl
module "research_agent" {
  source = "./modules/agent"

  agent_name = "research-agent"
  source_dir = "${path.module}/../agents/research"

  # Pass build arguments to Docker
  build_args = {
    PYTHON_VERSION = "3.12"
    APP_ENV        = "production"
    BUILD_DATE     = timestamp()
  }

  # Use custom Dockerfile
  dockerfile_path = "Dockerfile.production"
}
```

### Agent with IAM Role and Logging

```hcl
module "execution_agent" {
  source = "./modules/agent"

  agent_name = "execution-agent"
  source_dir = "${path.module}/../agents/execution"

  # Create IAM role for ECS tasks
  create_iam_role = true
  iam_role_principals = [
    "ecs-tasks.amazonaws.com"
  ]

  # Attach policies
  iam_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
    "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
  ]

  # Create CloudWatch Log Group
  create_log_group    = true
  log_retention_days  = 30
}

output "execution_agent_role" {
  value = module.execution_agent.role_arn
}
```

### Agent with Custom Lifecycle Policy

```hcl
module "processor_agent" {
  source = "./modules/agent"

  agent_name = "processor-agent"
  source_dir = "${path.module}/../agents/processor"

  # Disable default lifecycle policy
  enable_default_lifecycle_policy = false

  # Custom lifecycle policy
  lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 20 production images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["prod-"]
          countType     = "imageCountMoreThan"
          countNumber   = 20
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last 5 development images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["dev-"]
          countType     = "imageCountMoreThan"
          countNumber   = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
```

### Agent with KMS Encryption

```hcl
resource "aws_kms_key" "ecr" {
  description = "KMS key for ECR encryption"
}

module "secure_agent" {
  source = "./modules/agent"

  agent_name = "secure-agent"
  source_dir = "${path.module}/../agents/secure"

  # Enable KMS encryption
  encryption_type = "KMS"
  kms_key_arn    = aws_kms_key.ecr.arn

  # Enable image scanning
  scan_on_push = true

  # Immutable tags
  image_tag_mutability = "IMMUTABLE"
}
```

### Multi-Agent Deployment

```hcl
locals {
  agents = {
    "coordinator" = {
      source_dir = "${path.module}/../agents/coordinator"
      platform   = "linux/arm64"
    }
    "analyst" = {
      source_dir = "${path.module}/../agents/analyst"
      platform   = "linux/amd64"
    }
    "research" = {
      source_dir = "${path.module}/../agents/research"
      platform   = "linux/arm64"
    }
    "execution" = {
      source_dir = "${path.module}/../agents/execution"
      platform   = "linux/amd64"
    }
  }
}

module "agents" {
  for_each = local.agents
  source   = "./modules/agent"

  agent_name = "${each.key}-agent"
  source_dir = each.value.source_dir
  platform   = each.value.platform

  image_tag = var.image_version

  create_log_group = true
  create_iam_role  = true

  tags = {
    Environment = var.environment
    Agent       = each.key
  }
}

output "agent_images" {
  value = {
    for k, v in module.agents : k => v.image_uri
  }
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| agent_name | Name of the agent and ECR repository | string | - | yes |
| source_dir | Path to directory with Dockerfile | string | - | yes |
| ecr_registry | ECR registry URL | string | null | no |
| image_tag | Docker image tag | string | "latest" | no |
| platform | Target platform (linux/amd64, linux/arm64) | string | "linux/amd64" | no |
| build_args | Docker build arguments | map(string) | {} | no |
| enable_docker_build | Enable Docker build and push | bool | true | no |
| scan_on_push | Enable image scanning | bool | true | no |
| encryption_type | Encryption type (AES256 or KMS) | string | "AES256" | no |
| create_log_group | Create CloudWatch Log Group | bool | false | no |
| create_iam_role | Create IAM role | bool | false | no |
| tags | Resource tags | map(string) | {} | no |

## Outputs

| Name | Description |
|------|-------------|
| repository_url | ECR repository URL |
| image_uri | Full Docker image URI (repository:tag) |
| repository_arn | ARN of ECR repository |
| image_tag | Tag of the Docker image |
| role_arn | ARN of IAM role (if created) |
| log_group_name | CloudWatch Log Group name (if created) |

## Build Script

The module includes a robust `build.sh` script that handles:

- ECR authentication
- Multi-platform builds using Docker buildx
- ARM64/Graviton support
- Build argument injection
- Image tagging and pushing
- Build artifact cleanup
- Comprehensive error handling
- Colorized logging

## Directory Structure

Your agent source directory should contain:

```
agents/my-agent/
├── Dockerfile
├── requirements.txt (Python)
├── package.json (Node.js)
├── src/
│   └── agent code
└── tests/
    └── test files
```

## Best Practices

1. **Platform Selection**: Use ARM64 for better cost-performance with Graviton
2. **Image Tags**: Use semantic versioning for production images
3. **Lifecycle Policies**: Configure appropriate retention to control costs
4. **Image Scanning**: Enable for security compliance
5. **Build Triggers**: Module automatically detects source changes
6. **Multi-stage Builds**: Use in Dockerfile to reduce image size
7. **Security**: Enable KMS encryption for sensitive workloads

## Requirements

- Terraform >= 1.0
- AWS Provider >= 5.0
- Docker installed locally
- AWS CLI configured
- Docker buildx (for multi-platform builds)

## Troubleshooting

### Build Failures

If builds fail, check:
- Docker daemon is running
- AWS credentials are configured
- ECR repository exists
- Dockerfile syntax is valid

### Permission Errors

Ensure:
- AWS credentials have ECR push permissions
- Docker has access to source directory
- Build script is executable (`chmod +x build.sh`)

### Platform Issues

For ARM64 builds:
- Docker buildx must be installed
- QEMU emulation may be needed on non-ARM hosts
- First build may be slower due to emulation
