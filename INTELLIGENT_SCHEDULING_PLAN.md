# Intelligent Post Scheduling Plan

## Problem Statement

**User Request:**
1. Look back ~7 days when scraping (not just latest posts)
2. Prevent overwhelming LinkedIn algorithm with sudden burst of activity
3. Smart spacing even if user approves many posts at once

**Goal:** Make me look like a normal human, not a bot.

---

## Solution: Multi-Layer Intelligence

### Layer 1: Scraping Intelligence
**Lookback Period:** 7 days (configurable)

```python
# When scraping, filter by date
scraped_posts = await scrape_user_posts(
    handle="timcool",
    max_posts=50,  # Scrape more posts
    min_date=datetime.now() - timedelta(days=7)  # Only last 7 days
)
```

**Configuration:**
```python
SCRAPING_LOOKBACK_DAYS = 7  # How far back to look
SCRAPING_MAX_POSTS_PER_HANDLE = 50  # Max posts to scrape per user
```

---

### Layer 2: Approval Queue Intelligence
**Problem:** User approves 10 posts at 9am. We can't post all 10 immediately.

**Solution:** Approval creates a queued post with intelligent scheduling

```
User approves post at 9:15am
  ↓
Added to publish queue
  ↓
Smart scheduler assigns slot: "Tomorrow at 11:30am"
  ↓
Post waits in queue until scheduled time
  ↓
Published at 11:30am (looks natural)
```

---

### Layer 3: Smart Scheduling Algorithm

#### Rule 1: Daily Post Limit
**Maximum 3 posts per day** (configurable)

Why? LinkedIn algorithm penalizes excessive posting. Normal users post 1-3 times/day max.

```python
DAILY_POST_LIMIT = 3  # Max posts per day
```

#### Rule 2: Minimum Spacing Between Posts
**Minimum 90 minutes between posts** (configurable)

Why? Posting every 5 minutes = obvious bot. 90 min = natural human rhythm.

```python
MIN_POST_SPACING_MINUTES = 90  # Minimum time between posts
```

#### Rule 3: Preferred Posting Windows
**Only post during "business hours" in your timezone**

```python
POSTING_HOURS = {
    "start": 8,   # 8am MST
    "end": 18,    # 6pm MST
}
POSTING_DAYS = [0, 1, 2, 3, 4]  # Monday-Friday only (no weekends)
```

Why? Posting at 3am looks suspicious. Business hours = natural.

#### Rule 4: Randomization
**Add ±15 minute jitter to scheduled times**

```python
scheduled_time = base_time + random.randint(-15, 15) minutes
```

Why? Posting exactly every 90 minutes = predictable pattern. Randomness = human.

---

## Scheduling Logic Flow

### Scenario: User Approves 10 Posts at 9:15am on Monday

```
Current time: Monday 9:15am
Daily posts used today: 0
Queue: 10 approved posts waiting
```

**Scheduler assigns slots:**

```
Post 1: Monday 11:00am   (1h 45m from now - immediate slot)
Post 2: Monday 12:45pm   (+90 min spacing)
Post 3: Monday 2:30pm    (+90 min spacing, DAILY LIMIT REACHED)

Post 4: Tuesday 9:15am   (next day, first slot)
Post 5: Tuesday 11:00am  (+90 min spacing)
Post 6: Tuesday 1:00pm   (+90 min spacing, DAILY LIMIT REACHED)

Post 7: Wednesday 10:30am (next day, first slot)
Post 8: Wednesday 12:15pm (+90 min spacing)
Post 9: Wednesday 2:45pm  (+90 min spacing, DAILY LIMIT REACHED)

Post 10: Thursday 11:00am (next day, first slot)
```

**Result:** 10 posts spread over 4 days, looks completely natural.

---

## Database Schema Updates

### New Table: `scheduled_posts`

```sql
CREATE TABLE scheduled_posts (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,  -- FK to linkedin_posts
    approved_at TIMESTAMP,      -- When user approved
    scheduled_for TIMESTAMP,    -- When to publish
    published_at TIMESTAMP,     -- When actually published (null if pending)
    status TEXT,                -- pending, published, failed, cancelled
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Status Flow:**
```
pending → published  (success)
pending → failed     (error, can retry)
pending → cancelled  (user cancelled)
```

---

## Configuration Parameters

### Add to Infisical / .env

```bash
# Scraping Configuration
SCRAPING_LOOKBACK_DAYS=7
SCRAPING_MAX_POSTS_PER_HANDLE=50

# Posting Intelligence
DAILY_POST_LIMIT=3
MIN_POST_SPACING_MINUTES=90
POSTING_HOUR_START=8
POSTING_HOUR_END=18
POSTING_WEEKDAYS_ONLY=true

# Scheduler
ENABLE_POSTING_JITTER=true
POSTING_JITTER_MINUTES=15
```

---

## API Changes

### Modified Approval Flow

**Before:**
```
User approves → Post status = "approved" → Done
```

**After:**
```
User approves → Post status = "approved" → Add to schedule queue → Assign smart slot
```

### New Endpoints

#### `GET /schedule/queue`
List all scheduled posts

```json
{
  "total_scheduled": 15,
  "today": 3,
  "this_week": 12,
  "queue": [
    {
      "post_id": 42,
      "original_author": "timcool",
      "scheduled_for": "2025-12-06T11:00:00",
      "time_until": "1 hour 45 minutes",
      "slot_assigned": "2025-12-05T09:15:00"
    }
  ]
}
```

#### `POST /schedule/{post_id}/reschedule`
Manually reschedule a post

```bash
curl -X POST "http://localhost:8080/schedule/42/reschedule?new_time=2025-12-07T14:00:00"
```

#### `DELETE /schedule/{post_id}`
Cancel a scheduled post

```bash
curl -X DELETE http://localhost:8080/schedule/42
```

---

## Scheduler Implementation

### Background Worker

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = AsyncIOScheduler(timezone="America/Denver")

# Check queue every 5 minutes
scheduler.add_job(
    func=process_publish_queue,
    trigger=IntervalTrigger(minutes=5),
    id="publish_queue_processor"
)

# Scrape monitored handles twice daily
scheduler.add_job(
    func=scrape_all_handles,
    trigger=CronTrigger(hour="11,16", minute="0"),  # 11am & 4pm
    id="handle_scraper"
)
```

### Queue Processor Logic

```python
async def process_publish_queue():
    """Check for posts ready to publish."""
    now = datetime.now()
    
    # Get pending posts scheduled for now or earlier
    pending = await db.execute(
        select(ScheduledPost)
        .where(ScheduledPost.status == "pending")
        .where(ScheduledPost.scheduled_for <= now)
        .order_by(ScheduledPost.scheduled_for)
    )
    
    for scheduled_post in pending:
        try:
            # Publish to LinkedIn
            await publish_post(scheduled_post.post_id)
            
            # Mark as published
            scheduled_post.status = "published"
            scheduled_post.published_at = now
            
        except Exception as e:
            logger.error(f"Failed to publish post {scheduled_post.post_id}: {e}")
            scheduled_post.retry_count += 1
            
            if scheduled_post.retry_count >= 3:
                scheduled_post.status = "failed"
            else:
                # Retry in 15 minutes
                scheduled_post.scheduled_for = now + timedelta(minutes=15)
    
    await db.commit()
```

### Smart Slot Assignment

```python
async def assign_publish_slot(post_id: int) -> datetime:
    """Intelligently assign a publish time for approved post."""
    
    # Get all scheduled posts
    scheduled = await get_all_scheduled_posts()
    
    # Find next available slot
    candidate_time = datetime.now()
    
    while True:
        # Move to next valid hour
        if candidate_time.hour < POSTING_HOUR_START:
            candidate_time = candidate_time.replace(
                hour=POSTING_HOUR_START, minute=0
            )
        elif candidate_time.hour >= POSTING_HOUR_END:
            # Move to next day
            candidate_time = candidate_time + timedelta(days=1)
            candidate_time = candidate_time.replace(
                hour=POSTING_HOUR_START, minute=0
            )
        
        # Skip weekends if configured
        if POSTING_WEEKDAYS_ONLY and candidate_time.weekday() in [5, 6]:
            candidate_time = candidate_time + timedelta(days=1)
            continue
        
        # Check if this day is at daily limit
        posts_on_day = count_posts_on_day(scheduled, candidate_time.date())
        if posts_on_day >= DAILY_POST_LIMIT:
            # Move to next day
            candidate_time = candidate_time + timedelta(days=1)
            candidate_time = candidate_time.replace(
                hour=POSTING_HOUR_START, minute=0
            )
            continue
        
        # Check spacing from last post
        last_post_time = get_last_scheduled_time(scheduled)
        if last_post_time:
            time_diff = (candidate_time - last_post_time).total_seconds() / 60
            if time_diff < MIN_POST_SPACING_MINUTES:
                candidate_time = last_post_time + timedelta(
                    minutes=MIN_POST_SPACING_MINUTES
                )
                continue
        
        # Found valid slot!
        break
    
    # Add jitter
    if ENABLE_POSTING_JITTER:
        jitter = random.randint(-POSTING_JITTER_MINUTES, POSTING_JITTER_MINUTES)
        candidate_time = candidate_time + timedelta(minutes=jitter)
    
    return candidate_time
```

---

## User Experience Examples

### Example 1: Approving Single Post
```
You approve 1 post at 2:30pm Monday
  ↓
System: "Post scheduled for Monday 4:00pm (in 1h 30m)"
  ↓
Email confirmation: "Your post will be published at 4:00pm today"
```

### Example 2: Approving Many Posts
```
You approve 8 posts at 9am Tuesday
  ↓
System assigns:
  - Post 1: Today 11:00am
  - Post 2: Today 12:30pm  
  - Post 3: Today 2:15pm
  - Post 4: Tomorrow 10:00am
  - Post 5: Tomorrow 11:45am
  - Post 6: Tomorrow 1:30pm
  - Post 7: Thursday 9:30am
  - Post 8: Thursday 11:15am
  ↓
Email: "8 posts scheduled over the next 3 days (see schedule)"
```

### Example 3: Queue Already Full
```
Current queue: 9 posts scheduled over next 3 days
You approve 1 more post
  ↓
System: "Post scheduled for Monday next week at 10:00am"
  ↓
Email: "Post queued. Currently 9 posts ahead in queue."
```

---

## Safety Features

### 1. Session Health Check Before Publishing
```python
# Before publishing ANY post
health = await check_session_health()
if health["status"] == "expired":
    # Cancel all scheduled posts
    # Send urgent email to refresh session
    return
```

### 2. Duplicate Detection
```python
# Before scheduling, check if we already posted this URL
existing = await db.execute(
    select(LinkedInPost)
    .where(LinkedInPost.url == post.url)
    .where(LinkedInPost.status == PostStatus.POSTED)
)
if existing:
    logger.warning(f"Already posted {post.url} - skipping")
    return
```

### 3. Rate Limit Protection
```python
# Track posting rate
recent_posts = count_posts_in_last_hour()
if recent_posts >= 5:
    logger.warning("Rate limit protection: too many posts in last hour")
    # Delay all pending posts by 1 hour
    return
```

---

## Monitoring & Alerts

### Daily Summary Email
```
Subject: LinkedIn Reposter Daily Report - 3 posts published

Today's Activity:
  ✅ Published 3 posts (11:00am, 12:45pm, 2:30pm)
  📊 Queue: 6 posts scheduled for next 2 days
  ⏰ Next post: Tomorrow at 10:15am
  
Session Health: ✅ Healthy (12 days old)

Posted Today:
  1. "How to build better products..." (from @timcool)
  2. "The future of software is..." (from @elena-dietrich)
  3. "Remote work strategies..." (from @smartchurchsolutions)
```

### Weekly Summary Email
```
Subject: LinkedIn Reposter Weekly Report - 12 posts published

This Week (Dec 2-8):
  ✅ Published: 12 posts
  📬 Scraped: 47 posts from 7 handles
  ✉️  Sent: 15 approval emails
  👍 Approved: 12 posts
  👎 Rejected: 3 posts
  
Session Health: ⚠️  Warning (26 days old) - Refresh soon!

Top Sources:
  1. @timcool - 5 posts
  2. @smartchurchsolutions - 3 posts
  3. @elena-dietrich - 2 posts
```

---

## Configuration Example

### Recommended Settings

**Conservative (Look Human):**
```bash
SCRAPING_LOOKBACK_DAYS=7
DAILY_POST_LIMIT=2
MIN_POST_SPACING_MINUTES=120
POSTING_HOUR_START=9
POSTING_HOUR_END=17
POSTING_WEEKDAYS_ONLY=true
ENABLE_POSTING_JITTER=true
```

**Moderate (Default):**
```bash
SCRAPING_LOOKBACK_DAYS=7
DAILY_POST_LIMIT=3
MIN_POST_SPACING_MINUTES=90
POSTING_HOUR_START=8
POSTING_HOUR_END=18
POSTING_WEEKDAYS_ONLY=true
ENABLE_POSTING_JITTER=true
```

**Aggressive (More Posts):**
```bash
SCRAPING_LOOKBACK_DAYS=14
DAILY_POST_LIMIT=5
MIN_POST_SPACING_MINUTES=60
POSTING_HOUR_START=7
POSTING_HOUR_END=20
POSTING_WEEKDAYS_ONLY=false
ENABLE_POSTING_JITTER=true
```

---

## Laptop Testing Setup

### Run on Mac for Full Test

```bash
# 1. Clone/update code
cd /Users/matt/repo/linkedin-reposter

# 2. Build for Mac
docker compose build

# 3. Run with local .env (not Infisical)
docker compose -f docker-compose.local.yml up

# 4. Manual LinkedIn setup (browser opens)
curl -X POST http://localhost:8080/linkedin/manual-setup

# 5. Trigger test scrape (7 days back)
curl -X POST "http://localhost:8080/linkedin/scrape?handle=timcool&max_posts=50"

# 6. Generate variants for scraped posts
# (Automatic, happens in background)

# 7. Check approval emails in inbox

# 8. Approve some posts (click email links)

# 9. Check queue
curl http://localhost:8080/schedule/queue | jq

# 10. Watch scheduler process queue
docker logs -f linkedin-reposter
```

---

## Implementation Phases

### Phase 5.5: Database Updates (30 min)
- [x] Add `scheduled_posts` table
- [x] Add migration script
- [x] Update models

### Phase 6: Smart Scheduling (2 hours)
- [ ] Implement slot assignment algorithm
- [ ] Add configuration parameters
- [ ] Build queue processor
- [ ] Add safety checks (duplicates, rate limits)

### Phase 7: Scheduler Integration (1 hour)
- [ ] Add APScheduler
- [ ] Queue processor background job
- [ ] Scraping background jobs (11am & 4pm)
- [ ] Session health checks

### Phase 8: API & Monitoring (1 hour)
- [ ] Schedule management endpoints
- [ ] Daily summary emails
- [ ] Weekly summary emails
- [ ] Logging enhancements

### Phase 9: Testing (1 hour)
- [ ] Laptop setup documentation
- [ ] Test full workflow
- [ ] Verify spacing algorithm
- [ ] Edge case testing

**Total Estimated Time:** 5.5 hours

---

## LinkedIn Algorithm Considerations

### What LinkedIn Penalizes
1. **Posting too frequently** → Daily limit prevents this
2. **Posting at odd hours** → Business hours restriction prevents this
3. **Mechanical patterns** → Jitter/randomization prevents this
4. **Identical content** → We're reposting others' content (fine)
5. **Sudden activity bursts** → Queue spreading prevents this

### What LinkedIn Rewards
1. **Consistent posting schedule** → Our queue provides this
2. **Engaging during business hours** → We enforce this
3. **Spacing between posts** → 90 min minimum ensures this
4. **Natural human patterns** → Jitter simulates this

---

## Next Steps

1. **Review & Approve Plan** - Does this match your needs?
2. **Adjust Parameters** - What daily limit feels right? (2-5 posts/day)
3. **Implement Database Changes** - Add `scheduled_posts` table
4. **Build Scheduling Algorithm** - Implement slot assignment
5. **Test on Laptop** - Full workflow test with real LinkedIn
6. **Deploy to Production** - Move to TrueNAS after testing

---

## Questions for You

1. **Daily post limit:** 2, 3, or 5 posts per day?
2. **Posting hours:** 8am-6pm MST, or different?
3. **Weekends:** Should we skip weekends or post 7 days/week?
4. **Lookback period:** 7 days good, or want 14 days?
5. **Queue visibility:** Want dashboard to see/manage queue?

Let me know your preferences and I'll implement!
