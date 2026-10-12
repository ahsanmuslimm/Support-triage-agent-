# Railway.app - Quick Start Deployment

**Deploy your Support Triage Agent in 5 minutes!**

---

## ✅ Pre-Deployment Checklist

Before you start, verify:

- [ ] GitHub account ready
- [ ] Support-triage-agent repo committed and pushed
- [ ] All code committed (check: `git status` shows clean)
- [ ] `.env.production` file exists in repo
- [ ] `Dockerfile` exists in repo
- [ ] `pyproject.toml` has all dependencies

**Status:** All ✅ (ready to go!)

---

## 🚀 Step 1: Go to Railway.app

**Open your browser:**
```
https://railway.app
```

---

## 🚀 Step 2: Sign Up with GitHub

1. Click **"Login with GitHub"**
2. Authorize Railway to access your GitHub account
3. Choose your username
4. Verify email (if prompted)
5. Dashboard loads

---

## 🚀 Step 3: Create New Project

1. Click **"Create New Project"**
2. Select **"Deploy from GitHub repo"**
3. If prompted: "Authorize GitHub" → Allow

---

## 🚀 Step 4: Select Your Repository

1. Search for: `Support-triage-agent`
2. Click on your repository
3. Select branch: **`main`**
4. Click **"Deploy"**

Railway will:
- Clone your repo
- Detect Python
- Build application
- Start deployment

**Status shown:** "Building..." → "Running"

---

## 🚀 Step 5: Add PostgreSQL Database

1. In Railway dashboard, click **"New"** (or + button)
2. Select **"Database"**
3. Click **"PostgreSQL"**
4. Click **"Add"**

Railway will:
- Create PostgreSQL instance
- Auto-inject `DATABASE_URL` env variable
- Connect to your Python app

**Status shown:** "Running" with PostgreSQL in services list

---

## 🚀 Step 6: Add Redis Cache

1. Click **"New"** again
2. Select **"Database"**
3. Click **"Redis"**
4. Click **"Add"**

Railway will:
- Create Redis instance
- Auto-inject `REDIS_URL` env variable
- Connect to your Python app

**Status shown:** "Running" with Redis in services list

---

## 🚀 Step 7: Verify Environment Variables

Click on **Python app service** → **"Variables"**

You should see auto-populated:
```
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
PORT=8000
```

If not visible yet, wait 30 seconds for Railway to inject them.

---

## 🚀 Step 8: Wait for Deployment

Dashboard shows progress:
```
Building... (30-60 seconds)
   ↓
Starting... (10-20 seconds)
   ↓
Running ✅ (2-3 minutes total)
```

Watch the status change. Look for:
- ✅ Python service: Running
- ✅ PostgreSQL: Running
- ✅ Redis: Running

---

## 🚀 Step 9: Get Your Public URL

Once "Running" status shows:

1. Click on **Python app service**
2. Look for **"Public URL"** or **"Domain"**
3. Copy the URL (looks like: `https://support-triage-[random].railway.app`)

---

## 🚀 Step 10: Test Your Application

Open browser and go to:
```
https://support-triage-[YOUR-URL].railway.app/health
```

You should see:
```json
{"status": "ok", "version": "1.0"}
```

If you see this, **YOUR APP IS LIVE!** 🎉

---

## 📊 View Logs (If Issues)

Click on **Python service** → **"Logs"** tab

You'll see:
- Application startup logs
- Error messages (if any)
- Request logs
- Database connection status

---

## 🎯 After Deployment: Next Steps

### Test the application:
```bash
# Health check
curl https://support-triage-[YOUR-URL].railway.app/health

# Get version
curl https://support-triage-[YOUR-URL].railway.app/version

# Try triage endpoint (if exposed)
curl -X POST https://support-triage-[YOUR-URL].railway.app/api/triage \
  -H "Content-Type: application/json" \
  -d '{"text":"My order is broken"}'
```

### Set up auto-deployment:
Every time you `git push` to GitHub:
- Railway webhook triggers
- Code pulled
- App rebuilt
- New version deployed

**No manual steps needed!**

### Add custom domain (optional):
1. Go to **Settings** → **Domains**
2. Add your custom domain
3. Update DNS records (Railway shows instructions)
4. HTTPS auto-generated

---

## 🆘 Troubleshooting

### App won't start?
1. Check **Logs** tab for errors
2. Common issues:
   - Missing environment variables
   - Database connection failed
   - Import errors in code
3. Fix locally, commit, push → auto-redeploys

### Database not connecting?
1. Check PostgreSQL status (should be ✅ Running)
2. Check `DATABASE_URL` is set (Variables tab)
3. Check logs for connection errors

### Redis not connecting?
1. Check Redis status (should be ✅ Running)
2. Check `REDIS_URL` is set (Variables tab)
3. Check logs for connection errors

### Application times out?
1. Check Python service resources
2. Can upgrade to larger plan if needed
3. Check for infinite loops in code

---

## 📱 Dashboard Overview

Once deployed, your Railway dashboard shows:

**Services:**
- Python (your app)
- PostgreSQL (database)
- Redis (cache)

**Each service shows:**
- Status (Running / Stopped / Building)
- Public URL (only Python has this)
- Resource usage (CPU, Memory)
- Recent logs
- Deployment history

**Settings:**
- Environment variables
- Custom domains
- Team members
- Billing

---

## ✨ Congratulations!

Your Support Triage Agent is now:
- ✅ Deployed to Railway.app
- ✅ Running 24/7
- ✅ Publicly accessible
- ✅ Auto-scaling
- ✅ Monitored
- ✅ Production-ready

---

## 📊 What You Have

**Live Infrastructure:**
```
https://support-triage-[random].railway.app
├─ FastAPI backend (your code)
├─ PostgreSQL database (connected)
├─ Redis cache (connected)
└─ HTTPS/SSL (automatic)
```

**Capabilities:**
- ✅ Multi-user triage
- ✅ Ticket storage
- ✅ Sentiment analysis
- ✅ Escalation workflows
- ✅ Real-time monitoring
- ✅ Analytics dashboard

---

## 🎬 Go Live Now!

**URL:** https://railway.app

**Timeline:**
1. Sign up (1 minute)
2. Create project (1 minute)
3. Add services (2 minutes)
4. Wait for build (2 minutes)
5. **LIVE!** ✨

**Total: 5 minutes to production**

---

## 💡 Remember

- Every `git push` triggers automatic deployment
- Logs are available in dashboard
- Custom domain available in Settings
- Team members can be added
- Scaling automatic as traffic grows

---

**Let's go! Visit https://railway.app now!** 🚀
