terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
  }
  # NOTE: S3 backend will be configured after initial setup
  # backend "s3" {
  #   bucket  = "support-triage-tfstate-ACCOUNT_ID"
  #   key     = "production/terraform.tfstate"
  #   region  = "ap-southeast-2"
  #   encrypt = true
  # }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  default_tags { tags = local.common_tags }
}

locals {
  common_tags = {
    Project     = var.app_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Team        = "platform"
    CostCenter  = "poc"
  }
}
