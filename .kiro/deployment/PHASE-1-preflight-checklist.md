# Phase 1: Pre-Flight Checklist (Infrastructure Setup)

**Estimated Time:** 45-60 minutes  
**Status:** Implementation Phase  
**Last Updated:** 2024

## Overview

Pre-flight verification ensures all prerequisites are met before AWS infrastructure deployment. This phase validates AWS account access, permissions, local tooling, and creates required configuration templates.

## Prerequisites Verification

### 1. AWS Account Setup

**Required:**
- [ ] AWS account with appropriate permissions
- [ ] AWS credentials configured locally
- [ ] IAM user or role with at least these policies:
  - `AdministratorAccess` (for initial setup) OR
  - Custom policy with CloudFormation, RDS, ElastiCache, ECS, ALB, IAM, ECR permissions

**Steps:**
```bash
# Verify AWS CLI is installed
aws --version

# Verify AWS credentials are configured
aws sts get-caller-identity

# Expected output:
# {
#     "UserId": "AIDAI...",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/deployment"
# }

# List available AWS profiles
aws configure list

# If using specific profile, set environment variable
export AWS_PROFILE=your-profile-name
```

**Troubleshooting:**
- If `get-caller-identity` fails: run `aws configure` with AWS Access Key ID and Secret Access Key
- If wrong account shown: verify `AWS_PROFILE` or credential configuration in `~/.aws/credentials`

### 2. Local Development Tools

**Required Tools:**
- [ ] Docker (v20.10+)
- [ ] Docker Compose (v1.29+)
- [ ] Terraform (v1.5+)
- [ ] AWS CLI (v2.13+)
- [ ] Git (v2.40+)
- [ ] Python (v3.10+)
- [ ] jq (for JSON parsing)
- [ ] curl

**Installation Steps:**

**Windows (PowerShell):**
```powershell
# Check Docker
docker --version

# Check Terraform
terraform --version

# Check AWS CLI
aws --version

# Install Terraform (if needed)
choco install terraform
# Or download from https://www.terraform.io/downloads

# Install jq
choco install jq

# Install AWS CLI v2
# Download from https://awscli.amazonaws.com/AWSCLIV2.msi
# Or use choco: choco install awscli
```

**macOS (Homebrew):**
```bash
# Check tools
docker --version
terraform --version
aws --version

# Install if missing
brew install terraform aws-cli jq

# Verify installations
which docker terraform aws jq
```

**Linux (Ubuntu/Debian):**
```bash
# Install required tools
sudo apt-get update
sudo apt-get install -y docker.io awscli terraform jq curl git

# Start Docker daemon
sudo systemctl start docker
sudo usermod -aG docker $USER

# Verify installations
docker --version
terraform --version
aws --version
```

**Verification Commands:**
```bash
docker --version          # Expected: Docker version 20.10+
docker run hello-world    # Should complete successfully
terraform --version       # Expected: Terraform v1.5+
aws --version            # Expected: aws-cli/2.13+
aws s3 ls                # Should list S3 buckets without error (if any exist)
jq --version             # Expected: jq-1.6 or higher
```

### 3. Environment Variables

**Create `.env.production` file:**
```bash
# Copy template
cp deployment/.env.production.template .env.production

# Edit with production values
# See deployment/.env.production.template for full list
```

**Critical Environment Variables:**
```
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
ENVIRONMENT=production
APP_NAME=support-triage-agent

# RDS Configuration
DB_ENGINE=postgresql
DB_VERSION=15
DB_INSTANCE_CLASS=db.t3.medium
DB_STORAGE_GB=100
DB_MULTI_AZ=true

# ElastiCache Configuration
CACHE_ENGINE=redis
CACHE_NODE_TYPE=cache.t3.micro
CACHE_NUM_CACHE_NODES=3

# ECS Configuration
ECS_CONTAINER_CPU=512
ECS_CONTAINER_MEMORY=1024
ECS_DESIRED_COUNT=3

# ALB Configuration
ALB_PORT=443
ALB_SSL_CERTIFICATE_ARN=arn:aws:acm:us-east-1:123456789012:certificate/xxxxx
```

**Verification:**
```bash
# Verify environment file exists and is readable
[ -f ".env.production" ] && echo "✓ Environment file found" || echo "✗ Missing"

# Verify required variables are set
for var in AWS_REGION AWS_ACCOUNT_ID ENVIRONMENT; do
  value=$(grep "^$var=" .env.production | cut -d'=' -f2)
  [ -n "$value" ] && echo "✓ $var = $value" || echo "✗ $var missing"
done
```

### 4. Project Structure Validation

**Expected Directory Structure:**
```
Support-triage-agent-/
├── .kiro/
│   └── deployment/              # Deployment artifacts
├── services/
│   ├── triage-api/              # FastAPI service
│   ├── triage-worker/           # Celery worker
│   └── triage-console/          # Admin console
├── packages/
│   └── triage-core/             # Shared library
├── Dockerfile                    # API container
├── docker-compose.yml           # Local development
├── pyproject.toml               # Python project config
└── Makefile                     # Build automation
```

**Validation Steps:**
```bash
# Check critical files exist
required_files=(
  "services/triage-api/main.py"
  "services/triage-worker/tasks.py"
  "services/triage-console/app.py"
  "Dockerfile"
  "docker-compose.yml"
  "pyproject.toml"
)

for file in "${required_files[@]}"; do
  [ -f "$file" ] && echo "✓ $file" || echo "✗ MISSING: $file"
done
```

### 5. Git Repository Validation

**Requirements:**
- [ ] Repository is clean (no uncommitted changes)
- [ ] Main branch is up to date
- [ ] Deployment branch can be created
- [ ] Git remotes are configured

**Steps:**
```bash
# Check repository status
git status
# Expected: "On branch main" and "nothing to commit, working tree clean"

# Check remotes
git remote -v
# Expected: origin pointing to correct repository

# Verify main branch is up to date
git fetch origin
git log -1 --oneline main
git log -1 --oneline origin/main

# Create deployment branch
git checkout -b deploy/production-v1.0

# Verify branch created
git branch -v
```

## Pre-Flight Checklist Script

**Run automated validation:**
```bash
bash deployment/scripts/pre-flight-check.sh
```

**Expected Output:**
```
=== Pre-Flight Checklist ===
✓ Docker installed (v20.10.21)
✓ Docker daemon running
✓ Terraform installed (v1.5.1)
✓ AWS CLI installed (v2.13.15)
✓ AWS credentials configured
✓ AWS account accessible (123456789012)
✓ Python 3.10+ installed
✓ Project structure valid
✓ Git repository clean
✓ All required files present

=== Status: READY FOR DEPLOYMENT ===
Deployment can proceed to Phase 2.
```

## Configuration Files Created

### 1. `.env.production.template`
Location: `deployment/.env.production.template`
Contains all required environment variables with descriptions.

**Usage:**
```bash
cp deployment/.env.production.template .env.production
# Edit .env.production with actual values
# NEVER commit .env.production to git
```

### 2. `terraform/variables.tf`
Defines all Terraform input variables with validation rules.

### 3. `terraform/terraform.tfvars.template`
Template for Terraform variable values to match AWS environment.

## Deliverables

- [x] AWS account access verified
- [x] Local tools installed and verified
- [x] Environment configuration template created
- [x] Project structure validated
- [x] Git repository ready
- [x] Pre-flight checklist script generated

## Success Criteria

- ✓ All AWS credentials valid and permissions sufficient
- ✓ All local tools installed with correct versions
- ✓ Environment variables configured correctly
- ✓ Project structure complete and valid
- ✓ Pre-flight check script runs without errors
- ✓ Git repository clean and deployment branch created

## Next Steps

→ **Proceed to Phase 2: Infrastructure Setup**
- Run: `bash deployment/scripts/pre-flight-check.sh`
- Review: `deployment/PHASE-2-infrastructure-setup.md`
- Execute Terraform plan and apply

## Troubleshooting

| Issue | Solution |
|-------|----------|
| AWS credentials not found | Run `aws configure` with valid credentials |
| Docker not running | Start Docker daemon: `systemctl start docker` or Docker Desktop app |
| Terraform version too old | Update: `brew upgrade terraform` or download latest |
| Permission denied on scripts | Add execute permission: `chmod +x deployment/scripts/*.sh` |
| Missing Python packages | Install: `pip install -r requirements.txt` |

## References

- [AWS CLI Documentation](https://docs.aws.amazon.com/cli/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Docker Documentation](https://docs.docker.com/)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
