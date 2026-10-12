# Docker Image Build & ECR Push - Deployment Guide

**Status:** Ready to build and push to ECR  
**Date:** October 10, 2026  
**Region:** ap-southeast-2  
**Account:** 130486712225

---

## Summary

Your Support Triage Agent is ready for containerization. All Docker artifacts have been created:

- ✅ Dockerfile (multi-stage: builder + runtime)
- ✅ buildspec.yml (AWS CodeBuild config)
- ✅ Build scripts (local Docker, CodeBuild, alternative paths)
- ✅ Documentation (DOCKER-BUILD-GUIDE.md)
- ✅ All code committed to GitHub

**Next:** Build image and push to ECR, then ECS will auto-deploy new version.

---

## Docker Image Specs

| Item | Value |
|------|-------|
| **Base Image** | python:3.12-slim |
| **Build Stage** | python:3.12 (builder + dependencies) |
| **Runtime Stage** | python:3.12-slim (optimized for size) |
| **Ports** | 8000 (FastAPI) |
| **Memory** | 512 MB (ECS free tier) |
| **CPU** | 256 vCPU (ECS free tier) |
| **Health Check** | GET /health (30s interval) |
| **Startup Command** | `uvicorn services.api.src.triage.api.main:app --host 0.0.0.0 --port 8000` |

---

## Build Approaches

### Option 1: AWS CodeBuild (Recommended ⭐)

**Best for:** Cloud-native, no local setup, free tier, automated

**Why?**
- No local Docker Desktop required
- Runs in AWS (cloud-based)
- Free: 100 build minutes/month
- Automatic ECR push
- Build logs in CloudWatch
- Can be integrated with CodePipeline

**Quick Start:**
```bash
# Via PowerShell:
.\build-with-codebuild.ps1

# Via Bash:
bash setup-codebuild.sh

# Or via AWS Console:
# 1. Go to CodeBuild console
# 2. Create project with buildspec.yml
# 3. Start build
```

**Time:** ~5 minutes build + 1-2 minutes ECS deployment

---

### Option 2: Local Docker Desktop

**Best for:** Testing locally, full control, want to debug

**Requirements:**
- Docker Desktop installed
- Docker in PowerShell PATH (may need restart)

**Steps:**
```powershell
cd "d:\WORKING\PORTFOLIO\FEATURED PROJECTS\Support-triage-agent-"
.\build-and-push.ps1
```

**What it does:**
1. Authenticates to AWS ECR
2. Builds Docker image (256 vCPU / 512 MB)
3. Tags: latest + commit hash
4. Pushes to ECR
5. Updates ECS service

**Time:** ~10-15 minutes build + 1-2 minutes ECS deployment

**Issue:** Docker not in PATH (common after first install)  
**Solution:** Restart PowerShell or use CodeBuild

---

### Option 3: Alternative Docker Paths

**For:** If Docker is installed but in non-standard location

```powershell
.\build-and-push-alt.ps1
```

Searches common Docker Desktop installation paths:
- `C:\Program Files\Docker\Docker\resources\bin\docker.exe`
- `$env:USERPROFILE\AppData\Local\Docker\Docker\resources\bin\docker.exe`
- WSL2 fallback

---

## Step-by-Step: Use CodeBuild (Recommended)

### 1. Via AWS Console (Visual)

1. Open: https://console.aws.amazon.com/codebuild/
2. Click **Create build project**
3. **Project name:** `support-triage-build`
4. **Source:**
   - Provider: GitHub
   - Repository: `https://github.com/ahsanmuslimm/Support-triage-agent-.git`
   - Branch: `main`
   - Buildspec: Use buildspec.yml from repo root ✅
5. **Environment:**
   - Managed image: Ubuntu
   - Runtime: Standard
   - Image: `aws/codebuild/standard:7.0`
   - Compute: `BUILD_GENERAL1_SMALL`
6. **Environment variables:**
   - `AWS_ACCOUNT_ID` = `130486712225`
   - `AWS_DEFAULT_REGION` = `ap-southeast-2`
   - `IMAGE_REPO_NAME` = `support-triage-agent`
7. **Service role:** Create new or use existing
8. Click **Create build project**

Then:
1. Select project: `support-triage-build`
2. Click **Start build**
3. Monitor logs in real-time
4. Build takes ~5 minutes

---

### 2. Via PowerShell Script (Automated)

```powershell
cd "d:\WORKING\PORTFOLIO\FEATURED PROJECTS\Support-triage-agent-"
.\build-with-codebuild.ps1
```

Script will:
1. Check AWS credentials ✓
2. Create CodeBuild project (if not exists) ✓
3. Start build ✓
4. Monitor progress (polls every 10s) ✓
5. Report success/failure ✓
6. Update ECS service ✓

---

### 3. Via Bash (Linux/Mac/WSL)

```bash
bash setup-codebuild.sh
```

Same as PowerShell but for Unix shells.

---

## After Build Completes

### 1. Verify Image in ECR

```bash
aws ecr describe-images \
  --repository-name support-triage-agent \
  --region ap-southeast-2 \
  --profile support-triage \
  --query 'imageDetails[0]'
```

Expected output:
```json
{
  "imageSizeBytes": 2147483648,
  "imageDigest": "sha256:abc123...",
  "registryId": "130486712225",
  "repositoryName": "support-triage-agent",
  "imageTags": ["latest", "e074bdc"]
}
```

### 2. Check ECS Service Status

```bash
aws ecs describe-services \
  --cluster support-triage-agent-cluster \
  --services support-triage-agent-service \
  --region ap-southeast-2 \
  --profile support-triage
```

Wait 1-2 minutes for ECS to:
1. Pull new image from ECR
2. Stop old task
3. Start new task with new image

### 3. Get Task Public IP

```bash
aws ecs list-tasks \
  --cluster support-triage-agent-cluster \
  --region ap-southeast-2 \
  --profile support-triage \
  --query 'taskArns[0]'

# Then get full details:
aws ecs describe-tasks \
  --cluster support-triage-agent-cluster \
  --tasks <TASK_ARN> \
  --region ap-southeast-2 \
  --profile support-triage
```

Look for `publicIp` in the output.

### 4. Test Application

```bash
# Health check
curl http://<PUBLIC_IP>:8000/health

# Should return:
# {"status": "ok", "version": "1.0"}
```

### 5. View Logs

```bash
aws logs tail /ecs/support-triage-agent \
  --follow \
  --region ap-southeast-2 \
  --profile support-triage
```

Or via AWS CloudWatch console: https://console.aws.amazon.com/cloudwatch/

---

## Files Included

| File | Purpose | How to Use |
|------|---------|-----------|
| `Dockerfile` | Container image definition | Used by Docker/CodeBuild |
| `buildspec.yml` | AWS CodeBuild configuration | Used by CodeBuild |
| `build-and-push.ps1` | Local Docker build script | `.\build-and-push.ps1` |
| `build-with-codebuild.ps1` | CodeBuild via script | `.\build-with-codebuild.ps1` |
| `build-and-push-alt.ps1` | Alternative Docker paths | `.\build-and-push-alt.ps1` |
| `setup-codebuild.sh` | CodeBuild setup (Bash) | `bash setup-codebuild.sh` |
| `DOCKER-BUILD-GUIDE.md` | Comprehensive guide | Reference |

---

## Dockerfile Details

Multi-stage build for optimization:

```dockerfile
# Stage 1: Builder
FROM python:3.12
WORKDIR /build
RUN pip install uv
COPY . .
RUN uv sync --frozen

# Stage 2: Runtime (only ~2GB)
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build /app
ENV PATH="/app/.venv/bin:$PATH"
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
EXPOSE 8000
CMD ["uvicorn", "services.api.src.triage.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## ECR Image Location

```
130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent:latest
130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent:<commit-hash>
```

ECS service automatically pulls from: `:latest`

---

## Troubleshooting

### Build Fails with "Docker not found"

**Local Docker approach:**
- Restart PowerShell after Docker Desktop installation
- Or use AWS CodeBuild (recommended)

```powershell
# Restart PowerShell and try again
.\build-and-push.ps1
```

### ECR Push Fails

**Check credentials:**
```bash
aws sts get-caller-identity --profile support-triage
aws login --profile support-triage  # Refresh if expired
```

### ECS Task Not Updating

**Check service:**
```bash
aws ecs describe-services \
  --cluster support-triage-agent-cluster \
  --services support-triage-agent-service \
  --region ap-southeast-2 \
  --profile support-triage
```

**Common issues:**
- Image pull fails → Check ECR image exists
- Task fails to start → Check CloudWatch logs
- Old image still running → Wait 2 minutes, may still be updating

### Can't Access Application

**Check task IP:**
```bash
aws ecs describe-tasks --cluster support-triage-agent-cluster \
  --tasks <TASK_ARN> --region ap-southeast-2 \
  --profile support-triage | grep publicIp
```

**Verify security group allows port 8000:**
```bash
aws ec2 describe-security-groups \
  --region ap-southeast-2 \
  --profile support-triage \
  --filter "Name=group-name,Values=ecs-*"
```

---

## Next Steps (Checklist)

- [ ] Choose build method (Option 1 recommended)
- [ ] Run build (CodeBuild console or script)
- [ ] Monitor build progress (~5 minutes)
- [ ] Verify image in ECR
- [ ] Wait for ECS task to restart (1-2 minutes)
- [ ] Get public IP from ECS task
- [ ] Test health endpoint: `curl http://IP:8000/health`
- [ ] View application logs
- [ ] Deploy to production (when ready)

---

## Cost

**First 12 months (free tier):**
- ECS Fargate: Free (750 hrs/month)
- ECR: $0.10 per GB stored (minimal for 1 image)
- CodeBuild: Free (100 build minutes/month included)
- **Total: ~$0/month** ✅

**After 12 months:**
- ECS: ~$30/month
- ECR: ~$5/month
- CodeBuild: ~$0.005 per build minute
- **Total: ~$35/month**

---

## Summary

Your application is containerized, all build artifacts are ready, and infrastructure is deployed on AWS free tier.

**Recommended next step:**
1. Use AWS CodeBuild (cloud-native, no local Docker)
2. Or restart PowerShell and use local Docker Desktop

**Estimated time to live:** 10-15 minutes

---

**Questions?** See `DOCKER-BUILD-GUIDE.md` for detailed instructions.
