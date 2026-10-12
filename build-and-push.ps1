#!/usr/bin/env pwsh
# Build and push Support Triage Agent Docker image to AWS ECR

$AWS_REGION = "ap-southeast-2"
$AWS_ACCOUNT_ID = "130486712225"
$ECR_REPOSITORY = "support-triage-agent"
$ECR_URI = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
$IMAGE_NAME = "$ECR_URI/$ECR_REPOSITORY"

Write-Host "[*] Starting Docker Build and Push to ECR" -ForegroundColor Cyan

# Check Docker
Write-Host "[*] Checking Docker..." -ForegroundColor Yellow
docker ps > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Docker is not running" -ForegroundColor Red
    exit 1
}
Write-Host "[+] Docker is running" -ForegroundColor Green

# Check AWS
Write-Host "[*] Checking AWS credentials..." -ForegroundColor Yellow
aws sts get-caller-identity --profile support-triage > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] AWS credentials not configured" -ForegroundColor Red
    exit 1
}
Write-Host "[+] AWS credentials valid" -ForegroundColor Green

# Login to ECR
Write-Host "[*] Logging in to ECR..." -ForegroundColor Yellow
aws ecr get-login-password --region $AWS_REGION --profile support-triage | docker login --username AWS --password-stdin $ECR_URI > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] ECR login failed" -ForegroundColor Red
    exit 1
}
Write-Host "[+] ECR login successful" -ForegroundColor Green

# Build image
Write-Host "[*] Building Docker image..." -ForegroundColor Yellow
$commitHash = git rev-parse --short HEAD
$imageTag = $commitHash.Trim()
Write-Host "    Tags: latest, $imageTag" -ForegroundColor Cyan

docker build --tag "$IMAGE_NAME`:latest" --tag "$IMAGE_NAME`:$imageTag" .
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Docker build failed" -ForegroundColor Red
    exit 1
}
Write-Host "[+] Build successful" -ForegroundColor Green

# Push to ECR
Write-Host "[*] Pushing to ECR..." -ForegroundColor Yellow
docker push "$IMAGE_NAME`:latest"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Push failed" -ForegroundColor Red
    exit 1
}
docker push "$IMAGE_NAME`:$imageTag"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Push failed" -ForegroundColor Red
    exit 1
}
Write-Host "[+] Push successful" -ForegroundColor Green

# Update ECS
Write-Host "[*] Updating ECS service..." -ForegroundColor Yellow
aws ecs update-service --cluster support-triage-agent-cluster --service support-triage-agent-service --force-new-deployment --region $AWS_REGION --profile support-triage > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[+] ECS service updated" -ForegroundColor Green
}

# Summary
Write-Host ""
Write-Host "[+] Build and Push Complete!" -ForegroundColor Green
Write-Host "    Image: $IMAGE_NAME`:$imageTag" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  Check logs: aws logs tail /ecs/support-triage-agent --follow --region ap-southeast-2 --profile support-triage" -ForegroundColor Cyan
Write-Host ""
