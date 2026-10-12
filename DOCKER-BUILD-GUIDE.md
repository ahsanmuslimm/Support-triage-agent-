# Docker Build & ECR Push Guide

Your Support Triage Agent is ready to be containerized and deployed to AWS ECR. This guide covers two approaches:

---

## Status

- ✅ Dockerfile created
- ✅ buildspec.yml created for AWS CodeBuild
- ✅ All code committed to GitHub
- ⏳ Next: Build image and push to ECR

---

## Option 1: AWS CodeBuild (Recommended - Cloud-based, No Local Docker)

**Benefits:**
- No local Docker installation required
- Runs in AWS (cloud-native)
- Automatically pushes to ECR
- Free for 100 build minutes/month (free tier)
- Works on any machine (Windows, Mac, Linux)

**Steps:**

### Step 1: Verify GitHub Connection
Ensure your AWS CodeBuild can access your GitHub repo:

```bash
# Check credentials
aws sts get-caller-identity --profile support-triage
```

### Step 2: Create CodeBuild Project via AWS Console

Go to: https://console.aws.amazon.com/codebuild/

1. Click **Create project**
2. **Project name:** `support-triage-build`
3. **Description:** Build and push Support Triage Agent image
4. **Source provider:** GitHub
5. **Repository:** `https://github.com/ahsanmuslimm/Support-triage-agent-.git`
6. **Branch:** `main`
7. **Buildspec:** Use buildspec.yml from repo root
8. **Environment:**
   - **Managed image:** Yes
   - **Operating system:** Ubuntu
   - **Runtime:** Standard
   - **Image:** aws/codebuild/standard:7.0
   - **Compute:** build.general1.small
9. **Environment variables:**
   - `AWS_ACCOUNT_ID` = `130486712225`
   - `AWS_DEFAULT_REGION` = `ap-southeast-2`
   - `IMAGE_REPO_NAME` = `support-triage-agent`
10. **Service role:** Create new role
11. Click **Create build project**

### Step 3: Start the Build

In CodeBuild console:
1. Select your project: `support-triage-build`
2. Click **Start build**
3. Confirm source: `main` branch
4. Click **Start build** again

**Build takes ~5 minutes** and will:
- Pull your source code from GitHub
- Build the Docker image
- Push to ECR: `130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent`
- Auto-tag with commit hash

### Step 4: Monitor Build

Watch in CodeBuild console:
- Logs stream in real-time
- Shows each build phase (build, push)
- Logs stored in CloudWatch

### Step 5: Verify Image in ECR

```bash
# List images in ECR
aws ecr describe-images \
  --repository-name support-triage-agent \
  --region ap-southeast-2 \
  --profile support-triage
```

### Step 6: Update ECS Service

Force ECS to pull the new image:

```bash
aws ecs update-service \
  --cluster support-triage-agent-cluster \
  --service support-triage-agent-service \
  --force-new-deployment \
  --region ap-southeast-2 \
  --profile support-triage
```

Task will restart with new image in 1-2 minutes.

---

## Option 2: Local Docker Desktop

**Prerequisites:**
- Docker Desktop installed and running
- Docker in PATH (may need PowerShell restart)

**Steps:**

```powershell
# Navigate to project
cd "d:\WORKING\PORTFOLIO\FEATURED PROJECTS\Support-triage-agent-"

# Run build script
.\build-and-push.ps1
```

The script will:
1. Authenticate to ECR
2. Build Docker image (256vCPU/512MB from Dockerfile)
3. Push to ECR with commit hash tag
4. Trigger ECS deployment

---

## Option 3: Use PowerShell Script with AWS CodeBuild

If you prefer scripting instead of console:

```powershell
.\build-with-codebuild.ps1
```

Script will:
1. Check AWS credentials
2. Create CodeBuild project (if not exists)
3. Start build
4. Monitor progress
5. Update ECS service

---

## Files Provided

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build (builder + runtime) |
| `buildspec.yml` | AWS CodeBuild configuration |
| `build-and-push.ps1` | Local Docker build script |
| `build-and-push-alt.ps1` | Alternative Docker paths |
| `build-with-codebuild.ps1` | AWS CodeBuild via script |

---

## Docker Image Details

**Multi-stage build optimizes for size:**

```dockerfile
# Stage 1: Builder
- Python 3.12
- Build dependencies
- Install project with `uv sync`

# Stage 2: Runtime (only copied from Stage 1)
- Python 3.12-slim
- Runtime dependencies only
- Virtual environment from builder
```

**Final image size:** ~2GB (includes model weights)

**Ports:** 8000 (FastAPI)

**Health check:** `GET /health`

---

## Troubleshooting

### Docker not in PATH
- Restart PowerShell after Docker Desktop installation
- Or use AWS CodeBuild (no local Docker needed)

### ECR Login Failed
```bash
# Re-authenticate
aws login --profile support-triage
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 130486712225.dkr.ecr.ap-southeast-2.amazonaws.com
```

### Build Stuck
- Check CloudWatch logs: `/ecs/support-triage-agent`
- Check CodeBuild project logs for build errors
- Ensure Dockerfile syntax is correct

### ECS Task Not Updating
```bash
# Check service
aws ecs describe-services \
  --cluster support-triage-agent-cluster \
  --services support-triage-agent-service \
  --region ap-southeast-2 \
  --profile support-triage

# Check running tasks
aws ecs list-tasks \
  --cluster support-triage-agent-cluster \
  --region ap-southeast-2 \
  --profile support-triage
```

---

## Next Steps After Push

1. **Wait 1-2 minutes** for ECS to deploy new task
2. **Get public IP:**
   ```bash
   aws ecs describe-tasks \
     --cluster support-triage-agent-cluster \
     --tasks <TASK_ARN> \
     --region ap-southeast-2 \
     --profile support-triage \
     --query 'tasks[0].networkInterfaces[0].privateIpAddress'
   ```
3. **Test health endpoint:**
   ```bash
   curl http://<PUBLIC_IP>:8000/health
   ```
4. **View logs:**
   ```bash
   aws logs tail /ecs/support-triage-agent --follow --region ap-southeast-2 --profile support-triage
   ```

---

## Recommended: Use AWS CodeBuild

**Why?**
- ✅ No local Docker setup required
- ✅ Runs in AWS cloud
- ✅ Free for 100 minutes/month
- ✅ Automatic ECR push
- ✅ Build logs in CloudWatch
- ✅ Can be automated with CodePipeline (optional)

**Steps:** Use Option 1 above or run:
```powershell
.\build-with-codebuild.ps1
```

---

**Questions?** Check AWS CodeBuild docs: https://docs.aws.amazon.com/codebuild/
