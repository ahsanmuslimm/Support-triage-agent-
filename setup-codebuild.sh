#!/bin/bash
# Quick setup and execution of AWS CodeBuild for Support Triage Agent

set -e

AWS_REGION="ap-southeast-2"
AWS_ACCOUNT_ID="130486712225"
PROJECT_NAME="support-triage-build"
GITHUB_REPO="https://github.com/ahsanmuslimm/Support-triage-agent-.git"

echo "[*] Setting up AWS CodeBuild for Support Triage Agent"
echo ""

# Step 1: Check AWS credentials
echo "[*] Checking AWS credentials..."
if ! aws sts get-caller-identity --region $AWS_REGION > /dev/null 2>&1; then
    echo "[X] AWS credentials not configured"
    echo "    Run: aws login"
    exit 1
fi
echo "[+] AWS credentials valid"

# Step 2: Create CodeBuild IAM role (if not exists)
echo "[*] Checking CodeBuild service role..."
ROLE_NAME="codebuild-role"
TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Service": "codebuild.amazonaws.com"
    },
    "Action": "sts:AssumeRole"
  }]
}'

INLINE_POLICY='{
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
}'

# Check if role exists
if ! aws iam get-role --role-name $ROLE_NAME > /dev/null 2>&1; then
    echo "[*] Creating CodeBuild service role..."
    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document "$TRUST_POLICY"
    
    aws iam put-role-policy \
        --role-name $ROLE_NAME \
        --policy-name CodeBuildECRPolicy \
        --policy-document "$INLINE_POLICY"
    
    echo "[+] CodeBuild service role created"
else
    echo "[+] CodeBuild service role already exists"
fi

# Step 3: Create CodeBuild project
echo "[*] Creating CodeBuild project..."
ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$ROLE_NAME"

aws codebuild create-project \
    --name $PROJECT_NAME \
    --source type=GITHUB,location=$GITHUB_REPO,gitCloneDepth=1 \
    --service-role $ROLE_ARN \
    --environment type=LINUX_CONTAINER,image=aws/codebuild/standard:7.0,computeType=BUILD_GENERAL1_SMALL,environmentVariablesOverride='[
        {name=AWS_ACCOUNT_ID,value='$AWS_ACCOUNT_ID'},
        {name=AWS_DEFAULT_REGION,value='$AWS_REGION'},
        {name=IMAGE_REPO_NAME,value=support-triage-agent}
    ]' \
    --artifacts type=NO_ARTIFACTS \
    --region $AWS_REGION 2>/dev/null || {
    echo "[*] Project already exists, using existing"
}

echo "[+] CodeBuild project ready: $PROJECT_NAME"

# Step 4: Start build
echo ""
echo "[*] Starting CodeBuild..."
BUILD_RESULT=$(aws codebuild start-build \
    --project-name $PROJECT_NAME \
    --region $AWS_REGION)

BUILD_ID=$(echo $BUILD_RESULT | grep -o '"id": "[^"]*"' | head -1 | cut -d'"' -f4)
echo "[+] Build started: $BUILD_ID"
echo ""

# Step 5: Monitor build
echo "[*] Monitoring build progress..."
BUILD_STATUS="IN_PROGRESS"
MAX_WAIT=600

while [ "$BUILD_STATUS" = "IN_PROGRESS" ] && [ $MAX_WAIT -gt 0 ]; do
    sleep 10
    MAX_WAIT=$((MAX_WAIT - 10))
    
    BUILD_STATUS=$(aws codebuild batch-get-builds --ids $BUILD_ID --region $AWS_REGION | grep -o '"buildStatus": "[^"]*"' | cut -d'"' -f4)
    PHASE=$(aws codebuild batch-get-builds --ids $BUILD_ID --region $AWS_REGION | grep -o '"currentPhase": "[^"]*"' | cut -d'"' -f4)
    
    echo "    Phase: $PHASE | Status: $BUILD_STATUS"
done

if [ "$BUILD_STATUS" = "SUCCEEDED" ]; then
    echo ""
    echo "[+] Build Successful!"
    echo "[+] Image pushed to ECR"
else
    echo ""
    echo "[X] Build Failed: $BUILD_STATUS"
    exit 1
fi

# Step 6: Update ECS Service
echo ""
echo "[*] Updating ECS service..."
aws ecs update-service \
    --cluster support-triage-agent-cluster \
    --service support-triage-agent-service \
    --force-new-deployment \
    --region $AWS_REGION > /dev/null

echo "[+] ECS service updated"
echo ""
echo "[+] Build and Deploy Complete!"
echo "    Image: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/support-triage-agent"
echo ""
echo "Next Steps:"
echo "  1. Wait 1-2 minutes for ECS task to restart"
echo "  2. Check logs: aws logs tail /ecs/support-triage-agent --follow --region $AWS_REGION"
echo ""
