# Security and Optimization Updates

This document describes recent security hardening and optimization improvements to the LinkedIn Reposter.

## Security Improvements

### Secret Masking in Logs

**What changed:** All sensitive values (passwords, tokens, API keys, secrets) are now fully masked in application logs.

**Before:**
```
✓ LINKEDIN_PASSWORD: mypasswo...
✓ GITHUB_TOKEN: ghp_1234...
```

**After:**
```
✓ LINKEDIN_PASSWORD: ***MASKED***
✓ GITHUB_TOKEN: ***MASKED***
```

**Impact:** Prevents accidental secret exposure in log files, debugging output, or monitoring systems.

### VNC Password Requirement

**What changed:** The default VNC password has been removed from `docker-compose.yml`.

**Before:**
```yaml
- VNC_PASSWORD=${VNC_PASSWORD:-linkedin123}  # Weak default!
```

**After:**
```yaml
- VNC_PASSWORD=${VNC_PASSWORD}  # REQUIRED: Set a strong password
```

**Action Required:** You **must** set a strong VNC password in your `.env` file:
```bash
# Add to .env
VNC_PASSWORD=your-strong-password-here
```

**Why:** Default passwords are a security risk. VNC provides remote desktop access to the browser automation, so it must be properly secured.

### Database Uniqueness Constraints

**What changed:** Added database-level constraints to prevent duplicate posts and scheduling:

1. **Unique Post URLs**: `linkedin_posts.original_post_url` now has a unique constraint (when not null) to prevent scraping the same post twice.

2. **Unique Scheduling**: `scheduled_posts` table enforces uniqueness on `(post_id, variant_id)` to prevent accidentally scheduling the same post/variant combination multiple times.

3. **Unique Approval Tokens**: `approval_requests.approval_token` already had uniqueness enforced - this is now documented.

**Impact:** 
- Prevents duplicate post scraping
- Prevents double-scheduling of approved posts
- Ensures data integrity at the database level

## Optimization Improvements

### Scheduler Duplication Bug Fixed

**What changed:** Removed duplicate code block in `app/scheduler.py` (lines 166-207) that was creating two database entries for each scheduled post.

**Before:**
```python
# Create scheduled post
scheduled_post = ScheduledPost(...)
db.add(scheduled_post)
await db.commit()

# DUPLICATE BLOCK - BUG!
scheduled_post = ScheduledPost(...)  
db.add(scheduled_post)
await db.commit()
```

**After:**
```python
# Create scheduled post (once!)
scheduled_post = ScheduledPost(...)
db.add(scheduled_post)
await db.commit()
```

**Impact:** Each approved post now creates exactly one scheduled database row instead of two.

### Jitter Clamping

**What changed:** Scheduling jitter (random time adjustment for natural appearance) is now clamped to respect posting windows and minimum spacing.

**Before:**
```python
# Apply jitter without bounds checking
jittered_time = candidate_time + timedelta(minutes=random_jitter)
```

**After:**
```python
# Apply jitter with bounds checking
jittered_time = candidate_time + timedelta(minutes=random_jitter)
jittered_time = normalize_to_posting_hours(jittered_time)
# Also ensure minimum spacing is maintained
```

**Impact:** 
- Jitter no longer pushes posts outside configured posting hours (6am-9pm)
- Minimum spacing between posts is always maintained even after jitter
- More predictable and reliable scheduling

### Timezone Awareness (UTC)

**What changed:** All datetime operations now use timezone-aware UTC timestamps instead of naive local time.

**Before:**
```python
now = datetime.now()  # Naive, local timezone
scheduled_for = datetime.now()
approved_at = datetime.utcnow()  # Deprecated, no timezone
```

**After:**
```python
now = datetime.now(timezone.utc)  # Aware, UTC
scheduled_for = datetime.now(timezone.utc)
approved_at = datetime.now(timezone.utc)
```

**Files affected:**
- `app/scheduler.py`
- `app/main.py`
- `app/models.py`

**Impact:**
- Consistent time handling across the application
- No timezone-related bugs when comparing times
- Proper handling of daylight saving time transitions
- Works correctly regardless of server timezone

**Note:** Posting hour configuration (e.g., 6am-9pm) is still interpreted in your configured timezone (default: `America/Denver`). The system converts to/from UTC internally for consistency.

### Async-Safe Delays

**What changed:** Added async versions of all delay/sleep functions to avoid blocking the event loop.

**New functions in `app/utils.py`:**
- `async_random_delay(min, max)` - Async version of random_delay
- `async_random_short_delay()` - 0.5-1.5 seconds
- `async_random_medium_delay()` - 2-4 seconds  
- `async_random_long_delay()` - 5-8 seconds
- `async_random_profile_delay()` - 1-3 minutes
- `async_human_scroll_delay()` - 0.8-2.0 seconds

**When to use:**
- **Async functions**: Use `async_*` versions (e.g., `await async_random_delay()`)
- **Selenium/sync code**: Use regular versions (e.g., `random_delay()`)

**Impact:**
- Async operations no longer block the event loop
- Better concurrency and performance
- Maintains natural human-like timing for both sync and async contexts

### Retry with Exponential Backoff

**What added:** New `app/retry_utils.py` module with retry decorators for external API calls.

**Usage example:**
```python
from app.retry_utils import async_retry

@async_retry(max_retries=3, base_delay=1.0, max_delay=60.0)
async def call_external_api():
    # This will retry up to 3 times with exponential backoff
    response = await httpx.get("https://api.example.com")
    return response.json()
```

**Features:**
- Exponential backoff (1s, 2s, 4s, 8s, ...)
- Random jitter to prevent thundering herd
- Configurable max delay (default: 60s)
- Both async (`async_retry`) and sync (`sync_retry`) decorators
- Detailed logging of retry attempts

**Impact:**
- More resilient external API calls
- Automatic recovery from transient failures
- Better handling of rate limits

## Dependency Updates

**What changed:** Updated all major dependencies to current stable versions (Python 3.11 compatible).

**Key updates:**
- FastAPI: `0.109.0` → `0.115.5`
- Uvicorn: `0.27.0` → `0.32.1`
- SQLAlchemy: `2.0.25` → `2.0.36`
- Selenium: `4.16.0` → `4.27.1`
- Playwright: `1.41.0` → `1.49.1`
- Pydantic: `2.5.3` → `2.10.3`
- OpenAI: `1.10.0` → `1.55.3`
- httpx: `0.26.0` → `0.28.1`

**Impact:**
- Security patches and bug fixes
- Performance improvements
- Better Python 3.11 compatibility
- Modern async/await support

## Recommended Actions

### Immediate (Required)

1. **Set VNC Password**: Add `VNC_PASSWORD` to your `.env` file with a strong password
2. **Review Logs**: Check that no secrets are being logged (they should show as `***MASKED***`)
3. **Update Dependencies**: Rebuild Docker image to get updated dependencies

### Short Term (Recommended)

1. **Check Database**: Verify no duplicate scheduled posts exist from the old bug
2. **Monitor Scheduling**: Ensure jitter is working correctly and posts stay within posting hours
3. **Test Timezone**: Verify posting times are correct in your timezone

### Long Term (Optional)

1. **Security Audit**: Consider running `pip-audit` and `bandit` on the codebase
2. **Session Storage**: Document/implement encryption for LinkedIn session cookies if stored
3. **WebDriver Pinning**: Document specific Chromium/ChromeDriver versions for reproducibility

## Security Tooling

### pip-audit (Dependency Vulnerability Scanning)

```bash
# Install pip-audit
pip install pip-audit

# Scan dependencies for known vulnerabilities
pip-audit -r requirements.txt
```

### bandit (Static Security Analysis)

```bash
# Install bandit
pip install bandit

# Scan code for security issues
bandit -r app/
```

### Recommended: Add to CI/CD

If you have a CI/CD pipeline, consider adding these checks:

```yaml
# Example GitHub Actions job
security-scan:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: pip install pip-audit bandit
    - name: Check dependencies
      run: pip-audit -r requirements.txt
    - name: Security scan
      run: bandit -r app/ -f json -o bandit-report.json
```

## Migration Notes

### Database Schema Changes

The new uniqueness constraints are applied when creating tables. If you have an existing database:

1. **Backup your database** first:
   ```bash
   docker cp linkedin-reposter:/app/data/linkedin_reposter.db ./backup.db
   ```

2. **Option A: Fresh start** (loses history):
   ```bash
   docker-compose down
   rm data/linkedin_reposter.db
   docker-compose up -d
   ```

3. **Option B: Manual migration** (keeps history):
   ```sql
   -- Connect to database
   sqlite3 data/linkedin_reposter.db
   
   -- Add unique constraint on post URLs (may fail if duplicates exist)
   CREATE UNIQUE INDEX idx_unique_post_url 
   ON linkedin_posts(original_post_url) 
   WHERE original_post_url IS NOT NULL;
   
   -- Add unique constraint on scheduled posts
   -- First, remove any duplicates manually
   CREATE UNIQUE INDEX uq_scheduled_post_variant 
   ON scheduled_posts(post_id, variant_id);
   ```

### No Breaking Changes

All changes are backward compatible:
- Existing code continues to work
- New async functions are additions, not replacements
- Retry utilities are opt-in
- Timezone changes are internal (posting hours still in configured TZ)

## Questions?

For questions or issues related to these changes, please:
1. Check the updated documentation in README.md
2. Review this SECURITY_UPDATES.md document
3. Open an issue on GitHub with the `security` or `optimization` label
