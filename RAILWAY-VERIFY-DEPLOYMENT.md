# Railway Deployment Verification Checklist

After the Docker build completes on Railway, use this checklist to verify everything is working.

## Step 1: Check Build Status

**In Railway Dashboard:**
1. Go to https://railway.app/dashboard
2. Select your "Support Triage Agent" project
3. Look at the Service status

**Expected states (in order):**
- ⏳ "Building..." (1-3 minutes)
- ✅ "Running" (green check)
- ❌ If it shows "Deploy failed" → see **Troubleshooting** below

**If build succeeds:**
- You should see a public domain like `https://support-triage-agent-prod-xxxx.railway.app`
- Note this URL for testing

---

## Step 2: Test Health Endpoint

**Via PowerShell:**
```powershell
# Replace DOMAIN with your Railway domain
$domain = "https://support-triage-agent-prod-xxxx.railway.app"
curl "$domain/health"
```

**Expected response:**
```json
{"status":"ok"}
```

**If it fails:**
- Wait 10-15 seconds (container startup takes time)
- Try again
- Check Railway logs for errors

---

## Step 3: Check Database Connection

**In Railway Logs:**
1. Dashboard → Service → Logs
2. Look for startup messages
3. Should see something like:
   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```

**If you see connection errors:**
- Check that PostgreSQL service is running (should show "Running" in dashboard)
- Check that Redis service is running
- Verify environment variables are set (DATABASE_URL, REDIS_URL)

---

## Step 4: Test Message Ingestion Endpoint

**Via PowerShell:**
```powershell
$domain = "https://support-triage-agent-prod-xxxx.railway.app"
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    message = "My account is locked"
    channel = "email"
    customer_id = "test-123"
} | ConvertTo-Json

curl -Method POST "$domain/api/v1/messages" -Headers $headers -Body $body
```

**Expected response:**
```json
{"message_id":"<uuid>","status":"ingested"}
```

**If you get 404:**
- Wait for container to fully start
- Check if endpoints are implemented (look for `endpoints/messages.py`)

**If you get 500:**
- Check Railway logs for stack trace
- May need to adjust database initialization

---

## Step 5: Monitor Performance

**In Railway Dashboard:**
1. Go to Service → Metrics
2. Watch for:
   - ✅ CPU usage (should be <5% at idle)
   - ✅ Memory usage (should be <200MB at idle)
   - ✅ Network I/O (should be minimal at idle)

**If metrics look bad:**
- Reduce `--workers` in Dockerfile (currently 1)
- Check if container is being restarted repeatedly
- Look for resource exhaustion in logs

---

## Troubleshooting

### Build Failed: Docker Error

**Symptom:** Railway shows "Deploy failed" during build phase

**Fix:**
1. Check Railway build logs for exact error
2. Common issues:
   - Package missing: Add to `apt-get install` in Dockerfile
   - Dependency conflict: Pin a different version in pip install
   - Memory: Railway free tier may have limits

3. If you need to debug locally:
   ```powershell
   docker build -t triage-agent:latest .
   docker run -p 8000:8000 triage-agent:latest
   # Then test: curl http://localhost:8000/health
   ```

### Container Starts but `/health` Times Out

**Symptom:** Curl hangs or returns connection refused

**Fix:**
1. Wait 30-60 seconds (startup can be slow)
2. Check if container is actually running (look at logs)
3. Verify port 8000 is exposed (check Dockerfile: `EXPOSE 8000`)
4. Try accessing Railway logs directly

### Database Connection Fails

**Symptom:** Logs show `psycopg2.OperationalError` or `asyncpg` error

**Fix:**
1. Verify PostgreSQL service is running (check Railway dashboard)
2. Check environment variables in Railway:
   - `DATABASE_URL` should be set
   - Format: `postgresql://user:pass@host:5432/dbname`
3. Verify Redis service is running
4. Check `REDIS_URL` environment variable

### 502 Bad Gateway

**Symptom:** App responds with 502 from Railway proxy

**Fix:**
1. Container likely crashed or is unresponsive
2. Check logs for the crash
3. Increase health check timeout in Dockerfile
4. May need to restart service

---

## Success Criteria

✅ All of these should be true:

- [ ] Railway dashboard shows "Running" (green)
- [ ] `/health` endpoint returns `{"status":"ok"}`
- [ ] Database service shows "Running"
- [ ] Redis service shows "Running"
- [ ] CPU <5%, Memory <300MB
- [ ] No error messages in logs
- [ ] Can send test message to `/api/v1/messages`

---

## Environment Variables to Check

In Railway dashboard, under your Service → Variables:

```
DATABASE_URL=postgresql://user:pass@...
REDIS_URL=redis://...
ENVIRONMENT=production
LOG_LEVEL=info
PORT=8000
```

If any are missing:
1. Get the values from Railway database/Redis services
2. Add them to your Service → Variables
3. Redeploy

---

## Logs to Monitor

**In Railway Logs tab, watch for:**

```
✅ Good signs:
- "Uvicorn running on http://0.0.0.0:8000"
- "Application startup complete"
- "Connected to database"
- Requests logging: "GET /health 200"

❌ Bad signs:
- "ConnectionRefusedError"
- "FATAL: database does not exist"
- "No module named 'triage'"
- Repeated restarts/crashes
- Out of memory errors
```

---

## Next: Production Checklist

Once verified, you can then:

1. **Set up monitoring** (Railway has built-in monitoring)
2. **Configure domain** (point your custom domain to Railway)
3. **Set up CI/CD** (GitHub → Railway automatic deployments)
4. **Monitor costs** (watch free tier usage)
5. **Scale if needed** (upgrade from free tier to paid)

---

**Estimated time:** 5-10 minutes for full verification

**Questions?** Check Railway documentation: https://docs.railway.app/
