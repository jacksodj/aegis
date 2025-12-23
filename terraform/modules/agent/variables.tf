# Agent Module Variables

variable "agent_name" {
  description = "Name of the agent and ECR repository"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-_/]*$", var.agent_name))
    error_message = "Agent name must start with a lowercase letter or number and can only contain lowercase letters, numbers, hyphens, underscores, and forward slashes."
  }
}

variable "source_dir" {
  description = "Path to the directory containing the Dockerfile and agent source code"
  type        = string

  validation {
    condition     = can(fileexists("${var.source_dir}/Dockerfile"))
    error_message = "Source directory must contain a Dockerfile."
  }
}

variable "ecr_registry" {
  description = "ECR registry URL (defaults to current account registry if not specified)"
  type        = string
  default     = null
}

variable "image_tag" {
  description = "Docker image tag"
  type        = string
  default     = "latest"
}

variable "additional_tags" {
  description = "Comma-separated list of additional Docker image tags"
  type        = string
  default     = ""
}

variable "platform" {
  description = "Target platform for Docker build (e.g., linux/amd64, linux/arm64)"
  type        = string
  default     = "linux/amd64"

  validation {
    condition     = can(regex("^linux/(amd64|arm64)$", var.platform))
    error_message = "Platform must be linux/amd64 or linux/arm64."
  }
}

variable "build_args" {
  description = "Map of Docker build arguments"
  type        = map(string)
  default     = {}
}

variable "dockerfile_path" {
  description = "Path to Dockerfile relative to source_dir (default: Dockerfile)"
  type        = string
  default     = "Dockerfile"
}

variable "build_trigger_patterns" {
  description = "File patterns to trigger rebuilds when changed"
  type        = list(string)
  default = [
    "**/*.py",
    "**/*.js",
    "**/*.ts",
    "**/requirements.txt",
    "**/package.json",
    "**/Dockerfile",
    "**/*.go",
    "**/*.java"
  ]
}

variable "enable_docker_build" {
  description = "Enable Docker build and push to ECR"
  type        = bool
  default     = true
}

variable "force_rebuild" {
  description = "Force rebuild on every Terraform apply"
  type        = bool
  default     = false
}

# ECR Configuration
variable "image_tag_mutability" {
  description = "Image tag mutability setting (MUTABLE or IMMUTABLE)"
  type        = string
  default     = "MUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "Image tag mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "scan_on_push" {
  description = "Enable image scanning on push"
  type        = bool
  default     = true
}

variable "encryption_type" {
  description = "Encryption type (AES256 or KMS)"
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "KMS"], var.encryption_type)
    error_message = "Encryption type must be AES256 or KMS."
  }
}

variable "kms_key_arn" {
  description = "KMS key ARN for ECR encryption (required if encryption_type is KMS)"
  type        = string
  default     = null
}

variable "force_delete" {
  description = "Force delete ECR repository even if it contains images"
  type        = bool
  default     = false
}

# Lifecycle Policy Configuration
variable "lifecycle_policy" {
  description = "JSON-encoded ECR lifecycle policy"
  type        = string
  default     = null
}

variable "enable_default_lifecycle_policy" {
  description = "Enable default lifecycle policy if none provided"
  type        = bool
  default     = true
}

variable "max_image_count" {
  description = "Maximum number of images to keep in the repository"
  type        = number
  default     = 10
}

variable "untagged_image_days" {
  description = "Number of days to keep untagged images"
  type        = number
  default     = 7
}

# Repository Policy
variable "repository_policy" {
  description = "JSON-encoded ECR repository policy for cross-account access"
  type        = string
  default     = null
}

# CloudWatch Logs
variable "create_log_group" {
  description = "Create CloudWatch Log Group for the agent"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
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

# IAM Role
variable "create_iam_role" {
  description = "Create IAM role for the agent"
  type        = bool
  default     = false
}

variable "iam_role_principals" {
  description = "List of AWS service principals that can assume the agent role"
  type        = list(string)
  default     = ["ecs-tasks.amazonaws.com", "lambda.amazonaws.com"]
}

variable "iam_policy_arns" {
  description = "List of IAM policy ARNs to attach to the agent role"
  type        = list(string)
  default     = []
}

variable "iam_inline_policy" {
  description = "JSON-encoded inline IAM policy for the agent role"
  type        = string
  default     = null
}

# Build Info
variable "output_build_info" {
  description = "Output build information to .build_info.json file"
  type        = bool
  default     = true
}

# Tags
variable "tags" {
  description = "Map of tags to apply to resources"
  type        = map(string)
  default     = {}
}
