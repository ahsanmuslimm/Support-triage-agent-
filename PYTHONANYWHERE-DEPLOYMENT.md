# PythonAnywhere Deployment Guide

**PythonAnywhere is perfect for always-on hosting without idle timeout**

- ✅ Always running (no sleep after idle)
- ✅ Free tier available
- ✅ Python-optimized hosting
- ✅ PostgreSQL + MySQL support
- ✅ Web framework support (FastAPI)
- ✅ Background tasks
- ✅ Custom domain support
- ✅ Easy to use

---

## 📊 Comparison: Railway vs PythonAnywhere

| Feature | Railway | PythonAnywhere |
|---------|---------|---|
| **Idle timeout** | ❌ No (always on) | ❌ No (always on) |
| **Free tier** | Yes ($5 credit) | Yes (limited) |
| **Auto-deploy from GitHub** | ✅ Yes | ⚠️ Manual setup |
| **PostgreSQL** | ✅ Included | ⚠️ Requires extra setup |
| **Redis** | ✅ Included | ⚠️ External only |
| **Setup time** | 5 min | 20-30 min |
| **Always running** | ✅ Yes | ✅ Yes |
| **Custom domain** | ✅ Free | ⚠️ Paid only |
| **Price/month** | $13 | $5-12 |
| **Beginner friendly** | ✅ Yes | ⚠️ More complex |

---

## 🎯 When to Use PythonAnywhere

Choose PythonAnywhere if:
- ✅ You want simple Python hosting
- ✅ You want lowest cost
- ✅ You don't need auto-deploy
- ✅ You prefer manual control
- ✅ You're comfortable with FTP/manual uploads

---

## 🚀 PythonAnywhere Setup (20-30 minutes)

### **Part 1: Create PythonAnywhere Account (2 minutes)**

1. Go to: https://www.pythonanywhere.com
2. Click **"Sign up"**
3. Choose plan: **"Beginner"** (free)
4. Register with email
5. Verify email
6. Login to dashboard

### **Part 2: Set Up Web App (5 minutes)**

1. Dashboard → **"Web"** tab
2. Click **"Add a new web app"**
3. Choose domain: `your-username.pythonanywhere.com`
4. Select Python framework: **"Flask"** or **"Manual"**
   - Choose **"Manual configuration"** for FastAPI
5. Python version: **3.12**
6. Create

PythonAnywhere creates:
- ✅ Web app configuration
- ✅ Public URL: `your-username.pythonanywhere.com`
- ✅ WSGI configuration file

### **Part 3: Upload Your Code (5-10 minutes)**

**Option A: Clone from GitHub (recommended)**

1. PythonAnywhere → **Files** tab
2. Click **Upload a new file** → Select files
3. Or use **Console** tab:

```bash
cd /home/your-username
git clone https://github.com/your-username/Support-triage-agent-.git
cd Support-triage-agent-
```

**Option B: Manual upload**

1. Compress your project: `support-triage-agent.zip`
2. PythonAnywhere → **Files** tab
3. Upload ZIP file
4. Extract in file manager

### **Part 4: Install Dependencies (5 minutes)**

1. Dashboard → **Consoles** tab
2. Click **"Start a new console"** → **"Bash"**
3. Run commands:

```bash
cd /home/your-username/Support-triage-agent-

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
# OR if using pyproject.toml:
pip install uv
uv sync
```

### **Part 5: Configure WSGI (5 minutes)**

PythonAnywhere needs WSGI configuration for FastAPI.

1. Dashboard → **Web** tab
2. Find **"WSGI configuration file"** → Click to edit
3. Replace content with:

```python
import sys
import os

# Add your project to path
project_home = '/home/your-username/Support-triage-agent-'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Import FastAPI app
os.chdir(project_home)
from services.api.src.triage.api.main import app

# WSGI application
application = app
```

4. Save

### **Part 6: Set Environment Variables (3 minutes)**

1. Dashboard → **Web** tab
2. Scroll to **"Environment variables"**
3. Add:

```
DATABASE_URL=postgres://user:pass@host/db
REDIS_URL=redis://host:port/0
ENVIRONMENT=production
LOG_LEVEL=INFO
```

For PythonAnywhere free tier, use external services:
- **PostgreSQL:** Supabase (free tier: 500MB)
- **Redis:** Upstash (free tier: 10,000 commands/day)

### **Part 7: Deploy & Test (2 minutes)**

1. Dashboard → **Web** tab
2. Click **"Reload"** button
3. Status changes to **✅ Running**
4. Access: `https://your-username.pythonanywhere.com`
5. Test health: `https://your-username.pythonanywhere.com/health`

---

## 📦 Setting Up External Databases

### **PostgreSQL: Use Supabase (Free Tier)**

1. Go to: https://supabase.com
2. Click **"Start your project"**
3. Sign up with GitHub
4. Create project
5. Copy connection string:
   ```
   postgresql://user:password@host/db
   ```
6. Add to PythonAnywhere environment variables:
   ```
   DATABASE_URL=postgresql://...
   ```

**Supabase Free Tier:**
- 500MB database
- Unlimited API requests
- Good for MVP

### **Redis: Use Upstash (Free Tier)**

1. Go to: https://upstash.com
2. Sign up
3. Create Redis database
4. Copy connection URL:
   ```
   redis://default:password@host:port
   ```
5. Add to PythonAnywhere:
   ```
   REDIS_URL=redis://...
   ```

**Upstash Free Tier:**
- 1GB storage
- 10,000 commands/day
- Good for caching

---

## 🔄 Updating Your Application

### After making changes locally:

**Option 1: Git pull in PythonAnywhere**

```bash
# In PythonAnywhere Bash console
cd /home/your-username/Support-triage-agent-
git pull origin main
source venv/bin/activate
uv sync  # If dependencies changed
```

Then reload from Web tab.

**Option 2: Manual file upload**

1. Make changes locally
2. Compress updated files
3. Upload ZIP to PythonAnywhere
4. Extract and replace files
5. Reload web app

---

## 📊 Monitoring & Logs

PythonAnywhere provides:

**Web logs:**
- Dashboard → **Web** tab
- Click on app name
- View **Error log**, **Access log**, **Server log**

**Console output:**
- Run test commands in Bash console
- See output immediately

**Resource usage:**
- **CPU time:** Free tier: 100 seconds/day
- **RAM:** Free tier: 512 MB
- **Disk:** Free tier: 512 MB

**Scaling if needed:**
- Free → Beginner ($5/month): 1 CPU, 1GB RAM
- Beginner → Hacker ($19/month): 2 CPUs, 2GB RAM

---

## 💰 Cost Breakdown

### Free Tier
```
Python hosting: FREE (512MB RAM, 100s CPU/day)
Domain: your-username.pythonanywhere.com
PostgreSQL: Use Supabase (free tier: 500MB)
Redis: Use Upstash (free tier: 1GB)

Total: $0/month
```

**Limitation:** 100 seconds of CPU per day (enough for ~200-300 requests)

### Beginner Plan ($5/month)
```
Python hosting: $5
Unlimited CPU time
1GB RAM
Domain: your-username.pythonanywhere.com
PostgreSQL: Supabase free ($0)
Redis: Upstash free ($0)

Total: $5/month
```

**Recommendation:** Start free, upgrade to Beginner if needed

---

## ⚠️ PythonAnywhere Limitations

### Free Tier Limits
- **CPU time:** 100 seconds/day (~200-300 requests)
- **RAM:** 512 MB
- **Disk:** 512 MB
- **Custom domain:** ❌ Not available
- **Background tasks:** Limited
- **Scheduled tasks:** Limited

### Workarounds
- Use async tasks (Celery) via Upstash
- Optimize database queries
- Cache aggressively
- Upgrade to Beginner plan ($5/month)

---

## 🚀 Full Setup Checklist

### Before Starting
- [ ] Support Triage Agent repo ready
- [ ] All code committed to GitHub
- [ ] Python 3.12 compatible

### PythonAnywhere Setup
- [ ] Account created
- [ ] Free tier selected
- [ ] Web app created

### Code Upload
- [ ] Code cloned or uploaded
- [ ] Virtual environment created
- [ ] Dependencies installed

### Configuration
- [ ] WSGI file configured for FastAPI
- [ ] Environment variables set
- [ ] Database credentials added

### Databases
- [ ] Supabase PostgreSQL created
- [ ] Upstash Redis created
- [ ] Connection strings in env vars

### Testing
- [ ] Web app reloaded
- [ ] Public URL accessible
- [ ] Health endpoint responds
- [ ] Logs show no errors

### Optimization
- [ ] Response times acceptable
- [ ] Database queries optimized
- [ ] Caching configured
- [ ] Ready for users

---

## 🆘 Troubleshooting

### App not accessible?

1. Check web status: Dashboard → **Web** → Status shows ✅
2. Reload web app: Dashboard → **Web** → Click **"Reload"**
3. Check error log: Dashboard → **Web** → **Error log**
4. Verify URL: `https://your-username.pythonanywhere.com`

### 502 Bad Gateway?

1. Check WSGI configuration
2. Verify app imports work
3. Check error log for Python errors
4. Ensure all dependencies installed

### Database connection failed?

1. Check DATABASE_URL format
2. Verify Supabase credentials
3. Check network access rules
4. Test connection in console:
   ```bash
   python3 -c "import psycopg2; psycopg2.connect(os.environ['DATABASE_URL'])"
   ```

### Redis connection failed?

1. Check REDIS_URL format
2. Verify Upstash credentials
3. Test connection:
   ```bash
   python3 -c "import redis; redis.from_url(os.environ['REDIS_URL']).ping()"
   ```

### Exceeding CPU limit?

1. Optimize database queries (add indexes)
2. Implement caching
3. Use background task queues
4. Upgrade to Beginner plan ($5/month)

---

## 📱 Custom Domain (Paid Feature)

To use custom domain (requires paid plan):

1. Buy domain: GoDaddy, Namecheap, etc.
2. PythonAnywhere → **Web** tab
3. Add custom domain
4. Update DNS records (PythonAnywhere provides)
5. SSL certificate auto-generated

---

## 🔒 Security

PythonAnywhere provides:
- ✅ HTTPS by default
- ✅ Environment variable encryption
- ✅ Isolated accounts
- ✅ DDoS protection
- ✅ Automatic security updates

---

## ✨ Key Differences from Railway

| Feature | Railway | PythonAnywhere |
|---------|---------|---|
| **Setup** | 5 min (auto-deploy) | 20-30 min (manual) |
| **Idle timeout** | ❌ Always on | ❌ Always on |
| **Free database** | ✅ Included | ⚠️ External only |
| **GitHub integration** | ✅ Auto | ⚠️ Manual git pull |
| **Beginner friendly** | ✅ Yes | ⚠️ More steps |
| **Cost** | $13/mo | $5/mo (or free) |
| **Scalability** | ✅ Auto-scale | ⚠️ Manual upgrade |

---

## 🎯 Quick Start

```
1. Go to: https://www.pythonanywhere.com
2. Sign up (free tier)
3. Create web app (Python 3.12)
4. Clone repo from GitHub
5. Create virtual environment
6. Install dependencies
7. Configure WSGI for FastAPI
8. Add environment variables
9. Set up Supabase (PostgreSQL)
10. Set up Upstash (Redis)
11. Click Reload
12. Test: https://your-username.pythonanywhere.com/health
13. Live! ✨
```

---

## 📚 Links

- **PythonAnywhere:** https://www.pythonanywhere.com
- **PythonAnywhere Docs:** https://help.pythonanywhere.com
- **Supabase:** https://supabase.com (PostgreSQL)
- **Upstash:** https://upstash.com (Redis)

---

## ✅ When to Choose PythonAnywhere

Choose PythonAnywhere if you want:
- ✅ Always-on hosting (no idle timeout)
- ✅ Cheapest option ($5/month)
- ✅ Simple Python hosting
- ✅ No auto-deploy needed
- ✅ Easy scalability path

Choose **Railway** if you want:
- ✅ Fastest setup (5 min)
- ✅ Auto-deploy from GitHub
- ✅ Built-in databases
- ✅ Modern infrastructure
- ✅ Better for complex apps

---

**Both are great. Railway is faster, PythonAnywhere is cheaper and always-on.**

**Pick one and deploy today! 🚀**
