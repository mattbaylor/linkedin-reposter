# LinkedIn Reposter

Automated LinkedIn post monitoring and reposting service with AI-powered content generation and web-based approval workflow.

## Features

- 🔍 Monitor LinkedIn profiles and company pages for new posts
- 🤖 AI-powered post rephrasing using **GitHub Copilot GPT-4o** (unlimited) with fallback to GitHub Models
- 🎛️ **Admin Dashboard** - Web UI for approving posts, regenerating variants, and managing content
- 📧 Email approval workflow via Postal (optional - dashboard preferred)
- 🔐 Secure secret management with **Infisical Machine Identity** (auto-updating tokens)
- 🖥️ **Web-based VNC** for LinkedIn manual authentication and CAPTCHA solving
- ⏰ Scheduled monitoring (5:30am & 1:00pm MST/MDT)
- 🎯 **Smart Scheduling** - Priority-based queue (URGENT > GOOD > OK > STALE) with automatic conflict resolution
- 🗑️ **Schedule Management** - Delete scheduled posts, auto-scrub conflicts, and manual schedule regeneration
- 🤖 **Human-like Scraping** - Random 1-3 minute delays between profiles to avoid detection
- 🐳 Fully containerized with Docker
- 🏗️ Multi-architecture support (arm64 + amd64) via GitHub Actions

<img width="1505" height="1609" alt="image" src="https://github.com/user-attachments/assets/53cdd63e-252f-4a26-8892-db0bf4c90ecd" />

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   LinkedIn Monitor Service                   │
│                      (Docker Container)                      │
├─────────────────────────────────────────────────────────────┤
│  1. Post Monitor → Track LinkedIn handles (Selenium)        │
│  2. AI Engine → Generate variants (Copilot GPT-4o)         │
│  3. Admin Dashboard → Web UI for approval/management       │
│  4. Email Approval → Send via Postal (optional)            │
│  5. LinkedIn Poster → Publish approved posts (Selenium)    │
│  6. SQLite Database → Track posts, approvals, history       │
│  7. VNC Server → Manual auth & CAPTCHA handling (noVNC)    │
│  8. Infisical Machine Identity → Auto-sync Copilot tokens  │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker & Docker Compose
- **Infisical Machine Identity** (for auto-updating Copilot tokens)
- **Infisical OpenCode Project** (with GitHub Copilot `ghu_` refresh token)
- Postal email server access (optional - dashboard is primary approval method)
- LinkedIn account

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/mattbaylor/linkedin-reposter.git
cd linkedin-reposter
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your Infisical credentials
nano .env
```

Required environment variables in `.env`:
```bash
INFISICAL_URL=https://infisical.example.com
INFISICAL_TOKEN=st.xxxx.yyyy.zzzz  # Your Service Token from Infisical
INFISICAL_PROJECT_ID=LinkedInReposter
INFISICAL_ENVIRONMENT=dev

# Machine Identity for Copilot token sync (get from Infisical)
OPENCODE_INFISICAL_PROJECT_ID=your-opencode-project-id
INFISICAL_MACHINE_IDENTITY_CLIENT_ID=your-machine-identity-client-id
INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET=your-machine-identity-client-secret

# VNC Password (REQUIRED for security - no default provided)
VNC_PASSWORD=your-strong-vnc-password-here
```

**How to get your Infisical Service Token:**
1. Go to https://infisical.example.com/
2. Navigate to: `LinkedInReposter` → `Settings` → `Service Tokens`
3. Click "Create Service Token"
4. Copy the generated token (format: `st.xxxx.yyyy.zzzz`)
5. Paste it into your `.env` file as `INFISICAL_TOKEN`

**Machine Identity Setup:**
The Machine Identity (`linkedin-reposter-copilot`) is pre-configured with cross-project access to:
- `LinkedInReposter` project (main secrets)
- `OpenCode` project (GitHub Copilot tokens - auto-syncing)

### 3. Configure Secrets in Infisical

Log into Infisical (https://infisical.example.com/) and add these secrets to the `LinkedInReposter` project:

**Required Secrets:**
- `LINKEDIN_EMAIL` - Your LinkedIn login email
- `LINKEDIN_PASSWORD` - Your LinkedIn password
- `LINKEDIN_HANDLES` - Comma-separated LinkedIn handles (e.g., "john-doe,jane-smith,company/acme-corp")
- `APP_BASE_URL` - Public URL for admin dashboard (https://liposter.example.com)
- `TIMEZONE` - Timezone for scheduling (America/Denver)

**Optional Secrets:**
- `POSTAL_API_KEY` - Postal server API key (if using email approvals)
- `POSTAL_SERVER_URL` - Postal server URL (https://dlvr.rehosted.us)
- `APPROVAL_EMAIL` - Email to receive approval requests (if using email)
- `AI_MODEL` - Override default AI model (default: gpt-4o)

**GitHub Copilot Tokens** (stored in separate OpenCode project):
These are automatically synced via Machine Identity - no manual configuration needed!
- `GITHUB_COPILOT_TOKEN` - Auto-updated from OpenCode project

### 4. Build and Run

```bash
# Build the Docker image
docker compose build

# Start the service
docker compose up -d

# View logs
docker compose logs -f app
```

### 5. Verify Health & Access Dashboard

```bash
# Check health endpoint
curl http://localhost:8080/health

# Or visit in browser
open http://localhost:8080

# Access admin dashboard
open http://localhost:8080/admin
```

**Admin Dashboard Features:**
- View all scraped posts and their variants
- Filter by status (All, Pending, Approved, Rejected, Published)
- Approve posts with one click
- Regenerate variants using AI
- Monitor publishing schedule
- **Delete scheduled posts** with one click
- **Priority-based scheduling** - Posts automatically ordered by priority (URGENT, GOOD, OK, STALE)
- **Automatic conflict resolution** - Schedule auto-scrubs after approvals to fix spacing/priority issues
- **Manual schedule regeneration** - Trigger full schedule rebuild via admin button

**VNC Access** (for LinkedIn manual auth):
- URL: `http://localhost:6080/vnc.html`
- Use this to solve CAPTCHAs or handle 2FA during LinkedIn login

## Development

### Project Structure

```
linkedin-reposter/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application & admin routes
│   ├── config.py            # Infisical + Machine Identity integration
│   ├── database.py          # SQLAlchemy models
│   ├── models.py            # Pydantic schemas
│   ├── linkedin_selenium.py # Selenium automation (replaces Playwright)
│   ├── ai_copilot.py        # GitHub Copilot GPT-4o (primary)
│   ├── ai.py                # Fallback logic (Copilot → GitHub Models)
│   ├── email_service.py     # Postal API (optional)
│   ├── admin_dashboard.py   # Jinja2 templates for admin UI
│   └── scheduler.py         # APScheduler jobs
├── data/                    # Persistent storage (gitignored)
│   ├── linkedin.db          # SQLite database
│   ├── browser_data/        # Selenium persistent sessions
│   └── vnc/                 # VNC display settings
├── Dockerfile               # Multi-stage build with Selenium + VNC
├── docker-compose.yml       # Service orchestration
├── requirements.txt
├── .github/workflows/       # Multi-arch builds → GHCR
└── README.md
```

### Local Development

```bash
# Install dependencies locally (optional, for IDE support)
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Run without Docker (requires .env setup)
python -m uvicorn app.main:app --reload --port 8080
```

## API Endpoints

### Public Endpoints
- `GET /` - Service information
- `GET /health` - Health check and status

### Admin Dashboard
- `GET /admin` or `GET /admin/dashboard` - Main admin UI
- `POST /admin/approve/{post_id}/{variant_number}` - Approve a variant
- `POST /admin/reject/{post_id}` - Reject all variants
- `POST /admin/regenerate/{post_id}` - Regenerate variants with AI
- `DELETE /admin/scheduled/{scheduled_post_id}` - Delete a scheduled post
- `POST /admin/scrub-schedule` - Manually trigger schedule conflict resolution
- `POST /admin/trigger-scrape` - Manually trigger LinkedIn scraping

### Email Approval (Legacy - Dashboard Preferred)
- `GET /approve?id=<post_id>&variant=<1-3>&token=<token>` - Approve a post
- `GET /reject?id=<post_id>&token=<token>` - Reject a post

## Deployment

### Local (Mac)

1. Build and run with Docker Compose (see Quick Start)
2. Configure Caddy to proxy `https://liposter.example.com` → `192.168.1.8:8080`

### TrueNAS Scale

1. Pull image from GitHub Container Registry:
   ```bash
   docker pull ghcr.io/mattbaylor/linkedin-reposter:latest
   ```

2. Create application with:
   - Persistent storage: `/app/data`
   - Environment variables: All Infisical credentials + Machine Identity
   - Port mapping: `8080:8080` (admin), `6080:6080` (VNC)
   - Restart policy: `unless-stopped`

3. Configure Caddy reverse proxy + Authelia authentication:
   - See `CADDY_AUTHELIA.md` for setup guide
   - Protect `/admin` routes with Authelia
   - Public routes: `/`, `/health` (for monitoring)

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `INFISICAL_URL` | Infisical server URL | https://infisical.example.com | ✅ |
| `INFISICAL_TOKEN` | Infisical Service Token (st.xxx.yyy.zzz) | - | ✅ |
| `INFISICAL_PROJECT_ID` | Infisical project ID | LinkedInReposter | ✅ |
| `INFISICAL_ENVIRONMENT` | Environment (dev/staging/prod) | dev | ✅ |
| `OPENCODE_INFISICAL_PROJECT_ID` | OpenCode project for Copilot tokens | - | ✅ |
| `INFISICAL_MACHINE_IDENTITY_CLIENT_ID` | Machine Identity client ID | - | ✅ |
| `INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET` | Machine Identity secret | - | ✅ |
| `APP_PORT` | Application port | 8080 | ❌ |
| `AI_MODEL` | AI model to use | gpt-4o | ❌ |

### Secrets (stored in Infisical)

All application secrets are stored securely in Infisical and fetched at runtime. See section 3 above for required secrets.

## AI Integration

### GitHub Copilot (Primary)
- **Model**: GPT-4o via GitHub Copilot API
- **Rate Limits**: Unlimited (no throttling)
- **Token Management**: Auto-syncing via Machine Identity from OpenCode project
- **Implementation**: `app/ai_copilot.py`

### GitHub Models (Fallback)
- **Model**: GPT-4o via GitHub Models API
- **Rate Limits**: Severe (429 errors after 2-3 requests)
- **Usage**: Only when Copilot is unavailable
- **Implementation**: `app/ai.py`

### How It Works
1. System attempts to use GitHub Copilot first
2. If Copilot fails/unavailable, falls back to GitHub Models
3. Generates 3 unique variants per original post
4. Each variant maintains author attribution and core message
5. Variants optimized for LinkedIn engagement

See `GITHUB_COPILOT_SETUP.md` for detailed integration documentation.

## Smart Scheduling System

The LinkedIn Reposter includes an intelligent scheduling system that automatically manages your posting queue:

### Priority Levels
Posts are categorized into 4 priority levels based on their age:
- **URGENT** (0-2 days old) - Jumps to front of queue, can bump lower-priority posts
- **GOOD** (2-4 days old) - High priority scheduling
- **OK** (4-6 days old) - Normal priority
- **STALE** (6+ days old) - Lowest priority, easily bumped by URGENT posts

### Scheduling Rules
- **Posting Hours**: 6:00 AM - 9:00 PM MST/MDT
- **Posting Days**: Weekdays only (Monday-Friday)
- **Spacing**: Minimum 90 minutes between posts
- **Daily Limit**: Maximum 3 posts per day

### URGENT Post Bumping
When an URGENT post is approved:
1. System finds the earliest available slot
2. If blocked by STALE/OK posts, bumps them to next day
3. Can exceed daily limit by moving STALE posts
4. Cascades bumps if conflicts occur
5. Maintains 90-minute spacing throughout

### Automatic Conflict Resolution
After every variant approval, the system automatically:
1. Removes duplicate scheduled posts (same post_id)
2. Reorders posts by priority (URGENT → GOOD → OK → STALE)
3. Fixes spacing violations (< 90 min between posts)
4. Ensures all posts respect posting hours and weekends
5. Cascades changes to maintain schedule integrity

**Manual Controls:**
- Delete scheduled posts via dashboard 🗑️ button
- Trigger manual scrub via "Scrub Schedule" button in admin dashboard
- Schedule regenerates automatically after each approval

## Human-like Scraping

To avoid LinkedIn bot detection and rate limiting, the scraper implements several humanization techniques:

### Profile Scraping Delays
- **Between profiles**: Random 1-3 minute delays
- **Page scrolling**: Random 0.8-2.0 second delays
- **Typing**: Random 40-70 WPM with occasional hesitations
- **Navigation**: Random 2-4 second delays after page loads

### Scraping Schedule
- **Morning scrape**: 5:30 AM MST/MDT
- **Afternoon scrape**: 1:00 PM MST/MDT
- Browser session persists to avoid frequent logins
- Automatic CAPTCHA alerts via email (requires VNC intervention)

## VNC Remote Access

The container includes a web-based VNC server for manual intervention:

- **URL**: `http://localhost:6080/vnc.html`
- **Use Cases**:
  - LinkedIn CAPTCHA solving
  - 2FA authentication
  - Manual browser session debugging
  - Verification of scraping/posting actions

**Security Note**: In production, protect VNC port (6080) with firewall rules or only expose via Twingate.

## Monitoring & Logs

```bash
# View live logs
docker compose logs -f app

# Check container status
docker compose ps

# Restart service
docker compose restart app
```

## Troubleshooting

### Infisical Connection Failed

- Verify `INFISICAL_TOKEN` is correct and in format `st.xxx.yyy.zzz`
- Check that the Infisical URL is correct: `https://infisical.example.com`
- Ensure the project ID matches: `LinkedInReposter`
- Verify the environment exists (dev/staging/prod) in your Infisical project
- Service Token must have access to the specified project and environment

### Machine Identity Issues

- Verify `INFISICAL_MACHINE_IDENTITY_CLIENT_ID` and `CLIENT_SECRET` are correct
- Check that Machine Identity has access to both projects:
  - `LinkedInReposter` (main project)
  - `OpenCode` (for Copilot tokens)
- Copilot token should auto-sync - if missing, check OpenCode project secrets

### LinkedIn Authentication Issues

- Verify credentials in Infisical are correct
- Use VNC at `http://localhost:6080/vnc.html` to:
  - Solve CAPTCHAs manually
  - Handle 2FA prompts
  - Verify browser session state
- Check Selenium browser data persists in `/app/data/browser_data/`

### AI Generation Failures

- Primary: GitHub Copilot (should work unlimited)
- Fallback: GitHub Models (may hit rate limits)
- Check logs for which AI provider is being used
- Verify Copilot token is syncing from OpenCode project

### Admin Dashboard Not Loading

- Verify container is running: `docker compose ps`
- Check port 8080 is accessible
- Review logs: `docker compose logs -f app`
- Clear browser cache if templates don't update

### Email Not Sending

- Email approval is optional - use admin dashboard instead
- Verify Postal API key and server URL in Infisical
- Check Postal server is accessible from container
- Review application logs for error details

## License

MIT

## Contributing

Contributions welcome! Please open an issue or PR.

## Roadmap

- [x] Phase 1: Foundation & Infisical integration
- [x] Phase 2: Database & FastAPI core
- [x] Phase 3: Email service (Postal) - optional
- [x] Phase 4: AI service (GitHub Copilot + fallback)
- [x] Phase 5: LinkedIn automation (Selenium + VNC)
- [x] Phase 6: Scheduler (11am/4pm MST)
- [x] Phase 7: GitHub Actions multi-arch builds
- [x] Phase 8: Admin Dashboard with web UI
- [x] Phase 9: Machine Identity for auto-updating tokens
- [x] Phase 10: Smart scheduling with priority-based queue
- [x] Phase 11: Human-like scraping delays (1-3 min between profiles)
- [x] Phase 12: Schedule management (delete, auto-scrub, manual regeneration)
- [ ] Phase 13: Production deployment
- [ ] Phase 14: Analytics and performance monitoring

## Support

For issues and questions, please open a GitHub issue.
