# LinkedIn Reposter

Automated LinkedIn post monitoring and reposting service with AI-powered content generation and email approval workflow.

## Features

- 🔍 Monitor LinkedIn profiles and company pages for new posts
- 🤖 AI-powered post rephrasing using GitHub Models (GPT-4o)
- 📧 Email approval workflow via Postal
- 🔐 Secure secret management with Infisical
- ⏰ Scheduled monitoring (11am & 4pm MST/MDT)
- 🐳 Fully containerized with Docker
- 🏗️ Multi-architecture support (arm64 + amd64)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   LinkedIn Monitor Service                   │
│                      (Docker Container)                      │
├─────────────────────────────────────────────────────────────┤
│  1. Post Monitor → Track LinkedIn handles                   │
│  2. AI Engine → Generate 3 repost variants (GPT-4o)        │
│  3. Email Approval → Send via Postal, await confirmation   │
│  4. LinkedIn Poster → Publish approved posts                │
│  5. SQLite Database → Track posts, approvals, history       │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker & Docker Compose
- Infisical account with configured project
- Postal email server access
- GitHub Copilot subscription (for AI models)
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

# Edit .env with your Infisical Service Token
nano .env
```

Required environment variables in `.env`:
```bash
INFISICAL_URL=https://infisical.example.com
INFISICAL_TOKEN=st.xxxx.yyyy.zzzz  # Your Service Token from Infisical
INFISICAL_PROJECT_ID=LinkedInReposter
INFISICAL_ENVIRONMENT=dev
```

**How to get your Infisical Service Token:**
1. Go to https://infisical.example.com/
2. Navigate to: `LinkedInReposter` → `Settings` → `Service Tokens`
3. Click "Create Service Token"
4. Copy the generated token (format: `st.xxxx.yyyy.zzzz`)
5. Paste it into your `.env` file as `INFISICAL_TOKEN`

### 3. Configure Secrets in Infisical

Log into Infisical (https://infisical.example.com/) and add these secrets to the `LinkedInReposter` project:

**Required Secrets:**
- `LINKEDIN_EMAIL` - Your LinkedIn login email
- `LINKEDIN_PASSWORD` - Your LinkedIn password
- `GITHUB_TOKEN` - GitHub PAT with Copilot access
- `POSTAL_API_KEY` - Postal server API key
- `POSTAL_SERVER_URL` - Postal server URL (https://dlvr.rehosted.us)
- `APPROVAL_EMAIL` - Email to receive approval requests
- `LINKEDIN_HANDLES` - Comma-separated LinkedIn handles (e.g., "john-doe,jane-smith,acme-corp")
- `APP_BASE_URL` - Public URL for approval links (https://liposter.example.com)
- `TIMEZONE` - Timezone for scheduling (America/Denver)

**Optional Secrets:**
- `AI_MODEL` - Override default AI model (default: gpt-4o)

### 4. Build and Run

```bash
# Build the Docker image
docker compose build

# Start the service
docker compose up -d

# View logs
docker compose logs -f app
```

### 5. Verify Health

```bash
# Check health endpoint
curl http://localhost:8080/health

# Or visit in browser
open http://localhost:8080
```

## Development

### Project Structure

```
linkedin-reposter/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Infisical integration
│   ├── database.py          # SQLAlchemy models
│   ├── models.py            # Pydantic schemas
│   ├── linkedin.py          # Playwright automation
│   ├── ai_service.py        # GitHub Models API
│   ├── email_service.py     # Postal API
│   └── scheduler.py         # APScheduler jobs
├── data/                    # Persistent storage (gitignored)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
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

- `GET /` - Service information
- `GET /health` - Health check and status
- `GET /approve?id=<post_id>&variant=<1-3>&token=<token>` - Approve a post
- `GET /reject?id=<post_id>&token=<token>` - Reject a post

## Deployment

### Local (Mac)

1. Build and run with Docker Compose (see Quick Start)
2. Configure Caddy to proxy `https://liposter.example.com` → `192.0.2.10:8080`

### TrueNAS Scale

1. Pull image from GitHub Container Registry:
   ```bash
   docker pull ghcr.io/mattbaylor/linkedin-reposter:latest
   ```

2. Create application with:
   - Persistent storage: `/app/data`
   - Environment variables: Infisical credentials
   - Port mapping: `8080:8080`
   - Restart policy: `unless-stopped`

3. Configure Caddy reverse proxy through Twingate

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `INFISICAL_URL` | Infisical server URL | https://infisical.example.com | ✅ |
| `INFISICAL_TOKEN` | Infisical Service Token (st.xxx.yyy.zzz) | - | ✅ |
| `INFISICAL_PROJECT_ID` | Infisical project ID | LinkedInReposter | ✅ |
| `INFISICAL_ENVIRONMENT` | Environment (dev/staging/prod) | dev | ✅ |
| `APP_PORT` | Application port | 8080 | ❌ |
| `AI_MODEL` | AI model to use | gpt-4o | ❌ |

### Secrets (stored in Infisical)

All application secrets are stored securely in Infisical and fetched at runtime. See section 3 above for required secrets.

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

### LinkedIn Authentication Issues

- Verify credentials in Infisical are correct
- Check Playwright browser logs in `/app/data/playwright/`
- LinkedIn may require 2FA - session-based auth coming soon

### Email Not Sending

- Verify Postal API key and server URL in Infisical
- Check Postal server is accessible from container
- Review application logs for error details

## License

MIT

## Contributing

Contributions welcome! Please open an issue or PR.

## Roadmap

- [x] Phase 1: Foundation & Infisical integration
- [ ] Phase 2: Database & FastAPI core
- [ ] Phase 3: Email service (Postal)
- [ ] Phase 4: AI service (GitHub Models)
- [ ] Phase 5: LinkedIn automation (Playwright)
- [ ] Phase 6: Scheduler (11am/4pm MST)
- [ ] Phase 7: GitHub Actions multi-arch builds
- [ ] Phase 8: Production deployment (TrueNAS)

## Support

For issues and questions, please open a GitHub issue.
