#!/usr/bin/env pwsh
# Alternative: Build using Docker through WSL2 or direct docker daemon

$AWS_REGION = "ap-southeast-2"
$AWS_ACCOUNT_ID = "130486712225"
$ECR_REPOSITORY = "support-triage-agent"
$ECR_URI = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
$IMAGE_NAME = "$ECR_URI/$ECR_REPOSITORY"

Write-Host "[*] Docker Build & Push via WSL/Docker CLI" -ForegroundColor Cyan

# Try to find docker in common locations
$dockerPaths = @(
    "C:\Program Files\Docker\Docker\resources\bin\docker.exe",
    "$env:USERPROFILE\AppData\Local\Docker\Docker\resources\bin\docker.exe",
    "C:\Program Files\Docker Desktop\resources\bin\docker.exe",
    "wsl.exe"  # Try WSL fallback
)

$dockerExe = $null
foreach ($path in $dockerPaths) {
    if (Test-Path $path) {
        $dockerExe = $path
        break
    }
}

if ($null -eq $dockerExe) {
    Write-Host "[X] Docker not found in standard locations" -ForegroundColor Red
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "1. Install Docker Desktop from https://www.docker.com/products/docker-desktop" -ForegroundColor Cyan
    Write-Host "2. Or, use AWS CodeBuild (cloud-based): .\build-with-codebuild.ps1" -ForegroundColor Cyan
    exit 1
}

Write-Host "[+] Docker found at: $dockerExe" -ForegroundColor Green

# Create a wrapper function
$docker = if ($dockerExe -eq "wsl.exe") {
    { wsl.exe docker $args }
} else {
    { & $dockerExe $args }
}

# Login to ECR
Write-Host "[*] Logging in to ECR..." -ForegroundColor Yellow
aws ecr get-login-password --region $AWS_REGION --profile support-triage | & $docker login --username AWS --password-stdin $ECR_URI
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] ECR login failed" -ForegroundColor Red
    exit 1
}
Write-Host "[+] ECR login successful" -ForegroundColor Green

# Build image
Write-Host "[*] Building Docker image..." -ForegroundColor Yellow
$commitHash = (git rev-parse --short HEAD).Trim()
Write-Host "    Tags: latest, $commitHash" -ForegroundColor Cyan

& $docker build --tag "$IMAGE_NAME`:latest" --tag "$IMAGE_NAME`:$commitHash" .
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Docker build failed" -ForegroundColor Red
    exit 1
}
Write-Host "[+] Build successful" -ForegroundColor Green

# Push to ECR
Write-Host "[*] Pushing to ECR..." -ForegroundColor Yellow
& $docker push "$IMAGE_NAME`:latest"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Push failed" -ForegroundColor Red
    exit 1
}
& $docker push "$IMAGE_NAME`:$commitHash"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Push failed" -ForegroundColor Red
    exit 1
}
Write-Host "[+] Push successful" -ForegroundColor Green

# Update ECS
Write-Host "[*] Updating ECS service..." -ForegroundColor Yellow
aws ecs update-service --cluster support-triage-agent-cluster --service support-triage-agent-service --force-new-deployment --region $AWS_REGION --profile support-triage > $null 2>&1
Write-Host "[+] ECS service updated" -ForegroundColor Green

Write-Host ""
Write-Host "[+] Build and Deploy Complete!" -ForegroundColor Green
Write-Host "    Image: $IMAGE_NAME`:$commitHash" -ForegroundColor Cyan
Write-Host ""
