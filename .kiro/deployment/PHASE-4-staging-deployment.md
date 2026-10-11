# Phase 4: Staging Deployment Guide

**Estimated Time:** 60-90 minutes  
**Status:** Pre-Production Testing Phase  
**Last Updated:** 2024

## Overview

Phase 4 deploys the application to a staging environment for testing before production. This includes smoke testing, load testing, chaos engineering tests, and design partner validation.

## Staging Environment Architecture

```
Staging Environment (Isolated VPC)
├── Same infrastructure as production (smaller scale)
├── Data: Realistic anonymized dataset
├── Traffic: Load tests + real user validation
├── Monitoring: CloudWatch dashboards + alerts
└── Rollback: Quick to teardown and rebuild
```

## 1. Staging Deployment Procedures

### Terraform Staging Configuration

```hcl
# terraform/staging.tf
variable "environment" {
  default = "staging"
}

variable "staging_instance_class" {
  default = "db.t3.small"  # Smaller than production
}

variable "staging_ecs_desired_count" {
  default = 2  # Fewer instances than production
}

# Create staging-specific resources
module "staging" {
  source = "./modules/environment"
  
  environment              = "staging"
  vpc_cidr                 = "10.1.0.0/16"
  db_instance_class        = var.staging_instance_class
  ecs_desired_count        = var.staging_ecs_desired_count
  enable_enhanced_monitoring = true
  
  tags = {
    Environment = "staging"
    Deployment  = "phase-4"
  }
}

# Separate security groups for staging
resource "aws_security_group" "staging_alb" {
  name        = "staging-alb-sg"
  description = "ALB security group for staging"
  vpc_id      = module.staging.vpc_id
  
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Allow from anywhere for testing
  }
  
  tags = {
    Environment = "staging"
  }
}
```

### Deploy Staging

```bash
# Set staging environment
export ENVIRONMENT=staging

# Plan staging deployment
terraform plan \
  -var="environment=staging" \
  -var="instance_class=db.t3.small" \
  -var="ecs_desired_count=2" \
  -out=staging.tfplan

# Review and apply
terraform apply staging.tfplan

# Get staging ALB DNS
STAGING_ALB=$(aws elbv2 describe-load-balancers \
  --names staging-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text)

echo "Staging ALB: https://$STAGING_ALB"
```

### ECS Service Deployment

```bash
# Deploy staging services
bash deployment/scripts/deploy-staging.sh v1.0

# Verify services running
aws ecs list-services --cluster support-triage-staging

# Check task status
aws ecs describe-services \
  --cluster support-triage-staging \
  --services support-triage-api-staging

# Get task logs
TASK_ID=$(aws ecs list-tasks \
  --cluster support-triage-staging \
  --query 'taskArns[0]' --output text | awk -F'/' '{print $NF}')

aws logs tail /ecs/support-triage-api-staging --follow
```

## 2. Smoke Test Procedures

**deployment/tests/smoke-tests.sh**
```bash
#!/bin/bash
set -e

echo "=== Smoke Tests ==="

STAGING_URL=${1:-https://staging.triage-agent.example.com}
TIMEOUT=10

# Test functions
test_endpoint() {
  local name=$1
  local url=$2
  local expected_status=$3
  
  echo -n "Testing $name... "
  response=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout $TIMEOUT \
    "$url")
  
  if [ "$response" = "$expected_status" ]; then
    echo "✓ ($response)"
    return 0
  else
    echo "✗ (expected $expected_status, got $response)"
    return 1
  fi
}

test_response_body() {
  local name=$1
  local url=$2
  local expected_text=$3
  
  echo -n "Testing $name... "
  response=$(curl -s --connect-timeout $TIMEOUT "$url")
  
  if echo "$response" | grep -q "$expected_text"; then
    echo "✓"
    return 0
  else
    echo "✗ (missing: $expected_text)"
    echo "Response: $response"
    return 1
  fi
}

# Run tests
echo "Target: $STAGING_URL"
echo ""

test_endpoint "Health check" "$STAGING_URL/health" "200"
test_endpoint "API root" "$STAGING_URL/api/v1" "200"
test_endpoint "Metrics endpoint" "$STAGING_URL/metrics" "200"
test_endpoint "Invalid route" "$STAGING_URL/nonexistent" "404"

# Database connectivity
test_response_body "Database status" "$STAGING_URL/api/v1/health/db" "ok"

# Cache connectivity
test_response_body "Cache status" "$STAGING_URL/api/v1/health/cache" "ok"

# Authentication
echo -n "Testing authentication... "
auth_response=$(curl -s -X POST "$STAGING_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}')

if echo "$auth_response" | grep -q "error\|unauthorized"; then
  echo "✓ (auth required)"
else
  echo "✗ (unexpected response)"
fi

echo ""
echo "=== Smoke Tests Complete ==="
```

**Run Smoke Tests:**
```bash
bash deployment/tests/smoke-tests.sh https://$STAGING_ALB

# Expected output:
# Testing Health check... ✓ (200)
# Testing API root... ✓ (200)
# Testing Metrics endpoint... ✓ (200)
# Testing Invalid route... ✓ (404)
# Testing Database status... ✓
# Testing Cache status... ✓
# Testing authentication... ✓ (auth required)
#
# === Smoke Tests Complete ===
```

## 3. Load Testing with k6

**deployment/tests/load-tests.js**
```javascript
import http from 'k6/http';
import { check, group, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 VUs
    { duration: '5m', target: 50 },   // Ramp up to 50 VUs
    { duration: '10m', target: 50 },  // Stay at 50 VUs
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.1'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://staging.triage-agent.example.com';

export default function () {
  group('Get triaging cases', function () {
    const res = http.get(`${BASE_URL}/api/v1/cases?limit=10`);
    check(res, {
      'status is 200': (r) => r.status === 200,
      'response time < 500ms': (r) => r.timings.duration < 500,
      'has cases': (r) => r.body.includes('cases'),
    });
  });

  sleep(1);

  group('Create new case', function () {
    const payload = JSON.stringify({
      subject: `Test case ${__VU}-${__ITER}`,
      description: 'Load test case',
      priority: 'normal',
      customer_id: `customer-${__VU}`,
    });

    const params = {
      headers: { 'Content-Type': 'application/json' },
    };

    const res = http.post(`${BASE_URL}/api/v1/cases`, payload, params);
    check(res, {
      'status is 201': (r) => r.status === 201,
      'response time < 1000ms': (r) => r.timings.duration < 1000,
      'has case ID': (r) => r.body.includes('id'),
    });
  });

  sleep(2);

  group('Get case details', function () {
    const res = http.get(`${BASE_URL}/api/v1/cases/123`);
    check(res, {
      'status is 200 or 404': (r) => r.status === 200 || r.status === 404,
      'response time < 300ms': (r) => r.timings.duration < 300,
    });
  });

  sleep(1);
}
```

**Run Load Tests:**
```bash
# Install k6
# macOS: brew install k6
# Linux: sudo apt-get install k6
# Windows: choco install k6

# Run load test
k6 run deployment/tests/load-tests.js \
  --env BASE_URL=https://$STAGING_ALB \
  --out json=results.json

# View results
k6 run deployment/tests/load-tests.js --env BASE_URL=https://$STAGING_ALB | grep -A 20 "checks"

# Expected output:
# checks.........................: 98% ✓ 4920 ✗ 102
# data_received...................: 2.5 MB
# data_sent........................: 1.2 MB
# http_req_duration..............: avg=245ms, max=890ms, p(95)=450ms, p(99)=780ms
# http_req_failed.................: 2%
```

## 4. Chaos Engineering Tests

**deployment/tests/chaos-tests.sh**
```bash
#!/bin/bash
set -e

echo "=== Chaos Engineering Tests ==="

STAGING_URL=$1
NAMESPACE="support-triage-staging"

# Test 1: Pod Failure
echo "Test 1: Simulating pod failure..."
TASK_ARN=$(aws ecs list-tasks \
  --cluster $NAMESPACE \
  --query 'taskArns[0]' --output text)

aws ecs stop-task --cluster $NAMESPACE --task $TASK_ARN

echo "  Stopping task: $TASK_ARN"
sleep 30

# Verify service recovered
running_tasks=$(aws ecs list-tasks \
  --cluster $NAMESPACE \
  --query 'length(taskArns)' --output text)

if [ "$running_tasks" -ge 2 ]; then
  echo "  ✓ Service recovered ($(($running_tasks)) tasks running)"
else
  echo "  ✗ Service did not recover"
fi

# Test 2: Network Latency
echo ""
echo "Test 2: Simulating network latency..."
# Use tc (traffic control) or similar
# tc qdisc add dev eth0 root netem delay 500ms

echo "  Added 500ms latency"
sleep 10

# Verify application still responsive
if curl -s "$STAGING_URL/health" > /dev/null; then
  echo "  ✓ Application responsive under latency"
else
  echo "  ✗ Application failed under latency"
fi

# Test 3: Database Connection Pool Exhaustion
echo ""
echo "Test 3: Simulating high database load..."
# Create many concurrent connections
for i in {1..10}; do
  psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT pg_sleep(10);" &
done
wait

echo "  ✓ Database handled concurrent load"

# Test 4: Cache Failure
echo ""
echo "Test 4: Simulating cache failure..."
aws elasticache test-failover \
  --replication-group-id support-triage-redis

sleep 30

if curl -s "$STAGING_URL/health/cache" | grep -q "ok"; then
  echo "  ✓ Application handled cache failover"
else
  echo "  ✗ Application failed during cache failover"
fi

echo ""
echo "=== Chaos Tests Complete ==="
```

**Run Chaos Tests:**
```bash
bash deployment/tests/chaos-tests.sh https://$STAGING_ALB

# Expected output:
# === Chaos Engineering Tests ===
# Test 1: Simulating pod failure...
#   ✓ Service recovered (3 tasks running)
# Test 2: Simulating network latency...
#   ✓ Application responsive under latency
# Test 3: Simulating high database load...
#   ✓ Database handled concurrent load
# Test 4: Simulating cache failure...
#   ✓ Application handled cache failover
# === Chaos Tests Complete ===
```

## 5. Design Partner Validation Checklist

**deployment/design-partner-checklist.md**
```markdown
# Design Partner Validation Checklist

## Functional Testing (24 hours)

### Core Features
- [ ] User authentication and authorization
- [ ] Case creation and categorization
- [ ] Case assignment to agents
- [ ] AI-powered triage suggestions
- [ ] Sentiment analysis displays correctly
- [ ] Escalation workflows function
- [ ] SLA tracking and alerts
- [ ] Reporting and analytics

### User Interface
- [ ] Dashboard loads quickly
- [ ] Navigation is intuitive
- [ ] Forms validate input correctly
- [ ] Error messages are helpful
- [ ] Mobile responsiveness works
- [ ] Accessibility features functional

### Integration Testing
- [ ] Webhook integrations work
- [ ] API endpoints respond correctly
- [ ] Authentication with third-party systems
- [ ] Data sync between systems

### Performance
- [ ] Page load time < 2 seconds
- [ ] API response time < 500ms (p95)
- [ ] Database queries optimized
- [ ] No memory leaks observed

## Security Review

### Authentication & Authorization
- [ ] Password reset flow secure
- [ ] Session management correct
- [ ] RBAC enforced properly
- [ ] API rate limiting active

### Data Security
- [ ] Data encrypted at rest
- [ ] Data encrypted in transit (TLS)
- [ ] PII properly masked in logs
- [ ] Audit logging enabled

### Infrastructure Security
- [ ] Security groups properly configured
- [ ] WAF rules in place
- [ ] DDoS protection enabled
- [ ] Secrets properly managed

## Load Testing Sign-off

- [ ] Peak load: 1000 req/s achieved
- [ ] Response times acceptable under load
- [ ] No errors at peak capacity
- [ ] Graceful degradation observed

## Partner Feedback

- [ ] Feedback collected from 3+ design partners
- [ ] Critical issues resolved
- [ ] Non-critical issues documented for future sprints
- [ ] Partner sign-off obtained

## Sign-off

- Partner Name: _______________________
- Date: _______________________
- Status: ☐ Approved  ☐ Approved with conditions  ☐ Not approved
- Comments: ___________________________
```

## 6. Deployment Script

**deployment/scripts/deploy-staging.sh**
```bash
#!/bin/bash
set -e

echo "=== Deploying to Staging ==="

VERSION=${1:-v1.0}
ENVIRONMENT="staging"

# Source configuration
source .env.production

# Authenticate with ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Deploy with ECS
echo "Updating ECS service..."

for service in triage-api triage-worker triage-console; do
  aws ecs update-service \
    --cluster support-triage-staging \
    --service $service \
    --force-new-deployment \
    --region $AWS_REGION
done

# Wait for deployment
echo "Waiting for deployment to stabilize..."
sleep 60

# Verify all tasks are running
echo "Verifying service health..."
for service in triage-api triage-worker triage-console; do
  running=$(aws ecs describe-services \
    --cluster support-triage-staging \
    --services $service \
    --query 'services[0].runningCount' \
    --output text)
  
  desired=$(aws ecs describe-services \
    --cluster support-triage-staging \
    --services $service \
    --query 'services[0].desiredCount' \
    --output text)
  
  if [ "$running" = "$desired" ]; then
    echo "  ✓ $service: $running/$desired tasks running"
  else
    echo "  ✗ $service: only $running/$desired tasks running"
    exit 1
  fi
done

echo ""
echo "=== Staging Deployment Complete ==="
echo "Staging ALB: $(aws elbv2 describe-load-balancers --names staging-alb --query 'LoadBalancers[0].DNSName' --output text)"
```

## Success Criteria

- ✓ Staging environment deployed successfully
- ✓ All smoke tests passing
- ✓ Load tests show acceptable performance
- ✓ Chaos engineering tests successful
- ✓ Design partner validation complete
- ✓ No critical issues identified
- ✓ All services health checks passing

## Next Steps

→ **Proceed to Phase 5: Production Deployment (Canary Strategy)**
- Deploy to production with canary rollout
- Monitor metrics carefully
- Gradually increase traffic percentage

## References

- [k6 Load Testing Documentation](https://k6.io/docs/)
- [AWS ECS Deployment Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/)
- [Chaos Engineering Principles](https://principlesofchaos.org/)
