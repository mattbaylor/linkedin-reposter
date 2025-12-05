# LinkedIn Reposter - API Endpoints

Base URL: `http://192.0.2.10:8080` (local) or `https://liposter.example.com` (public)

---

## Health & Monitoring

### GET /
Root endpoint - service info

**Response:**
```json
{
  "service": "LinkedIn Reposter",
  "version": "0.1.0",
  "status": "running"
}
```

---

### GET /health
Health check with configuration details

**Response:**
```json
{
  "status": "healthy",
  "environment": "dev",
  "ai_model": "gpt-4o",
  "timezone": "America/Denver",
  "database_initialized": true
}
```

---

### GET /stats
Statistics about posts and processing

**Response:**
```json
{
  "total_posts": 42,
  "total_variants": 126,
  "awaiting_approval": 5,
  "approved": 12,
  "rejected": 8,
  "posted": 15,
  "failed": 2
}
```

---

## Post Management

### GET /posts
List all LinkedIn posts with filtering

**Query Parameters:**
- `status` (optional): Filter by status (scraped, awaiting_approval, approved, rejected, posted, failed)
- `author_handle` (optional): Filter by LinkedIn handle
- `limit` (default: 50, max: 100): Posts per page
- `offset` (default: 0): Pagination offset

**Example:**
```bash
curl "http://192.0.2.10:8080/posts?status=awaiting_approval&limit=10"
```

**Response:**
```json
{
  "total": 42,
  "limit": 10,
  "offset": 0,
  "posts": [...]
}
```

---

### GET /posts/{post_id}
Get detailed information about a specific post

**Example:**
```bash
curl http://192.0.2.10:8080/posts/1
```

**Response:**
```json
{
  "id": 1,
  "author_name": "Tim Cool",
  "author_handle": "timcool",
  "content": "...",
  "url": "https://linkedin.com/...",
  "status": "approved",
  "variants": [...],
  "approval_request": {...}
}
```

---

## Approval Webhooks

### GET /webhook/approve/{token}
Approve a post variant (called from email link)

**Query Parameters:**
- `variant_id` (required): ID of variant to approve

**Example:**
```bash
curl "http://192.0.2.10:8080/webhook/approve/abc123...?variant_id=2"
```

**Response:**
```json
{
  "success": true,
  "message": "Post variant approved successfully!",
  "post_id": 1,
  "variant_id": 2
}
```

---

### GET /webhook/reject/{token}
Reject all variants for a post (called from email link)

**Example:**
```bash
curl http://192.0.2.10:8080/webhook/reject/abc123...
```

**Response:**
```json
{
  "success": true,
  "message": "Post rejected successfully.",
  "post_id": 1
}
```

---

## LinkedIn Session Management

### POST /linkedin/manual-setup
One-time manual login to establish trusted session

**Use Cases:**
- Initial setup
- Session expired (every ~30 days)
- LinkedIn requires re-verification

**Example:**
```bash
curl -X POST http://192.0.2.10:8080/linkedin/manual-setup
```

**What Happens:**
1. Browser opens (non-headless)
2. You login manually
3. Complete verification challenges
4. Session saved automatically
5. Browser closes

**Response:**
```json
{
  "success": true,
  "message": "LinkedIn session established and saved successfully!",
  "session_file": "/app/data/linkedin_session/state.json",
  "next_steps": [...]
}
```

**Important:**
- Run on your Mac (not headless server)
- Takes 1-2 minutes
- Session lasts ~30 days

---

### POST /linkedin/cookie-auth
Authenticate using li_at cookie (alternative to manual setup)

**Query Parameters:**
- `li_at_cookie` (required): LinkedIn li_at cookie value

**How to Get Cookie:**
1. Login to LinkedIn in browser
2. F12 → Application → Cookies → linkedin.com
3. Copy value of `li_at` cookie

**Example:**
```bash
curl -X POST "http://192.0.2.10:8080/linkedin/cookie-auth?li_at_cookie=AQEDATEa..."
```

**Response:**
```json
{
  "success": true,
  "message": "LinkedIn session established with cookie successfully!",
  "session_file": "/app/data/linkedin_session/state.json"
}
```

---

### GET /linkedin/session-status
Check session health and age

**Example:**
```bash
curl http://192.0.2.10:8080/linkedin/session-status
```

**Response (Healthy):**
```json
{
  "session_exists": true,
  "session_file": "/app/data/linkedin_session/state.json",
  "age_days": 5,
  "health_status": "healthy",
  "message": "Session is healthy",
  "email_sent": false,
  "warnings": [],
  "recommendations": []
}
```

**Response (Warning - 25+ days):**
```json
{
  "session_exists": true,
  "age_days": 27,
  "health_status": "warning",
  "message": "Session expiring soon",
  "email_sent": true,
  "warnings": ["Session is 27 days old"],
  "recommendations": ["Refresh session within 5 days"]
}
```

**Response (Expired - 30+ days):**
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

### POST /linkedin/scrape
Scrape posts from a LinkedIn user

**Query Parameters:**
- `handle` (required): LinkedIn handle (e.g., "timcool")
- `max_posts` (default: 10, max: 50): Max posts to scrape

**Example:**
```bash
curl -X POST "http://192.0.2.10:8080/linkedin/scrape?handle=timcool&max_posts=5"
```

**What Happens:**
1. Checks session health (blocks if expired)
2. Scrapes recent posts from profile
3. Saves new posts to database
4. Returns scraped posts

**Response:**
```json
{
  "success": true,
  "message": "Scraped 5 posts from @timcool (3 new)",
  "handle": "timcool",
  "scraped_count": 5,
  "new_posts_count": 3,
  "session_health": "healthy",
  "posts": [
    {
      "author_name": "Tim Cool",
      "author_handle": "timcool",
      "content": "...",
      "url": "https://linkedin.com/...",
      "post_date": "2025-01-05T10:30:00"
    }
  ]
}
```

**Error (Session Expired):**
```json
{
  "detail": "LinkedIn session expired. Please refresh at https://liposter.example.com/linkedin/manual-setup"
}
```

---

### POST /linkedin/publish/{post_id}
Publish an approved post to LinkedIn

**Path Parameters:**
- `post_id`: ID of approved post

**Example:**
```bash
curl -X POST http://192.0.2.10:8080/linkedin/publish/1
```

**What Happens:**
1. Checks session health (blocks if expired)
2. Verifies post is approved
3. Publishes approved variant to LinkedIn
4. Updates post status to "posted"

**Response:**
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

**Errors:**
- 404: Post not found
- 400: Post not approved / No approved variant
- 403: Session expired
- 500: Publishing failed

---

## Test Endpoints

### POST /test/send-approval-email
Send test approval email using existing post

**Example:**
```bash
curl -X POST http://192.0.2.10:8080/test/send-approval-email
```

**Response:**
```json
{
  "success": true,
  "message": "Test approval email sent successfully",
  "post_id": 1,
  "approval_token": "abc123...",
  "approval_links": {
    "variant_1": "https://liposter.example.com/webhook/approve/abc123?variant_id=1",
    "variant_2": "https://liposter.example.com/webhook/approve/abc123?variant_id=2",
    "variant_3": "https://liposter.example.com/webhook/approve/abc123?variant_id=3",
    "reject": "https://liposter.example.com/webhook/reject/abc123"
  }
}
```

---

### POST /test/generate-variants
Test AI variant generation with sample post

**Example:**
```bash
curl -X POST http://192.0.2.10:8080/test/generate-variants
```

**Response:**
```json
{
  "success": true,
  "message": "Variants generated successfully",
  "original_post": "...",
  "variants": [
    {
      "variant_number": 1,
      "content": "..."
    },
    {
      "variant_number": 2,
      "content": "..."
    },
    {
      "variant_number": 3,
      "content": "..."
    }
  ],
  "model": "gpt-4o"
}
```

---

## Session Health States

| Age | Status | Operations | Email Alert |
|-----|--------|-----------|-------------|
| 0-24 days | `healthy` | All work | No |
| 25-29 days | `warning` | All work | Yes (once) |
| 30+ days | `expired` | **Blocked** | Yes (daily) |

---

## Common Workflows

### Initial Setup
```bash
# 1. Setup LinkedIn session (one-time)
curl -X POST http://192.0.2.10:8080/linkedin/manual-setup

# 2. Verify session
curl http://192.0.2.10:8080/linkedin/session-status

# 3. Test scraping
curl -X POST "http://192.0.2.10:8080/linkedin/scrape?handle=timcool&max_posts=5"
```

---

### Daily Operations (Automated in Phase 6)
```bash
# 1. Scrape posts from monitored handles
curl -X POST "http://192.0.2.10:8080/linkedin/scrape?handle=timcool&max_posts=10"

# 2. Generate AI variants (happens automatically)

# 3. Send approval email (happens automatically)

# 4. User clicks approval link in email

# 5. Publish approved post
curl -X POST http://192.0.2.10:8080/linkedin/publish/1
```

---

### Session Refresh (Every ~25 days)
```bash
# 1. Check if refresh needed
curl http://192.0.2.10:8080/linkedin/session-status

# 2. If age_days > 25, refresh session
curl -X POST http://192.0.2.10:8080/linkedin/manual-setup

# 3. Verify refresh
curl http://192.0.2.10:8080/linkedin/session-status
# Should show: age_days: 0
```

---

## Error Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Invalid parameters, post not approved |
| 401 | Unauthorized | Session invalid, login failed |
| 403 | Forbidden | Session expired, operation blocked |
| 404 | Not Found | Post/token not found |
| 410 | Gone | Approval request expired |
| 500 | Server Error | LinkedIn error, automation failure |

---

## Next Phase: Scheduler

Phase 6 will add:
- APScheduler for 11am & 4pm MST
- Automated workflow: scrape → AI → email → await → post
- Monitor all 7 LinkedIn handles
- Automatic session health checks
- Email alerts for failures

