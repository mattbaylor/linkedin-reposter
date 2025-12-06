# Admin Dashboard Guide

## Overview

The Admin Dashboard provides a web-based interface for managing LinkedIn posts, approving variants, and controlling the reposter workflow without needing to check email.

**URL**: `http://localhost:8080/admin/dashboard` (local) or `https://liposter.example.com/admin/dashboard` (production)

## Features

### 1. Dashboard View

**Stats Cards** (top of page):
- Total Posts
- Awaiting Approval
- Approved
- Posted
- Rejected

**Filters**:
- Status filter (All, Awaiting Approval, Approved, Rejected, Posted, Failed)
- Author filter (dropdown of all handles)
- Refresh button

**Default View**: Shows posts awaiting approval

### 2. Post Management

Each post card shows:
- **Author name** and handle
- **Scraped date**
- **Status badge** (color-coded)
- **Original post content**
- **AI-generated variants** (expandable)

### 3. Available Actions

#### Per Variant:
- **✅ Approve** - Approve this variant for posting (schedules for 1 hour from now)

#### Per Post:
- **🔄 Regenerate AI** - Create 3 new AI variants (replaces existing ones)
- **❌ Reject All** - Reject all variants for this post
- **🗑️ Delete** - Permanently delete post and all variants

## Usage

### Approve a Post

1. Open dashboard: `http://localhost:8080/admin/dashboard`
2. Find the post you want to approve
3. Click "Show AI Variants" to expand
4. Review the 3 variants
5. Click **✅ Approve** on your preferred variant
6. Post will be scheduled for publishing in 1 hour

### Regenerate AI Variants

If the AI variants aren't good:

1. Click **🔄 Regenerate AI** button
2. Wait ~10-30 seconds (AI processing)
3. Page will reload with new variants
4. Review and approve your favorite

### Reject a Post

If you don't want to repost at all:

1. Click **❌ Reject All**
2. Post status changes to "Rejected"
3. Won't appear in default view anymore

### Delete a Post

To permanently remove (cleanup):

1. Click **🗑️ Delete**
2. Confirm the action
3. Post and all variants are deleted from database

## Filtering

### By Status

Use the status dropdown to filter:
- **Awaiting Approval** (default) - Posts needing your attention
- **Approved** - Posts you've approved but not yet posted
- **Posted** - Successfully posted to LinkedIn
- **Rejected** - Posts you rejected
- **Failed** - Posts that failed to post (may need retry)

### By Author

Filter by specific LinkedIn handle to see posts from one person/company.

## Navigation

**Header Links**:
- **🏠 Dashboard** - Main dashboard (current page)
- **🖥️ VNC Viewer** - Web-based VNC for security challenges
- **📈 Stats API** - JSON stats endpoint
- **📚 API Docs** - FastAPI auto-generated docs

## Workflows

### Daily Workflow

1. **Check Dashboard** after scheduled scrapes (11 AM and 4 PM MST)
2. **Review pending posts** (default view)
3. **Approve favorites** or regenerate if needed
4. **Check Posted** section to see what's been published

### Bulk Management

1. **Filter by status** to see all pending
2. **Approve multiple** one after another
3. **Reject unwanted** posts quickly
4. **Delete old** posts for cleanup

### Quality Control

1. Find a posted variant that worked well
2. Compare with original to see AI quality
3. Use insights to evaluate future variants

## Security (Authelia Protection)

When deployed to production with Authelia:

### Protected Routes (require login):
- `/admin/*` - All admin endpoints including dashboard
- `/websockify/*` - VNC WebSocket
- `/stats` - Statistics
- `/docs` - API documentation
- `/test/*` - Test endpoints

### Public Routes (no auth):
- `/webhook/*` - Email approval links
- `/health` - Health check

### First Access:

1. Visit `https://liposter.example.com/admin/dashboard`
2. Redirected to `https://auth.example.com`
3. Log in with Authelia credentials
4. Redirected back to dashboard

## API Endpoints

The dashboard uses these API endpoints (also available for direct use):

### Approve Variant
```bash
POST /admin/posts/{post_id}/approve/{variant_id}
```

Example:
```bash
curl -X POST http://localhost:8080/admin/posts/1/approve/3
```

Response:
```json
{
  "success": true,
  "message": "Variant approved",
  "scheduled_time": "2025-12-06T01:00:00"
}
```

### Regenerate Variants
```bash
POST /admin/posts/{post_id}/regenerate
```

Example:
```bash
curl -X POST http://localhost:8080/admin/posts/1/regenerate
```

Response:
```json
{
  "success": true,
  "message": "Generated 3 new variants"
}
```

### Reject Post
```bash
POST /admin/posts/{post_id}/reject
```

Example:
```bash
curl -X POST http://localhost:8080/admin/posts/1/reject
```

Response:
```json
{
  "success": true,
  "message": "Post rejected"
}
```

### Delete Post
```bash
DELETE /admin/posts/{post_id}
```

Example:
```bash
curl -X DELETE http://localhost:8080/admin/posts/1
```

Response:
```json
{
  "success": true,
  "message": "Post deleted"
}
```

## Comparison: Email vs Dashboard

### Email Approval (Original)
**Pros**:
- Works from anywhere
- No login needed
- Email notification

**Cons**:
- One post per email
- Can't regenerate variants
- Can't see all pending at once
- Must click email link

### Dashboard (New)
**Pros**:
- See all posts at once
- Filter and search
- Regenerate AI variants
- Bulk management
- Better UX

**Cons**:
- Requires login (in production)
- Must navigate to URL
- No push notifications

### Recommendation

Use **both**:
- **Email** - Quick approvals on the go
- **Dashboard** - Batch management, regeneration, quality control

## Troubleshooting

### Dashboard Not Loading

```bash
# Check service is running
docker compose ps

# Check logs
docker compose logs --tail 50

# Restart
docker compose restart
```

### Can't Approve Variant

**Error**: "Post not found"
- Post may have been deleted
- Refresh the page

**Error**: "Variant not found"
- Variant ID mismatch
- Refresh the page

### Regenerate Takes Too Long

- Normal: 10-30 seconds for AI processing
- If > 1 minute: May have hit rate limit
- Check logs: `docker compose logs | grep -i error`

### Stats Not Updating

- Stats are calculated on page load
- Click **🔄 Refresh** button to update

## Tips & Tricks

### Keyboard Shortcuts

- **Cmd/Ctrl + R** - Refresh page (update stats)
- **Cmd/Ctrl + F** - Search page content

### URL Parameters

Bookmark filtered views:

```
# Awaiting approval
http://localhost:8080/admin/dashboard?status=awaiting_approval

# Approved but not posted
http://localhost:8080/admin/dashboard?status=approved

# All posts from timcool
http://localhost:8080/admin/dashboard?author=timcool

# Combine filters
http://localhost:8080/admin/dashboard?status=awaiting_approval&author=timcool
```

### Batch Processing

1. Open dashboard in multiple tabs
2. One tab per filter (status, author)
3. Process each batch independently

### Mobile Access

Dashboard is responsive and works on:
- iPhone/iPad (Safari)
- Android (Chrome)
- Tablets

Buttons are touch-friendly, but regenerate may be slow on mobile data.

## Future Enhancements

Potential additions (not yet implemented):

- [ ] Real-time updates (WebSocket)
- [ ] Keyboard shortcuts for approve/reject
- [ ] Inline editing of variants
- [ ] Preview before posting
- [ ] Analytics dashboard
- [ ] Export/import posts
- [ ] Scheduled posting time picker
- [ ] Dark mode

---

**Current Version**: 1.0  
**Last Updated**: December 5, 2025
