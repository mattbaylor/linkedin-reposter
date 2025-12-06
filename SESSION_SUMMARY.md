# LinkedIn Reposter - Session Summary

## Completed Tasks

### 1. Fixed Browser Session Management ✅
- Modified scraping to use single browser session across all handles
- Prevents repeated LinkedIn security checks
- Browser starts once before loop, stops once after all handles

### 2. Improved AI Content Generation ✅
- Extract real names from LinkedIn profiles (e.g., "Tim Cool" not "timcool")
- AI summarization creates 30-50% shorter variants
- Third-person attribution uses full names

### 3. Company Page Support ✅
- Handles with `company/` prefix use correct URL format
- Personal profiles and company pages both work

### 4. Web-Based VNC Viewer Implementation ✅
- Integrated noVNC for browser-based VNC access
- No Jump Desktop required - works in any browser
- Endpoints:
  - Local: `http://localhost:8080/admin/vnc`
  - Production: `https://liposter.example.com/admin/vnc`

### 5. Security Challenge Detection & Email Alerts ✅
- Detects LinkedIn security challenges during login and scraping
- Sends HTML email alerts via Postal
- Email includes clickable link to web VNC viewer
- Automatic retry after manual resolution

### 6. Production Deployment Setup ✅
- GitHub Actions workflow for automated Docker builds
- Images published to GHCR: `ghcr.io/mattbaylor/linkedin-reposter:latest`
- Production docker-compose configuration
- Comprehensive DEPLOYMENT.md guide

### 7. Caddy Configuration ✅
- WebSocket proxying for noVNC
- Path-based routing with `uri strip_prefix`
- Proper handling of production vs local connections

## System Architecture

```
Production Flow:
1. User visits: https://liposter.example.com/admin/vnc
2. Caddy proxies /websockify* to localhost:6080
3. Websockify bridges WebSocket ↔ VNC (port 5900)
4. noVNC displays browser session in iframe

Security Challenge Flow:
1. Scraper detects challenge → raises exception
2. Email sent with VNC link
3. Admin completes challenge via web browser
4. System checks every 10s for resolution
5. Scraper automatically continues

Scraping Flow:
1. Start browser once (with login)
2. For each handle:
   - Navigate to profile/company page
   - Check for security challenge
   - If challenge: email + wait → retry
   - Scrape posts
   - Extract real names
3. Stop browser once
4. Generate AI variants
5. Send approval emails
```

## Configuration Files

### docker-compose.yml (Development)
- Uses GHCR image by default
- Can uncomment `build:` section for local builds
- Environment: `dev`
- Infisical project ID: `4627ccea-f94c-4f19-9605-6892dfd37ee0`

### docker-compose.production.yml (TrueNAS)
- Uses GHCR image only (no local build)
- Environment: `prod`
- Designed for server deployment

### .github/workflows/docker-publish.yml
- Triggers on push to `main` or tags
- Builds and pushes to GHCR
- Tags: `latest`, `main-{sha}`, `v1.2.3` (for tagged releases)
- Uses GitHub Actions cache for faster builds

## Secrets (Infisical)

### Development Environment (`dev`)
- Used for local Mac testing
- Separate from production

### Production Environment (`prod`)
- Real LinkedIn credentials
- Production email settings
- Used on TrueNAS

Secrets stored:
- `LINKEDIN_EMAIL`
- `LINKEDIN_PASSWORD`
- `LINKEDIN_HANDLES` (10 handles)
- `APPROVAL_EMAIL`
- `POSTAL_SERVER_URL`
- `POSTAL_API_KEY`
- `GITHUB_TOKEN` (for AI models)
- `APP_BASE_URL`
- `TIMEZONE` (MST/MDT)

## Deployment Steps

### GitHub Actions Build (In Progress)
```bash
# Status: Building Docker image
# URL: https://github.com/mattbaylor/linkedin-reposter/actions/runs/19980102311
# When complete, image will be at: ghcr.io/mattbaylor/linkedin-reposter:latest
```

### TrueNAS Deployment (After Build Completes)
```bash
# SSH to TrueNAS
ssh your-truenas-server

# Create directory
mkdir -p /mnt/pool/apps/linkedin-reposter
cd /mnt/pool/apps/linkedin-reposter

# Download production compose file
curl -O https://raw.githubusercontent.com/mattbaylor/linkedin-reposter/main/docker-compose.production.yml
mv docker-compose.production.yml docker-compose.yml

# Create .env file with Infisical token
cat > .env << 'EOF'
INFISICAL_URL=https://infisical.example.com
INFISICAL_TOKEN=your-production-token
INFISICAL_PROJECT_ID=4627ccea-f94c-4f19-9605-6892dfd37ee0
INFISICAL_ENVIRONMENT=prod
DISPLAY=:99
EOF

# Create data directory
mkdir -p data

# Pull and start
docker compose pull
docker compose up -d

# Check logs
docker compose logs -f
```

### Caddy Configuration (TrueNAS)
Ensure Caddyfile has:
```caddy
liposter.example.com {
    handle /websockify* {
        uri strip_prefix /websockify
        reverse_proxy localhost:6080
    }
    
    reverse_proxy http://localhost:8080 {
        header_up Host {http.request.host}
        header_up X-Real-IP {remote_host}
    }
    
    encode gzip
}
```

## Testing

### Local Testing
```bash
# Health check
curl http://localhost:8080/health

# Stats
curl http://localhost:8080/stats

# Trigger scrape
curl -X POST http://localhost:8080/test/trigger-scrape

# VNC access
open http://localhost:8080/admin/vnc
```

### Production Testing
```bash
# Health check
curl https://liposter.example.com/health

# VNC access
open https://liposter.example.com/admin/vnc
```

## Known Issues & Solutions

### GitHub Models Rate Limiting
- **Issue**: 429 Too Many Requests after 4-5 posts
- **Impact**: Some posts won't get AI variants generated
- **Solution**: Gracefully skips and continues with next post
- **Future Fix**: Add retry with exponential backoff

### LinkedIn Session Expiration
- **Issue**: Sessions expire after ~30 days
- **Solution**: Automatic security challenge detection + email alert
- **Action**: Complete challenge via web VNC when email received

## Next Steps

1. ✅ **Wait for GitHub Actions build to complete** (~5-10 minutes)
2. **Deploy to TrueNAS** using steps above
3. **Test production deployment**:
   - Verify health endpoint
   - Test web VNC access
   - Trigger test scrape
4. **Monitor first scheduled run** (next 11am or 4pm MST)

## Files Created/Modified

### New Files
- `.github/workflows/docker-publish.yml` - CI/CD pipeline
- `DEPLOYMENT.md` - Deployment guide
- `docker-compose.production.yml` - Production config
- `app/linkedin_selenium.py` - Selenium automation with security handling
- `app/health_monitor.py` - Health monitoring
- `app/utils.py` - Utility functions
- `app/linkedin_manual_login.py` - Manual login support

### Modified Files
- `docker-compose.yml` - Updated to use GHCR image
- `VNC_SETUP.md` - Added web VNC and Caddy config
- `app/main.py` - Added /admin/vnc endpoint and security handling
- `docker-entrypoint.sh` - Added websockify startup
- `Dockerfile` - Added noVNC download and setup
- `requirements.txt` - Added websockify

## Resources

- **GitHub Repository**: https://github.com/mattbaylor/linkedin-reposter
- **GHCR Image**: https://github.com/mattbaylor/linkedin-reposter/pkgs/container/linkedin-reposter
- **GitHub Actions**: https://github.com/mattbaylor/linkedin-reposter/actions
- **Production URL**: https://liposter.example.com
- **VNC URL**: https://liposter.example.com/admin/vnc

## Monitoring Handles

Current handles (10 total):
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

Schedule:
- **Scraping**: 11:00 AM and 4:00 PM MST/MDT
- **Publishing**: Every 5 minutes (checks queue)

---

**Status**: Development complete, GitHub Actions build in progress
**Date**: December 5, 2025
**Environment**: Mac M2 (dev) → TrueNAS (prod)
