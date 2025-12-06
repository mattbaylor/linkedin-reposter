# One Week Monitoring Guide - LinkedIn Reposter

## Running on Mac Laptop (Development Environment)

**Start Date**: December 5, 2025  
**Duration**: 1 week monitoring period  
**Environment**: `dev` (Infisical)

## Quick Reference

### Service Status
```bash
# Check if container is running
docker compose ps

# View logs (live)
docker compose logs -f

# View recent logs
docker compose logs --tail 100

# Restart service
docker compose restart

# Stop service
docker compose down

# Start service
docker compose up -d
```

### Health Checks
```bash
# Overall health
curl http://localhost:8080/health | jq

# Statistics
curl http://localhost:8080/stats | jq

# Scheduled posts queue
curl http://localhost:8080/schedule/queue | jq
```

### Access Points
- **API**: http://localhost:8080
- **Health**: http://localhost:8080/health
- **Stats**: http://localhost:8080/stats
- **VNC**: http://localhost:8080/admin/vnc
- **Docs**: http://localhost:8080/docs (FastAPI auto-docs)

## Automated Schedule

### Scraping
- **Time**: 11:00 AM and 4:00 PM MST
- **What happens**:
  1. Scrapes all 10 LinkedIn handles
  2. Saves new posts to database
  3. Generates 3 AI variants per post
  4. Sends approval email to matt@example.com

### Publishing
- **Time**: Every 5 minutes
- **What happens**:
  1. Checks for approved posts in queue
  2. Posts to LinkedIn if scheduled time has arrived
  3. Updates post status to "posted"

## Expected Behavior

### Normal Operation

**Every 11 AM and 4 PM**:
```
📥 Starting scheduled scrape...
🔍 Scraping @timcool...
✅ Scraped 5 posts from @timcool
🤖 Generating AI variants...
📧 Sending approval email...
📥 Scraping @company/smartchurchsolutions...
[continues for all 10 handles]
✅ Scrape completed
```

**Every 5 minutes**:
```
📅 Checking publish queue...
✅ No posts ready to publish yet
```

Or if posts are ready:
```
📅 Checking publish queue...
📤 Publishing variant 123...
✅ Post published successfully
```

### Security Challenges

If LinkedIn shows a security check:
```
🚨 Security challenge detected during login
📧 Sending alert email to matt@example.com
⏳ Waiting up to 30 minutes for resolution...
```

**Your action**:
1. Check email for alert with subject "🚨 LinkedIn Security Check Required"
2. Click the link to VNC viewer (or go to http://localhost:8080/admin/vnc)
3. Complete the LinkedIn security challenge in the browser
4. Wait - the scraper will detect resolution and continue automatically

### Email Workflow

**Approval Email** (sent after each scrape):
- Subject: "New LinkedIn Post Approval - [Author Name]"
- Contains: Original post + 3 AI variants
- Action: Click button to approve one variant
- Link format: `http://localhost:8080/webhook/approve/{token}?variant_id={id}`

**Security Alert Email** (sent when challenge detected):
- Subject: "🚨 LinkedIn Security Check Required"
- Contains: Link to VNC viewer
- Action: Click link and complete challenge

## What to Monitor

### Daily Checks (2x per day after scrapes)

1. **Check Email**:
   - Did you receive approval emails?
   - Are posts from expected handles?
   - Do AI variants look good?

2. **Review Stats**:
   ```bash
   curl http://localhost:8080/stats | jq
   ```
   - Total posts increasing?
   - Any failures?
   - Approval backlog reasonable?

3. **Check Logs for Errors**:
   ```bash
   docker compose logs --tail 50 | grep -i error
   ```

### Things to Watch For

#### ✅ Good Signs
- New posts discovered every scrape
- AI variants generated successfully
- Approval emails sent
- No rate limiting errors
- LinkedIn session stays valid

#### ⚠️ Warning Signs
- 429 errors (rate limiting) - Expected occasionally, system handles gracefully
- No new posts found - Could be normal if people aren't posting
- Security challenges - Expected occasionally, just complete them

#### 🚨 Red Flags
- Container keeps restarting
- Database errors
- Email sending failures
- Browser crashes during scraping
- Session constantly invalidating

## Common Tasks

### Approve a Post
1. Open approval email
2. Click the button for your preferred variant
3. Post will be queued for publishing in 1 hour

### Reject a Post
1. Open approval email
2. Click "Reject All" at the bottom
3. Post will be marked as rejected

### Manual Scrape (for testing)
```bash
curl -X POST http://localhost:8080/test/trigger-scrape
```

### View Database Contents
```bash
# Enter container
docker compose exec app sh

# Open database
sqlite3 /app/data/linkedin_reposter.db

# View posts
SELECT id, author_name, status, created_at FROM linkedin_posts ORDER BY created_at DESC LIMIT 10;

# Exit
.quit
exit
```

### Clear Database (if needed)
```bash
# CAUTION: This deletes all data
docker compose down
rm data/linkedin_reposter.db
docker compose up -d
```

## Troubleshooting

### Container Not Starting
```bash
# View logs
docker compose logs

# Check environment
docker compose config

# Rebuild
docker compose down
docker compose up -d --build
```

### LinkedIn Session Expired
```bash
# Trigger a scrape to detect and handle
curl -X POST http://localhost:8080/test/trigger-scrape

# You'll get an email with VNC link
# Complete the challenge and scraper continues
```

### VNC Not Working
```bash
# Check websockify log
docker compose exec app cat /tmp/websockify.log

# Restart container
docker compose restart

# Test VNC directly
open http://localhost:8080/admin/vnc
```

### Email Not Sending
```bash
# Check logs for email errors
docker compose logs | grep -i email

# Verify Postal API key in Infisical
# Test endpoint directly
curl http://localhost:8080/health
```

### Rate Limiting (429 errors)
- **Expected**: GitHub Models has rate limits
- **Impact**: Some posts won't get AI variants
- **Action**: Just monitor, system handles gracefully
- **Future**: Will add retry logic

## Data Location

All data stored in: `./data/`

Files:
- `linkedin_reposter.db` - SQLite database
- `linkedin_session/` - Browser cookies/session
- `linkedin_page_*.html` - Debug HTML dumps (when issues occur)
- `linkedin_reposter.log` - Application logs

**Backup** (recommended):
```bash
# Daily backup
cp data/linkedin_reposter.db data/backups/linkedin_reposter_$(date +%Y%m%d).db
```

## Performance Expectations

### Per Scrape Run (11 AM / 4 PM)
- **Duration**: 5-10 minutes for all 10 handles
- **Posts Found**: Varies (0-50 depending on activity)
- **AI Processing**: ~10 seconds per post
- **Email Sending**: ~2 seconds per email

### Resource Usage
- **CPU**: Low (spikes during scraping)
- **Memory**: ~2GB (Chromium browser + container)
- **Disk**: ~500MB for database and session data
- **Network**: Moderate during scraping

## Week-End Checklist

After 1 week, review:

### Success Metrics
- [ ] Total scrape runs: ~14 (7 days × 2 per day)
- [ ] Posts discovered: _____
- [ ] Posts approved: _____
- [ ] Posts published: _____
- [ ] Security challenges: _____
- [ ] System uptime: _____

### Issues Encountered
- [ ] Container restarts: _____
- [ ] LinkedIn blocks: _____
- [ ] Email failures: _____
- [ ] Rate limit errors: _____
- [ ] Other: _____

### AI Quality Review
- [ ] Variants maintain original meaning?
- [ ] Attribution clear (names not handles)?
- [ ] Length appropriate (30-50% shorter)?
- [ ] Tone/style good?

### Decision Points
- [ ] Ready for production (TrueNAS)?
- [ ] Need any adjustments?
- [ ] Schedule changes needed?
- [ ] Handle list changes?

## Notes

**Current Handles** (10):
1. timcool
2. company/smartchurchsolutions
3. elena-dietrich-b95b64249
4. patrick-hart-b6835958
5. nathan-parr-15504b43
6. tyler-david-thompson
7. company/espace-facility-management-software
8. casie-hildner-66352596
9. chelsey-stafki-87b4912b4
10. lee-cool-2941b2196

**Timezone**: MST/MDT (handles daylight saving automatically)

**Next Scrapes**:
- Today 4:00 PM MST (if still before that)
- Tomorrow 11:00 AM MST
- Tomorrow 4:00 PM MST

---

**Status**: ✅ Running on Mac laptop  
**Started**: December 5, 2025  
**Review Date**: December 12, 2025
