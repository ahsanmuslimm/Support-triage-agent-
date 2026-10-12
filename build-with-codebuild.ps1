#!/usr/bin/env pwsh
# Build and push Support Triage Agent using AWS CodeBuild (cloud-based, no local Docker needed)

$AWS_REGION = "ap-southeast-2"
$AWS_PROFILE = "support-triage"
$PROJECT_NAME = "support-triage-build"

Write-Host "[*] Starting Docker Build with AWS CodeBuild" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check AWS credentials
Write-Host "[*] Checking AWS credentials..." -ForegroundColor Yellow
aws sts get-caller-identity --profile $AWS_PROFILE > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] AWS credentials not configured" -ForegroundColor Red
    exit 1
}
Write-Host "[+] AWS credentials valid" -ForegroundColor Green

# Step 2: Check if buildspec.yml exists
Write-Host "[*] Checking buildspec.yml..." -ForegroundColor Yellow
if (-not (Test-Path "buildspec.yml")) {
    Write-Host "[X] buildspec.yml not found" -ForegroundColor Red
    exit 1
}
Write-Host "[+] buildspec.yml found" -ForegroundColor Green

# Step 3: Commit current changes
Write-Host "[*] Committing Dockerfile..." -ForegroundColor Yellow
git add Dockerfile buildspec.yml 2>&1 | Out-Null
git commit -m "Add Docker files for ECR deployment" 2>&1 | Out-Null
git push 2>&1 | Out-Null
Write-Host "[+] Changes committed to GitHub" -ForegroundColor Green

# Step 4: Check if build project exists
Write-Host "[*] Checking CodeBuild project..." -ForegroundColor Yellow
$projectExists = aws codebuild batch-get-projects --names $PROJECT_NAME --region $AWS_REGION --profile $AWS_PROFILE 2>&1 | ConvertFrom-Json
if ($projectExists.projects.Length -eq 0) {
    Write-Host "[*] Creating CodeBuild project..." -ForegroundColor Yellow
    
    # Create build project
    aws codebuild create-project `
        --name $PROJECT_NAME `
        --source type=GITHUB,location=https://github.com/ahsanmuslimm/Support-triage-agent-.git,gitCloneDepth=1 `
        --service-role arn:aws:iam::130486712225:role/codebuild-role `
        --environment type=LINUX_GPU_CONTAINER,image=aws/codebuild/standard:7.0,computeType=BUILD_GENERAL1_SMALL,environmentVariables="[{name=AWS_DEFAULT_REGION,value=$AWS_REGION},{name=AWS_ACCOUNT_ID,value=130486712225},{name=IMAGE_REPO_NAME,value=support-triage-agent}]" `
        --artifacts type=NO_ARTIFACTS `
        --region $AWS_REGION `
        --profile $AWS_PROFILE > $null 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Failed to create CodeBuild project" -ForegroundColor Red
        exit 1
    }
    Write-Host "[+] CodeBuild project created" -ForegroundColor Green
} else {
    Write-Host "[+] CodeBuild project already exists" -ForegroundColor Green
}

# Step 5: Start the build
Write-Host "[*] Starting CodeBuild..." -ForegroundColor Yellow
$buildResult = aws codebuild start-build `
    --project-name $PROJECT_NAME `
    --region $AWS_REGION `
    --profile $AWS_PROFILE 2>&1 | ConvertFrom-Json

$buildId = $buildResult.build.id
Write-Host "[+] Build started: $buildId" -ForegroundColor Green

# Step 6: Monitor build
Write-Host ""
Write-Host "[*] Monitoring build progress..." -ForegroundColor Cyan
$buildStatus = "IN_PROGRESS"
$maxWait = 600  # 10 minutes

while ($buildStatus -eq "IN_PROGRESS" -and $maxWait -gt 0) {
    Start-Sleep -Seconds 10
    $maxWait -= 10
    
    $build = aws codebuild batch-get-builds --ids $buildId --region $AWS_REGION --profile $AWS_PROFILE 2>&1 | ConvertFrom-Json
    $buildStatus = $build.builds[0].buildStatus
    $phase = $build.builds[0].currentPhase
    
    Write-Host "    Phase: $phase | Status: $buildStatus" -ForegroundColor Cyan
}

if ($buildStatus -eq "SUCCEEDED") {
    Write-Host ""
    Write-Host "[+] Build Successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "[+] Image pushed to ECR" -ForegroundColor Green
    Write-Host "    Repository: support-triage-agent" -ForegroundColor Cyan
    Write-Host "    Region: $AWS_REGION" -ForegroundColor Cyan
}
else {
    Write-Host ""
    Write-Host "[X] Build Failed: $buildStatus" -ForegroundColor Red
    Write-Host ""
    Write-Host "View logs at:" -ForegroundColor Yellow
    Write-Host "    aws codebuild batch-get-builds --ids $buildId --region $AWS_REGION --profile $AWS_PROFILE" -ForegroundColor Cyan
    exit 1
}

# Step 7: Update ECS Service
Write-Host "[*] Updating ECS service..." -ForegroundColor Yellow
aws ecs update-service `
    --cluster support-triage-agent-cluster `
    --service support-triage-agent-service `
    --force-new-deployment `
    --region $AWS_REGION `
    --profile $AWS_PROFILE > $null 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[+] ECS service updated" -ForegroundColor Green
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "[+] Build and Deploy Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Wait 1-2 minutes for ECS to deploy" -ForegroundColor Cyan
Write-Host "  2. Check logs: aws logs tail /ecs/support-triage-agent --follow --region $AWS_REGION --profile $AWS_PROFILE" -ForegroundColor Cyan
Write-Host ""
