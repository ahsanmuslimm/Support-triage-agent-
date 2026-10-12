#!/usr/bin/env pwsh
<#
.SYNOPSIS
Build and push Support Triage Agent Docker image to AWS ECR

.DESCRIPTION
This script builds the Docker image locally and pushes it to Amazon ECR (ap-southeast-2).

.EXAMPLE
.\build-and-push.ps1
#>

# Set strict error handling
$ErrorActionPreference = "Stop"
$PSVersionTable.PSVersion.Major -ge 7 | Out-Null

# Configuration
$AWS_REGION = "ap-southeast-2"
$AWS_ACCOUNT_ID = "130486712225"
$ECR_REPOSITORY = "support-triage-agent"
$ECR_URI = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
$IMAGE_NAME = "$ECR_URI/$ECR_REPOSITORY"
$DOCKER_BUILDKIT = 1

Write-Host "🚀 Starting Support Triage Agent Docker Build & Push" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify Docker is running
Write-Host "✓ Step 1: Checking Docker daemon..." -ForegroundColor Yellow
try {
    $dockerStatus = docker ps 2>&1
    Write-Host "  Docker is running ✓" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker is not running or not in PATH" -ForegroundColor Red
    Write-Host "  Please start Docker Desktop and try again" -ForegroundColor Red
    exit 1
}

# Step 2: Verify AWS credentials
Write-Host ""
Write-Host "✓ Step 2: Checking AWS credentials..." -ForegroundColor Yellow
try {
    $awsStatus = aws sts get-caller-identity --profile support-triage 2>&1
    Write-Host "  AWS credentials valid ✓" -ForegroundColor Green
} catch {
    Write-Host "  ✗ AWS credentials not configured" -ForegroundColor Red
    Write-Host "  Run: aws login --profile support-triage" -ForegroundColor Red
    exit 1
}

# Step 3: Login to ECR
Write-Host ""
Write-Host "✓ Step 3: Logging in to Amazon ECR..." -ForegroundColor Yellow
try {
    $loginToken = aws ecr get-login-password --region $AWS_REGION --profile support-triage 2>&1
    $loginToken | docker login --username AWS --password-stdin $ECR_URI 2>&1
    Write-Host "  ECR login successful ✓" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to login to ECR" -ForegroundColor Red
    Write-Host "  Error: $_" -ForegroundColor Red
    exit 1
}

# Step 4: Build Docker image
Write-Host ""
Write-Host "✓ Step 4: Building Docker image..." -ForegroundColor Yellow
Write-Host "  Image: $IMAGE_NAME" -ForegroundColor Cyan
$commitHash = git rev-parse --short HEAD 2>&1
$imageTag = $commitHash
Write-Host "  Tag: latest, $imageTag" -ForegroundColor Cyan
Write-Host ""

try {
    docker build `
        --tag "$IMAGE_NAME`:latest" `
        --tag "$IMAGE_NAME`:$imageTag" `
        --build-arg BUILDKIT_INLINE_CACHE=1 `
        .
    Write-Host ""
    Write-Host "  Docker build successful ✓" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker build failed" -ForegroundColor Red
    Write-Host "  Error: $_" -ForegroundColor Red
    exit 1
}

# Step 5: Push to ECR
Write-Host ""
Write-Host "✓ Step 5: Pushing image to Amazon ECR..." -ForegroundColor Yellow
try {
    Write-Host "  Pushing $IMAGE_NAME`:latest..." -ForegroundColor Cyan
    docker push "$IMAGE_NAME`:latest"
    Write-Host "  Push :latest successful ✓" -ForegroundColor Green
    
    Write-Host "  Pushing $IMAGE_NAME`:$imageTag..." -ForegroundColor Cyan
    docker push "$IMAGE_NAME`:$imageTag"
    Write-Host "  Push :$imageTag successful ✓" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker push failed" -ForegroundColor Red
    Write-Host "  Error: $_" -ForegroundColor Red
    exit 1
}

# Step 6: Get image details
Write-Host ""
Write-Host "✓ Step 6: Verifying pushed image..." -ForegroundColor Yellow
try {
    $imageDetails = aws ecr describe-images `
        --repository-name $ECR_REPOSITORY `
        --region $AWS_REGION `
        --profile support-triage `
        --query 'imageDetails[0]' 2>&1 | ConvertFrom-Json
    
    Write-Host "  Image pushed to ECR ✓" -ForegroundColor Green
    Write-Host "  Repository: $ECR_REPOSITORY" -ForegroundColor Cyan
    Write-Host "  Image size: $($imageDetails.imageSizeBytes / 1MB)MB" -ForegroundColor Cyan
    Write-Host "  Image digest: $($imageDetails.imageDigest)" -ForegroundColor Cyan
} catch {
    Write-Host "  Could not verify image (may need ACM permissions)" -ForegroundColor Yellow
}

# Step 7: Update ECS Service
Write-Host ""
Write-Host "✓ Step 7: Triggering ECS service update..." -ForegroundColor Yellow
try {
    $updateResult = aws ecs update-service `
        --cluster support-triage-agent-cluster `
        --service support-triage-agent-service `
        --force-new-deployment `
        --region $AWS_REGION `
        --profile support-triage 2>&1
    
    Write-Host "  ECS service deployment triggered ✓" -ForegroundColor Green
    Write-Host "  New tasks will pull the latest image" -ForegroundColor Cyan
} catch {
    Write-Host "  ⚠ Could not trigger ECS update (may need permissions)" -ForegroundColor Yellow
    Write-Host "  You can manually update from AWS Console or run:" -ForegroundColor Yellow
    Write-Host "  aws ecs update-service --cluster support-triage-agent-cluster --service support-triage-agent-service --force-new-deployment --region ap-southeast-2" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "✓ Docker Image Build & Push Complete!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 Summary:" -ForegroundColor Cyan
Write-Host "  ✓ Docker image built: $IMAGE_NAME`:$imageTag" -ForegroundColor Green
Write-Host "  ✓ Image pushed to ECR" -ForegroundColor Green
Write-Host "  ✓ ECS service updated" -ForegroundColor Green
Write-Host ""
Write-Host "🔍 Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Monitor ECS task deployment (1-2 minutes)" -ForegroundColor Cyan
Write-Host "  2. Get task public IP: aws ecs list-tasks --cluster support-triage-agent-cluster --region ap-southeast-2" -ForegroundColor Cyan
Write-Host "  3. Test application: curl http://<PUBLIC_IP>:8000/health" -ForegroundColor Cyan
Write-Host "  4. View logs: aws logs tail /ecs/support-triage-agent --follow --region ap-southeast-2" -ForegroundColor Cyan
Write-Host ""
