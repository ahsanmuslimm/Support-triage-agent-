# Quick Start - Build & Deploy

Your application infrastructure is deployed. Now push the Docker image to ECR.

## Status

✅ Infrastructure deployed (VPC, ECS, ElastiCache, ECR)  
✅ Dockerfile & buildspec.yml ready  
❌ Docker image not in ECR yet  
⏳ Next: Build image and push to ECR

---

## Simplest Path: Manual Push via Docker CLI

**Prerequisite:** Docker Desktop must be running

### Step 1: Open Terminal/PowerShell

```powershell
cd "d:\WORKING\PORTFOLIO\FEATURED PROJECTS\Support-triage-agent-"
```

### Step 2: Login to ECR

```powershell
aws ecr get-login-password --region ap-southeast-2 --profile support-triage | docker login --username AWS --password-stdin 130486712225.dkr.ecr.ap-southeast-2.amazonaws.com
```

Expected: `Login Succeeded`

### Step 3: Build Docker Image

```powershell
docker build -t 130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent:latest -t 130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent:v1.0 .
```

**Time:** 10-15 minutes (first run, lots of dependencies)

### Step 4: Push to ECR

```powershell
docker push 130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent:latest
docker push 130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent:v1.0
```

**Time:** 5 minutes

### Step 5: Update ECS

```powershell
aws ecs update-service --cluster support-triage-agent-cluster --service support-triage-agent-service --force-new-deployment --region ap-southeast-2 --profile support-triage
```

### Step 6: Wait & Test (1-2 minutes)

```powershell
# Get task IP
aws ecs describe-tasks --cluster support-triage-agent-cluster --tasks $(aws ecs list-tasks --cluster support-triage-agent-cluster --region ap-southeast-2 --profile support-triage --query 'taskArns[0]' --output text) --region ap-southeast-2 --profile support-triage --query 'tasks[0].networkInterfaces[0].publicIpAddress'

# Test
curl http://<PUBLIC_IP>:8000/health
```

---

## If Docker Commands Don't Work

**Common issue:** Docker not in PowerShell PATH

### Solution A: Use Python Script
```powershell
python build-docker.py
```

### Solution B: Verify Docker Running
1. Open Docker Desktop app
2. Check "Docker Engine" is running
3. Restart PowerShell
4. Try commands again

### Solution C: Use Full Docker Path
```powershell
"C:\Program Files\Docker\Docker\resources\bin\docker.exe" build -t ... .
```

(Replace path if Docker installed elsewhere)

---

## Timeline

- **Build:** 10-15 minutes
- **Push:** 5 minutes  
- **ECS restart:** 2 minutes
- **Total to live:** ~20-25 minutes

---

## Success Criteria

✅ Docker image built locally  
✅ Image pushed to ECR  
✅ ECS service updated  
✅ New task running with new image  
✅ Health endpoint responds: `http://PUBLIC_IP:8000/health`

---

**Next:** Run the commands above in PowerShell, or ask if you hit issues!
