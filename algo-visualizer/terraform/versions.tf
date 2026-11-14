terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Remote state (recommended for teams). Create the bucket first, then uncomment:
  # backend "s3" {
  #   bucket       = "my-terraform-state"
  #   key          = "algo-visualizer/terraform.tfstate"
  #   region       = "eu-central-1"
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "algo-visualizer"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
