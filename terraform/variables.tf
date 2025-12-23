# ============================================================================
# Input Variables
# ============================================================================
# This file defines all configurable parameters for the infrastructure.
# Override defaults using terraform.tfvars or -var flags.
# ============================================================================

# ============================================================================
# General Configuration
# ============================================================================

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "agent-orchestration"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must contain only lowercase letters, numbers, and hyphens."
  }
}

# ============================================================================
# Lambda Configuration
# ============================================================================

variable "controller_memory" {
  description = "Memory allocation for controller Lambda function (MB)"
  type        = number
  default     = 1024

  validation {
    condition     = var.controller_memory >= 128 && var.controller_memory <= 10240
    error_message = "Controller memory must be between 128 and 10240 MB."
  }
}

variable "controller_timeout" {
  description = "Timeout for controller Lambda function (seconds)"
  type        = number
  default     = 900 # 15 minutes

  validation {
    condition     = var.controller_timeout >= 60 && var.controller_timeout <= 900
    error_message = "Controller timeout must be between 60 and 900 seconds."
  }
}

variable "callback_memory" {
  description = "Memory allocation for callback Lambda function (MB)"
  type        = number
  default     = 256
}

variable "callback_timeout" {
  description = "Timeout for callback Lambda function (seconds)"
  type        = number
  default     = 30
}

variable "lambda_architecture" {
  description = "Lambda function architecture (x86_64 or arm64)"
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "Lambda architecture must be either x86_64 or arm64."
  }
}

variable "lambda_runtime" {
  description = "Python runtime version for Lambda functions"
  type        = string
  default     = "python3.12"
}

# ============================================================================
# Workflow Configuration
# ============================================================================

variable "approval_timeout_hours" {
  description = "Timeout for human approval callbacks (hours)"
  type        = number
  default     = 24

  validation {
    condition     = var.approval_timeout_hours >= 1 && var.approval_timeout_hours <= 168
    error_message = "Approval timeout must be between 1 and 168 hours (7 days)."
  }
}

variable "workflow_state_retention_days" {
  description = "Number of days to retain workflow state in DynamoDB (via TTL)"
  type        = number
  default     = 14

  validation {
    condition     = var.workflow_state_retention_days >= 1
    error_message = "Workflow state retention must be at least 1 day."
  }
}

# ============================================================================
# Agent Configuration
# ============================================================================

variable "agent_types" {
  description = "List of agent types to create ECR repositories for"
  type        = list(string)
  default     = ["researcher", "analyst", "writer"]
}

variable "enable_container_image_scanning" {
  description = "Enable vulnerability scanning for container images"
  type        = bool
  default     = true
}

# ============================================================================
# Storage Configuration
# ============================================================================

variable "artifact_bucket_versioning" {
  description = "Enable versioning for the artifact S3 bucket"
  type        = bool
  default     = true
}

variable "artifact_retention_days" {
  description = "Number of days to retain artifacts before transitioning to cheaper storage"
  type        = number
  default     = 90
}

# ============================================================================
# Observability Configuration
# ============================================================================

variable "enable_xray_tracing" {
  description = "Enable AWS X-Ray tracing for Lambda functions"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 7

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180,
      365, 400, 545, 731, 1827, 3653
    ], var.log_retention_days)
    error_message = "Log retention days must be a valid CloudWatch Logs retention period."
  }
}

variable "enable_api_access_logging" {
  description = "Enable access logging for API Gateway"
  type        = bool
  default     = true
}

# ============================================================================
# Security Configuration
# ============================================================================

variable "enable_api_gateway_auth" {
  description = "Enable IAM authentication for API Gateway endpoints"
  type        = bool
  default     = true
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to invoke API Gateway (empty = all)"
  type        = list(string)
  default     = []
}

# ============================================================================
# Resource Tagging
# ============================================================================

variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
