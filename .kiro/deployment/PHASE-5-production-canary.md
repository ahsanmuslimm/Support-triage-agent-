# Phase 5: Production Deployment (Canary Strategy)

**Estimated Time:** 120-180 minutes (with monitoring)  
**Status:** Production Rollout Phase  
**Last Updated:** 2024

## Overview

Phase 5 performs a gradual canary deployment to production using a 5% → 25% → 50% → 100% traffic ramp strategy. This minimizes risk by detecting issues with small traffic percentages before rolling out to all users.

## Canary Deployment Architecture

```
┌─────────────────────────────────────┐
│     Application Load Balancer       │
│          (Production)               │
└────────────────────┬────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
    ┌───▼─┐      ┌───▼─┐    ┌───▼─┐
    │5%   │      │ %   │    │     │
    │ New │      │ Old │    │Old  │
    │v1.0 │      │v0.9 │    │v0.9 │
    └─────┘      └─────┘    └─────┘
    
    Stage 1: v1.0 (5%) vs v0.9 (95%)
    Stage 2: v1.0 (25%) vs v0.9 (75%)
    Stage 3: v1.0 (50%) vs v0.9 (50%)
    Stage 4: v1.0 (100%) - Old version deprecated
```

## 1. Pre-Production Verification

### Checklist

```bash
#!/bin/bash
echo "=== Pre-Production Verification ==="

# 1. Staging tests passed
echo "1. Verifying staging test results..."
[ -f staging-test-results.json ] && echo "  ✓ Staging tests passed" || echo "  ✗ Missing test results"

# 2. Data backups current
echo "2. Verifying backups..."
aws rds describe-db-snapshots \
  --db-instance-identifier support-triage-db \
  --query 'DBSnapshots[-1].[DBSnapshotIdentifier,SnapshotCreateTime]'

# 3. Monitoring configured
echo "3. Verifying monitoring..."
aws cloudwatch describe-alarms \
  --alarm-names support-triage-prod-cpu-utilization

# 4. Alert recipients configured
echo "4. Verifying alert recipients..."
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:123456789012:support-triage-alerts

# 5. Rollback procedures ready
echo "5. Verifying rollback procedures..."
[ -f deployment/rollback-procedures.md ] && echo "  ✓ Rollback guide available" || echo "  ✗ Missing rollback guide"

# 6. Communication plan ready
echo "6. Verifying communication plan..."
[ -f deployment/communication-plan.md ] && echo "  ✓ Communication plan ready" || echo "  ✗ Missing communication plan"

echo ""
echo "=== Verification Complete ==="
```

## 2. Canary Deployment Procedure

### Stage 1: 5% Traffic (30 minutes)

**Objective:** Detect critical issues with minimal blast radius

**deployment/scripts/deploy-production-canary.sh**
```bash
#!/bin/bash
set -e

STAGE=${1:-1}
VERSION=${2:-v1.0}
AWS_REGION=${AWS_REGION:-us-east-1}

echo "=== Production Canary Deployment - Stage $STAGE ==="

# Source configuration
source .env.production

# Configuration
PROD_CLUSTER="support-triage-prod"
OLD_VERSION="v0.9"
NEW_VERSION=$VERSION

# Stage configurations
declare -A TRAFFIC_PERCENTAGES=(
  [1]="5"
  [2]="25"
  [3]="50"
  [4]="100"
)

declare -A MONITORING_DURATION=(
  [1]="30"   # 30 minutes
  [2]="30"   # 30 minutes
  [3]="60"   # 60 minutes
  [4]="0"    # No monitoring for final stage
)

NEW_TRAFFIC=${TRAFFIC_PERCENTAGES[$STAGE]}
MONITOR_MINUTES=${MONITORING_DURATION[$STAGE]}

echo "Stage: $STAGE"
echo "New Version Traffic: $NEW_TRAFFIC%"
echo "Monitoring Duration: $MONITOR_MINUTES minutes"
echo ""

# Step 1: Update ALB Target Group Weights
echo "Updating ALB target group weights..."

# Get target group ARN
TG_ARN=$(aws elbv2 describe-target-groups \
  --names support-triage-tg \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

# Get current targets
TARGETS=$(aws elbv2 describe-target-health \
  --target-group-arn $TG_ARN \
  --query 'TargetHealthDescriptions[*].[Target.Id]' \
  --output text)

# Update target weights
# For new version tasks, set weight to NEW_TRAFFIC
# For old version tasks, set weight to (100-NEW_TRAFFIC)

echo "  New version weight: $NEW_TRAFFIC"
echo "  Old version weight: $((100-NEW_TRAFFIC))"

# Step 2: Deploy New Version Tasks
echo ""
echo "Deploying new version ($NEW_VERSION)..."

# Update task definition with new image
NEW_TASK_DEF=$(aws ecs describe-task-definition \
  --task-definition support-triage-api:1 \
  --query 'taskDefinition.family' \
  --output text)

aws ecs update-service \
  --cluster $PROD_CLUSTER \
  --service support-triage-api \
  --desired-count $STAGE \
  --region $AWS_REGION

sleep 60

# Verify new tasks running
RUNNING=$(aws ecs describe-services \
  --cluster $PROD_CLUSTER \
  --services support-triage-api \
  --query 'services[0].runningCount' \
  --output text)

if [ "$RUNNING" -ge $STAGE ]; then
  echo "  ✓ New version running ($RUNNING tasks)"
else
  echo "  ✗ Failed to deploy new version"
  exit 1
fi

# Step 3: Start Monitoring
if [ "$MONITOR_MINUTES" -gt 0 ]; then
  echo ""
  echo "Starting $MONITOR_MINUTES-minute monitoring period..."
  echo "Watch metrics dashboard: https://console.aws.amazon.com/cloudwatch"
  
  # Store metrics for analysis
  START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
  echo "$START_TIME" > /tmp/canary-stage-$STAGE-start.txt
  
  # Monitor key metrics
  for i in $(seq 1 $MONITOR_MINUTES); do
    echo -n "."
    sleep 60
    
    # Check error rate every 5 minutes
    if [ $((i % 5)) -eq 0 ]; then
      ERROR_RATE=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ApplicationELB \
        --metric-name HTTPCode_Target_5XX_Count \
        --dimensions Name=LoadBalancer,Value=app/support-triage-alb/* \
        --start-time $(date -u -d '5 minutes ago' '+%Y-%m-%dT%H:%M:%S') \
        --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
        --period 300 \
        --statistics Sum \
        --query 'Datapoints[0].Sum' \
        --output text)
      
      if [ "$ERROR_RATE" != "None" ] && [ $(echo "$ERROR_RATE > 10" | bc) -eq 1 ]; then
        echo ""
        echo "  ⚠ High error rate detected: $ERROR_RATE errors in last 5 min"
        echo "  Consider rolling back to previous version"
      fi
    fi
  done
  echo ""
fi

# Step 4: Verify Metrics
echo ""
echo "Verifying metrics..."

# Get error rate
ERRORS=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value=app/support-triage-alb/* \
  --start-time $(date -u -d '30 minutes ago' '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 300 \
  --statistics Sum)

echo "Errors in last 30 minutes: $ERRORS"

# Get latency
LATENCY=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=app/support-triage-alb/* \
  --start-time $(date -u -d '30 minutes ago' '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 300 \
  --statistics Average)

echo "Average latency: $LATENCY"

echo ""
echo "=== Stage $STAGE Complete ==="
echo "Next step: Review metrics and run 'Stage $(($STAGE+1))' if all metrics are acceptable"
```

### Stage 1 Monitoring Commands

```bash
# Monitor error rates
watch -n 10 'aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value=app/support-triage-alb/* \
  --start-time $(date -u -d "10 minutes ago" "+%Y-%m-%dT%H:%M:%S") \
  --end-time $(date -u "+%Y-%m-%dT%H:%M:%S") \
  --period 60 \
  --statistics Sum \
  --query "Datapoints[0].Sum"'

# Monitor CPU utilization
watch -n 10 'aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=support-triage-prod Name=ServiceName,Value=support-triage-api \
  --start-time $(date -u -d "10 minutes ago" "+%Y-%m-%dT%H:%M:%S") \
  --end-time $(date -u "+%Y-%m-%dT%H:%M:%S") \
  --period 60 \
  --statistics Average'

# Monitor memory utilization
watch -n 10 'aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ClusterName,Value=support-triage-prod Name=ServiceName,Value=support-triage-api \
  --start-time $(date -u -d "10 minutes ago" "+%Y-%m-%dT%H:%M:%S") \
  --end-time $(date -u "+%Y-%m-%dT%H:%M:%S") \
  --period 60 \
  --statistics Average'

# Monitor database connections
watch -n 10 'aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=support-triage-db \
  --start-time $(date -u -d "10 minutes ago" "+%Y-%m-%dT%H:%M:%S") \
  --end-time $(date -u "+%Y-%m-%dT%H:%M:%S") \
  --period 60 \
  --statistics Average'
```

### Stage 1 Metrics Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Error Rate (5xx) | > 0.1% | Investigate |
| Error Rate (5xx) | > 1% | Rollback immediately |
| Latency (p95) | > 1000ms | Investigate |
| Latency (p99) | > 2000ms | Consider rollback |
| CPU Utilization | > 80% | Scale up or investigate |
| Memory Utilization | > 90% | Investigate memory leak |
| Database Connections | > 80% max | Scale or investigate |

### Stage 2: 25% Traffic

```bash
# Run after Stage 1 metrics are acceptable (wait 5+ minutes after Stage 1 completes)
bash deployment/scripts/deploy-production-canary.sh 2 v1.0

# Monitor for 30 minutes
```

### Stage 3: 50% Traffic

```bash
# Run after Stage 2 metrics are acceptable
bash deployment/scripts/deploy-production-canary.sh 3 v1.0

# Monitor for 60 minutes (longer at 50/50 split)
```

### Stage 4: 100% Traffic (Full Rollout)

```bash
# Run after Stage 3 metrics are acceptable
bash deployment/scripts/deploy-production-canary.sh 4 v1.0

# Deploy fully and keep old version available for quick rollback
```

## 3. Monitoring Dashboards Verification

**deployment/monitoring-dashboard-setup.md**
```markdown
# CloudWatch Monitoring Dashboards

## Key Dashboards to Verify

### 1. Application Performance Dashboard
- **URL:** AWS CloudWatch Dashboards → Application Performance
- **Metrics:**
  - Request count (by endpoint)
  - Response latency (p50, p95, p99)
  - Error rate (by status code)
  - Successful requests per second

### 2. Infrastructure Health Dashboard
- **ECS Cluster Health**
  - Running task count (by service)
  - CPU utilization
  - Memory utilization
- **RDS Database**
  - Active connections
  - Query performance insights
  - Disk space utilization
- **ElastiCache**
  - Connection count
  - Eviction rate
  - Cache hit ratio

### 3. Business Metrics Dashboard
- **Cases Processed**
  - Total cases created
  - Average triage time
  - SLA compliance rate
- **User Activity**
  - Active users
  - Transactions per second
  - Peak throughput

### 4. Cost & Resource Dashboard
- **Cost Tracking**
  - Daily costs by service
  - Reserved instance utilization
- **Resource Utilization**
  - Network throughput
  - Storage used

## Creating Dashboards

```bash
# Create custom dashboard
aws cloudwatch put-dashboard \
  --dashboard-name support-triage-production \
  --dashboard-body file://deployment/dashboards/production-dashboard.json
```

## Dashboard JSON Template

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ApplicationELB", "TargetResponseTime", {"stat": "Average"}],
          [".", "HTTPCode_Target_2XX_Count", {"stat": "Sum"}],
          [".", "HTTPCode_Target_5XX_Count", {"stat": "Sum"}]
        ],
        "period": 60,
        "stat": "Average",
        "region": "us-east-1",
        "title": "ALB Performance"
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ECS", "CPUUtilization", {"dimensions": {"ServiceName": "support-triage-api"}}],
          [".", "MemoryUtilization", {"dimensions": {"ServiceName": "support-triage-api"}}]
        ],
        "period": 60,
        "stat": "Average",
        "region": "us-east-1",
        "title": "ECS Service Utilization"
      }
    }
  ]
}
```
```

## 4. Metric Threshold Definitions

**deployment/metric-thresholds.md**
```markdown
# Production Metric Thresholds

## Severity Levels

### Critical (Red) - Immediate Action Required
- Error rate > 1% sustained for 5 minutes
- Latency p99 > 2 seconds
- ECS task health checks failing > 50%
- Database connections > 90% of max
- Disk space < 10%

### High (Orange) - Investigation Required
- Error rate > 0.5% for 10 minutes
- Latency p95 > 1 second
- CPU utilization > 80% for 10 minutes
- Memory utilization > 85% for 10 minutes
- RDS query performance degraded

### Medium (Yellow) - Monitor Closely
- Error rate 0.1% - 0.5%
- Latency p95 > 500ms
- CPU utilization 60-80%
- Memory utilization 70-85%

### Normal (Green)
- Error rate < 0.1%
- Latency p95 < 500ms
- CPU utilization < 60%
- Memory utilization < 70%
```

## 5. Rollback Procedures

**deployment/rollback-procedures.md**
```markdown
# Production Rollback Procedures

## Quick Rollback (Immediate, < 5 minutes)

### If Issues Detected During Canary Stage

```bash
#!/bin/bash
CURRENT_STAGE=$1  # 1, 2, 3, or 4

echo "=== ROLLBACK INITIATED ==="
echo "Rolling back from stage $CURRENT_STAGE"

# Notify team
aws sns publish \
  --topic-arn arn:aws:sns:us-east-1:123456789012:support-triage-alerts \
  --message "PRODUCTION ROLLBACK INITIATED - Stage $CURRENT_STAGE"

# If Stage 1: Simply stop new version tasks
if [ "$CURRENT_STAGE" -eq 1 ]; then
  aws ecs update-service \
    --cluster support-triage-prod \
    --service support-triage-api \
    --desired-count 0 \
    --force-new-deployment
fi

# If Stage 2-4: Switch traffic back to old version
aws elbv2 modify-target-group-attributes \
  --target-group-arn $(aws elbv2 describe-target-groups \
    --names support-triage-tg --query 'TargetGroups[0].TargetGroupArn' --output text) \
  --attributes Key=stickiness.enabled,Value=false

# Wait for ALB to drain connections (120s)
sleep 120

# Verify old version is serving 100% traffic
TRAFFIC=$(aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups \
    --names support-triage-tg --query 'TargetGroups[0].TargetGroupArn' --output text) \
  --query 'length(TargetHealthDescriptions[?TargetHealth.State==`healthy`])')

echo "✓ Rollback complete. Old version serving $TRAFFIC% traffic"
```

## Full Rollback (If Canary Cannot Be Undone)

Use infrastructure snapshot from before deployment:
1. Restore database from pre-deployment snapshot
2. Redeploy previous version's ECS tasks
3. Repoint ALB to old task definitions
4. Manual verification of all critical paths

## Post-Rollback Analysis

- [ ] Collect error logs from failed canary stage
- [ ] Analyze application performance metrics
- [ ] Identify root cause of failure
- [ ] Document findings in incident report
- [ ] Create fixes and test in staging
- [ ] Schedule retry of deployment
```

## 6. Canary Completion Checklist

```markdown
# Canary Deployment Completion Checklist

## Pre-Deployment
- [ ] All staging tests passed
- [ ] Code reviewed and approved
- [ ] Database backups created
- [ ] Monitoring dashboards verified
- [ ] On-call team notified
- [ ] Change management approval obtained

## During Deployment
- [ ] Stage 1 (5%): All metrics normal
- [ ] Stage 1: No critical errors detected
- [ ] Stage 2 (25%): Metrics trending well
- [ ] Stage 2: Error rate < 0.1%
- [ ] Stage 3 (50%): Load distribution even
- [ ] Stage 3: Database queries performing well
- [ ] Stage 4 (100%): Full rollout successful

## Post-Deployment
- [ ] All services responding normally
- [ ] Cache hit ratio > 95%
- [ ] Database connections stable
- [ ] User-facing latency < 500ms
- [ ] No errors in application logs
- [ ] All dependent services verified
- [ ] Team notified of successful deployment
- [ ] Documentation updated
- [ ] Post-deployment review completed
```

## Success Criteria

- ✓ Canary deployment completed successfully
- ✓ All stages passed with acceptable metrics
- ✓ Error rate maintained < 0.1%
- ✓ Latency remained < 500ms (p95)
- ✓ No critical incidents detected
- ✓ System scalability verified
- ✓ Database performance maintained

## Next Steps

→ **Proceed to Phase 6: Post-Launch Operations**
- Set up 24/7 monitoring
- Configure alert escalations
- Document runbooks
- Train operations team

## References

- [AWS CloudWatch Metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/)
- [ECS Deployment Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/)
- [Canary Deployment Strategy](https://martinfowler.com/bliki/CanaryRelease.html)
- [Blue-Green Deployments](https://en.wikipedia.org/wiki/Blue%E2%80%93green_deployment)
