variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Environment name (staging, prod, ...)"
  type        = string
  default     = "staging"
}

variable "image_tag" {
  description = "Container image tag to deploy (CI passes the git SHA)"
  type        = string
  default     = "latest"
}

variable "cpu" {
  description = "App Runner vCPU (256 = 0.25 vCPU)"
  type        = string
  default     = "256"
}

variable "memory" {
  description = "App Runner memory in MB"
  type        = string
  default     = "512"
}

variable "min_instances" {
  type    = number
  default = 1
}

variable "max_instances" {
  type    = number
  default = 5
}

variable "max_concurrency" {
  description = "Concurrent requests per instance before App Runner scales out"
  type        = number
  default     = 50
}
