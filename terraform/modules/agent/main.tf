# Agent Module
# Reusable module for creating containerized agents with ECR repository and Docker build

# Data sources
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ECR Repository for Agent Container Images
resource "aws_ecr_repository" "agent" {
  name                 = var.agent_name
  image_tag_mutability = var.image_tag_mutability

  # Image scanning configuration
  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }

  # Encryption configuration
  encryption_configuration {
    encryption_type = var.encryption_type
    kms_key         = var.kms_key_arn
  }

  # Force delete (useful for development)
  force_delete = var.force_delete

  tags = merge(
    var.tags,
    {
      Name = var.agent_name
    }
  )
}

# ECR Lifecycle Policy
resource "aws_ecr_lifecycle_policy" "agent" {
  count = var.lifecycle_policy != null ? 1 : 0

  repository = aws_ecr_repository.agent.name
  policy     = var.lifecycle_policy
}

# Default lifecycle policy (if none provided)
resource "aws_ecr_lifecycle_policy" "agent_default" {
  count = var.lifecycle_policy == null && var.enable_default_lifecycle_policy ? 1 : 0

  repository = aws_ecr_repository.agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last ${var.max_image_count} images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = var.max_image_count
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images older than ${var.untagged_image_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_image_days
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ECR Repository Policy (for cross-account access)
resource "aws_ecr_repository_policy" "agent" {
  count = var.repository_policy != null ? 1 : 0

  repository = aws_ecr_repository.agent.name
  policy     = var.repository_policy
}

# Local variables for build configuration
locals {
  ecr_url              = "${var.ecr_registry != null ? var.ecr_registry : data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com"
  repository_url       = aws_ecr_repository.agent.repository_url
  image_tag            = var.image_tag
  image_uri            = "${local.repository_url}:${local.image_tag}"
  build_script_path    = "${path.module}/build.sh"

  # Build triggers - will force rebuild when these change
  build_trigger = {
    source_hash       = fileexists("${var.source_dir}/Dockerfile") ? sha256(file("${var.source_dir}/Dockerfile")) : ""
    requirements_hash = fileexists("${var.source_dir}/requirements.txt") ? sha256(file("${var.source_dir}/requirements.txt")) : ""
    source_files_hash = sha256(join("", [for f in fileset(var.source_dir, var.build_trigger_patterns) : filesha256("${var.source_dir}/${f}")]))
    image_tag         = var.image_tag
    build_args        = jsonencode(var.build_args)
    platform          = var.platform
    timestamp         = var.force_rebuild ? timestamp() : ""
  }
}

# Docker Build and Push
resource "null_resource" "docker_build" {
  count = var.enable_docker_build ? 1 : 0

  # Triggers for rebuild
  triggers = local.build_trigger

  # Build and push Docker image
  provisioner "local-exec" {
    command = <<-EOT
      bash ${local.build_script_path} \
        "${var.source_dir}" \
        "${local.repository_url}" \
        "${local.image_tag}" \
        "${data.aws_region.current.name}" \
        "${var.platform}" \
        "${jsonencode(var.build_args)}" \
        "${var.dockerfile_path}" \
        "${var.additional_tags}"
    EOT

    environment = {
      AWS_REGION     = data.aws_region.current.name
      AWS_ACCOUNT_ID = data.aws_caller_identity.current.account_id
    }
  }

  depends_on = [
    aws_ecr_repository.agent
  ]

  lifecycle {
    create_before_destroy = false
  }
}

# CloudWatch Log Group for Agent (if agent runs in ECS/Lambda)
resource "aws_cloudwatch_log_group" "agent" {
  count = var.create_log_group ? 1 : 0

  name              = "/aws/agent/${var.agent_name}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name = "${var.agent_name}-logs"
    }
  )
}

# IAM Role for Agent (if needed for ECS Task or Lambda)
resource "aws_iam_role" "agent" {
  count = var.create_iam_role ? 1 : 0

  name = "${var.agent_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = var.iam_role_principals
        }
      }
    ]
  })

  tags = merge(
    var.tags,
    {
      Name = "${var.agent_name}-role"
    }
  )
}

# Attach IAM policies to the agent role
resource "aws_iam_role_policy_attachment" "agent_policies" {
  for_each = var.create_iam_role ? toset(var.iam_policy_arns) : []

  role       = aws_iam_role.agent[0].name
  policy_arn = each.value
}

# Inline IAM policy for agent
resource "aws_iam_role_policy" "agent_inline" {
  count = var.create_iam_role && var.iam_inline_policy != null ? 1 : 0

  name   = "${var.agent_name}-inline-policy"
  role   = aws_iam_role.agent[0].id
  policy = var.iam_inline_policy
}

# Output file with build information
resource "local_file" "build_info" {
  count = var.output_build_info ? 1 : 0

  filename = "${var.source_dir}/.build_info.json"
  content = jsonencode({
    agent_name     = var.agent_name
    repository_url = local.repository_url
    image_uri      = local.image_uri
    image_tag      = local.image_tag
    region         = data.aws_region.current.name
    account_id     = data.aws_caller_identity.current.account_id
    built_at       = timestamp()
    source_hash    = local.build_trigger.source_files_hash
  })

  depends_on = [
    null_resource.docker_build
  ]
}
