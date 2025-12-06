# Deployment Guide

## Docker Image

The LinkedIn Reposter is automatically built and published to GitHub Container Registry (GHCR) on every push to the `main` branch.

**Image URL**: `ghcr.io/mattbaylor/linkedin-reposter:latest`

## Development Deployment (Local Mac)

### 1. Clone Repository

```bash
git clone https://github.com/mattbaylor/linkedin-reposter.git
cd linkedin-reposter
```

### 2. Set Environment Variables

```bash
export INFISICAL_TOKEN="your-dev-token"
export INFISICAL_PROJECT_ID="4627ccea-f94c-4f19-9605-6892dfd37ee0"
export INFISICAL_ENVIRONMENT="dev"
```

### 3. Run with Docker Compose

```bash
# Pull latest image and start
docker compose pull
docker compose up -d

# Check logs
docker compose logs -f

# Access services
# - API: http://localhost:8080
# - VNC: http://localhost:8080/admin/vnc
# - Health: http://localhost:8080/health
```

### 4. Local Development (Build from Source)

If you want to build locally instead of pulling from GHCR:

```bash
# Edit docker-compose.yml and uncomment the build section
# Then run:
docker compose up -d --build
```

## Production Deployment (TrueNAS)

### 1. Prerequisites

- TrueNAS with Docker/Kubernetes support
- Caddy reverse proxy configured
- Infisical production token
- Twingate configured to allow ports 8080, 5900, 6080

### 2. Create Deployment Directory

```bash
ssh your-truenas-server
mkdir -p /mnt/pool/apps/linkedin-reposter
cd /mnt/pool/apps/linkedin-reposter
```

### 3. Download Production Compose File

```bash
curl -O https://raw.githubusercontent.com/mattbaylor/linkedin-reposter/main/docker-compose.production.yml
mv docker-compose.production.yml docker-compose.yml
```

### 4. Create Data Directory

```bash
mkdir -p data
chmod 755 data
```

### 5. Set Environment Variables

Create a `.env` file:

```bash
cat > .env << 'EOF'
INFISICAL_URL=https://infisical.example.com
INFISICAL_TOKEN=your-production-infisical-token
INFISICAL_PROJECT_ID=4627ccea-f94c-4f19-9605-6892dfd37ee0
INFISICAL_ENVIRONMENT=prod
APP_PORT=8080
AI_MODEL=gpt-4o
DISPLAY=:99
EOF

chmod 600 .env
```

### 6. Configure Caddy Reverse Proxy

Add to your Caddyfile:

```caddy
liposter.example.com {
    # WebSocket proxy for noVNC
    handle /websockify* {
        uri strip_prefix /websockify
        reverse_proxy localhost:6080
    }
    
    # Main application proxy
    reverse_proxy http://localhost:8080 {
        header_up Host {http.request.host}
        header_up X-Real-IP {remote_host}
    }
    
    encode gzip
}
```

Reload Caddy:

```bash
caddy reload --config /path/to/Caddyfile
```

### 7. Start the Service

```bash
docker compose pull
docker compose up -d
```

### 8. Verify Deployment

```bash
# Check container status
docker compose ps

# Check logs
docker compose logs -f

# Check health endpoint
curl http://localhost:8080/health

# Check external access
curl https://liposter.example.com/health
```

### 9. Access Web VNC

If LinkedIn shows a security challenge:
- You'll receive an email alert
- Click the link: `https://liposter.example.com/admin/vnc`
- Complete the challenge in the browser
- The scraper will automatically continue

## Updating to Latest Version

### Development (Mac)

```bash
cd /Users/matt/repo/linkedin-reposter
docker compose pull
docker compose up -d
```

### Production (TrueNAS)

```bash
cd /mnt/pool/apps/linkedin-reposter
docker compose pull
docker compose up -d
```

The container will automatically restart with the new image.

## GitHub Actions CI/CD

Every push to `main` triggers:

1. **Build**: Multi-stage Docker build
2. **Tag**: Tags image with:
   - `latest` (for main branch)
   - `main-{git-sha}` (commit-specific)
   - `v1.2.3` (for tagged releases)
3. **Push**: Publishes to `ghcr.io/mattbaylor/linkedin-reposter`
4. **Cache**: Uses GitHub Actions cache for faster builds

### Manual Trigger

You can manually trigger a build from GitHub:
1. Go to: https://github.com/mattbaylor/linkedin-reposter/actions
2. Select "Build and Push Docker Image"
3. Click "Run workflow"

## Secrets Management

All sensitive data is stored in Infisical:

**Development Environment** (`dev`):
- Used for local Mac testing
- Separate from production data

**Production Environment** (`prod`):
- Used on TrueNAS server
- Real LinkedIn credentials
- Real email recipients

Secrets stored in Infisical:
- `LINKEDIN_EMAIL`
- `LINKEDIN_PASSWORD`
- `LINKEDIN_HANDLES`
- `APPROVAL_EMAIL`
- `POSTAL_SERVER_URL`
- `POSTAL_API_KEY`
- `GITHUB_TOKEN` (for AI models)
- `APP_BASE_URL`
- `TIMEZONE`

## Monitoring

### Health Check

```bash
curl https://liposter.example.com/health
```

Returns:
```json
{
  "status": "healthy",
  "timestamp": "2025-12-06T00:00:00Z"
}
```

### Stats Endpoint

```bash
curl https://liposter.example.com/stats
```

Returns post counts, approval rates, etc.

### Logs

```bash
# Real-time logs
docker compose logs -f

# Last 100 lines
docker compose logs --tail 100

# Specific service
docker compose logs app
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs

# Verify environment variables
docker compose config

# Check Infisical connection
docker compose exec app env | grep INFISICAL
```

### LinkedIn Security Challenge

1. Check email for alert
2. Open VNC: `https://liposter.example.com/admin/vnc`
3. Complete challenge manually
4. Scraper continues automatically

### VNC Not Connecting

```bash
# Check if websockify is running
docker compose exec app cat /tmp/websockify.log

# Verify ports are exposed
docker compose ps

# Test locally
curl http://localhost:6080
```

### Database Issues

```bash
# Backup database
cp data/linkedin_reposter.db data/linkedin_reposter.db.backup

# Reset database (WARNING: deletes all data)
rm data/linkedin_reposter.db
docker compose restart
```

## Backup & Restore

### Backup

```bash
# Backup data directory
tar -czf linkedin-reposter-backup-$(date +%Y%m%d).tar.gz data/

# Backup to remote location
rsync -av data/ user@backup-server:/backups/linkedin-reposter/
```

### Restore

```bash
# Stop container
docker compose down

# Restore data
tar -xzf linkedin-reposter-backup-20251206.tar.gz

# Start container
docker compose up -d
```

## Maintenance

### Update Secrets in Infisical

1. Go to Infisical dashboard
2. Select LinkedIn Reposter project
3. Choose environment (dev/prod)
4. Update secrets
5. Restart container: `docker compose restart`

### Clear Old Posts

```bash
# Connect to database
docker compose exec app sqlite3 /app/data/linkedin_reposter.db

# Delete posts older than 90 days
DELETE FROM linkedin_posts WHERE created_at < datetime('now', '-90 days');
DELETE FROM post_variants WHERE post_id NOT IN (SELECT id FROM linkedin_posts);
.quit
```

### Rotate LinkedIn Session

If LinkedIn session expires (after ~30 days):
1. Security challenge will be triggered automatically
2. You'll receive email alert
3. Complete challenge via web VNC
4. New session will be saved automatically

## Support

For issues or questions:
- GitHub Issues: https://github.com/mattbaylor/linkedin-reposter/issues
- Documentation: See `README.md`, `VNC_SETUP.md`, `DEVELOPMENT.md`
