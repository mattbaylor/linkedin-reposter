# LinkedIn Reposter - Development Documentation

> **Purpose**: This document tracks development progress, decisions, and session state for easy recovery after crashes or between sessions.

---

## Project Overview

**Repository**: `mattbaylor/linkedin-reposter`  
**Local Path**: `/Users/matt/repo/linkedin-reposter/`  
**Purpose**: Automated LinkedIn post monitoring and reposting with AI-powered content generation and email approval workflow.

---

## Current Status: Phase 1 - Foundation ✅

### Completed Tasks

#### 1. Project Structure Created ✅
- Git repository initialized with `main` branch
- Directory structure: `app/`, `data/`, `.github/workflows/`
- All core configuration files in place

#### 2. Configuration Files ✅
- **Dockerfile**: Multi-stage build with Playwright support (arm64 + amd64 compatible)
- **docker-compose.yml**: No version field (using modern Compose spec)
- **requirements.txt**: All Python dependencies defined
- **.gitignore** & **.dockerignore**: Properly configured
- **.env.example**: Template with correct Service Token auth format
- **.env**: Created locally (user needs to add actual token)

#### 3. Application Code ✅
- **app/config.py**: Infisical SDK integration using Service Token authentication
- **app/main.py**: FastAPI skeleton with health check and approval endpoints
- **app/__init__.py**: Package initialization

#### 4. Documentation ✅
- **README.md**: Complete setup and usage instructions
- **DEVELOPMENT.md**: This file - tracks progress and decisions

---

## Important Decisions & Discoveries

### Infisical Authentication Method
**Decision**: Use Service Token authentication (not Universal Auth)

**Reason**: 
- User has a Service Token from Infisical: `REDACTED_INFISICAL_TOKEN`
- Service Token auth does NOT require CLIENT_ID (that's only for Universal Auth)
- Self-hosted Infisical at: `https://infisical.example.com/`

**Implementation**:
```python
# Using infisical_sdk (not infisical_python)
from infisical_sdk import InfisicalSDKClient

client = InfisicalSDKClient(
    host="https://infisical.example.com",
    token="st.xxx.yyy.zzz"
)

secrets = client.secrets.list_secrets(
    project_id="LinkedInReposter",
    environment_slug="dev",
    secret_path="/"
)
```

**Environment Variables Required**:
```bash
INFISICAL_URL=https://infisical.example.com
INFISICAL_TOKEN=st.xxx.yyy.zzz
INFISICAL_PROJECT_ID=LinkedInReposter
INFISICAL_ENVIRONMENT=dev
```

---

## Configuration Details

### Network Configuration
- **Local IP**: 192.0.2.10 (M2 Mac)
- **Container Port**: 8080
- **Public URL**: https://liposter.example.com
- **Caddy Target**: 192.0.2.10:8080 (configured by user)

### Infisical Project Setup
- **Project Name**: LinkedInReposter
- **Environments**: dev, staging, prod (all configured)
- **Service Token**: Generated and ready to use

### Secrets in Infisical (all environments)
All these are already configured in Infisical by the user:
- `LINKEDIN_EMAIL`
- `LINKEDIN_PASSWORD`
- `GITHUB_TOKEN` (for GitHub Copilot/Models API)
- `POSTAL_API_KEY`
- `POSTAL_SERVER_URL` (https://dlvr.rehosted.us)
- `APPROVAL_EMAIL`
- `LINKEDIN_HANDLES` (comma-separated)
- `APP_BASE_URL` (https://liposter.example.com)
- `TIMEZONE` (America/Denver)
- `AI_MODEL` (optional override, default: gpt-4o)

### Postal Email Server
- **Server URL**: https://dlvr.rehosted.us (HTTPS on port 443, not SMTP port 587)
- **API Endpoint**: `/api/v1/send/message`
- **Authentication**: API key in headers
- **API Docs**: https://apiv1.postalserver.io/controllers/send.html

### GitHub Models API
- **Model**: gpt-4o (configurable via AI_MODEL env var)
- **Authentication**: GitHub Token (user has Copilot subscription with key sharing via Infisical)
- **Purpose**: Generate 3 post variants for approval

---

## Tech Stack

### Core
- **Language**: Python 3.11
- **Framework**: FastAPI 0.109.0
- **Server**: Uvicorn
- **Container**: Docker + docker-compose (no version field)

### Services
- **Browser Automation**: Playwright 1.41.0 (Chromium)
- **Database**: SQLite with SQLAlchemy 2.0.25 + aiosqlite
- **Scheduling**: APScheduler 3.10.4 (11am & 4pm MST/MDT)
- **Secrets**: Infisical SDK 1.5.0 (Service Token auth)
- **Email**: Postal API via httpx
- **AI**: OpenAI SDK 1.10.0 (GitHub Models compatible)

### Multi-Architecture Support
- **Development**: arm64 (M2 Mac with Docker Desktop)
- **Production**: amd64 (TrueNAS Intel at 192.0.2.20)
- **Build**: Multi-stage Dockerfile with Playwright dependencies
- **Note**: Avoiding AVX/AVX2 CPU instruction dependencies

---

## Next Steps - Phase 1 Testing

### Ready to Test
1. ✅ Project structure complete
2. ✅ All configuration files updated
3. ⏳ **User needs to**: Edit `.env` with actual Service Token
4. ⏳ Build Docker image
5. ⏳ Test Infisical connection
6. ⏳ Verify health endpoint

### Commands to Run (After .env is configured)
```bash
cd /Users/matt/repo/linkedin-reposter

# Build the image
docker compose build

# Start the service
docker compose up

# Expected output:
# 🔐 Connecting to Infisical...
# ✅ Connected to Infisical successfully
# ✅ Loaded X secrets from Infisical
# FastAPI running on http://0.0.0.0:8080

# In another terminal, test health:
curl http://192.0.2.10:8080/health
```

---

## Upcoming Phases (Not Started)

### Phase 2: Database & FastAPI Core
- Implement `database.py` with SQLAlchemy models
- Create `models.py` with Pydantic schemas  
- Finish approval/rejection webhook logic
- Add database persistence for posts and approvals

### Phase 3: Email Service (Postal)
- Implement `email_service.py` with Postal API
- Create HTML + plain text email templates
- Test sending approval emails with clickable links

### Phase 4: AI Service (GitHub Models)
- Implement `ai_service.py` using OpenAI SDK
- Create prompt templates for post rephrasing
- Generate 3 quality variants per post

### Phase 5: LinkedIn Automation (Playwright)
- Implement `linkedin.py` with Playwright browser automation
- Build login flow with session persistence
- Build post scraping for configured handles
- Build post publishing functionality

### Phase 6: Scheduler
- Implement `scheduler.py` with APScheduler
- Create main workflow orchestration
- Configure 11am/4pm MST cron triggers

### Phase 7: GitHub Actions
- Create `.github/workflows/docker-build.yml`
- Set up multi-arch builds (arm64 + amd64)
- Publish to GitHub Container Registry (ghcr.io)

### Phase 8: Production Deployment
- Deploy to TrueNAS Scale
- Configure Caddy reverse proxy
- End-to-end testing

---

## Known Issues & Blockers

### Current Blockers
1. **User must add Service Token to .env** - Waiting for user to edit file
2. **Infisical SDK package name** - Using `infisical-python==1.5.0` in requirements, but code imports `infisical_sdk` - need to verify correct package

### Resolved Issues
1. ✅ CLIENT_ID confusion - Discovered Service Token auth doesn't need CLIENT_ID
2. ✅ Postal URL port confusion - Clarified HTTPS (443) not SMTP (587)
3. ✅ Docker Compose version field - Removed deprecated version field

---

## Dependencies to Verify

### Python Package Note
**IMPORTANT**: Need to verify the correct Infisical Python package name:
- PyPI package might be: `infisical-python` or `infisical` or `infisical-sdk`
- Import statement uses: `from infisical_sdk import InfisicalSDKClient`
- requirements.txt currently has: `infisical-python==1.5.0`
- **TODO**: Test this during Phase 1 build, may need to update requirements.txt

---

## Session Recovery Checklist

If resuming after a crash or new session:

1. ✅ Project location: `/Users/matt/repo/linkedin-reposter/`
2. ✅ Git repository initialized
3. ✅ Configuration files all created
4. ✅ Using Service Token auth (not Universal Auth)
5. ⏳ Check if `.env` has actual Service Token filled in
6. ⏳ Check if Docker image has been built
7. ⏳ Check if Infisical connection tested
8. ⏳ Read this DEVELOPMENT.md to understand current state
9. ⏳ Check TODO list in code comments for next steps

---

## Quick Reference

### Important URLs
- Infisical: https://infisical.example.com/
- Public App URL: https://liposter.example.com
- Postal API Docs: https://apiv1.postalserver.io/controllers/send.html
- GitHub Repo: https://github.com/mattbaylor/linkedin-reposter

### Important Paths
- Project: `/Users/matt/repo/linkedin-reposter/`
- Data Volume: `./data` (mounted to `/app/data` in container)
- Playwright Sessions: `./data/playwright/`
- SQLite DB: `./data/linkedin-reposter.db` (will be created)

### Key Files
- Configuration: `app/config.py`
- Main Application: `app/main.py`
- Docker Build: `Dockerfile`
- Compose: `docker-compose.yml`
- Dependencies: `requirements.txt`
- Environment: `.env` (gitignored, needs manual setup)

---

**Last Updated**: December 5, 2025 - Phase 1 Foundation Complete  
**Next Action**: User needs to add Service Token to `.env`, then build and test
