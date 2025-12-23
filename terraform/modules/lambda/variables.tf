# Lambda Module Variables

variable "function_name" {
  description = "Name of the Lambda function"
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9-_]+$", var.function_name))
    error_message = "Function name can only contain alphanumeric characters, hyphens, and underscores."
  }
}

variable "handler" {
  description = "Lambda function handler (e.g., index.handler, main.lambda_handler)"
  type        = string
}

variable "runtime" {
  description = "Lambda runtime (e.g., python3.11, nodejs20.x, python3.12)"
  type        = string
}

variable "memory_size" {
  description = "Amount of memory in MB allocated to the Lambda function"
  type        = number
  default     = 128

  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240
    error_message = "Memory size must be between 128 MB and 10240 MB."
  }
}

variable "timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 3

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 900
    error_message = "Timeout must be between 1 and 900 seconds."
  }
}

variable "environment_variables" {
  description = "Map of environment variables for the Lambda function"
  type        = map(string)
  default     = {}
}

variable "source_dir" {
  description = "Path to the directory containing Lambda source code"
  type        = string
}

variable "exclude_files" {
  description = "List of file patterns to exclude from the Lambda package"
  type        = list(string)
  default = [
    "**/.git/**",
    "**/.terraform/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/node_modules/**",
    "**/.env",
    "**/tests/**",
    "**/.pytest_cache/**"
  ]
}

variable "policy_arns" {
  description = "List of IAM policy ARNs to attach to the Lambda execution role"
  type        = list(string)
  default     = []
}

variable "inline_policy" {
  description = "JSON-encoded inline IAM policy to attach to the Lambda execution role"
  type        = string
  default     = null
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

variable "vpc_config" {
  description = "VPC configuration for the Lambda function"
  type = object({
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}

variable "dead_letter_config" {
  description = "Dead Letter Queue configuration"
  type = object({
    target_arn = string
  })
  default = null
}

variable "ephemeral_storage_size" {
  description = "Size of ephemeral storage in MB (512-10240)"
  type        = number
  default     = 512

  validation {
    condition     = var.ephemeral_storage_size >= 512 && var.ephemeral_storage_size <= 10240
    error_message = "Ephemeral storage size must be between 512 MB and 10240 MB."
  }
}

variable "reserved_concurrent_executions" {
  description = "Number of reserved concurrent executions (-1 for unreserved)"
  type        = number
  default     = -1
}

variable "tracing_mode" {
  description = "X-Ray tracing mode (PassThrough or Active)"
  type        = string
  default     = "PassThrough"

  validation {
    condition     = contains(["PassThrough", "Active"], var.tracing_mode)
    error_message = "Tracing mode must be either 'PassThrough' or 'Active'."
  }
}

variable "architectures" {
  description = "Instruction set architecture (x86_64 or arm64)"
  type        = list(string)
  default     = ["x86_64"]

  validation {
    condition = alltrue([
      for arch in var.architectures : contains(["x86_64", "arm64"], arch)
    ])
    error_message = "Architectures must be 'x86_64' or 'arm64'."
  }
}

variable "layers" {
  description = "List of Lambda Layer ARNs to attach"
  type        = list(string)
  default     = []
}

variable "enable_function_url" {
  description = "Enable Lambda Function URL"
  type        = bool
  default     = false
}

variable "function_url_auth_type" {
  description = "Authorization type for Function URL (AWS_IAM or NONE)"
  type        = string
  default     = "AWS_IAM"

  validation {
    condition     = contains(["AWS_IAM", "NONE"], var.function_url_auth_type)
    error_message = "Function URL auth type must be 'AWS_IAM' or 'NONE'."
  }
}

variable "function_url_cors" {
  description = "CORS configuration for Function URL"
  type = object({
    allow_credentials = optional(bool, false)
    allow_headers     = optional(list(string), [])
    allow_methods     = optional(list(string), ["*"])
    allow_origins     = optional(list(string), ["*"])
    expose_headers    = optional(list(string), [])
    max_age           = optional(number, 0)
  })
  default = null
}

variable "schedule_expression" {
  description = "CloudWatch Event schedule expression (e.g., rate(5 minutes), cron(0 12 * * ? *))"
  type        = string
  default     = null
}

variable "alias_name" {
  description = "Name for the Lambda alias"
  type        = string
  default     = null
}

variable "alias_function_version" {
  description = "Function version for the alias"
  type        = string
  default     = "$LATEST"
}

variable "tags" {
  description = "Map of tags to apply to resources"
  type        = map(string)
  default     = {}
}
