# Railway.app Deployment Guide

**Railway.app is the best free option for Support Triage Agent**

- ✅ Free: $5/month credit (covers everything)
- ✅ Auto-deploy from GitHub
- ✅ PostgreSQL + Redis included
- ✅ Custom domain support
- ✅ Python/FastAPI native
- ✅ No local tools needed
- ✅ 5-minute setup

---

## 📋 Prerequisites

✅ GitHub account (you have this)  
✅ Support-triage-agent repo pushed to GitHub  
✅ Email address

---

## 🚀 Step-by-Step Setup

### **Step 1: Sign Up (1 minute)**

1. Go to: https://railway.app
2. Click **"Login with GitHub"**
3. Authorize Railway to access your repos
4. Accept terms
5. Dashboard loads

### **Step 2: Create New Project (1 minute)**

1. Click **"Create New Project"**
2. Select **"Deploy from GitHub repo"**
3. If prompted: Authorize Railway to GitHub

### **Step 3: Select Your Repository (30 seconds)**

1. Search: `Support-triage-agent`
2. Click repository
3. Select branch: `main`
4. Click **"Deploy"**

Railway will:
- ✅ Clone your repo
- ✅ Detect Python (from pyproject.toml)
- ✅ Build application
- ✅ Auto-start on port 8000

### **Step 4: Add PostgreSQL Database (1 minute)**

1. In Railway dashboard, click **"New"**
2. Select **"Database"**
3. Click **"PostgreSQL"**
4. Click **"Add"**

Railway automatically:
- ✅ Creates PostgreSQL instance
- ✅ Injects `DATABASE_URL` environment variable
- ✅ Connects to your Python app

### **Step 5: Add Redis Cache (1 minute)**

1. Click **"New"** again
2. Select **"Database"**
3. Click **"Redis"**
4. Click **"Add"**

Railway automatically:
- ✅ Creates Redis instance
- ✅ Injects `REDIS_URL` environment variable
- ✅ Connects to your Python app

### **Step 6: Configure Environment Variables (1 minute)**

Click on Python app service → **Variables**

Add (if not auto-detected):
```
ENVIRONMENT=production
LOG_LEVEL=INFO
FLASK_ENV=production
```

Set from Railway defaults:
- `DATABASE_URL` ← Auto from PostgreSQL
- `REDIS_URL` ← Auto from Redis
- `PORT` ← 8000 (auto)

### **Step 7: Deploy (2 minutes)**

Railway deploys automatically:
1. Builds Docker image
2. Runs migrations (if any)
3. Starts application
4. Assigns public URL

Wait for status: **✅ Running**

### **Step 8: Access Your Application (1 minute)**

1. Click on Python service
2. Look for "Public URL" or "Domain"
3. Copy URL: `https://support-triage-[random].railway.app`
4. Test health endpoint:
   ```
   curl https://support-triage-[random].railway.app/health
   ```

Expected response:
```json
{"status": "ok", "version": "1.0"}
```

---

## 🎯 What Happens Automatically

When you push to GitHub:

```
git push origin main
    ↓
GitHub webhook fires
    ↓
Railway receives notification
    ↓
Railway pulls latest code
    ↓
Docker build (30-60 seconds)
    ↓
Start application (10-20 seconds)
    ↓
Application live
```

**Total time:** 1-2 minutes from push to live

---

## 🔒 Security

Railway provides:
- ✅ HTTPS by default
- ✅ Environment variable encryption
- ✅ PostgreSQL password auto-generated
- ✅ Redis password auto-generated
- ✅ Isolated network

No passwords in code needed - all via environment variables.

---

## 📊 Monitoring

In Railway dashboard:

**Logs tab:**
- View real-time application logs
- Errors visible immediately
- Deployments tracked

**Metrics tab:**
- CPU usage
- Memory usage
- Network I/O
- Active connections

**Events tab:**
- Deployment history
- Service status changes
- Automatic restarts

---

## 🚨 Troubleshooting

### App not starting?

Check logs:
1. Click Python service
2. Go to **Logs** tab
3. Look for error messages
4. Common issues:
   - Missing dependencies → Add to pyproject.toml
   - Port conflict → Change PORT env var
   - Database connection → Check DATABASE_URL format

### Database not connecting?

1. PostgreSQL service running?
   - Click PostgreSQL → Check status (should be ✅)
2. DATABASE_URL variable set?
   - Click Python app → Variables → See DATABASE_URL
3. Migrations needed?
   - Run in Railway terminal or before deploy

### Redis not working?

1. Redis service running?
   - Click Redis → Check status
2. REDIS_URL set?
   - Click Python app → Variables → See REDIS_URL
3. Connection timeout?
   - Check network configuration

### Domain/URL access issues?

- **New deployment:** Wait 2-3 minutes
- **Custom domain:** Go to Settings → Custom Domain
- **HTTPS:** Auto-enabled
- **DNS:** Point to Railway's nameserver

---

## 💰 Cost & Free Tier

### Monthly Credit: $5

Your usage:
```
Python App:
  24/7 uptime (730 hours) × $0.007/hour = $5.10

PostgreSQL:
  Base tier (5GB, 1000 connections) = $5.00

Redis:
  Base tier (1GB) = $3.00

Total: $13.10
```

**But with $5 monthly credit for first 3 months:**
```
Cost = $13.10 - $5.00 = ~$8/month
```

**After 3 months:** ~$13-15/month (affordable)

### How to stay free longer:

1. **Limit background jobs** (use queues efficiently)
2. **Optimize database queries** (add indexes)
3. **Use CDN for static files** (Cloudflare free)
4. **Monitor resource usage** (Railway dashboard)

---

## 🔄 Continuous Deployment

Once set up, deployment is automatic:

```
Local: git push origin main
    ↓
GitHub receives code
    ↓
Railway webhook triggers
    ↓
Railway deploys automatically
    ↓
Application updates live
```

No manual deployment needed!

---

## 🎓 Advanced Features

### Custom Domain

1. Buy domain (GoDaddy, Namecheap, etc.)
2. In Railway: Settings → Domains
3. Add custom domain
4. Update DNS records (Railway provides)
5. HTTPS auto-generated (Let's Encrypt)

### Environment-specific configs

Create multiple deployments:
```
main branch → Production (railway.app)
staging → Staging environment
dev → Development environment
```

Each has own database, Redis, URL

### Scheduled jobs

```python
# In your FastAPI app
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_task, 'cron', hour=2, minute=0)
scheduler.start()
```

Railway keeps app running 24/7 for cron jobs.

---

## 📱 Dashboard Overview

**Main page shows:**
- ✅ Project name
- ✅ Active services (Python, PostgreSQL, Redis)
- ✅ Public URLs
- ✅ Deployment history
- ✅ Resource usage
- ✅ Team members

**Service page shows:**
- ✅ Service name & status
- ✅ Environment variables
- ✅ Recent logs
- ✅ Deployment logs
- ✅ Resource limits
- ✅ Recent deployments

---

## ✨ What's Different from AWS

| Feature | AWS | Railway |
|---------|-----|---------|
| Setup time | 30 min | 5 min |
| Cost | Free tier (90 days) | Free tier (always) |
| GitHub integration | Manual | Auto |
| Database | Separate | Included |
| Redis | Separate | Included |
| Scaling | Manual | Auto |
| Monitoring | CloudWatch | Built-in |
| Custom domain | Paid extras | Included |

---

## 🎬 Quick Reference

| Task | Command/Step |
|------|---|
| **Sign up** | https://railway.app → GitHub auth |
| **Deploy repo** | New Project → GitHub repo |
| **Add database** | New service → PostgreSQL |
| **Add Redis** | New service → Redis |
| **View logs** | Click service → Logs tab |
| **Set variables** | Click service → Variables |
| **Custom domain** | Settings → Domains |
| **View metrics** | Click service → Metrics |
| **Redeploy** | git push origin main |
| **Check status** | Dashboard shows ✅/❌ |

---

## ✅ Success Checklist

- [ ] Signed up to Railway
- [ ] Connected GitHub account
- [ ] Imported Support-triage-agent repo
- [ ] Added PostgreSQL service
- [ ] Added Redis service
- [ ] Application status shows ✅ Running
- [ ] Public URL assigned
- [ ] Health endpoint responds
- [ ] Can view logs in dashboard
- [ ] Set up custom domain (optional)

---

## 🚀 Next: Deploy Now!

**Go to:** https://railway.app

Follow steps above. Your app will be live in ~5 minutes.

**Questions?**
- Railway docs: https://docs.railway.app
- Support: help@railway.app

**That's it! Completely free, no AWS, no local tools.**
