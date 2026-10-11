# Phase 3: Docker Build & Registry

**Estimated Time:** 45-60 minutes  
**Status:** Containerization & Image Management Phase  
**Last Updated:** 2024

## Overview

Phase 3 builds Docker container images for three services (triage-api, triage-worker, triage-console) and pushes them to AWS ECR (Elastic Container Registry) for use in ECS deployment.

## Architecture

```
┌─────────────────────────────────────────────┐
│         Local Docker Build                  │
├─────────────────────────────────────────────┤
│  Dockerfile.api      → triage-api:v1.0      │
│  Dockerfile.worker   → triage-worker:v1.0   │
│  Dockerfile.console  → triage-console:v1.0  │
└──────────────┬────────────────────────────┘
               │ Docker push
               ▼
┌─────────────────────────────────────────────┐
│   AWS ECR (Elastic Container Registry)      │
├─────────────────────────────────────────────┤
│  123456789012.dkr.ecr.us-east-1.            │
│  amazonaws.com/support-triage/               │
│  ├── triage-api:v1.0                        │
│  ├── triage-api:latest                      │
│  ├── triage-worker:v1.0                     │
│  ├── triage-worker:latest                   │
│  ├── triage-console:v1.0                    │
│  └── triage-console:latest                  │
└─────────────────────────────────────────────┘
```

## 1. Create ECR Repositories

### Terraform Configuration

```hcl
# terraform/ecr.tf
resource "aws_ecr_repository" "triage_api" {
  name                 = "support-triage/triage-api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = "triage-api-registry"
    Environment = "production"
  }
}

resource "aws_ecr_repository" "triage_worker" {
  name                 = "support-triage/triage-worker"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "triage-worker-registry"
    Environment = "production"
  }
}

resource "aws_ecr_repository" "triage_console" {
  name                 = "support-triage/triage-console"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "triage-console-registry"
    Environment = "production"
  }
}

# Lifecycle policy to keep only last 10 images
resource "aws_ecr_lifecycle_policy" "main" {
  repository = aws_ecr_repository.triage_api.name

  lifecycle_policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus     = "any"
        countType     = "imageCountMoreThan"
        countNumber   = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

output "ecr_api_repository_url" {
  value = aws_ecr_repository.triage_api.repository_url
}

output "ecr_worker_repository_url" {
  value = aws_ecr_repository.triage_worker.repository_url
}

output "ecr_console_repository_url" {
  value = aws_ecr_repository.triage_console.repository_url
}
```

### Deploy ECR Repositories

```bash
# Apply Terraform
terraform apply -target=aws_ecr_repository.triage_api \
                -target=aws_ecr_repository.triage_worker \
                -target=aws_ecr_repository.triage_console

# Get repository URLs
TRIAGE_API_REPO=$(terraform output -raw ecr_api_repository_url)
TRIAGE_WORKER_REPO=$(terraform output -raw ecr_worker_repository_url)
TRIAGE_CONSOLE_REPO=$(terraform output -raw ecr_console_repository_url)

# Verify repositories created
aws ecr describe-repositories --repository-names \
  support-triage/triage-api \
  support-triage/triage-worker \
  support-triage/triage-console
```

## 2. Local Docker Build

### Dockerfiles

**services/triage-api/Dockerfile**
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/triage-api/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/triage-api/ .
COPY packages/triage-core/ ../packages/triage-core/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run Uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**services/triage-worker/Dockerfile**
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/triage-worker/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/triage-worker/ .
COPY packages/triage-core/ ../packages/triage-core/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Run Celery worker
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "--concurrency=4"]
```

**services/triage-console/Dockerfile**
```dockerfile
FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY services/triage-console/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy application code
COPY services/triage-console/ .

# Build frontend
RUN npm run build

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:3000 || exit 1

# Start application
CMD ["npm", "start"]
```

### Build Script

**deployment/scripts/build-images.sh**
```bash
#!/bin/bash
set -e

echo "=== Building Docker Images ==="

# Configuration
APP_NAME="support-triage"
VERSION=${1:-v1.0}
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
GIT_SHA=$(git rev-parse --short HEAD)
TAG="${VERSION}-${GIT_SHA}"

# Load environment
if [ -f ".env.production" ]; then
  source .env.production
fi

AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-}

if [ -z "$AWS_ACCOUNT_ID" ]; then
  echo "Error: AWS_ACCOUNT_ID not set"
  exit 1
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Functions
build_image() {
  local service=$1
  local dockerfile=$2
  local context=$3
  
  echo "Building ${service}..."
  
  docker build \
    -f "$dockerfile" \
    -t "${APP_NAME}/${service}:${TAG}" \
    -t "${APP_NAME}/${service}:latest" \
    --build-arg BUILD_DATE="$BUILD_DATE" \
    --build-arg VCS_REF="$GIT_SHA" \
    --build-arg VERSION="$VERSION" \
    "$context"
  
  echo "✓ Built ${service}:${TAG}"
}

# Build all images
build_image "triage-api" \
  "services/triage-api/Dockerfile" \
  "."

build_image "triage-worker" \
  "services/triage-worker/Dockerfile" \
  "."

build_image "triage-console" \
  "services/triage-console/Dockerfile" \
  "."

# Verify builds
echo ""
echo "=== Image Verification ==="
docker images | grep "support-triage"

# Run basic tests (optional)
echo ""
echo "=== Running Container Tests ==="

# Test API image
echo "Testing triage-api image..."
docker run --rm "${APP_NAME}/triage-api:${TAG}" python -c "import main; print('✓ API module imports successfully')"

# Test Worker image
echo "Testing triage-worker image..."
docker run --rm "${APP_NAME}/triage-worker:${TAG}" python -c "import tasks; print('✓ Worker module imports successfully')"

echo ""
echo "=== Build Complete ==="
echo "Images built with tag: ${TAG}"
echo "Ready for ECR push"
```

### Run Local Build

```bash
# Make script executable
chmod +x deployment/scripts/build-images.sh

# Build images
bash deployment/scripts/build-images.sh v1.0

# Verify build success
docker images | grep support-triage
# Expected output:
# support-triage/triage-api        latest         sha256:abc123...
# support-triage/triage-api        v1.0-abc123    sha256:abc123...
# support-triage/triage-worker     latest         sha256:def456...
# support-triage/triage-worker     v1.0-def456    sha256:def456...
# support-triage/triage-console    latest         sha256:ghi789...
# support-triage/triage-console    v1.0-ghi789    sha256:ghi789...
```

## 3. Push to ECR

### Authentication

```bash
# Authenticate Docker with ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.us-east-1.amazonaws.com

# Expected output: "Login Succeeded"

# Verify authentication
docker pull 123456789012.dkr.ecr.us-east-1.amazonaws.com/support-triage/triage-api:latest 2>&1 | \
  head -1
# Expected: Either pull succeeds or "image not found" (not "no basic auth credentials")
```

### Push Script

**deployment/scripts/push-to-ecr.sh**
```bash
#!/bin/bash
set -e

echo "=== Pushing Images to ECR ==="

# Configuration
APP_NAME="support-triage"
VERSION=${1:-v1.0}
GIT_SHA=$(git rev-parse --short HEAD)
TAG="${VERSION}-${GIT_SHA}"

# Load environment
source .env.production

AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-}
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Authenticate with ECR
echo "Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Function to push image
push_image() {
  local service=$1
  local local_image="${APP_NAME}/${service}:${TAG}"
  local ecr_image="${ECR_REGISTRY}/${APP_NAME}/${service}:${TAG}"
  local ecr_latest="${ECR_REGISTRY}/${APP_NAME}/${service}:latest"
  
  echo "Pushing ${service}..."
  
  # Tag for ECR
  docker tag "$local_image" "$ecr_image"
  docker tag "$local_image" "$ecr_latest"
  
  # Push both tags
  docker push "$ecr_image"
  docker push "$ecr_latest"
  
  echo "✓ Pushed ${service}"
}

# Push all images
push_image "triage-api"
push_image "triage-worker"
push_image "triage-console"

echo ""
echo "=== ECR Push Complete ==="
echo "ECR Registry: $ECR_REGISTRY"
echo ""

# List pushed images
echo "Pushed images:"
aws ecr list-images --repository-name support-triage/triage-api \
  --query 'imageIds[*].[imageTag]' --output table

aws ecr list-images --repository-name support-triage/triage-worker \
  --query 'imageIds[*].[imageTag]' --output table

aws ecr list-images --repository-name support-triage/triage-console \
  --query 'imageIds[*].[imageTag]' --output table
```

### Execute Push

```bash
# Make script executable
chmod +x deployment/scripts/push-to-ecr.sh

# Push images to ECR
bash deployment/scripts/push-to-ecr.sh v1.0

# Verify push
aws ecr list-images --repository-name support-triage/triage-api
# Expected: images tagged with v1.0 and latest
```

## 4. Image Tagging Strategy

### Tagging Convention

```
Format: <version>-<git-sha>[-<build-number>]

Examples:
  v1.0-abc1234          (Release version)
  v1.0-abc1234-build.5  (Build run within version)
  latest                (Always points to most recent)
  staging               (Points to staging branch builds)
  main                  (Points to main branch builds)
```

### Tag Management

```bash
# Retag image as stable
docker tag support-triage/triage-api:v1.0-abc1234 \
            support-triage/triage-api:stable

# Push stable tag
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/support-triage/triage-api:stable

# List all tags for image
aws ecr list-images --repository-name support-triage/triage-api \
  --query 'sort_by(imageIds, &imagePushedAt)[-10:]' \
  --output table
```

## 5. Image Security

### Security Scanning

```bash
# Enable ECR image scanning (in terraform/ecr.tf)
image_scanning_configuration {
  scan_on_push = true
}

# Check scan results
aws ecr describe-image-scan-findings \
  --repository-name support-triage/triage-api \
  --image-id imageTag=v1.0-abc1234
```

### Best Practices

**Dockerfile Best Practices:**
```dockerfile
# ✓ Use specific base image versions (not :latest)
FROM python:3.10-slim

# ✓ Use non-root user
USER appuser

# ✓ Multi-stage builds for smaller images
FROM python:3.10-slim as build
RUN pip install -r requirements.txt
FROM python:3.10-slim
COPY --from=build /app /app

# ✗ Don't include secrets in images
# ✗ Don't use :latest tags
# ✗ Don't run as root
```

### Container Image Vulnerability Scanning

```bash
# Use Trivy for local scanning
trivy image support-triage/triage-api:v1.0

# Output format:
# Total: 5 vulnerabilities (2 CRITICAL, 3 HIGH)
# ...recommendations...
```

## 6. Registry Cleanup

### Lifecycle Policies

```hcl
resource "aws_ecr_lifecycle_policy" "cleanup" {
  repository = aws_ecr_repository.triage_api.name

  lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only last 20 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v"]
          countType     = "imageCountMoreThan"
          countNumber   = 20
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
```

### Manual Cleanup

```bash
# Delete old images
aws ecr batch-delete-image \
  --repository-name support-triage/triage-api \
  --image-ids imageTag=old-version

# Delete entire repository (WARNING: destructive)
aws ecr delete-repository \
  --repository-name support-triage/triage-api \
  --force
```

## Success Criteria

- ✓ Three ECR repositories created (triage-api, triage-worker, triage-console)
- ✓ Docker images built successfully locally
- ✓ All images run without errors
- ✓ Images pushed to ECR with proper tagging
- ✓ Images scanned for vulnerabilities
- ✓ Lifecycle policies configured
- ✓ Image can be pulled from ECR and run

## Verification Checklist

```bash
#!/bin/bash
echo "=== Docker Build & Registry Verification ==="

# Check local images
echo "1. Checking local Docker images..."
docker images | grep support-triage || echo "✗ No local images found"

# Check ECR repositories
echo "2. Checking ECR repositories..."
aws ecr describe-repositories --query 'repositories[*].repositoryName'

# Check pushed images
echo "3. Checking pushed images..."
for repo in triage-api triage-worker triage-console; do
  count=$(aws ecr list-images --repository-name support-triage/$repo --query 'length(imageIds)' --output text)
  echo "  support-triage/$repo: $count images"
done

# Check image scans
echo "4. Checking image scan results..."
aws ecr describe-image-scan-findings \
  --repository-name support-triage/triage-api \
  --image-id imageTag=latest \
  --query 'imageScanFindings.findingSeverityCounts'
```

## Next Steps

→ **Proceed to Phase 4: Staging Deployment**
- Deploy images to staging environment
- Run smoke tests and load tests
- Get design partner validation

## References

- [ECR Documentation](https://docs.aws.amazon.com/AmazonECR/)
- [Docker Image Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Trivy Vulnerability Scanner](https://github.com/aquasecurity/trivy)
- [Container Security Scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html)
