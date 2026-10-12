#!/usr/bin/env python3
"""
Create CodeBuild project for Support Triage Agent
"""

import sys
import json
import time

try:
    import boto3
except ImportError:
    print("[X] boto3 not installed")
    sys.exit(1)

AWS_REGION = "ap-southeast-2"
AWS_ACCOUNT_ID = "130486712225"
PROJECT_NAME = "support-triage-build"
GITHUB_REPO = "https://github.com/ahsanmuslimm/Support-triage-agent-.git"
ROLE_NAME = "codebuild-service-role"
SERVICE_ROLE = f"arn:aws:iam::{AWS_ACCOUNT_ID}:role/{ROLE_NAME}"

print("[*] Creating CodeBuild Project for Support Triage Agent")
print("")

# Initialize clients
try:
    session = boto3.Session(profile_name="support-triage")
    codebuild = session.client("codebuild", region_name=AWS_REGION)
    iam = session.client("iam")
    sts = session.client("sts")
except Exception as e:
    print(f"[X] Failed to initialize: {e}")
    sys.exit(1)

# Verify credentials
try:
    identity = sts.get_caller_identity()
    print(f"[+] Authenticated as: {identity['Arn']}")
except Exception as e:
    print(f"[X] Authentication failed: {e}")
    sys.exit(1)

# Step 1: Create IAM role if needed
print("[*] Checking IAM role...")
try:
    iam.get_role(RoleName=ROLE_NAME)
    print(f"[+] Role exists: {ROLE_NAME}")
except iam.exceptions.NoSuchEntityException:
    print(f"[*] Creating IAM role: {ROLE_NAME}")
    
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
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="CodeBuild service role for Support Triage Agent"
        )
        print("[+] Role created")
        
        # Add ECR permissions
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
                        "ecr:CompleteLayerUpload"
                    ],
                    "Resource": "*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        iam.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName="CodeBuildECRPolicy",
            PolicyDocument=json.dumps(ecr_policy)
        )
        print("[+] ECR permissions added")
        time.sleep(3)
    except Exception as e:
        print(f"[X] Failed to create role: {e}")
        sys.exit(1)
except Exception as e:
    print(f"[!] Warning: {e}")

# Step 2: Check if project exists
print("[*] Checking CodeBuild project...")
try:
    existing = codebuild.batch_get_projects(names=[PROJECT_NAME])
    if existing.get("projects"):
        print(f"[+] Project already exists: {PROJECT_NAME}")
        project = existing["projects"][0]
    else:
        print(f"[*] Project not found, creating: {PROJECT_NAME}")
        
        response = codebuild.create_project(
            name=PROJECT_NAME,
            description="Build and push Support Triage Agent Docker image to ECR",
            source={
                "type": "GITHUB",
                "location": GITHUB_REPO,
                "gitCloneDepth": 1,
                "buildspec": "buildspec.yml"
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
                        "type": "PLAINTEXT"
                    },
                    {
                        "name": "AWS_DEFAULT_REGION",
                        "value": AWS_REGION,
                        "type": "PLAINTEXT"
                    },
                    {
                        "name": "IMAGE_REPO_NAME",
                        "value": "support-triage-agent",
                        "type": "PLAINTEXT"
                    }
                ]
            },
            serviceRole=SERVICE_ROLE,
            logsConfig={
                "cloudWatchLogs": {
                    "status": "ENABLED",
                    "groupName": f"/aws/codebuild/{PROJECT_NAME}"
                }
            }
        )
        
        print(f"[+] Project created: {PROJECT_NAME}")
        print("")
        print("Project details:")
        print(f"  Name: {response['project']['name']}")
        print(f"  ARN: {response['project']['arn']}")
        print(f"  Source: GitHub")
        print(f"  Repository: {GITHUB_REPO}")
        print("")

except Exception as e:
    print(f"[X] Failed to create project: {e}")
    sys.exit(1)

# Step 3: Display instructions
print("=" * 60)
print("[+] CodeBuild Project Ready!")
print("=" * 60)
print("")
print("Next Steps:")
print("")
print("1. Go to AWS Console:")
print(f"   https://console.aws.amazon.com/codebuild/v1/projects")
print("")
print("2. Find project: support-triage-build")
print("")
print("3. Click 'Start build'")
print("")
print("4. Build will:")
print("   - Pull source from GitHub (main branch)")
print("   - Read buildspec.yml")
print("   - Build Docker image")
print("   - Push to ECR")
print("   - Takes ~5 minutes")
print("")
print("5. After build succeeds:")
print("   Run: aws ecs update-service --cluster support-triage-agent-cluster \\")
print("        --service support-triage-agent-service \\")
print("        --force-new-deployment --region ap-southeast-2")
print("")
print("6. Wait 1-2 minutes for ECS task to restart with new image")
print("")
