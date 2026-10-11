# Phase 6: Post-Launch Operations

**Estimated Time:** Ongoing (initial setup 60-90 minutes)  
**Status:** Production Operations & Monitoring Phase  
**Last Updated:** 2024

## Overview

Phase 6 establishes 24/7 operations, monitoring, alerting, incident response, and success verification for the production deployment.

## 1. Monitoring Dashboard Setup

### CloudWatch Dashboard Creation

```bash
# Create comprehensive production monitoring dashboard
aws cloudwatch put-dashboard \
  --dashboard-name support-triage-production-ops \
  --dashboard-body file://deployment/dashboards/production-ops.json
```

**deployment/dashboards/production-ops.json**
```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ApplicationELB", "TargetResponseTime", {
            "dimensions": {"LoadBalancer": "app/support-triage-alb/*"},
            "stat": "Average",
            "label": "Avg Response Time"
          }],
          ["...", {"stat": "p95", "label": "P95 Response Time"}],
          ["...", {"stat": "p99", "label": "P99 Response Time"}]
        ],
        "period": 60,
        "region": "us-east-1",
        "title": "ALB Response Time",
        "yAxis": {"left": {"min": 0, "max": 5000}}
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ApplicationELB", "HTTPCode_Target_2XX_Count", {
            "dimensions": {"LoadBalancer": "app/support-triage-alb/*"},
            "stat": "Sum"
          }],
          [".", "HTTPCode_Target_4XX_Count", {"stat": "Sum"}],
          [".", "HTTPCode_Target_5XX_Count", {"stat": "Sum", "color": "#d62728"}]
        ],
        "period": 60,
        "region": "us-east-1",
        "title": "HTTP Response Codes",
        "yAxis": {"left": {"min": 0}}
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ECS", "CPUUtilization", {
            "dimensions": {
              "ClusterName": "support-triage-prod",
              "ServiceName": "support-triage-api"
            },
            "stat": "Average"
          }],
          [".", "MemoryUtilization", {
            "dimensions": {
              "ClusterName": "support-triage-prod",
              "ServiceName": "support-triage-api"
            },
            "stat": "Average"
          }]
        ],
        "period": 60,
        "region": "us-east-1",
        "title": "ECS Service Utilization",
        "yAxis": {"left": {"min": 0, "max": 100}}
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/RDS", "DatabaseConnections", {
            "dimensions": {"DBInstanceIdentifier": "support-triage-db"},
            "stat": "Average"
          }],
          [".", "CPUUtilization", {"stat": "Average"}],
          [".", "FreeableMemory", {"stat": "Average"}]
        ],
        "period": 60,
        "region": "us-east-1",
        "title": "RDS Database Health"
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ElastiCache", "BytesUsedForCache", {
            "dimensions": {"CacheClusterId": "support-triage-redis-001"},
            "stat": "Average"
          }],
          [".", "CacheMisses", {"stat": "Sum"}],
          [".", "CacheHits", {"stat": "Sum"}]
        ],
        "period": 60,
        "region": "us-east-1",
        "title": "ElastiCache Performance"
      }
    },
    {
      "type": "log",
      "properties": {
        "query": "fields @timestamp, @message | filter @message like /ERROR/ | stats count() as error_count by bin(5m)",
        "region": "us-east-1",
        "title": "Application Errors (5-min bins)"
      }
    }
  ]
}
```

## 2. Alert Rule Configuration

### Critical Alerts

**deployment/alerts/critical-alerts.md**
```markdown
# Critical Alert Rules

## 1. High Error Rate (5xx)

**Condition:** HTTPCode_Target_5XX_Count > 10 for 5 minutes

**Alert Configuration:**
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name support-triage-high-error-rate \
  --alarm-description "Alert when 5xx error rate is high" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:support-triage-alerts-critical
```

**Response:** Page on-call engineer immediately

## 2. High Latency (p99)

**Condition:** TargetResponseTime (p99) > 2000ms for 10 minutes

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name support-triage-high-latency \
  --alarm-description "Alert when p99 latency exceeds 2s" \
  --metric-name TargetResponseTime \
  --namespace AWS/ApplicationELB \
  --statistic p99 \
  --period 300 \
  --threshold 2000 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:support-triage-alerts-high
```

**Response:** Investigate application logs and database performance

## 3. Database Connection Pool Exhaustion

**Condition:** DatabaseConnections > 90 (90% of max 100)

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name support-triage-db-connection-high \
  --alarm-description "Alert when DB connections near max" \
  --metric-name DatabaseConnections \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 90 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:support-triage-alerts-high
```

**Response:** Check for connection leaks, consider scaling

## 4. ECS Task Health Check Failures

**Condition:** Healthy task count < desired count for 5 minutes

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name support-triage-ecs-unhealthy-tasks \
  --alarm-description "Alert when ECS tasks become unhealthy" \
  --metric-name TaskCount \
  --namespace ECS/ContainerInsights \
  --statistic Average \
  --period 300 \
  --threshold 2 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:support-triage-alerts-critical
```

## 5. Memory Leak Detection

**Condition:** ECS Memory Utilization trending upward > 85%

## 6. Disk Space Low

**Condition:** Available disk space < 20%

## 7. Cascading Failure Detection

**Condition:** Both API and Worker services unhealthy simultaneously
```

### Setting Up SNS Topics for Alerts

```bash
# Create SNS topics for different severity levels
aws sns create-topic --name support-triage-alerts-critical
aws sns create-topic --name support-triage-alerts-high
aws sns create-topic --name support-triage-alerts-medium

# Subscribe to topics
# PagerDuty integration
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:123456789012:support-triage-alerts-critical \
  --protocol https \
  --notification-endpoint https://events.pagerduty.com/integration/YOUR-INTEGRATION-KEY/enqueue

# Email fallback
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:123456789012:support-triage-alerts-critical \
  --protocol email \
  --notification-endpoint ops-team@example.com

# Slack integration (via Lambda)
# See deployment/alerts/slack-notification-setup.md
```

## 3. Daily Operations Checklists

**deployment/operations/daily-checklist.md**
```markdown
# Daily Operations Checklist

## Start of Day (9:00 AM)

**Time Estimate: 15 minutes**

- [ ] **Check Dashboard:** Navigate to CloudWatch dashboard
  - Verify no active alarms
  - Check error rates (should be < 0.1%)
  - Verify all services showing green health

- [ ] **Database Health:** 
  ```bash
  aws rds describe-db-instances --db-instance-identifier support-triage-db \
    --query 'DBInstances[0].[DBInstanceStatus,PendingModifiedValues]'
  ```
  - Status should be: `available`
  - Pending modifications should be: `{}`

- [ ] **Application Logs:**
  ```bash
  aws logs tail /ecs/support-triage-api --since 1h | grep ERROR
  ```
  - Review any ERROR messages from overnight
  - Note patterns for investigation

- [ ] **Performance Metrics:**
  - Request latency p95: < 500ms
  - Error rate: < 0.1%
  - API response time: < 200ms median

- [ ] **Backups:**
  - Verify daily backup completed
  - Check backup size is reasonable

## Throughout Day

**Continuous Monitoring**

- [ ] **Alert Response:** React to any PagerDuty alerts within SLA
- [ ] **Metrics Monitoring:** Keep CloudWatch dashboard visible
- [ ] **Log Monitoring:** Check application logs every 2 hours
- [ ] **User Reports:** Monitor support channels for user issues

## End of Day (5:00 PM)

**Time Estimate: 20 minutes**

- [ ] **Day Summary:**
  ```bash
  aws cloudwatch get-metric-statistics \
    --namespace AWS/ApplicationELB \
    --metric-name HTTPCode_Target_5XX_Count \
    --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 86400 \
    --statistics Sum
  ```

- [ ] **Error Analysis:** Any error spikes or patterns?
- [ ] **Performance Trends:** Any degradation noted?
- [ ] **Update War Room:** Post summary in #operations

- [ ] **Handoff to Night Team:**
  - Document any ongoing issues
  - Note expected maintenance windows
  - Share any customer-impacting notes

## Weekly Operations (Friday)

**Time Estimate: 1 hour**

- [ ] **Cost Analysis:** Review AWS billing for the week
- [ ] **Capacity Planning:** Check growth trends
- [ ] **Backup Testing:** Restore from backup to test recovery
- [ ] **Security Review:** Check for any unauthorized access attempts
- [ ] **Performance Trends:** Generate weekly performance report

## Monthly Operations (End of Month)

**Time Estimate: 2 hours**

- [ ] **Disaster Recovery Drill:** Full backup/restore test
- [ ] **Security Audit:** Review access logs and permissions
- [ ] **Capacity Review:** Identify scaling needs
- [ ] **Cost Optimization:** Review and optimize spending
- [ ] **SLA Compliance:** Verify 99.9% uptime maintained
- [ ] **Version Updates:** Plan any dependency updates
```

## 4. Incident Response Procedures

**deployment/incident-response-runbook.md**
```markdown
# Incident Response Runbook

## Incident Severity Levels

### Critical (Red) - P1
- Service completely unavailable
- Data loss or potential data loss
- Security breach
- Affects > 50% of users
- **Response Time:** Immediate (< 5 minutes)
- **Escalation:** VP Engineering

### High (Orange) - P2
- Service severely degraded
- Affects 10-50% of users
- Potential revenue impact
- **Response Time:** < 15 minutes
- **Escalation:** Engineering Lead

### Medium (Yellow) - P3
- Service partially impacted
- Affects < 10% of users
- Workaround available
- **Response Time:** < 1 hour
- **Escalation:** On-call Engineer

### Low (Green) - P4
- Minor issue, no user impact
- Cosmetic issues
- **Response Time:** < 24 hours
- **Escalation:** Backlog

## P1 Response Protocol

### Immediate Actions (0-5 minutes)

1. **Page On-Call Team**
   ```bash
   aws sns publish \
     --topic-arn arn:aws:sns:us-east-1:123456789012:support-triage-critical \
     --message "CRITICAL INCIDENT: [Brief Description]"
   ```

2. **Gather Information:**
   - What is happening?
   - When did it start?
   - Who is affected?
   - What was changed recently?

3. **Start War Room:**
   - Create Zoom room: support-triage-incident-war-room
   - Add: On-call engineer, team lead, PM
   - Share: Incident link in Slack

4. **Assess Severity:**
   - Confirm P1 classification
   - Estimate time to resolution

### Investigation Phase (5-30 minutes)

**Check Dashboard:**
```bash
# Check all critical metrics
aws cloudwatch describe-alarms --state-value ALARM
```

**Check Logs:**
```bash
# Tail application logs
aws logs tail /ecs/support-triage-api --follow --since 30m | grep ERROR

# Check error patterns
aws logs start-query \
  --log-group-name /ecs/support-triage-api \
  --start-time $(date -d '30 min ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | filter @message like /ERROR/ | stats count() by @message'
```

**Database Health:**
```bash
# Check DB connections
aws rds describe-db-instances --db-instance-identifier support-triage-db \
  --query 'DBInstances[0].[DBInstanceStatus,EngineVersion]'

# Check CPU and connections
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT count(*) as connections FROM pg_stat_activity;"
```

**Service Health:**
```bash
# Check ECS tasks
aws ecs describe-services \
  --cluster support-triage-prod \
  --services support-triage-api support-triage-worker \
  --query 'services[*].[serviceName,runningCount,desiredCount,status]'

# Check recent task failures
aws ecs list-tasks --cluster support-triage-prod --desired-status STOPPED --max-results 10
```

### Resolution Phase (30+ minutes)

**Option 1: Rollback**
```bash
# If recent deployment caused issue
bash deployment/rollback-procedures.sh
```

**Option 2: Scale Up**
```bash
# If capacity issue
aws ecs update-service \
  --cluster support-triage-prod \
  --service support-triage-api \
  --desired-count 5
```

**Option 3: Database Failover**
```bash
# If primary DB down
aws rds reboot-db-instance \
  --db-instance-identifier support-triage-db \
  --force-failover
```

### Communication During Incident

- **Initial Message (5 min):** "We are investigating a service issue"
- **Updates (Every 15 min):** Status and ETA
- **Resolution (Immediate):** Confirm service restored
- **Post-Mortem (24 hours):** Document what happened

### Post-Incident (24 hours)

1. **Declare All-Clear:** Service fully recovered
2. **Write Incident Report:**
   - What happened?
   - Root cause?
   - What was done?
   - How do we prevent this?
3. **Schedule Post-Mortem:** 48 hours after incident
4. **Create Action Items:** Implement learnings

## P2/P3 Response

**Similar process but with longer response times**

- Initial acknowledgment required
- Don't need full war room
- Can batch investigation with other issues
- Regular updates every hour

## Common Incident Scenarios

### API Response Timeout

**Diagnosis:**
```bash
# Check for slow queries
psql -h $DB_HOST -c "SELECT query, query_start FROM pg_stat_activity WHERE state='active';"

# Check ECS logs for timeout errors
aws logs tail /ecs/support-triage-api | grep -i timeout
```

**Resolution:**
- Kill slow queries: `SELECT pg_terminate_backend(pid);`
- Restart affected services
- Scale database resources

### Database Connection Exhaustion

**Diagnosis:**
```bash
psql -h $DB_HOST -c "SELECT count(*) FROM pg_stat_activity;"
```

**Resolution:**
- Identify and kill idle connections
- Check application connection pool settings
- Restart application services

### Memory Leak in Service

**Diagnosis:**
```bash
# Monitor memory over time
watch -n 5 'aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ServiceName,Value=support-triage-api \
  --start-time $(date -u -d "1 hour ago" +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Average'
```

**Resolution:**
- Restart affected service (forces memory reclaim)
- Deploy fix in next release
- Monitor for recurrence

### Cascading Failure

**Symptoms:** Multiple services failing simultaneously

**Diagnosis:**
- Check if one service failure triggered others
- Check for resource exhaustion (CPU, memory, connections)
- Check for circular dependencies

**Resolution:**
- Identify root cause service
- Restart in dependency order
- Scale resources if needed
```

## 5. Success Criteria Verification

**deployment/success-criteria-checklist.md**
```markdown
# Post-Launch Success Criteria Verification

## Business Metrics (Week 1)

- [ ] System availability: 99.9% (5.4 minutes downtime max)
- [ ] Case processing latency: < 2 seconds (avg)
- [ ] Triage accuracy: > 92% (human review validation)
- [ ] User adoption: > 80% of target teams active
- [ ] Agent satisfaction: > 4.0/5.0 rating

## Technical Metrics (Week 1)

- [ ] API response latency p95: < 500ms
- [ ] API response latency p99: < 1000ms
- [ ] Error rate: < 0.1%
- [ ] Database query latency p95: < 100ms
- [ ] Cache hit ratio: > 95%

## Infrastructure Metrics

- [ ] CPU utilization: < 60% average
- [ ] Memory utilization: < 70% average
- [ ] Database connections: < 70% of max pool
- [ ] Storage utilization: < 60%
- [ ] Network throughput: Stable without spikes

## Reliability Metrics

- [ ] No cascading failures observed
- [ ] All health checks passing consistently
- [ ] Alerts firing appropriately (not over/under-alerting)
- [ ] Backup/restore procedures verified working
- [ ] Zero unplanned downtime incidents

## Security Metrics

- [ ] No unauthorized access attempts detected
- [ ] All API calls authenticated and authorized
- [ ] Data encryption verified (at rest and in transit)
- [ ] No sensitive data in logs
- [ ] Security scan results clean

## Cost Metrics

- [ ] Total monthly cost < budget ($750/month)
- [ ] No unexpected charges
- [ ] Reserved instances optimized
- [ ] Storage optimized and efficient

## Verification Commands

### Week 1 Summary Report

```bash
#!/bin/bash
echo "=== Post-Launch Verification Report ==="
echo "Generated: $(date)"
echo ""

# Uptime calculation
ERRORS=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum \
  --query 'Datapoints[].Sum' \
  --output text | awk '{s+=$1} END {print s}')

UPTIME=$(echo "scale=4; ((604800*100 - ($ERRORS*5))/604800)" | bc)
echo "Calculated Uptime: $UPTIME%"

# Latency metrics
echo ""
echo "Response Time Metrics (p95, p99):"
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 604800 \
  --statistics p95,p99 \
  --query 'Datapoints[0].[p95,p99]'

# Cost breakdown
echo ""
echo "Estimated Weekly Cost:"
aws ce list-cost-and-usage \
  --time-period Start=$(date -u -d '7 days ago' +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity DAILY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE

echo ""
echo "=== Verification Complete ==="
```
```

## 6. Training & Documentation

**deployment/operations/training-guide.md**
```markdown
# Operations Team Training Guide

## Role Overview

### Tier 1 - Alert Monitoring
- Monitor CloudWatch dashboards
- Acknowledge and triage alerts
- Escalate to Tier 2 if needed

### Tier 2 - Incident Response
- Investigate and troubleshoot issues
- Execute runbooks
- Coordinate with development if needed

### Tier 3 - Engineering Lead
- Oversee complex incidents
- Make architectural decisions
- Manage escalations

## Essential Skills

1. **AWS Console Navigation**
   - CloudWatch dashboards
   - ECS cluster management
   - RDS database management

2. **Command Line Tools**
   - AWS CLI
   - SSH to databases
   - Docker commands

3. **Log Analysis**
   - CloudWatch Logs
   - Analyzing error patterns
   - Performance analysis

4. **Runbook Execution**
   - Knowing when to rollback
   - Scaling services
   - Database failover

## Certifications

- AWS Certified Cloud Practitioner (recommended)
- Advanced: AWS Certified Solutions Architect Associate

## Resources

- [Runbook Repository](./incident-response-runbook.md)
- [Alert Configuration](./alerts/)
- [Dashboard Access](./dashboards/)
```

## 7. Metrics Dashboard Verification

```bash
#!/bin/bash
echo "=== Production Metrics Dashboard Verification ==="

# List all active alarms
echo "Active Alarms:"
aws cloudwatch describe-alarms --state-value ALARM --output table

# Get dashboard links
echo ""
echo "Dashboard URLs:"
echo "1. Application Performance: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=support-triage-production-ops"
echo "2. Service Health: https://console.aws.amazon.com/ecs/v2/clusters/support-triage-prod"
echo "3. Database Performance: https://console.aws.amazon.com/rds/home?region=us-east-1#databases:/support-triage-db"

# Verify SNS subscriptions
echo ""
echo "Alert Notification Subscriptions:"
for topic in critical-alerts high-alerts medium-alerts; do
  aws sns list-subscriptions-by-topic \
    --topic-arn arn:aws:sns:us-east-1:123456789012:support-triage-$topic \
    --query 'Subscriptions[*].[Protocol,Endpoint]'
done

echo "=== Verification Complete ==="
```

## Success Criteria

- ✓ Comprehensive monitoring dashboards created and verified
- ✓ Alert rules configured for all critical scenarios
- ✓ 24/7 alert routing to operations team
- ✓ Incident response procedures documented and practiced
- ✓ Daily/weekly operations checklists in place
- ✓ Team trained on operations procedures
- ✓ Success metrics being tracked and reported
- ✓ Post-launch review scheduled

## 30-Day Review

```markdown
# 30-Day Post-Launch Review

## Metrics Summary

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Availability | 99.9% | ? | ☐ Pass ☐ Fail |
| API Latency (p95) | <500ms | ? | ☐ Pass ☐ Fail |
| Error Rate | <0.1% | ? | ☐ Pass ☐ Fail |
| Database CPU | <60% avg | ? | ☐ Pass ☐ Fail |
| Monthly Cost | <$750 | ? | ☐ Pass ☐ Fail |

## Incidents Summary

- Total incidents: ?
- P1: ?
- P2: ?
- P3: ?
- Average resolution time: ?

## Improvements Made

- [ ] Fix #1
- [ ] Fix #2
- [ ] Optimization #3

## Next Steps

- [ ] Scale database (if needed)
- [ ] Add new features
- [ ] Optimize performance
- [ ] Plan Phase 2 improvements
```

## Next Steps

→ **Production Deployment Complete**
- Continue 24/7 monitoring
- Collect customer feedback
- Plan Sprint 6+ features

## References

- [AWS Operations Best Practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/best-practices-infrastructure-as-code/)
- [Incident Response Best Practices](https://aws.amazon.com/builders/well-architected/incident-response/)
- [CloudWatch Monitoring Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html)
