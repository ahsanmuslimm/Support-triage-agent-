# Production Deployment Guide

**Support Triage Agent - AI-Powered Customer Support System**

This directory contains complete production deployment procedures for the Support Triage Agent across 6 phases, from pre-flight validation to post-launch operations.

## Quick Start

### Prerequisites
- AWS Account with appropriate permissions
- Docker (v20.10+)
- Terraform (v1.5+)
- AWS CLI (v2.13+)
- Local system tools: git, curl, jq, python3.10+

### Deployment Path

```
Phase 1: Pre-Flight Checklist
    ↓
Phase 2: Infrastructure Setup (AWS)
    ↓
Phase 3: Docker Build & ECR Push
    ↓
Phase 4: Staging Deployment & Testing
    ↓
Phase 5: Production Canary Deployment
    ↓
Phase 6: Post-Launch Operations
```

## Phase Overview

| Phase | Duration | Purpose | Output |
|-------|----------|---------|--------|
| 1 | 45-60 min | Verify prerequisites | Ready to deploy |
| 2 | 90-120 min | Create AWS infrastructure | VPC, RDS, ElastiCache, ECS, ALB |
| 3 | 45-60 min | Build containers & push to ECR | Docker images ready |
| 4 | 60-90 min | Deploy to staging & test | Validated staging environment |
| 5 | 120-180 min | Canary rollout to production | Production deployment complete |
| 6 | Ongoing | Monitor & maintain | 24/7 operations ready |

## File Structure

```
deployment/
├── README.md (this file)
├── PHASE-1-preflight-checklist.md       ← Start here
├── PHASE-2-infrastructure-setup.md
├── PHASE-3-docker-build-registry.md
├── PHASE-4-staging-deployment.md
├── PHASE-5-production-canary.md
├── PHASE-6-post-launch-operations.md
│
├── scripts/
│   ├── pre-flight-check.sh              ← Automated validation
│   ├── build-images.sh                  ← Build Docker images
│   ├── deploy-staging.sh                ← Deploy to staging
│   └── deploy-production-canary.sh      ← Canary rollout
│
├── .env.production.template             ← Configuration template
├── monitoring-dashboard-setup.md        ← Dashboard setup
├── incident-response-runbook.md         ← Incident procedures
└── rollback-procedures.md               ← Emergency rollback
```

## Getting Started

### Step 1: Prepare Environment

```bash
# Navigate to project root
cd /path/to/Support-triage-agent-

# Copy and configure environment
cp deployment/.env.production.template .env.production

# Edit with your AWS account details
vim .env.production

# Should contain at minimum:
# AWS_REGION=us-east-1
# AWS_ACCOUNT_ID=123456789012
# ENVIRONMENT=production
```

### Step 2: Run Pre-Flight Check

```bash
# Make script executable
chmod +x deployment/scripts/pre-flight-check.sh

# Run validation
bash deployment/scripts/pre-flight-check.sh

# Expected output:
# ✓ Passed: 15
# ⚠ Warnings: 0
# ✗ Errors: 0
# ✓ Pre-flight check PASSED - Ready for deployment
```

### Step 3: Review Phase Guides

Start with **Phase 1** and proceed sequentially:

1. **[Phase 1: Pre-Flight Checklist](./PHASE-1-preflight-checklist.md)**
   - AWS account setup
   - Local tool verification
   - Environment configuration

2. **[Phase 2: Infrastructure Setup](./PHASE-2-infrastructure-setup.md)**
   - AWS infrastructure provisioning
   - RDS, ElastiCache, ECS, ALB
   - Database initialization

3. **[Phase 3: Docker Build & Registry](./PHASE-3-docker-build-registry.md)**
   - Build container images
   - Push to ECR
   - Image security scanning

4. **[Phase 4: Staging Deployment](./PHASE-4-staging-deployment.md)**
   - Deploy to staging
   - Run smoke tests
   - Load testing with k6
   - Design partner validation

5. **[Phase 5: Production Canary](./PHASE-5-production-canary.md)**
   - Canary deployment (5% → 100%)
   - Metric monitoring
   - Rollback procedures

6. **[Phase 6: Post-Launch Operations](./PHASE-6-post-launch-operations.md)**
   - 24/7 monitoring
   - Alert configuration
   - Incident response
   - Success verification

## Key Commands Reference

### Pre-Flight
```bash
bash deployment/scripts/pre-flight-check.sh
```

### Build Docker Images
```bash
bash deployment/scripts/build-images.sh v1.0
```

### Deploy Staging
```bash
bash deployment/scripts/deploy-staging.sh v1.0
```

### Production Canary (Stage 1: 5% traffic)
```bash
bash deployment/scripts/deploy-production-canary.sh 1 v1.0
```

### Monitor Production
```bash
# Watch metrics
watch -n 10 'aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --start-time $(date -u -d "10 minutes ago" "+%Y-%m-%dT%H:%M:%S") \
  --end-time $(date -u "+%Y-%m-%dT%H:%M:%S") \
  --period 60 \
  --statistics Average,p95,p99 \
  --query "Datapoints[0]"'
```

## Configuration

### Environment Variables

Essential variables in `.env.production`:

```bash
# AWS
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# Application
ENVIRONMENT=production
APP_NAME=support-triage-agent
VERSION=v1.0

# Database
DB_INSTANCE_CLASS=db.t3.medium
DB_STORAGE_GB=100
DB_MULTI_AZ=true

# Cache
CACHE_NODE_TYPE=cache.t3.micro
CACHE_NUM_NODES=3

# ECS
ECS_DESIRED_COUNT=3
ECS_CONTAINER_CPU=512
ECS_CONTAINER_MEMORY=1024

# ALB
ALB_PORT=443
SSL_CERTIFICATE_ARN=arn:aws:acm:...

# Monitoring
ALERT_EMAIL=ops-team@example.com
PAGERDUTY_INTEGRATION_KEY=<your-key>
SLACK_WEBHOOK_URL=<your-webhook>
```

## Monitoring & Alerts

### CloudWatch Dashboards

Automatically created dashboards:
- **Application Performance:** Request rate, latency, error rate
- **Infrastructure Health:** CPU, memory, database connections
- **Business Metrics:** Cases processed, SLA compliance
- **Cost Tracking:** Daily spend by service

### Alert Severities

- **P1 (Critical):** Service unavailable, immediate page
- **P2 (High):** Significant degradation, urgent investigation
- **P3 (Medium):** Partial impact, investigate within 1 hour
- **P4 (Low):** Minor issues, backlog

### Alert Recipients

- **Critical:** PagerDuty → On-call engineer
- **High:** Slack #support-triage-alerts + email
- **Medium:** Slack #support-triage-alerts
- **Low:** Issue in Jira

## Incident Response

See [Incident Response Runbook](./incident-response-runbook.md)

Quick reference for common issues:

| Issue | Command |
|-------|---------|
| High error rate | `bash deployment/rollback-procedures.sh` |
| Database connections exhausted | `psql ... -c "SELECT pg_terminate_backend(pid) ...;"` |
| Memory leak in service | `aws ecs update-service --force-new-deployment` |
| API timeout | Check CloudWatch Logs for slow queries |

## Rollback

### Quick Rollback (< 5 minutes)

If issues detected during deployment:

```bash
# Stage 1-2: Stop new version
aws ecs update-service \
  --cluster support-triage-prod \
  --service support-triage-api \
  --desired-count 0 \
  --force-new-deployment

# Verify old version handling 100%
```

### Full Rollback (Requires backup restoration)

See [Rollback Procedures](./rollback-procedures.md)

## Cost Estimation

**Monthly costs for production deployment:**

| Service | Config | Cost |
|---------|--------|------|
| RDS PostgreSQL | db.t3.medium Multi-AZ | $300 |
| ElastiCache | 3x cache.t3.micro | $90 |
| ECS Fargate | 3x (512 CPU, 1GB) | $120 |
| ALB | 1x Application LB | $25 |
| NAT Gateway | 2x HA | $60 |
| Data Transfer | ~100GB/month | ~$10 |
| **Total** | | **~$605** |

## Terraform State

Terraform state files are stored in AWS S3 with DynamoDB locking:

```bash
# View remote state
terraform show

# Check state lock
aws dynamodb scan --table-name terraform-lock

# Emergency unlock (if needed)
aws dynamodb delete-item --table-name terraform-lock \
  --key '{"ID": {"S": "support-triage-prod"}}'
```

## Security

### Secrets Management

All sensitive data stored in AWS Secrets Manager:

```bash
# View database credentials
aws secretsmanager get-secret-value \
  --secret-id support-triage/production/db

# Rotate credentials
aws secretsmanager rotate-secret \
  --secret-id support-triage/production/db \
  --rotation-rules AutomaticallyAfterDays=60
```

### Encryption

- **Data at rest:** AES-256 (RDS, S3, EBS)
- **Data in transit:** TLS 1.2+
- **Secrets:** AWS KMS encryption

### Access Control

- **IAM roles:** EC2 instances, ECS tasks use roles (not access keys)
- **Security groups:** Restrict inbound to required ports only
- **Network ACLs:** Additional network-level filtering

## Backup & Disaster Recovery

### Automated Backups

- **RDS:** Daily snapshots, 30-day retention
- **S3:** Cross-region replication enabled
- **Configuration:** Stored in git (not secrets)

### Restore Procedures

```bash
# List available snapshots
aws rds describe-db-snapshots --db-instance-identifier support-triage-db

# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier support-triage-db-restored \
  --db-snapshot-identifier support-triage-db-snapshot-xyz
```

## Performance Baseline

**Expected production metrics (day 1-7):**

| Metric | Target | Notes |
|--------|--------|-------|
| Availability | 99.9% | 5.4 min downtime/month max |
| Latency p95 | <500ms | Excludes network latency |
| Error rate | <0.1% | Excludes user errors (4xx) |
| Cache hit ratio | >95% | Redis should rarely miss |
| DB CPU | <60% avg | Indicates healthy headroom |

## Troubleshooting

### Deployment Fails at Terraform Apply

```bash
# Validate configuration
terraform validate

# Check for locked resources
terraform refresh

# Get detailed error
terraform apply -var-file=terraform.tfvars -no-color 2>&1 | tail -100
```

### ECS Tasks Won't Start

```bash
# Check task definition
aws ecs describe-task-definition --task-definition support-triage-api:1

# View task logs
aws logs tail /ecs/support-triage-api --follow

# Inspect specific task
aws ecs describe-tasks \
  --cluster support-triage-prod \
  --tasks $(aws ecs list-tasks --cluster support-triage-prod --query 'taskArns[0]' --output text)
```

### ALB Not Receiving Traffic

```bash
# Check target group health
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:...

# Check listener configuration
aws elbv2 describe-listeners \
  --load-balancer-arn arn:aws:elasticloadbalancing:...
```

## Support & Resources

- **AWS Documentation:** [AWS Deployment Best Practices](https://docs.aws.amazon.com/)
- **Terraform:** [AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- **Incident Response:** See [incident-response-runbook.md](./incident-response-runbook.md)
- **On-Call Guide:** [operations/daily-checklist.md](./operations/daily-checklist.md)

## Deployment Checklist

Before going live:

- [ ] Phase 1 pre-flight passed
- [ ] Phase 2 infrastructure created and verified
- [ ] Phase 3 Docker images built and scanned
- [ ] Phase 4 staging tested (smoke, load, chaos)
- [ ] Phase 4 design partner sign-off received
- [ ] Database backups created
- [ ] Monitoring dashboards verified
- [ ] Alert routing configured
- [ ] On-call team trained
- [ ] Incident response runbook reviewed
- [ ] Rollback procedures tested
- [ ] Change management approval obtained
- [ ] Stakeholders notified of deployment window

## Post-Deployment Checklist

After successful production deployment:

- [ ] Monitor dashboards for 24+ hours
- [ ] Verify no critical alerts
- [ ] Customer feedback collected
- [ ] Team debriefing completed
- [ ] Improvements documented
- [ ] 30-day success review scheduled

## Maintenance Schedule

**Weekly:**
- Review dashboards
- Check backup status
- Analyze cost trends

**Monthly:**
- Full disaster recovery drill
- Security audit
- Capacity planning review

**Quarterly:**
- Major version updates
- Infrastructure optimization
- Performance tuning

## Support Contacts

- **Deployment Issues:** devops-team@example.com
- **On-Call Escalation:** ops-escalation@example.com
- **Emergency (24/7):** +1-XXX-XXX-XXXX (PagerDuty)

---

**Last Updated:** 2024  
**Version:** 1.0  
**Status:** Production Ready
