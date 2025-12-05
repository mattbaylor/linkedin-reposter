# Golden Hour Optimization - How It Works

## The Golden Hour Problem

When someone posts on LinkedIn, there's a critical window where their post gets maximum engagement from the algorithm. If you repost content during this window, you "ride the wave" of engagement.

**The Science:**
- **0-3 hours:** 🔥 **Golden Hour** - Original post is getting peak engagement, algorithm is boosting it
- **3-12 hours:** ✅ **Still Good** - Engagement declining but still strong
- **12-24 hours:** ⏰ **OK** - Acceptable but fading
- **24+ hours:** ⚠️ **Stale** - Low engagement potential

---

## How Our Scheduler Handles It

### Priority Levels

| Age | Level | Priority Score | Scheduling Behavior |
|-----|-------|----------------|-------------------|
| **< 3 hours** | 🔥 URGENT | 100 | Schedule ASAP (next available slot) |
| **< 12 hours** | ✅ GOOD | 75 | Schedule today if possible |
| **< 24 hours** | ⏰ OK | 50 | Normal scheduling |
| **> 48 hours** | ⚠️ STALE | 25 | Back of queue / low priority |

---

## Real-World Examples

### Example 1: Perfect Timing (URGENT)

```
10:00am: Tim Cool posts about AI trends
10:30am: Your scraper finds it (30 minutes old)
11:00am: You approve the repost
11:15am: Scheduled for TODAY at 11:45am ← Next available slot!

Result: Posted 1h 45m after original - still riding the engagement wave! 🔥
```

---

### Example 2: Still Good (GOOD)

```
8:00am: Elena posts about remote work
2:00pm: Your scraper finds it (6 hours old)
2:30pm: You approve the repost
2:45pm: Scheduled for TODAY at 4:00pm

Result: Posted 8 hours after original - good engagement potential ✅
```

---

### Example 3: Getting Old (OK)

```
Yesterday 3pm: Patrick posts about leadership
Today 11am: Your scraper finds it (20 hours old)
Today 11:30am: You approve the repost
Today 12:00pm: Scheduled for TODAY at 2:00pm

Result: Posted 23 hours after original - acceptable but not ideal ⏰
```

---

### Example 4: Stale Content (STALE)

```
3 days ago: Nathan posts about productivity
Today 10am: Your scraper finds it (72 hours old)
Today 10:30am: You approve the repost
Today 11:00am: Scheduled for NEXT WEEK Monday

Result: Old content, low priority - pushed to back of queue ⚠️
```

---

## Scheduling Logic Flow

### When You Approve Multiple Posts

**Scenario:** You approve 5 posts at once with different ages:

```
Post A: 2 hours old (URGENT 🔥)
Post B: 8 hours old (GOOD ✅)
Post C: 20 hours old (OK ⏰)
Post D: 50 hours old (STALE ⚠️)
Post E: 1 hour old (URGENT 🔥)
```

**Scheduler assigns:**

```
Post E (1h old):  Today 11:30am  ← Most urgent!
Post A (2h old):  Today 1:00pm   ← Second URGENT
Post B (8h old):  Today 2:45pm   ← GOOD timing
Post C (20h old): Tomorrow 9:30am ← OK timing
Post D (50h old): Friday 11:00am ← STALE (back of queue)
```

**Result:** Fresh content gets posted quickly, stale content waits.

---

## Configuration

### Adjustable Thresholds

```python
# Default settings (configurable in app/scheduler.py)
GOLDEN_HOUR_URGENT = 3   # < 3 hours = URGENT
GOLDEN_HOUR_GOOD = 12    # < 12 hours = GOOD  
GOLDEN_HOUR_OK = 24      # < 24 hours = OK
GOLDEN_HOUR_STALE = 48   # > 48 hours = STALE
```

**Want to adjust?** Change these values to match your strategy:

**More Aggressive (Repost Everything Fast):**
```python
GOLDEN_HOUR_URGENT = 6   # Larger urgent window
GOLDEN_HOUR_GOOD = 24    # Larger good window
GOLDEN_HOUR_STALE = 72   # More lenient on stale
```

**More Conservative (Only Fresh Content):**
```python
GOLDEN_HOUR_URGENT = 2   # Tighter urgent window
GOLDEN_HOUR_GOOD = 6     # Shorter good window  
GOLDEN_HOUR_STALE = 24   # Stricter on stale
```

---

## Database Tracking

Every scheduled post stores:

```sql
priority_level: 'URGENT' / 'GOOD' / 'OK' / 'STALE'
priority_score: 100 / 75 / 50 / 25
post_age_hours: 2.5 (age when scheduled)
```

**Benefits:**
- See which posts were rushed vs delayed
- Analyze if golden hour strategy is working
- Adjust thresholds based on data

---

## API Response

When you approve a post, you'll see:

```json
{
  "success": true,
  "message": "Post scheduled successfully",
  "post_id": 42,
  "scheduled_for": "2025-12-05T11:45:00",
  "time_until": "45 minutes",
  "priority": {
    "level": "URGENT",
    "emoji": "🔥",
    "age_hours": 2.5,
    "reason": "Original post still in golden hour window"
  }
}
```

---

## Queue Visibility

**GET /schedule/queue** shows priority in queue:

```json
{
  "total_scheduled": 8,
  "queue": [
    {
      "post_id": 1,
      "scheduled_for": "2025-12-05T11:30:00",
      "time_until": "15 minutes",
      "priority": "🔥 URGENT",
      "post_age": "1.2 hours",
      "from": "timcool"
    },
    {
      "post_id": 2,
      "scheduled_for": "2025-12-05T13:00:00",
      "time_until": "1.5 hours",
      "priority": "✅ GOOD",
      "post_age": "7.5 hours",
      "from": "elena-dietrich"
    }
  ]
}
```

---

## Benefits of Golden Hour Optimization

### 1. **Maximum Engagement**
- Your reposts get boosted by LinkedIn algorithm
- Original post is already trending, so yours benefits too

### 2. **Appears in Relevant Conversations**
- People commenting on original see your repost too
- LinkedIn groups related content together

### 3. **Fresher Content**
- Your feed doesn't look like you're reposting old news
- Looks more timely and relevant

### 4. **Better Reach**
- LinkedIn algorithm favors recent, trending topics
- Your post rides the wave of existing momentum

---

## What Happens During Testing

### Initial Scrape (7 Days Lookback)

When you scrape Tim Cool's last 7 days:

```
Found 12 posts:
  3 posts < 3 hours old    → 🔥 URGENT priority
  2 posts < 12 hours old   → ✅ GOOD priority
  4 posts < 24 hours old   → ⏰ OK priority
  3 posts > 48 hours old   → ⚠️ STALE priority
```

### After You Approve All 12

```
Scheduler assigns:
  
  🔥 URGENT Posts (3):
    Post A: Today 11:30am (30 min from now)
    Post B: Today 1:00pm  (2.5 hours from now)
    Post C: Today 2:45pm  (3.75 hours from now)
    
  ✅ GOOD Posts (2):
    Post D: Today 4:30pm  (5.5 hours from now)
    Post E: Tomorrow 9:00am
    
  ⏰ OK Posts (4):
    Post F: Tomorrow 11:00am
    Post G: Tomorrow 1:00pm
    Post H: Friday 10:00am
    Post I: Friday 12:00pm
    
  ⚠️ STALE Posts (3):
    Post J: Next Monday 10:00am
    Post K: Next Monday 12:00pm  
    Post L: Next Tuesday 10:00am
```

**Result:** 
- Fresh content posts quickly (today!)
- Old content waits in queue
- You look current and relevant

---

## Smart Behavior: URGENT Posts

### Special Handling

When a post is **URGENT** (< 3 hours old):

1. **Skip normal queue** - Don't wait for "tomorrow"
2. **Find next slot TODAY** - Even if it means tighter spacing
3. **Override some rules** - Daily limit still applies, but prioritized

**Example:**

```
Current situation:
  - Already scheduled 3 posts today (at daily limit)
  - But new URGENT post comes in (1 hour old)
  
Traditional scheduler: "Sorry, wait until tomorrow"
Golden Hour scheduler: "Let's try to fit it in late today!"

Result: Scheduled for 8:30pm (last possible slot today)
```

---

## Why This Matters

**Without Golden Hour Optimization:**
```
You: *finds Tim's post from 2 hours ago*
You: *approves it*
System: "Scheduled for next Wednesday"
You: 😞 The post is dead by then
```

**With Golden Hour Optimization:**
```
You: *finds Tim's post from 2 hours ago*
You: *approves it*  
System: "🔥 URGENT! Scheduled for 30 minutes from now"
You: 🎉 Riding the engagement wave!
```

---

## Testing It

### Quick Test

```bash
# 1. Scrape Tim Cool (will find posts of various ages)
curl -X POST "http://localhost:8080/linkedin/scrape?handle=timcool&max_posts=20"

# 2. Check what priorities were assigned
curl http://localhost:8080/posts?status=scraped | jq '.posts[] | {id, age: .post_age, priority: .priority_level}'

# 3. Approve some posts via email

# 4. See the smart scheduling
curl http://localhost:8080/schedule/queue | jq
```

You'll see URGENT posts scheduled ASAP, STALE posts pushed back!

---

## Summary

**Golden Hour = Ride the Wave** 🏄

- Fresh posts (< 3h) get priority scheduling
- You post while original is still trending
- Maximum engagement from LinkedIn algorithm
- Looks timely and relevant (not reposting old news)
- Automatic prioritization - just approve and let the system handle it!
