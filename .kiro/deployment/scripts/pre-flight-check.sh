#!/bin/bash
# Pre-Flight Validation Script
# Purpose: Verify all prerequisites before deployment
# Exit Codes: 0=Success, 1=Critical failure, 2=Warning

set -e

echo "╔════════════════════════════════════════════╗"
echo "║  Pre-Flight Deployment Checklist           ║"
echo "║  Support Triage Agent - Production Deploy  ║"
echo "╚════════════════════════════════════════════╝"
echo ""

WARNINGS=0
ERRORS=0
PASSED=0

# Helper functions
check_command() {
  local name=$1
  local cmd=$2
  
  if command -v $cmd &> /dev/null; then
    local version=$($cmd --version 2>&1 | head -n1)
    echo "✓ $name installed: $version"
    ((PASSED++))
    return 0
  else
    echo "✗ $name NOT installed"
    ((ERRORS++))
    return 1
  fi
}

check_file() {
  local name=$1
  local path=$2
  
  if [ -f "$path" ]; then
    echo "✓ $name found"
    ((PASSED++))
    return 0
  else
    echo "✗ $name NOT found: $path"
    ((ERRORS++))
    return 1
  fi
}

check_aws_credentials() {
  if aws sts get-caller-identity &> /dev/null; then
    local account=$(aws sts get-caller-identity --query 'Account' --output text)
    local arn=$(aws sts get-caller-identity --query 'Arn' --output text)
    echo "✓ AWS credentials valid (Account: $account)"
    ((PASSED++))
    return 0
  else
    echo "✗ AWS credentials invalid or not configured"
    echo "  Run: aws configure"
    ((ERRORS++))
    return 1
  fi
}

check_aws_permissions() {
  local services=("ecs" "rds" "elasticache" "ec2" "ecr" "cloudwatch" "secretsmanager")
  local missing=0
  
  for service in "${services[@]}"; do
    if aws $service describe-* &> /dev/null 2>&1; then
      :
    else
      echo "  ⚠ May lack permissions for: $service"
      ((missing++))
    fi
  done
  
  if [ $missing -eq 0 ]; then
    echo "✓ AWS permissions appear sufficient"
    ((PASSED++))
  else
    echo "⚠ Warning: Some AWS permissions may be missing"
    ((WARNINGS++))
  fi
}

check_git_status() {
  if [ ! -d ".git" ]; then
    echo "✗ Not a git repository"
    ((ERRORS++))
    return 1
  fi
  
  if git status &> /dev/null; then
    local dirty=$(git status --short | wc -l)
    if [ $dirty -eq 0 ]; then
      echo "✓ Git repository clean"
      ((PASSED++))
      return 0
    else
      echo "✗ Git repository has uncommitted changes ($dirty files)"
      ((ERRORS++))
      return 1
    fi
  fi
}

check_environment_config() {
  if [ -f ".env.production" ]; then
    local required_vars=("AWS_REGION" "AWS_ACCOUNT_ID" "ENVIRONMENT")
    local missing=0
    
    for var in "${required_vars[@]}"; do
      if grep -q "^$var=" .env.production; then
        :
      else
        echo "  Missing: $var"
        ((missing++))
      fi
    done
    
    if [ $missing -eq 0 ]; then
      echo "✓ .env.production configured with required variables"
      ((PASSED++))
      return 0
    else
      echo "✗ .env.production missing $missing required variables"
      ((ERRORS++))
      return 1
    fi
  else
    echo "✗ .env.production not found"
    echo "  Create with: cp deployment/.env.production.template .env.production"
    ((ERRORS++))
    return 1
  fi
}

check_docker_daemon() {
  if docker info &> /dev/null; then
    local version=$(docker --version)
    echo "✓ Docker daemon running: $version"
    ((PASSED++))
    return 0
  else
    echo "✗ Docker daemon not running"
    echo "  Start with: docker daemon or Docker Desktop"
    ((ERRORS++))
    return 1
  fi
}

check_project_structure() {
  local required_dirs=("services/triage-api" "services/triage-worker" "services/triage-console" ".kiro/deployment")
  local missing=0
  
  for dir in "${required_dirs[@]}"; do
    if [ ! -d "$dir" ]; then
      echo "  Missing: $dir"
      ((missing++))
    fi
  done
  
  if [ $missing -eq 0 ]; then
    echo "✓ Project structure valid"
    ((PASSED++))
    return 0
  else
    echo "✗ Project structure missing $missing directories"
    ((ERRORS++))
    return 1
  fi
}

check_python_environment() {
  if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 not installed"
    ((ERRORS++))
    return 1
  fi
  
  local py_version=$(python3 --version 2>&1)
  echo "✓ Python installed: $py_version"
  
  if [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
    echo "✓ Python requirements file found"
    ((PASSED++))
    return 0
  else
    echo "⚠ No Python requirements file found"
    ((WARNINGS++))
    return 1
  fi
}

check_terraform() {
  if ! command -v terraform &> /dev/null; then
    echo "✗ Terraform not installed"
    ((ERRORS++))
    return 1
  fi
  
  local tf_version=$(terraform --version)
  echo "✓ Terraform installed: $tf_version"
  ((PASSED++))
  return 0
}

check_terraform_files() {
  if [ -d "terraform" ] && [ -f "terraform/main.tf" ]; then
    echo "✓ Terraform configuration found"
    
    # Check terraform syntax
    if terraform validate &> /dev/null; then
      echo "✓ Terraform configuration valid"
      ((PASSED++))
      return 0
    else
      echo "✗ Terraform configuration invalid"
      terraform validate
      ((ERRORS++))
      return 1
    fi
  else
    echo "⚠ Terraform configuration not found or incomplete"
    ((WARNINGS++))
  fi
}

# Run all checks
echo "1. Checking Tools Installation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_command "Docker" "docker"
check_command "AWS CLI" "aws"
check_command "Terraform" "terraform"
check_command "Git" "git"
check_command "jq" "jq"
check_command "curl" "curl"
echo ""

echo "2. Checking AWS Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_aws_credentials
check_aws_permissions
echo ""

echo "3. Checking Project Structure"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_project_structure
check_file "Dockerfile" "Dockerfile"
check_file "docker-compose.yml" "docker-compose.yml"
check_file "pyproject.toml" "pyproject.toml"
echo ""

echo "4. Checking Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_environment_config
check_terraform_files
echo ""

echo "5. Checking Deployment Prerequisites"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_docker_daemon
check_git_status
check_python_environment
echo ""

# Summary
echo "╔════════════════════════════════════════════╗"
echo "║  Pre-Flight Checklist Summary              ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "✓ Passed:  $PASSED"
echo "⚠ Warnings: $WARNINGS"
echo "✗ Errors:  $ERRORS"
echo ""

if [ $ERRORS -eq 0 ]; then
  echo "✓ Pre-flight check PASSED - Ready for deployment"
  echo ""
  echo "Next steps:"
  echo "  1. Review .env.production configuration"
  echo "  2. Run: bash deployment/scripts/build-images.sh"
  echo "  3. Run: bash deployment/scripts/deploy-staging.sh v1.0"
  echo ""
  exit 0
else
  echo "✗ Pre-flight check FAILED - Fix errors before proceeding"
  echo ""
  echo "Required fixes:"
  if ! command -v docker &> /dev/null; then
    echo "  - Install Docker: https://docs.docker.com/get-docker/"
  fi
  if ! command -v aws &> /dev/null; then
    echo "  - Install AWS CLI: https://aws.amazon.com/cli/"
  fi
  if ! command -v terraform &> /dev/null; then
    echo "  - Install Terraform: https://www.terraform.io/downloads"
  fi
  echo ""
  exit 1
fi
