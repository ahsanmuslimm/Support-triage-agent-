#!/usr/bin/env python3
"""
Build and push Docker image using subprocess (bypasses PATH issues)
"""

import subprocess
import sys
import json
import shutil

AWS_REGION = "ap-southeast-2"
AWS_ACCOUNT_ID = "130486712225"
ECR_REPO = "support-triage-agent"
ECR_URI = f"{AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com"
IMAGE_NAME = f"{ECR_URI}/{ECR_REPO}"

print("[*] Building Support Triage Agent Docker Image")
print("")

# Step 1: Find docker
print("[*] Finding Docker...")
docker_exe = shutil.which("docker")
if not docker_exe:
    print("[X] Docker not found in PATH")
    print("")
    print("Common Docker locations:")
    print("  Windows: C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe")
    print("  Docker Desktop WSL2")
    print("")
    print("Try:")
    print("  1. Restart PowerShell (PATH may not be updated)")
    print("  2. Or check Docker Desktop is running")
    sys.exit(1)

print(f"[+] Docker found: {docker_exe}")

# Step 2: Check docker running
print("[*] Checking Docker daemon...")
try:
    result = subprocess.run([docker_exe, "ps"], capture_output=True, timeout=5)
    if result.returncode == 0:
        print("[+] Docker is running")
    else:
        print("[X] Docker returned error")
        print(result.stderr.decode())
        sys.exit(1)
except subprocess.TimeoutExpired:
    print("[X] Docker daemon not responding")
    sys.exit(1)
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

# Step 3: Get commit hash
print("[*] Getting commit hash...")
try:
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    commit_hash = result.stdout.strip()
    print(f"[+] Commit: {commit_hash}")
except Exception as e:
    print(f"[X] Git error: {e}")
    sys.exit(1)

# Step 4: Login to ECR
print("[*] Logging in to ECR...")
try:
    # Get auth token
    result = subprocess.run(
        ["aws", "ecr", "get-login-password", "--region", AWS_REGION, "--profile", "support-triage"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode != 0:
        print(f"[X] AWS CLI error: {result.stderr}")
        sys.exit(1)
    
    auth_token = result.stdout.strip()
    
    # Login with token
    proc = subprocess.Popen(
        [docker_exe, "login", "--username", "AWS", "--password-stdin", ECR_URI],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = proc.communicate(input=auth_token, timeout=10)
    
    if proc.returncode == 0:
        print("[+] ECR login successful")
    else:
        print(f"[X] Docker login failed: {stderr}")
        sys.exit(1)
        
except subprocess.TimeoutExpired:
    print("[X] Timeout during ECR login")
    sys.exit(1)
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

# Step 5: Build image
print("[*] Building Docker image...")
print(f"    Image: {IMAGE_NAME}:{commit_hash}")
print("")

try:
    result = subprocess.run(
        [
            docker_exe, "build",
            "-t", f"{IMAGE_NAME}:latest",
            "-t", f"{IMAGE_NAME}:{commit_hash}",
            "."
        ],
        timeout=600
    )
    
    if result.returncode == 0:
        print("")
        print("[+] Build successful")
    else:
        print("[X] Build failed")
        sys.exit(1)
except subprocess.TimeoutExpired:
    print("[X] Build timeout (>10 min)")
    sys.exit(1)
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

# Step 6: Push to ECR
print("[*] Pushing to ECR...")

try:
    print(f"    Pushing {IMAGE_NAME}:latest...")
    result = subprocess.run(
        [docker_exe, "push", f"{IMAGE_NAME}:latest"],
        timeout=300
    )
    if result.returncode != 0:
        print("[X] Push failed")
        sys.exit(1)
    print("    [+] latest pushed")
    
    print(f"    Pushing {IMAGE_NAME}:{commit_hash}...")
    result = subprocess.run(
        [docker_exe, "push", f"{IMAGE_NAME}:{commit_hash}"],
        timeout=300
    )
    if result.returncode != 0:
        print("[X] Push failed")
        sys.exit(1)
    print(f"    [+] {commit_hash} pushed")
    
except subprocess.TimeoutExpired:
    print("[X] Push timeout")
    sys.exit(1)
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

# Step 7: Update ECS
print("[*] Updating ECS service...")
try:
    result = subprocess.run(
        [
            "aws", "ecs", "update-service",
            "--cluster", "support-triage-agent-cluster",
            "--service", "support-triage-agent-service",
            "--force-new-deployment",
            "--region", AWS_REGION,
            "--profile", "support-triage"
        ],
        capture_output=True,
        timeout=10
    )
    
    if result.returncode == 0:
        print("[+] ECS service updated")
    else:
        print(f"[!] ECS update warning: {result.stderr.decode()}")
        
except Exception as e:
    print(f"[!] Warning: {e}")

# Summary
print("")
print("=" * 60)
print("[+] Build and Push Complete!")
print("=" * 60)
print("")
print(f"Image: {IMAGE_NAME}:{commit_hash}")
print("")
print("Next Steps:")
print("  1. Wait 1-2 minutes for ECS task to restart")
print("  2. Get public IP:")
print(f"     aws ecs describe-tasks --cluster support-triage-agent-cluster \\")
print(f"       --tasks $(aws ecs list-tasks --cluster support-triage-agent-cluster \\")
print(f"         --region {AWS_REGION} --query 'taskArns[0]' --output text) \\")
print(f"       --region {AWS_REGION} --query 'tasks[0].networkInterfaces[0].publicIpAddress'")
print("  3. Test: curl http://<PUBLIC_IP>:8000/health")
print("  4. Logs: aws logs tail /ecs/support-triage-agent --follow --region ap-southeast-2")
print("")
