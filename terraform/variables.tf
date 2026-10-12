variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "ap-southeast-2"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "support-triage"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production-free-tier"
}

variable "app_name" {
  description = "Application name used in resource naming"
  type        = string
  default     = "support-triage-agent"
}

variable "availability_zone" {
  description = "Availability zone for resources (single AZ for free tier)"
  type        = string
  default     = "ap-southeast-2a"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for public subnet"
  type        = string
  default     = "10.0.101.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "db_instance_class" {
  description = "RDS instance class (free tier: db.t3.micro)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB (free tier: 20)"
  type        = number
  default     = 20
}

variable "db_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15"
}

variable "db_name" {
  description = "Initial database name"
  type        = string
  default     = "support_triage"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "admin"
  sensitive   = true
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

variable "cache_node_type" {
  description = "ElastiCache node type (free tier: cache.t3.micro)"
  type        = string
  default     = "cache.t3.micro"
}

variable "cache_engine_version" {
  description = "Redis engine version"
  type        = string
  default     = "7.0"
}

variable "ecs_cpu" {
  description = "ECS task CPU units (free tier: 256)"
  type        = number
  default     = 256
}

variable "ecs_memory" {
  description = "ECS task memory in MB (free tier: 512)"
  type        = number
  default     = 512
}

variable "ecs_desired_count" {
  description = "Desired number of ECS tasks (free tier: 1)"
  type        = number
  default     = 1
}

variable "container_image" {
  description = "Docker image URI for ECS task"
  type        = string
}

variable "ssl_certificate_arn" {
  description = "ARN of ACM SSL certificate for NLB (empty = no TLS)"
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days (free tier: 7)"
  type        = number
  default     = 7
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = "your-email@example.com"
}
