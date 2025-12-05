# LinkedIn Reposter - Quick Start Guide

## System Status: ✅ READY

Your LinkedIn Reposter is now running locally at **http://localhost:8080**

### What's Working:
- ✅ Docker containers built and running
- ✅ FastAPI service on port 8080
- ✅ Database initialized (SQLite)
- ✅ APScheduler background worker (checks every 5 minutes)
- ✅ Schedule queue endpoints active
- ✅ All API endpoints functional

### What You Need to Do:

#### 1. Get Your LinkedIn Cookie (One-Time Setup)

Since we're running in Docker (headless), you need to provide your LinkedIn session cookie:

**Steps:**
1. Open https://www.linkedin.com in your browser and log in
2. Press **F12** to open DevTools
3. Go to **Application** tab (Chrome) or **Storage** tab (Firefox)
4. Click **Cookies** → `https://www.linkedin.com`
5. Find the cookie named `li_at`
6. Copy its entire value (long string starting with `AQ...`)

**Then authenticate:**
```bash
curl -X POST "http://localhost:8080/linkedin/cookie-auth?li_at_cookie=YOUR_COOKIE_VALUE_HERE"
```

**Verify session:**
```bash
curl http://localhost:8080/linkedin/session-status | jq
```

#### 2. Test Scraping (7-Day Lookback)

Once authenticated, scrape posts from a LinkedIn user:

```bash
# Scrape from timcool (or any LinkedIn handle)
curl -X POST "http://localhost:8080/linkedin/scrape?handle=timcool&max_posts=50" | jq

# The system will:
# - Look back 7 days for posts
# - Save new posts to database
# - Return scraped posts
```

#### 3. Check What Was Scraped

```bash
# View all posts
curl "http://localhost:8080/posts" | jq

# View posts by status
curl "http://localhost:8080/posts?status=scraped" | jq
```

#### 4. View Schedule Queue

```bash
curl http://localhost:8080/schedule/queue | jq
```

**Golden Hour Priority Levels:**
- 🔥 **URGENT** (< 3 hours old): Scheduled ASAP
- ✅ **GOOD** (< 12 hours): Scheduled today if possible  
- ⏰ **OK** (< 24 hours): Normal scheduling
- ⚠️ **STALE** (> 48 hours): Low priority, back of queue

#### 5. View Stats

```bash
curl http://localhost:8080/stats | jq
```

### Important Configuration

**Scheduling Settings** (in `app/config.py`):
- **Daily Limit**: 3 posts per day
- **Min Spacing**: 90 minutes between posts
- **Posting Hours**: 6am - 9pm MST
- **Days**: Monday-Friday only (no weekends)
- **Jitter**: ±15 minutes for natural appearance
- **Lookback**: 7 days when scraping

### API Endpoints Available

**LinkedIn Session:**
- `POST /linkedin/cookie-auth` - Authenticate with li_at cookie
- `GET /linkedin/session-status` - Check session health

**Scraping:**
- `POST /linkedin/scrape?handle=USER&max_posts=50` - Scrape user's posts

**Schedule Management:**
- `GET /schedule/queue` - View scheduled posts
- `POST /schedule/{id}/reschedule?new_time=2024-12-06T14:30:00` - Move post
- `DELETE /schedule/{id}` - Cancel scheduled post

**Monitoring:**
- `GET /health` - Service health
- `GET /stats` - Post statistics
- `GET /posts` - List all posts

### Background Worker

The APScheduler runs every 5 minutes and:
1. Checks for posts scheduled now or earlier
2. Publishes them to LinkedIn
3. Handles retries (3 attempts, 30min delays)
4. Updates status automatically

**Check worker logs:**
```bash
cd ~/repo/linkedin-reposter
docker compose logs -f app | grep -E "(Publishing|Scheduled|URGENT|GOOD)"
```

### Session Expiry

LinkedIn sessions expire after ~30 days. You'll receive:
- Email warning at 25 days
- Email alert at 30+ days (expired)

Just re-authenticate when needed:
```bash
curl -X POST "http://localhost:8080/linkedin/cookie-auth?li_at_cookie=NEW_COOKIE"
```

### Container Management

```bash
cd ~/repo/linkedin-reposter

# View logs
docker compose logs -f app

# Restart
docker compose restart

# Stop
docker compose down

# Start
docker compose up -d
```

### Next Steps for Production

1. **Deploy to your server** (currently running locally on Mac)
2. **Update Infisical secrets** for production environment
3. **Configure reverse proxy** (Traefik/Nginx) for HTTPS
4. **Set up monitoring** for session expiry alerts
5. **Add your 7 LinkedIn handles** to monitoring config

### GitHub Repository

https://github.com/mattbaylor/linkedin-reposter

All code is committed and pushed!

---

**Questions?** Check the documentation:
- `API_ENDPOINTS.md` - Complete API reference
- `LINKEDIN_SETUP.md` - Detailed LinkedIn setup
- `GOLDEN_HOUR_OPTIMIZATION.md` - Scheduling strategy
- `INTELLIGENT_SCHEDULING_PLAN.md` - Full scheduling docs
