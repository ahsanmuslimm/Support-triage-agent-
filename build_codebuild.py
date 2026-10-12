#!/usr/bin/env python3
"""
Build and push Support Triage Agent using AWS CodeBuild
Uses boto3 (AWS SDK for Python) - no CLI required
"""

import sys
import time
import json
from pathlib import Path

try:
    import boto3
except ImportError:
    print("[X] boto3 not installed")
    print("Install with: pip install boto3")
    sys.exit(1)

# Configuration
AWS_REGION = "ap-southeast-2"
AWS_ACCOUNT_ID = "130486712225"
PROJECT_NAME = "support-triage-build"
GITHUB_REPO = "https://github.com/ahsanmuslimm/Support-triage-agent-.git"
ROLE_NAME = "codebuild-service-role"
SERVICE_ROLE = f"arn:aws:iam::{AWS_ACCOUNT_ID}:role/{ROLE_NAME}"

print("[*] Starting Docker Build with AWS CodeBuild (Python SDK)")
print("")

# Initialize clients with SSO profile
try:
    print("[*] Initializing AWS clients...")
    # Use SSO profile or default credentials
    session = boto3.Session(profile_name="support-triage")
    codebuild_client = session.client("codebuild", region_name=AWS_REGION)
    sts_client = session.client("sts", region_name=AWS_REGION)
    ecs_client = session.client("ecs", region_name=AWS_REGION)
    iam_client = session.client("iam")
    print("[+] AWS clients initialized")
except Exception as e:
    print(f"[X] Failed to initialize AWS clients: {e}")
    print("    Make sure you're authenticated: aws login --profile support-triage")
    sys.exit(1)

# Step 1: Verify credentials
print("[*] Checking AWS credentials...")
try:
    identity = sts_client.get_caller_identity()
    print(f"[+] Authenticated as: {identity['Arn']}")
except Exception as e:
    print(f"[X] Authentication failed: {e}")
    sys.exit(1)

# Step 2: Check if buildspec.yml exists
print("[*] Checking buildspec.yml...")
if not Path("buildspec.yml").exists():
    print("[X] buildspec.yml not found")
    sys.exit(1)
print("[+] buildspec.yml found")

# Step 3: Create IAM role if needed
print("[*] Checking CodeBuild IAM role...")
try:
    iam_client.get_role(RoleName=ROLE_NAME)
    print("[+] CodeBuild IAM role already exists")
except iam_client.exceptions.NoSuchEntityException:
    print(f"[*] Creating CodeBuild IAM role: {ROLE_NAME}")
    
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "codebuild.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        iam_client.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Service role for Support Triage CodeBuild",
        )
        
        # Add inline policy for ECR access
        ecr_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetAuthorizationToken",
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:PutImage",
                        "ecr:InitiateLayerUpload",
                        "ecr:UploadLayerPart",
                        "ecr:CompleteLayerUpload",
                    ],
                    "Resource": "*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        iam_client.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName="CodeBuildECRPolicy",
            PolicyDocument=json.dumps(ecr_policy),
        )
        
        print(f"[+] CodeBuild IAM role created")
        time.sleep(5)  # Wait for role to propagate
    except Exception as e:
        print(f"[X] Failed to create IAM role: {e}")
        sys.exit(1)
except Exception as e:
    print(f"[!] Warning: Could not check IAM role: {e}")

# Step 4: Check if CodeBuild project exists
print("[*] Checking CodeBuild project...")
try:
    projects = codebuild_client.batch_get_projects(names=[PROJECT_NAME])
    if len(projects.get("projects", [])) == 0:
        print(f"[*] Creating CodeBuild project: {PROJECT_NAME}")
        
        codebuild_client.create_project(
            name=PROJECT_NAME,
            source={
                "type": "GITHUB",
                "location": GITHUB_REPO,
                "gitCloneDepth": 1,
            },
            artifacts={"type": "NO_ARTIFACTS"},
            environment={
                "type": "LINUX_CONTAINER",
                "image": "aws/codebuild/standard:7.0",
                "computeType": "BUILD_GENERAL1_SMALL",
                "environmentVariables": [
                    {
                        "name": "AWS_ACCOUNT_ID",
                        "value": AWS_ACCOUNT_ID,
                        "type": "PLAINTEXT",
                    },
                    {
                        "name": "AWS_DEFAULT_REGION",
                        "value": AWS_REGION,
                        "type": "PLAINTEXT",
                    },
                    {
                        "name": "IMAGE_REPO_NAME",
                        "value": "support-triage-agent",
                        "type": "PLAINTEXT",
                    },
                ],
            },
            serviceRole=SERVICE_ROLE,
        )
        print("[+] CodeBuild project created")
    else:
        print("[+] CodeBuild project already exists")
except Exception as e:
    print(f"[X] CodeBuild project check failed: {e}")
    sys.exit(1)

# Step 5: Start the build
print("[*] Starting CodeBuild...")
try:
    response = codebuild_client.start_build(projectName=PROJECT_NAME)
    build_id = response["build"]["id"]
    print(f"[+] Build started: {build_id}")
except Exception as e:
    print(f"[X] Failed to start build: {e}")
    sys.exit(1)

# Step 6: Monitor build progress
print("")
print("[*] Monitoring build progress...")
max_wait = 600  # 10 minutes
start_time = time.time()
last_phase = None

while time.time() - start_time < max_wait:
    try:
        response = codebuild_client.batch_get_builds(ids=[build_id])
        build = response["builds"][0]
        status = build.get("buildStatus", "UNKNOWN")
        phase = build.get("currentPhase", "UNKNOWN")
        
        if phase != last_phase:
            print(f"    Phase: {phase} | Status: {status}")
            last_phase = phase
        
        if status != "IN_PROGRESS":
            break
        
        time.sleep(5)
    except Exception as e:
        print(f"[X] Error checking build status: {e}")
        break

# Step 7: Get final build status
print("")
try:
    response = codebuild_client.batch_get_builds(ids=[build_id])
    build = response["builds"][0]
    final_status = build.get("buildStatus", "UNKNOWN")
    
    if final_status == "SUCCEEDED":
        print("[+] Build Successful!")
        print("[+] Image pushed to ECR")
        print(f"    Repository: support-triage-agent")
        print(f"    Region: {AWS_REGION}")
    else:
        print(f"[X] Build Failed: {final_status}")
        print("")
        print("Build details:")
        print(f"  Build ID: {build_id}")
        print(f"  Phase: {build.get('currentPhase', 'UNKNOWN')}")
        if "failureDetails" in build:
            print(f"  Error: {build['failureDetails']}")
        sys.exit(1)
except Exception as e:
    print(f"[X] Error getting final status: {e}")
    sys.exit(1)

# Step 8: Update ECS Service
print("[*] Updating ECS service...")
try:
    ecs_client.update_service(
        cluster="support-triage-agent-cluster",
        service="support-triage-agent-service",
        forceNewDeployment=True,
    )
    print("[+] ECS service updated to pull new image")
except Exception as e:
    print(f"[!] Warning: Could not update ECS service: {e}")
    print("    You can manually update with:")
    print("    aws ecs update-service --cluster support-triage-agent-cluster \\")
    print("      --service support-triage-agent-service --force-new-deployment")

# Summary
print("")
print("=" * 48)
print("[+] Build and Deploy Complete!")
print("=" * 48)
print("")
print("Summary:")
print(f"  Image: {AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com/support-triage-agent")
print(f"  Build ID: {build_id}")
print(f"  Status: {final_status}")
print("")
print("Next Steps:")
print("  1. Wait 1-2 minutes for ECS task to restart")
print("  2. Get task public IP:")
print("     aws ecs describe-tasks --cluster support-triage-agent-cluster \\")
print("       --tasks <TASK_ARN> --region ap-southeast-2 --profile support-triage")
print("  3. Test health endpoint: curl http://<PUBLIC_IP>:8000/health")
print("  4. View logs:")
print("     aws logs tail /ecs/support-triage-agent --follow --region ap-southeast-2")
print("")


# Step 1: Verify credentials
print("[*] Checking AWS credentials...")
try:
    identity = sts_client.get_caller_identity()
    print(f"[+] Authenticated as: {identity['Arn']}")
except Exception as e:
    print(f"[X] Authentication failed: {e}")
    sys.exit(1)

# Step 2: Check if buildspec.yml exists
print("[*] Checking buildspec.yml...")
if not Path("buildspec.yml").exists():
    print("[X] buildspec.yml not found")
    sys.exit(1)
print("[+] buildspec.yml found")

# Step 3: Check if CodeBuild project exists
print("[*] Checking CodeBuild project...")
try:
    projects = codebuild_client.batch_get_projects(names=[PROJECT_NAME])
    if len(projects.get("projects", [])) == 0:
        print(f"[*] Creating CodeBuild project: {PROJECT_NAME}")
        
        codebuild_client.create_project(
            name=PROJECT_NAME,
            source={
                "type": "GITHUB",
                "location": GITHUB_REPO,
                "gitCloneDepth": 1,
            },
            artifacts={"type": "NO_ARTIFACTS"},
            environment={
                "type": "LINUX_CONTAINER",
                "image": "aws/codebuild/standard:7.0",
                "computeType": "BUILD_GENERAL1_SMALL",
                "environmentVariables": [
                    {
                        "name": "AWS_ACCOUNT_ID",
                        "value": AWS_ACCOUNT_ID,
                        "type": "PLAINTEXT",
                    },
                    {
                        "name": "AWS_DEFAULT_REGION",
                        "value": AWS_REGION,
                        "type": "PLAINTEXT",
                    },
                    {
                        "name": "IMAGE_REPO_NAME",
                        "value": "support-triage-agent",
                        "type": "PLAINTEXT",
                    },
                ],
            },
            serviceRole=SERVICE_ROLE,
        )
        print("[+] CodeBuild project created")
    else:
        print("[+] CodeBuild project already exists")
except Exception as e:
    print(f"[X] CodeBuild project check failed: {e}")
    sys.exit(1)

# Step 4: Start the build
print("[*] Starting CodeBuild...")
try:
    response = codebuild_client.start_build(projectName=PROJECT_NAME)
    build_id = response["build"]["id"]
    print(f"[+] Build started: {build_id}")
except Exception as e:
    print(f"[X] Failed to start build: {e}")
    sys.exit(1)

# Step 5: Monitor build progress
print("")
print("[*] Monitoring build progress...")
max_wait = 600  # 10 minutes
start_time = time.time()
last_phase = None

while time.time() - start_time < max_wait:
    try:
        response = codebuild_client.batch_get_builds(ids=[build_id])
        build = response["builds"][0]
        status = build.get("buildStatus", "UNKNOWN")
        phase = build.get("currentPhase", "UNKNOWN")
        
        if phase != last_phase:
            print(f"    Phase: {phase} | Status: {status}")
            last_phase = phase
        
        if status != "IN_PROGRESS":
            break
        
        time.sleep(5)
    except Exception as e:
        print(f"[X] Error checking build status: {e}")
        break

# Step 6: Get final build status
print("")
try:
    response = codebuild_client.batch_get_builds(ids=[build_id])
    build = response["builds"][0]
    final_status = build.get("buildStatus", "UNKNOWN")
    
    if final_status == "SUCCEEDED":
        print("[+] Build Successful!")
        print("[+] Image pushed to ECR")
        print(f"    Repository: support-triage-agent")
        print(f"    Region: {AWS_REGION}")
    else:
        print(f"[X] Build Failed: {final_status}")
        print("")
        print("Build details:")
        print(f"  Build ID: {build_id}")
        print(f"  Phase: {build.get('currentPhase', 'UNKNOWN')}")
        if "failureDetails" in build:
            print(f"  Error: {build['failureDetails']}")
        sys.exit(1)
except Exception as e:
    print(f"[X] Error getting final status: {e}")
    sys.exit(1)

# Step 7: Update ECS Service
print("[*] Updating ECS service...")
try:
    ecs_client.update_service(
        cluster="support-triage-agent-cluster",
        service="support-triage-agent-service",
        forceNewDeployment=True,
    )
    print("[+] ECS service updated to pull new image")
except Exception as e:
    print(f"[!] Warning: Could not update ECS service: {e}")
    print("    You can manually update with:")
    print("    aws ecs update-service --cluster support-triage-agent-cluster \\")
    print("      --service support-triage-agent-service --force-new-deployment")

# Summary
print("")
print("=" * 48)
print("[+] Build and Deploy Complete!")
print("=" * 48)
print("")
print("Summary:")
print(f"  Image: {AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com/support-triage-agent")
print(f"  Build ID: {build_id}")
print(f"  Status: {final_status}")
print("")
print("Next Steps:")
print("  1. Wait 1-2 minutes for ECS task to restart")
print("  2. Get task public IP:")
print("     aws ecs describe-tasks --cluster support-triage-agent-cluster \\")
print("       --tasks <TASK_ARN> --region ap-southeast-2 --profile support-triage")
print("  3. Test health endpoint: curl http://<PUBLIC_IP>:8000/health")
print("  4. View logs:")
print("     aws logs tail /ecs/support-triage-agent --follow --region ap-southeast-2")
print("")
