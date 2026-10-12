#!/usr/bin/env python3
"""
Start CodeBuild for Support Triage Agent
Retries if queue is full
"""

import sys
import time
import json
import boto3

AWS_REGION = "ap-southeast-2"
PROJECT_NAME = "support-triage-build"
MAX_RETRIES = 30  # Retry for up to 5 minutes

print("[*] Starting CodeBuild Build")
print("")

try:
    session = boto3.Session(profile_name="support-triage")
    codebuild = session.client("codebuild", region_name=AWS_REGION)
    ecs = session.client("ecs", region_name=AWS_REGION)
except Exception as e:
    print(f"[X] Failed to initialize: {e}")
    sys.exit(1)

# Try to start build with retries
build_id = None
for attempt in range(1, MAX_RETRIES + 1):
    try:
        print(f"[*] Attempt {attempt}/{MAX_RETRIES}: Starting build...")
        response = codebuild.start_build(projectName=PROJECT_NAME)
        build_id = response["build"]["id"]
        print(f"[+] Build started: {build_id}")
        break
    except codebuild.exceptions.AccountLimitExceededException as e:
        if attempt < MAX_RETRIES:
            print(f"    Queue full, waiting 10s... (retry {attempt})")
            time.sleep(10)
        else:
            print(f"[X] Build queue remains full after {MAX_RETRIES} attempts")
            sys.exit(1)
    except Exception as e:
        print(f"[X] Error: {e}")
        sys.exit(1)

if not build_id:
    print("[X] Failed to start build")
    sys.exit(1)

# Monitor build
print("")
print("[*] Monitoring build progress...")
start_time = time.time()
max_build_time = 600  # 10 minutes
last_phase = None

while time.time() - start_time < max_build_time:
    try:
        response = codebuild.batch_get_builds(ids=[build_id])
        if not response.get("builds"):
            print("[!] Build not found")
            break
        
        build = response["builds"][0]
        status = build.get("buildStatus", "UNKNOWN")
        phase = build.get("currentPhase", "UNKNOWN")
        
        if phase != last_phase:
            print(f"    [{phase}] {status}")
            last_phase = phase
        
        if status != "IN_PROGRESS":
            break
        
        time.sleep(5)
    except Exception as e:
        print(f"[!] Error checking status: {e}")
        break

# Get final status
print("")
try:
    response = codebuild.batch_get_builds(ids=[build_id])
    build = response["builds"][0]
    final_status = build.get("buildStatus")
    
    if final_status == "SUCCEEDED":
        print("[+] BUILD SUCCESSFUL!")
        print(f"    Build ID: {build_id}")
        print("")
        print("[*] Image pushed to ECR")
        print("    Repository: 130486712225.dkr.ecr.ap-southeast-2.amazonaws.com/support-triage-agent")
        print("")
        
        # Update ECS
        print("[*] Updating ECS service...")
        try:
            ecs.update_service(
                cluster="support-triage-agent-cluster",
                service="support-triage-agent-service",
                forceNewDeployment=True
            )
            print("[+] ECS service updated")
        except Exception as e:
            print(f"[!] Could not update ECS: {e}")
    else:
        print(f"[X] BUILD FAILED: {final_status}")
        print(f"    Build ID: {build_id}")
        print(f"    Phase: {build.get('currentPhase')}")
        if build.get("failureDetails"):
            print(f"    Error: {build['failureDetails']}")
        sys.exit(1)
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

print("")
print("=" * 60)
print("[+] Build and Deploy Complete!")
print("=" * 60)
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
