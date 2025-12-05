# LinkedIn Setup & Testing Guide

## Overview

The LinkedIn automation requires a **one-time manual setup** to establish a trusted session. This guide walks through the setup process and testing steps.

## Why Manual Setup?

LinkedIn's anti-bot protection blocks automated logins with verification challenges. The universal solution (used by all successful LinkedIn automation projects) is **cookie-based authentication**:

1. Manual first login in a real browser
2. Save the session cookies
3. Reuse cookies for automated operations (no more challenges)

## Setup Methods

### Method 1: Manual Browser Setup (Recommended)

**Best for:** First-time setup, when session expires

```bash
# 1. Ensure container is running
docker compose up -d

# 2. Trigger manual setup
curl -X POST http://192.0.2.10:8080/linkedin/manual-setup

# 3. A browser window will open automatically
# 4. Login to LinkedIn manually
# 5. Complete any verification challenges (2FA, email code, etc.)
# 6. Once logged in, the session is automatically saved
# 7. Browser will close and session is ready for automation
```

**Important Notes:**
- Run this on your **Mac** (not headless server)
- You'll see the actual browser window
- Take your time with verification - no rush
- Session saves to `/app/data/linkedin_session/state.json`

---

### Method 2: Cookie Authentication

**Best for:** Quick setup if you have the cookie already

```bash
# 1. Get your li_at cookie:
#    - Login to LinkedIn in Chrome/Firefox
#    - F12 -> Application -> Cookies -> linkedin.com
#    - Copy the value of 'li_at' cookie

# 2. Authenticate with cookie
curl -X POST "http://192.0.2.10:8080/linkedin/cookie-auth?li_at_cookie=YOUR_COOKIE_VALUE"
```

---

## Verify Setup

### Check Session Status

```bash
curl http://192.0.2.10:8080/linkedin/session-status
```

**Healthy Response:**
```json
{
  "session_exists": true,
  "age_days": 2,
  "health_status": "healthy",
  "message": "Session is healthy",
  "email_sent": false
}
```

**Warning Response (25+ days old):**
```json
{
  "session_exists": true,
  "age_days": 27,
  "health_status": "warning",
  "message": "Session expiring soon - please refresh within 5 days",
  "email_sent": true,
  "warnings": ["Session is 27 days old"]
}
```

**Expired Response (30+ days old):**
```json
{
  "session_exists": true,
  "age_days": 35,
  "health_status": "expired",
  "message": "Session expired - please refresh immediately",
  "email_sent": true,
  "warnings": ["Session is expired and may not work"]
}
```

---

## Session Lifecycle

### Session Expiry Timeline

| Age | Status | Behavior | Email Alert |
|-----|--------|----------|-------------|
| 0-24 days | Healthy | All operations work | No |
| 25-29 days | Warning | All operations work | Yes (once at 25 days) |
| 30+ days | Expired | Operations **blocked** | Yes (daily) |

### Email Alerts

You'll receive email alerts when:
- **Warning (25 days):** Session expiring soon, refresh recommended
- **Expired (30+ days):** Session expired, operations blocked

Email contains link to refresh: `https://liposter.example.com/linkedin/manual-setup`

---

## Testing Flow

### 1. Test Scraping

```bash
# Scrape posts from a LinkedIn user
curl -X POST "http://192.0.2.10:8080/linkedin/scrape?handle=timcool&max_posts=5"
```

**Success Response:**
```json
{
  "success": true,
  "message": "Scraped 5 posts from @timcool (3 new)",
  "handle": "timcool",
  "scraped_count": 5,
  "new_posts_count": 3,
  "session_health": "healthy",
  "posts": [...]
}
```

**Session Expired Error:**
```json
{
  "detail": "LinkedIn session expired. Please refresh at https://liposter.example.com/linkedin/manual-setup"
}
```

---

### 2. Test Full Workflow

```bash
# 1. Scrape a post
curl -X POST "http://192.0.2.10:8080/linkedin/scrape?handle=timcool&max_posts=1"

# 2. Generate AI variants (use post_id from scrape response)
# This happens automatically in production, but can be tested separately
curl -X POST http://192.0.2.10:8080/test/generate-variants

# 3. Send approval email (use post_id from scrape)
curl -X POST http://192.0.2.10:8080/test/send-approval-email

# 4. Click approval link in email
# (Click one of the variant links in the email)

# 5. Publish approved post (use post_id from scrape)
curl -X POST http://192.0.2.10:8080/linkedin/publish/1
```

---

### 3. Test Publishing

**WARNING:** This actually posts to LinkedIn!

```bash
# Publish an already-approved post
curl -X POST http://192.0.2.10:8080/linkedin/publish/1
```

**Success Response:**
```json
{
  "success": true,
  "message": "Post 1 published successfully to LinkedIn!",
  "post_id": 1,
  "variant_id": 2,
  "variant_number": 2,
  "content": "..."
}
```

---

## Troubleshooting

### Session Not Working After Setup

**Problem:** Manual setup completed but scraping fails

**Solution:**
```bash
# 1. Check logs
docker logs linkedin-reposter --tail 50

# 2. Verify session file exists
docker exec linkedin-reposter ls -la /app/data/linkedin_session/

# 3. Try cookie method as backup
# (Get li_at cookie from browser and use Method 2)
```

---

### Browser Doesn't Open (Manual Setup)

**Problem:** `manual_setup()` doesn't open browser

**Solution:**
- Run on your **local Mac**, not on the server
- SSH X11 forwarding won't work reliably with Playwright
- Alternative: Use **Method 2** (Cookie Auth) instead

---

### Session Expired But Email Not Received

**Problem:** Session is 30+ days old but no alert email

**Solution:**
```bash
# 1. Check Postal integration
curl http://192.0.2.10:8080/health

# 2. Manually trigger session check
curl http://192.0.2.10:8080/linkedin/session-status

# 3. Check application logs
docker logs linkedin-reposter | grep -i email
```

---

### Scraping Returns Empty Posts

**Problem:** Scraping succeeds but returns 0 posts

**Causes:**
1. User has no recent posts
2. User profile is private
3. Session expired (check with `/linkedin/session-status`)

**Solution:**
```bash
# Try a different user with recent public posts
curl -X POST "http://192.0.2.10:8080/linkedin/scrape?handle=satyanadella&max_posts=5"
```

---

## Session Refresh Workflow

When you receive an expiry email or see warnings:

```bash
# 1. Check current status
curl http://192.0.2.10:8080/linkedin/session-status

# 2. Refresh session (on your Mac)
curl -X POST http://192.0.2.10:8080/linkedin/manual-setup

# 3. Or use cookie method
curl -X POST "http://192.0.2.10:8080/linkedin/cookie-auth?li_at_cookie=NEW_COOKIE"

# 4. Verify refresh
curl http://192.0.2.10:8080/linkedin/session-status
# Should show age_days: 0
```

---

## Production Monitoring

### Regular Health Checks

Add to your monitoring system:

```bash
# Check session health daily
0 9 * * * curl http://192.0.2.10:8080/linkedin/session-status | jq '.health_status'
```

### Automation Workflow

The scheduler (Phase 6) will:
1. Check session health before each run
2. Block operations if expired
3. Send email alerts automatically
4. Continue operations with warnings (25-29 days)

---

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| Session state | `/app/data/linkedin_session/state.json` | Playwright session with cookies |
| Cookies (debug) | `/app/data/linkedin_session/cookies.json` | Cookie values for inspection |
| Metadata | `/app/data/linkedin_session/metadata.json` | Session creation timestamp |
| Database | `/app/data/linkedin_reposter.db` | Scraped posts, variants, approvals |
| Logs | `/app/data/linkedin_reposter.log` | Application logs |

---

## Next Steps

After successful setup:

1. ✅ Session established and verified
2. ✅ Scraping tested with real LinkedIn user
3. ✅ Session health monitoring active
4. 📅 **Next:** Phase 6 - Scheduler
   - Schedule scraping at 11am & 4pm MST
   - Automated workflow: scrape → AI variants → email → post
   - Integration with all existing services

---

## Quick Reference

```bash
# Setup (one-time)
curl -X POST http://192.0.2.10:8080/linkedin/manual-setup

# Check health
curl http://192.0.2.10:8080/linkedin/session-status

# Scrape
curl -X POST "http://192.0.2.10:8080/linkedin/scrape?handle=timcool&max_posts=5"

# Publish approved post
curl -X POST http://192.0.2.10:8080/linkedin/publish/1

# View stats
curl http://192.0.2.10:8080/stats | jq
```
