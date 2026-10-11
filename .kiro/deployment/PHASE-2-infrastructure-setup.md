# Phase 2: Infrastructure Deployment Plan

**Estimated Time:** 90-120 minutes  
**Status:** Architecture & Deployment Phase  
**Last Updated:** 2024

## Overview

Phase 2 establishes AWS infrastructure using Terraform. This includes relational database (RDS PostgreSQL), distributed cache (ElastiCache Redis), container orchestration (ECS Fargate), load balancing (ALB), and networking components.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  AWS Region (us-east-1)              │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │         Application Load Balancer (ALB)         │  │
│  │              (Port 443 - HTTPS)                 │  │
│  └──────────────────┬─────────────────────────────┘  │
│                     │                                 │
│  ┌──────────────────┼─────────────────────────────┐  │
│  │    ECS Fargate Cluster (3x Container Tasks)    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐       │  │
│  │  │ Triage   │ │ Triage   │ │ Triage   │       │  │
│  │  │ API #1   │ │ API #2   │ │ API #3   │       │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘       │  │
│  │       └────────────┼────────────┘               │  │
│  │                    │                            │  │
│  │  ┌─────────────────┴─────────────────┐        │  │
│  │  │    Triage Worker (Background)     │        │  │
│  │  │         (3x Tasks - Celery)       │        │  │
│  │  └─────────────────┬─────────────────┘        │  │
│  └────────────────────┼──────────────────────────┘  │
│                       │                              │
│     ┌─────────────────┼─────────────────┐            │
│     │                 │                 │            │
│ ┌───▼─────┐      ┌───▼─────┐      ┌───▼─────┐      │
│ │   RDS   │      │ElastiCache   │ │ Secrets │      │
│ │PostgreSQL   │ │   Redis      │      │Manager  │      │
│ │  (Multi-AZ) │ │  (3 nodes)   │ │  (Creds) │      │
│ └─────────┘  └──────────┘      └─────────┘      │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │  VPC (Private Subnets + Security Groups)        │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
└─────────────────────────────────────────────────────┘
```

## AWS Service Components

### 1. VPC & Networking

**Configuration:**
```
VPC CIDR:           10.0.0.0/16
Private Subnet 1:   10.0.1.0/24  (us-east-1a)
Private Subnet 2:   10.0.2.0/24  (us-east-1b)
Private Subnet 3:   10.0.3.0/24  (us-east-1c)
Database Subnet:    10.0.11.0/24, 10.0.12.0/24
```

**Deployment Steps:**
```bash
# Create VPC resources
terraform init
terraform plan -var-file=terraform.tfvars -out=tfplan

# Review plan
cat tfplan

# Apply infrastructure
terraform apply tfplan

# Verify VPC created
aws ec2 describe-vpcs --filters Name=tag:Name,Values=support-triage-agent-vpc
```

**Expected Output:**
```json
{
  "Vpcs": [
    {
      "VpcId": "vpc-0123456789abcdef",
      "CidrBlock": "10.0.0.0/16",
      "State": "available",
      "Tags": [{"Key": "Name", "Value": "support-triage-agent-vpc"}]
    }
  ]
}
```

### 2. RDS PostgreSQL Database

**Configuration:**
```
Engine:              PostgreSQL 15
Instance Class:      db.t3.medium (2 vCPU, 4 GB RAM)
Allocated Storage:   100 GB (gp3)
Multi-AZ:            Enabled
Backup Retention:    30 days
Encryption:          AES-256
Performance Insights: Enabled
```

**Pre-deployment:**
```bash
# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name support-triage-db-subnet \
  --db-subnet-group-description "Subnet group for triage database" \
  --subnet-ids subnet-123 subnet-456

# Create security group
aws ec2 create-security-group \
  --group-name support-triage-db-sg \
  --description "Security group for RDS database" \
  --vpc-id vpc-0123456789abcdef
```

**Terraform Deployment:**
```hcl
# terraform/rds.tf
resource "aws_db_instance" "triage_db" {
  allocated_storage       = var.db_storage_gb
  identifier              = "support-triage-db"
  engine                  = "postgres"
  engine_version          = "15"
  instance_class          = "db.t3.medium"
  username                = "triage_admin"
  password                = random_password.db_password.result
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  
  multi_az                = true
  storage_type            = "gp3"
  storage_encrypted       = true
  backup_retention_period = 30
  
  performance_insights_enabled = true
  enable_cloudwatch_logs_exports = ["postgresql"]
  
  skip_final_snapshot     = false
  final_snapshot_identifier = "support-triage-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
  
  tags = {
    Name        = "support-triage-db"
    Environment = "production"
  }
}
```

**Post-deployment Verification:**
```bash
# Get database endpoint
aws rds describe-db-instances \
  --db-instance-identifier support-triage-db \
  --query 'DBInstances[0].[Endpoint.Address,Endpoint.Port]'

# Expected output:
# [
#   "support-triage-db.c9akciq32.us-east-1.rds.amazonaws.com",
#   5432
# ]

# Test connection (from EC2 bastion or local machine with security group access)
psql -h support-triage-db.c9akciq32.us-east-1.rds.amazonaws.com \
     -U triage_admin \
     -d postgres

# Within psql:
postgres=# SELECT version();
postgres=# \l  # List databases
postgres=# \q  # Quit
```

**Database Initialization:**
```bash
# Run migrations
terraform apply -target=aws_db_instance.triage_db

# Store database credentials in Secrets Manager
aws secretsmanager create-secret \
  --name support-triage/db/credentials \
  --secret-string '{
    "username": "triage_admin",
    "password": "'$(terraform output -raw db_password)'",
    "host": "'$(terraform output -raw db_endpoint)'",
    "port": 5432,
    "dbname": "triage_production"
  }'
```

### 3. ElastiCache Redis Cluster

**Configuration:**
```
Engine:              Redis 7.0
Node Type:           cache.t3.micro (0.5 GB)
Number of Nodes:     3 (Multi-AZ with Auto-Failover)
Subnet Group:        Multi-AZ across 3 AZs
Parameter Group:     Custom (maxmemory-policy: allkeys-lru)
```

**Deployment:**
```hcl
# terraform/elasticache.tf
resource "aws_elasticache_subnet_group" "main" {
  name       = "support-triage-cache-subnet"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_description = "Redis cluster for triage service"
  engine                         = "redis"
  engine_version                 = "7.0"
  node_type                      = "cache.t3.micro"
  port                           = 6379
  parameter_group_name           = aws_elasticache_parameter_group.main.name
  subnet_group_name              = aws_elasticache_subnet_group.main.name
  security_group_ids             = [aws_security_group.elasticache.id]
  
  num_cache_clusters             = 3
  automatic_failover_enabled      = true
  multi_az_enabled               = true
  
  at_rest_encryption_enabled     = true
  transit_encryption_enabled     = true
  auth_token                     = random_password.redis_token.result
  
  snapshot_retention_limit       = 5
  snapshot_window               = "03:00-05:00"
  
  tags = {
    Name        = "support-triage-redis"
    Environment = "production"
  }
}
```

**Post-deployment Verification:**
```bash
# Get Redis endpoint
aws elasticache describe-replication-groups \
  --replication-group-id support-triage-redis \
  --query 'ReplicationGroups[0].MemberClusters'

# Expected output:
# [
#   "support-triage-redis-001",
#   "support-triage-redis-002",
#   "support-triage-redis-003"
# ]

# Get primary endpoint
aws elasticache describe-replication-groups \
  --replication-group-id support-triage-redis \
  --query 'ReplicationGroups[0].PrimaryEndpoint'

# Test Redis connection
redis-cli -h support-triage-redis.xxxxx.ng.0001.use1.cache.amazonaws.com \
          -p 6379 \
          --tls \
          ping
# Expected: PONG
```

### 4. ECS Fargate Cluster

**Configuration:**
```
Cluster Name:        support-triage-prod
Launch Type:         Fargate
Platform Version:    LATEST
CPU:                 512 units (0.5 vCPU)
Memory:              1024 MB (1 GB)
Desired Count:       3 (HA across 3 AZs)
```

**Deployment:**
```hcl
# terraform/ecs.tf
resource "aws_ecs_cluster" "main" {
  name = "support-triage-prod"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Environment = "production"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 2
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

resource "aws_ecs_task_definition" "triage_api" {
  family                   = "support-triage-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([{
    name      = "triage-api"
    image     = "${aws_ecr_repository.triage_api.repository_url}:latest"
    essential = true
    
    portMappings = [{
      containerPort = 8000
      hostPort      = 8000
      protocol      = "tcp"
    }]

    environment = [
      {
        name  = "ENVIRONMENT"
        value = "production"
      },
      {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
    ]

    secrets = [
      {
        name      = "DATABASE_URL"
        valueFrom = "${aws_secretsmanager_secret.db_secret.arn}:url::"
      },
      {
        name      = "REDIS_URL"
        valueFrom = "${aws_secretsmanager_secret.redis_secret.arn}:url::"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs_api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "triage_api" {
  name            = "support-triage-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.triage_api.arn
  desired_count   = 3
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.triage_api.arn
    container_name   = "triage-api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.main]
}
```

**Verification:**
```bash
# Verify cluster created
aws ecs describe-clusters --clusters support-triage-prod

# List running services
aws ecs list-services --cluster support-triage-prod

# Check task status
aws ecs list-tasks --cluster support-triage-prod

# Get task details
aws ecs describe-tasks \
  --cluster support-triage-prod \
  --tasks $(aws ecs list-tasks --cluster support-triage-prod --query 'taskArns[0]' --output text)
```

### 5. Application Load Balancer (ALB)

**Configuration:**
```
Name:                support-triage-alb
Scheme:              Internet-facing
IP Address Type:     IPv4
HTTP/2:              Enabled
HTTP to HTTPS:       Redirect (301)
Target Group:        support-triage-tg (port 8000)
Health Check:        GET /health (200 OK, 5s interval)
```

**Deployment:**
```hcl
# terraform/alb.tf
resource "aws_lb" "main" {
  name               = "support-triage-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = true
  enable_http2              = true

  tags = {
    Name        = "support-triage-alb"
    Environment = "production"
  }
}

resource "aws_lb_target_group" "triage_api" {
  name        = "support-triage-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/health"
    matcher             = "200"
  }

  tags = {
    Name = "support-triage-tg"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.ssl_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.triage_api.arn
  }
}
```

**Verification:**
```bash
# Get ALB DNS name
aws elbv2 describe-load-balancers \
  --names support-triage-alb \
  --query 'LoadBalancers[0].DNSName'

# Test HTTP redirect
curl -I http://<alb-dns>
# Expected: 301 redirect to HTTPS

# Test HTTPS endpoint
curl -I https://<alb-dns>/health
# Expected: 200 OK
```

### 6. AWS Secrets Manager

**Deployment:**
```hcl
# terraform/secrets.tf
resource "aws_secretsmanager_secret" "db_credentials" {
  name = "support-triage/production/db"
  
  tags = {
    Environment = "production"
  }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = aws_db_instance.main.username
    password = random_password.db_password.result
    engine   = "postgres"
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = aws_db_instance.main.db_name
  })
}

resource "aws_secretsmanager_secret" "redis_token" {
  name = "support-triage/production/redis"
  
  tags = {
    Environment = "production"
  }
}

resource "aws_secretsmanager_secret_version" "redis_token" {
  secret_id = aws_secretsmanager_secret.redis_token.id
  secret_string = jsonencode({
    auth_token = random_password.redis_token.result
    host       = aws_elasticache_replication_group.main.primary_endpoint_address
    port       = 6379
    db         = 0
  })
}
```

**Verification:**
```bash
# List secrets
aws secretsmanager list-secrets --filters Key=name,Values=support-triage

# Get secret value
aws secretsmanager get-secret-value \
  --secret-id support-triage/production/db \
  --query SecretString | jq .
```

## Database Initialization

### Initial Schema Setup

```bash
# 1. Create migration scripts directory
mkdir -p services/triage-api/migrations

# 2. Create initial schema migration
cat > services/triage-api/migrations/001_initial_schema.sql << 'EOF'
-- Create extensions
CREATE EXTENSION IF NOT EXISTS uuid-ossp;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS triage;

-- Create tables (example)
CREATE TABLE IF NOT EXISTS triage.cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id VARCHAR(255) NOT NULL,
    subject TEXT NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(20) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_cases_customer_id ON triage.cases(customer_id);
CREATE INDEX idx_cases_status ON triage.cases(status);
CREATE INDEX idx_cases_priority ON triage.cases(priority);
CREATE INDEX idx_cases_created_at ON triage.cases(created_at DESC);

-- Create audit log table
CREATE TABLE IF NOT EXISTS triage.audit_log (
    id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    changes JSONB,
    actor_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_log_entity ON triage.audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_log_created_at ON triage.audit_log(created_at DESC);

-- Enable Row Level Security
ALTER TABLE triage.cases ENABLE ROW LEVEL SECURITY;
EOF

# 3. Run migrations
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f services/triage-api/migrations/001_initial_schema.sql

# 4. Verify schema created
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "\dt triage.*"
```

## Database Backups

```bash
# Create automated backup configuration
aws rds modify-db-instance \
  --db-instance-identifier support-triage-db \
  --backup-retention-period 30 \
  --preferred-backup-window "03:00-04:00" \
  --apply-immediately

# Manual backup before major changes
aws rds create-db-snapshot \
  --db-snapshot-identifier support-triage-db-manual-$(date +%Y%m%d) \
  --db-instance-identifier support-triage-db
```

## Infrastructure Validation Tests

```bash
#!/bin/bash
# deployment/scripts/validate-infrastructure.sh

set -e

echo "=== Infrastructure Validation ==="

# Check VPC
echo "Checking VPC..."
aws ec2 describe-vpcs --filters Name=tag:Name,Values=support-triage-agent-vpc

# Check RDS
echo "Checking RDS..."
aws rds describe-db-instances --db-instance-identifier support-triage-db

# Check ElastiCache
echo "Checking ElastiCache..."
aws elasticache describe-replication-groups --replication-group-id support-triage-redis

# Check ECS Cluster
echo "Checking ECS Cluster..."
aws ecs describe-clusters --clusters support-triage-prod

# Check ALB
echo "Checking ALB..."
aws elbv2 describe-load-balancers --names support-triage-alb

echo "=== Validation Complete ==="
```

## Success Criteria

- ✓ VPC created with 3 private subnets across AZs
- ✓ RDS PostgreSQL operational with Multi-AZ enabled
- ✓ ElastiCache Redis cluster with 3 nodes operational
- ✓ ECS Fargate cluster with capacity providers configured
- ✓ ALB receiving traffic and routing to ECS tasks
- ✓ Security groups properly configured
- ✓ Secrets stored in AWS Secrets Manager
- ✓ Database schema initialized
- ✓ All health checks passing

## Cost Estimation

| Service | Instance/Config | Monthly Cost |
|---------|-----------------|--------------|
| RDS PostgreSQL | db.t3.medium Multi-AZ | ~$300 |
| ElastiCache | 3x cache.t3.micro | ~$90 |
| ECS Fargate | 3x (512 CPU, 1GB) | ~$120 |
| ALB | 1x Application Load Balancer | ~$25 |
| NAT Gateway | 2x (HA) | ~$60 |
| **Total Monthly** | - | **~$595** |

## Next Steps

→ **Proceed to Phase 3: Docker Build & Registry**
- Build and push container images to ECR
- Tag images for production
- Verify image security scanning

## References

- [AWS RDS PostgreSQL Guide](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PostgreSQL.html)
- [AWS ElastiCache for Redis](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/)
- [ECS Fargate Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ECS_AWSFAQ.html)
- [Application Load Balancer Guide](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
