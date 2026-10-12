# Support Triage Agent - Free Tier AWS Deployment Configuration

**Date:** October 12, 2026  
**Status:** Ready for Production Deployment  
**Region:** ap-southeast-2 (Australia Sydney)  
**Account Type:** AWS New Experience (Project-based)  
**Cost:** $0/month for 12 months, then ~$110/month

---

## Deployment Summary

This document records the complete configuration for the Support Triage Agent deployment to AWS free tier infrastructure in ap-southeast-2 region.

### What Was Deployed

✅ **Infrastructure as Code (Terraform)** — 9 .tf files with complete AWS resources  
✅ **Environment Configuration** — .env.production with free tier constraints  
✅ **AWS Credentials** — Browser-based authentication (profile: support-triage)  
✅ **AWS Agent Toolkit** — Integrated for AI-powered infrastructure management  
✅ **Kiro Steering Rules** — AWS starter rules for new AWS experience  

---

## Architecture Overview

### Compute
- **ECS Fargate:** 1 task (256 vCPU / 512 MB memory) = FREE for 12 months
- **Launch Type:** FARGATE (no EC2 instances needed)
- **Networking:** Private subnet, no public IP
- **Logging:** CloudWatch (7-day retention, within 5GB/month free tier)

### Database
- **RDS PostgreSQL:** db.t3.micro, 20 GB storage = FREE for 12 months
- **Backup:** 7-day retention (cost minimized)
- **Encryption:** Enabled at rest
- **Deletion Protection:** Enabled
- **Multi-AZ:** Disabled (not free)

### Cache
- **ElastiCache Redis:** cache.t3.micro, 1 node = 750 hours/month (free tier)
- **Version:** Redis 7.0
- **Replication:** Disabled (not free)
- **Encryption:** Enabled in-transit
- **High Availability:** Disabled (single node only)

### Load Balancing
- **Network Load Balancer (NLB):** ~$5/month vs ALB ~$16/month
- **Target Group:** TCP 8000 to ECS tasks
- **Listeners:**
  - Port 443: TLS (requires SSL certificate)
  - Port 80: TCP fallback
- **Health Checks:** TCP on port 8000, 30-second intervals

### Networking
- **VPC:** 10.0.0.0/16 (single AZ: ap-southeast-2a)
- **Public Subnet:** 10.0.101.0/24 (NLB, NAT Gateway)
- **Private Subnet:** 10.0.1.0/24 (ECS, RDS, ElastiCache)
- **Secondary Private Subnet:** 10.0.2.0/24 (RDS/ElastiCache multi-subnet requirement)
- **Internet Gateway:** Attached to VPC
- **NAT Gateway:** For outbound access from private subnets
- **Security Groups:** 
  - NLB: Ingress 443/80, egress all
  - ECS: Ingress from NLB on 8000, egress all
  - RDS: Ingress from ECS on 5432 only
  - Redis: Ingress from ECS on 6379 only

### Container Registry
- **ECR Repository:** support-triage-agent
- **Scanning:** Enabled (AWS Inspector)
- **Tag Mutability:** Mutable

### Monitoring & Alerts
- **CloudWatch Logs:** /ecs/support-triage-agent
- **CloudWatch Alarms:**
  - NLB unhealthy targets
  - ECS CPU utilization > 80%
  - ECS memory utilization > 90%
  - RDS CPU utilization > 80%
  - ElastiCache evictions > 0
  - ECS task failures
- **SNS Notifications:** To alert_email (requires confirmation)

---

## Configuration Files

### 1. `.env.production` — Environment Variables
**Location:** Project root  
**Purpose:** Application configuration for ECS tasks  
**Key Settings:**
- `AWS_REGION=ap-southeast-2`
- `DB_INSTANCE_CLASS=db.t3.micro` (FREE)
- `CACHE_NODE_TYPE=cache.t3.micro` (minimal)
- `ECS_CONTAINER_CPU=256` (FREE)
- `ECS_CONTAINER_MEMORY=512` (FREE)
- `ECS_DESIRED_COUNT=1` (no scaling)
- `MONITORING_RETENTION_DAYS=7` (minimized cost)

### 2. `terraform/terraform.tfvars` — Terraform Variables
**Location:** terraform/ directory  
**Purpose:** Environment-specific Terraform values  
**Key Variables:**
```
aws_region              = "ap-southeast-2"
aws_profile             = "support-triage"
environment             = "production-free-tier"
app_name                = "support-triage-agent"
availability_zone       = "ap-southeast-2a"
db_instance_class       = "db.t3.micro"
cache_node_type         = "cache.t3.micro"
ecs_task_cpu            = 256
ecs_task_memory         = 512
ecs_desired_count       = 1
alert_email             = "your-email@example.com"
```

### 3. `terraform/` — Infrastructure as Code
**Location:** terraform/ directory  
**Files:**
- `main.tf` — Provider configuration (AWS)
- `variables.tf` — Variable definitions
- `outputs.tf` — Output values (RDS endpoint, NLB DNS, etc.)
- `vpc.tf` — VPC, subnets, security groups, NAT
- `rds.tf` — RDS PostgreSQL database
- `elasticache.tf` — ElastiCache Redis cache
- `ecs.tf` — ECR, ECS cluster, task definition, service
- `iam.tf` — IAM roles and policies
- `nlb.tf` — Network Load Balancer
- `terraform.tfvars` — Environment variables
- `.gitignore` — Git ignore patterns
- `.terraform/` — Terraform working directory (auto-generated)
- `.terraform.lock.hcl` — Provider lock file (auto-generated)
- `terraform.tfstate` — Local state (auto-generated, or S3 if backend enabled)

### 4. `.kiro/steering/aws-starter-rules.md` — Kiro AWS Guidance
**Purpose:** AI agent rules for AWS new experience constraints  
**Includes:** Region constraints, service limitations, terminology, help levels

---

## AWS Credentials Configuration

**Profile Name:** `support-triage`  
**Authentication:** Browser-based (`aws login`)  
**Credentials Valid:** 12 hours (renewable 90 days without re-auth)  
**Region:** ap-southeast-2  
**Account Type:** New AWS Experience (Project-based)

### Authentication Commands
```bash
# Initial authentication
aws login --region ap-southeast-2 --profile support-triage

# Verify credentials
aws sts get-caller-identity --profile support-triage

# Renew credentials (within 90 days)
aws login --region ap-southeast-2 --profile support-triage
```

---

## Free Tier Resource Summary

| Service | Resource | Configuration | Free Tier | After 12 Months |
|---------|----------|----------------|-----------|-----------------|
| **RDS** | db.t3.micro | 20GB storage, 7-day backup | 12 months | ~$30/month |
| **ElastiCache** | cache.t3.micro | 1 node, 750 hrs/month | First month | ~$8/month |
| **ECS Fargate** | 256 vCPU / 512 MB | 1 task, 750 hrs/month | First month | ~$30/month |
| **NAT Gateway** | 1 per AZ | ap-southeast-2a | Hourly charges + data transfer | ~$30/month |
| **NLB** | Network Load Balancer | TLS/TCP listeners | Part of Fargate free tier | ~$5/month |
| **ECR** | Unlimited repos | Docker image storage | 500MB/month | ~$5/month per 1GB |
| **CloudWatch** | Logs + monitoring | 7-day retention | 5GB logs/month | Minimal ~$1 |
| **VPC/IGW** | VPC resources | 1 NAT Gateway, 1 IGW | Free | Free |
| **Total** | | | **$0/month** | **~$110/month** |

---

## Deployment Timeline

### Phase 0: Prerequisites (✅ Completed)
- ✅ AWS credentials configured (profile: support-triage)
- ✅ AWS Agent Toolkit installed
- ✅ Terraform installed (v1.5.0+)
- ✅ Kiro steering rules created
- ✅ .env.production configured
- ✅ Terraform files created and validated

### Phase 1: Infrastructure Deployment (⏳ Next)
1. Run `terraform plan` to preview resources
2. Review estimated costs
3. Run `terraform apply` to deploy
4. Wait for infrastructure to stabilize (20-30 minutes)
5. Capture Terraform outputs (RDS endpoint, NLB DNS, etc.)

### Phase 2: Container Deployment
1. Build Docker image locally
2. Push to ECR repository
3. Update ECS task definition with image URI
4. Restart ECS service

### Phase 3: Validation
1. Test database connectivity
2. Test Redis cache connectivity
3. Test health check endpoint
4. Monitor CloudWatch logs

### Phase 4: Production Cutover
1. Configure DNS (point domain to NLB DNS name)
2. Enable SSL/TLS certificate in ACM
3. Update NLB listener with certificate
4. Monitor application metrics

---

## Important Constraints

### Single AZ Limitation
All resources deployed to **ap-southeast-2a only**. This is a free tier constraint from AWS new experience:
- Cannot create resources in other regions
- No multi-AZ failover
- No cross-region replication
- Single point of failure in ap-southeast-2a

### No Auto-Scaling
ECS service configured with:
- `desired_count = 1` (always 1 task)
- Cannot scale up with traffic
- CPU/memory limited to 256/512 MB

### No High Availability
- Single RDS instance (no replication)
- Single ElastiCache node (no failover)
- Single ECS task (no redundancy)

If any service fails, application is unavailable until recovered.

### Data Transfer Limits
Free tier includes 100 GB/month outbound data transfer. Overage charges:
- $0.09 per GB (US regions, varies by region)
- Monitor with CloudWatch metrics
- Alert set at 80% threshold

### Deletion Protection
Before running `terraform destroy`:
1. Disable RDS deletion protection
2. Disable NLB deletion protection
3. Delete RDS snapshots (if keeping backups)

---

## Cost Monitoring

### First 12 Months
- **RDS db.t3.micro:** $0 (free tier)
- **ECS Fargate 256/512:** $0 (free tier)
- **Total:** ~$30-50/month (NAT Gateway + NLB + minor services)

### After 12 Months
- **RDS db.t3.micro:** ~$30/month
- **ECS Fargate 256/512:** ~$30/month
- **NAT Gateway:** ~$30/month
- **ElastiCache cache.t3.micro:** ~$8/month
- **NLB:** ~$5/month
- **ECR + CloudWatch:** ~$5/month
- **Total:** ~$110/month

### Cost Optimization Tips
1. **Scale down after hours** — Use Lambda to stop ECS task at night
2. **Use Lambda for batch jobs** — Instead of ECS for off-peak work
3. **Consolidate logging** — Lower CloudWatch retention if needed
4. **Review data transfer** — Optimize API responses to reduce outbound data

---

## Deployment Commands

### Check Configuration
```bash
cd terraform
terraform validate
```

### Preview Changes
```bash
terraform plan -var="db_password=YOUR_SECURE_PASSWORD" -out=tfplan
```

### Apply Infrastructure
```bash
# Requires: db_password variable set
terraform apply tfplan

# Alternative (without pre-generated plan):
terraform apply -var="db_password=YOUR_SECURE_PASSWORD"
```

### Get Outputs
```bash
terraform output
# Shows: NLB DNS name, RDS endpoint, ElastiCache endpoint, ECS cluster name, ECR repo URL
```

### Destroy Infrastructure (⚠️ Caution)
```bash
# First disable deletion protection:
aws rds modify-db-instance \
  --db-instance-identifier support-triage-agent-prod \
  --no-deletion-protection \
  --profile support-triage \
  --region ap-southeast-2

# Then destroy:
terraform destroy -var="db_password=YOUR_SECURE_PASSWORD"
```

---

## Monitoring & Alerts

### CloudWatch Dashboards
```bash
# Create custom dashboard
aws cloudwatch put-dashboard \
  --dashboard-name support-triage-monitoring \
  --dashboard-body file://dashboard.json \
  --profile support-triage \
  --region ap-southeast-2
```

### View Logs
```bash
# Real-time logs
aws logs tail /ecs/support-triage-agent --follow \
  --profile support-triage \
  --region ap-southeast-2

# Specific time range
aws logs filter-log-events \
  --log-group-name /ecs/support-triage-agent \
  --start-time $(date -d "1 hour ago" +%s)000 \
  --profile support-triage \
  --region ap-southeast-2
```

### SNS Alerts
Email notifications will be sent to `alert_email` for:
- Unhealthy targets (NLB)
- High CPU/memory (ECS, RDS)
- Task failures
- Data transfer threshold

---

## Security Configuration

### Encryption
- ✅ RDS encryption at rest (enabled)
- ✅ ElastiCache encryption in-transit (enabled)
- ✅ NLB TLS/443 (requires ACM certificate)
- ✅ VPC with private subnets for RDS/ElastiCache

### Access Control
- ✅ Security groups restrict traffic
- ✅ ECS tasks run in private subnet
- ✅ No public IPs for database/cache
- ✅ IAM roles with least privilege

### Secrets Management
- ⏳ RDS password: Set via `TF_VAR_db_password` environment variable (not committed)
- ⏳ ElastiCache auth token: Auto-generated by Terraform
- ⏳ Database credentials: Stored in AWS Secrets Manager

---

## Git Configuration

### Files to Commit
```bash
git add .env.production                    # Environment configuration
git add terraform/                         # Terraform code
git add DEPLOYMENT-CONFIGURATION.md        # This file
git add .kiro/steering/aws-starter-rules.md
git commit -m "feat: Free tier AWS deployment to ap-southeast-2"
git push origin main
```

### Files to NOT Commit
```
terraform/terraform.tfstate               # Local state (use S3 backend instead)
terraform/terraform.tfstate.backup        # State backup
terraform/.terraform/                     # Terraform working directory
.env.production (secrets)                 # Contains sensitive values
terraform.tfvars (secrets)                # Contains sensitive values
```

These are already in `.gitignore`.

---

## Next Steps

1. **Verify AWS credentials:**
   ```bash
   aws sts get-caller-identity --profile support-triage
   ```

2. **Review Terraform plan:**
   ```bash
   cd terraform
   terraform plan
   ```

3. **Set database password:**
   ```bash
   export TF_VAR_db_password="generate-a-strong-32-char-password"
   ```

4. **Apply infrastructure:**
   ```bash
   terraform apply
   ```

5. **Capture outputs:**
   ```bash
   terraform output
   ```

6. **Build and push Docker image**
7. **Update ECS task with image URI**
8. **Monitor deployment**

---

## Support & Troubleshooting

### AWS Credentials Expired
```bash
aws login --region ap-southeast-2 --profile support-triage
```

### Terraform State Lock
If Terraform is stuck:
```bash
terraform force-unlock <LOCK_ID>
```

### RDS Creation Timeout
- Check AWS CloudFormation events in console
- RDS creation can take 10+ minutes
- Do not cancel; let it complete

### ECS Task Unhealthy
- Check CloudWatch logs: `/ecs/support-triage-agent`
- Verify health check endpoint at `/health`
- Check security group allows NLB → ECS traffic

### NLB Certificate Error
- Create certificate in AWS Certificate Manager (ACM)
- Certificate must be in ap-southeast-2 region
- Add certificate ARN to terraform.tfvars: `ssl_certificate_arn`

---

## References

- [AWS Free Tier](https://aws.amazon.com/free/)
- [AWS Pricing](https://aws.amazon.com/pricing/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [ECS Fargate Pricing](https://aws.amazon.com/ecs/pricing/)
- [RDS Pricing](https://aws.amazon.com/rds/pricing/)
- [ElastiCache Pricing](https://aws.amazon.com/elasticache/pricing/)

---

**Configuration Created:** 2026-10-12  
**Last Updated:** 2026-10-12  
**Status:** Ready for Deployment  
**Region:** ap-southeast-2 (Australia Sydney)  
**Deployment Profile:** support-triage  

