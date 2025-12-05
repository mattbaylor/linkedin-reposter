# VNC Setup for LinkedIn Authentication

## ✅ VNC Server is Running!

Your LinkedIn Reposter container is now running with VNC support.

**Connection Details:**
- **Host**: `localhost` (or your Mac's IP if connecting from another device)
- **Port**: `5900`
- **Password**: None (no password required)
- **Display**: 1920x1080

## Step 1: Connect with Jump Desktop

1. Open **Jump Desktop** on your Mac
2. Click **"+"** to add a new connection
3. Select **VNC** as the protocol
4. Enter connection details:
   - **Name**: LinkedIn Reposter
   - **Address**: `localhost:5900`
   - **Password**: Leave blank (no password)
5. Click **Connect**

You should see a desktop with a gray/black background (Fluxbox window manager).

## Step 2: Run LinkedIn Manual Setup

Once connected via VNC, you'll see the desktop. Now trigger the LinkedIn setup:

### Option A: Via API (Recommended)

In your terminal (outside VNC):
```bash
curl -X POST http://localhost:8080/linkedin/manual-setup
```

This will open a Chromium browser window **inside the VNC session** where you can:
1. See LinkedIn's login page
2. Enter your credentials manually
3. Complete any 2FA or verification challenges
4. Session will be saved automatically

### Option B: Via Browser

1. In the VNC window, right-click to open Fluxbox menu
2. Select terminal (if available)
3. Or just watch for the browser to appear when you trigger the API call

## Step 3: Complete LinkedIn Login

When the browser opens in VNC:

1. **Log in to LinkedIn** with your credentials
2. **Complete any verification** (2FA, email code, etc.)
3. **Wait for confirmation** - the script will detect when you're logged in
4. **Session saved** - the browser will close and session is saved to `/app/data/linkedin_session/`

## Step 4: Verify Session

After manual setup completes:

```bash
# Check session status
curl http://localhost:8080/linkedin/session-status | jq

# Should show:
# {
#   "session_exists": true,
#   "health_status": "healthy",
#   "message": "Session is healthy (age: 0 days)"
# }
```

## Step 5: Test Scraping

Now try scraping with the authenticated session:

```bash
curl -X POST "http://localhost:8080/linkedin/scrape?handle=timcool&max_posts=10" | jq
```

You should see posts being scraped successfully!

## Troubleshooting

### Can't Connect to VNC

```bash
# Check if VNC is running
docker compose logs app | grep VNC

# Check if port is open
netstat -an | grep 5900

# Restart container
docker compose restart
```

### Browser Not Appearing

```bash
# Check logs
docker compose logs -f app

# The browser should appear in the VNC window when you call /linkedin/manual-setup
```

### LinkedIn Blocks Login

If LinkedIn detects automation even in headed mode:
- Try using a different browser profile
- Clear LinkedIn cookies
- Wait a few minutes and try again
- Use a different network (VPN, hotspot)

## After Setup

Once the session is established:

1. **VNC no longer needed** - The session persists in `/app/data/linkedin_session/`
2. **Disable VNC** - You can remove `DISPLAY=:99` from docker-compose.yml
3. **Session lasts 30 days** - Re-run manual setup when it expires
4. **Email alerts** - You'll get warnings at 25 days

## Session Maintenance

```bash
# Check session age
curl http://localhost:8080/linkedin/session-status | jq '.age_days'

# When it expires (after 30 days), just re-enable VNC and run manual setup again
```

---

**Current Status**: VNC server is running and waiting for your connection!

Connect with Jump Desktop to `localhost:5900` and then run:
```bash
curl -X POST http://localhost:8080/linkedin/manual-setup
```
