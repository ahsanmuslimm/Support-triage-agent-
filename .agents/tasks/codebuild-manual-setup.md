# AWS CodeBuild Manual Setup - Support Triage Agent

**Status:** CodeBuild project created, ready for manual trigger  
**Project:** support-triage-build  
**Region:** ap-southeast-2  
**Account:** 130486712225

---

## What's Done

✅ CodeBuild project created: `support-triage-build`  
✅ Service role created: `codebuild-service-role`  
✅ buildspec.yml in GitHub repo  
✅ Dockerfile in GitHub repo  
✅ All code committed

---

## Current Limitation

**Build Queue Limit:** Account has 0 concurrent builds allowed (new account restriction)

**Workaround:** Use AWS Console to trigger build manually (one-click, takes 5 minutes)

---

## Option 1: AWS Console (Easiest)

### Step 1: Open CodeBuild Console

Go to: https://console.aws.amazon.com/codebuild/v1/projects

### Step 2: Select Project

- Find: `support-triage-build`
- Click it

### Step 3: Start Build

- Click **Start build** (blue button)
- Use defaults (main branch, buildspec.yml from repo)
- Click **Start build** again

### Step 4: Monitor

- Watch logs in real-time
- Build takes ~5 minutes
- Should see "BUILD_SUCCEEDED"

### Step 5: Verify Image

After build completes:
```bash
# List images in ECR
aws ecr describe-images \
  --repository-name support-triage-agent \
  --region ap-southeast-2 \
  --profile support-triage
```

---

## Option 2: Automate Later (When Quota Increases)

If account quota increases, run:

```powershell
python build_codebuild.py
```

This will automatically:
1. Start build
2. Monitor progress
3. Update ECS service

---

## After Build Completes (Either Option)

### 1. Check Build Status

```bash
# View build details
aws codebuild batch-get-builds \
  --ids <BUILD_ID> \
  --region ap-southeast-2 \
  --profile support-triage
```

### 2. Force ECS Redeployment

```bash
aws ecs update-service \
  --cluster support-triage-agent-cluster \
  --service support-triage-agent-service \
  --force-new-deployment \
  --region ap-southeast-2 \
  --profile support-triage
```

### 3. Get ECS Task Public IP (wait 1-2 min)

```bash
# List tasks
aws ecs list-tasks \
  --cluster support-triage-agent-cluster \
  --region ap-southeast-2 \
  --profile support-triage

# Get full task details
aws ecs describe-tasks \
  --cluster support-triage-agent-cluster \
  --tasks <TASK_ARN> \
  --region ap-southeast-2 \
  --profile support-triage \
  --query 'tasks[0].{PublicIP: networkInterfaces[0].publicIpAddress, Status: lastStatus}'
```

### 4. Test Application

```bash
# Health check
curl http://<PUBLIC_IP>:8000/health

# Should return: {"status": "ok", "version": "1.0"}
```

### 5. View Logs

```bash
# Stream logs
aws logs tail /ecs/support-triage-agent \
  --follow \
  --region ap-southeast-2 \
  --profile support-triage \
  --max-items 50
```

---

## Files for Manual Trigger

All files are in GitHub ready:

```
.
├── Dockerfile              # Container image definition
├── buildspec.yml          # CodeBuild configuration ← Used by CodeBuild
├── build_codebuild.py     # Python script (queued builds)
├── build-and-push.ps1     # Local Docker script (if Docker setup later)
└── DOCKER-BUILD-GUIDE.md  # Detailed reference
```

---

## CodeBuild Project Details

| Setting | Value |
|---------|-------|
| **Name** | support-triage-build |
| **Source** | GitHub: ahsanmuslimm/Support-triage-agent- |
| **Branch** | main |
| **Buildspec** | buildspec.yml from repo root |
| **Environment** | Ubuntu, Standard 7.0 |
| **Compute** | BUILD_GENERAL1_SMALL |
| **Service Role** | codebuild-service-role |
| **Artifacts** | None (direct push to ECR) |
| **Image Repo** | support-triage-agent |
| **Region** | ap-southeast-2 |

---

## What CodeBuild Does (buildspec.yml)

```yaml
phases:
  pre_build:
    - Login to ECR
    - Set image tags (latest + commit hash)
  build:
    - Build Docker image: Dockerfile → 2GB image
  post_build:
    - Push to ECR: latest + commit-hash
    - Create imagedefinitions.json
```

**Result:** Image in ECR, ready for ECS to pull

---

## Quick Commands

```bash
# Trigger build from console
echo "Go to: https://console.aws.amazon.com/codebuild/v1/projects"
echo "Select: support-triage-build"
echo "Click: Start build"

# After build completes
aws ecs update-service --cluster support-triage-agent-cluster \
  --service support-triage-agent-service --force-new-deployment \
  --region ap-southeast-2 --profile support-triage

# Wait 1-2 minutes, then get public IP
aws ecs describe-tasks \
  --cluster support-triage-agent-cluster \
  --tasks $(aws ecs list-tasks --cluster support-triage-agent-cluster \
    --region ap-southeast-2 --profile support-triage \
    --query 'taskArns[0]' --output text) \
  --region ap-southeast-2 --profile support-triage \
  --query 'tasks[0].networkInterfaces[0].publicIpAddress'

# Test
curl http://<PUBLIC_IP>:8000/health
```

---

## Troubleshooting

### Build Fails: "Cannot have more than 0 builds in queue"

This is an AWS account limitation on new/free tier accounts.

**Solution:** Wait and retry, or use AWS Console (which may have different limits).

### Build Fails: "CodeBuild is not authorized"

Already resolved - service role created with permissions.

### Build Fails: "Failed to push to ECR"

Check buildspec.yml uses correct account ID and region.

### ECS Task Won't Update

1. Verify image exists in ECR
2. Check ECS task logs
3. Manually trigger with `force-new-deployment`

### Can't Access Application

1. Wait 1-2 minutes for task to start
2. Get public IP from task details
3. Verify security group allows port 8000

---

## Next Step

**Choose your path:**

1. **Manually via Console (easiest):**
   - Go to: https://console.aws.amazon.com/codebuild/v1/projects
   - Find: support-triage-build
   - Click: Start build
   - Wait: ~5 minutes

2. **Or, when quota increases:**
   - Run: `python build_codebuild.py`

Then:
- Wait for ECS to restart (~2 min)
- Get public IP
- Test health endpoint
- View logs

---

## Cost

**This build:**
- CodeBuild: Free (100 min/month included)
- ECR storage: ~$0.10/GB ($0 for first 10 GB)
- ECS task running: Free tier (750 hrs/month)

---

**Ready to proceed? Go to AWS Console and trigger the build manually!**
