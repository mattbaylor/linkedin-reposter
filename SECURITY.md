# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in LinkedIn Reposter, please send an email to **matt@example.com** with:

- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Any suggested fixes (optional)

### What to Expect

- **Response Time**: Within 48 hours
- **Updates**: You'll receive updates on the status
- **Credit**: You'll be credited for the discovery (if desired)
- **Fix Timeline**: Critical issues will be addressed ASAP

## Security Best Practices

### Environment Variables

**Never commit sensitive data to the repository:**
- ✅ Use Infisical or environment variables for secrets
- ✅ Use `.env.example` with placeholder values
- ❌ Never commit `.env` files
- ❌ Never hardcode passwords, tokens, or API keys

### Infisical Integration

This project uses Infisical for secure secret management:
- All secrets stored in Infisical, not in code
- Service Tokens rotated regularly
- Machine Identity for cross-project access
- Secrets fetched at runtime, never persisted in logs

### LinkedIn Credentials

**Protect your LinkedIn account:**
- Use strong, unique passwords
- Enable two-factor authentication (2FA)
- Use VNC for manual authentication (not automated)
- Monitor for suspicious activity

### Container Security

**Best practices for deployment:**
- Run containers with minimal privileges
- Use Docker secrets for sensitive data
- Keep base images updated
- Protect VNC port (6080) with firewall rules
- Use reverse proxy with authentication (Authelia)

### API Security

**Protect your endpoints:**
- Admin dashboard should be behind authentication
- Use Authelia or similar for access control
- Don't expose database directly
- Rotate API keys regularly

### Network Security

**Recommended setup:**
- Use Twingate or VPN for VNC access
- Firewall rules for port 6080
- HTTPS only (via Caddy reverse proxy)
- Rate limiting on public endpoints

## Known Security Considerations

### Browser Automation
- Selenium sessions may be detected by LinkedIn
- Use human-like delays (already implemented)
- Session persistence minimizes login frequency
- Manual intervention required for CAPTCHAs

### Data Storage
- SQLite database contains post content
- No LinkedIn passwords stored in database
- All credentials in Infisical only
- Local data in `/app/data` (Docker volume)

### Third-Party Services
- **Infisical**: Secret management
- **GitHub Copilot**: AI generation (API only)
- **Postal**: Email delivery (optional)
- All use encrypted connections (HTTPS)

## Security Updates

Security patches will be released as soon as possible after discovery. Update regularly:

```bash
# Pull latest image
docker pull ghcr.io/mattbaylor/linkedin-reposter:latest

# Restart with new image
docker compose pull
docker compose up -d
```

## Disclosure Policy

- We will acknowledge your report within 48 hours
- We aim to release fixes within 7 days for critical issues
- Public disclosure should wait until a fix is released
- We'll credit you in release notes (if you wish)

## Security Checklist

Before deploying to production:

- [ ] `.env` file is not committed to git
- [ ] All secrets stored in Infisical
- [ ] VNC port protected by firewall/VPN
- [ ] Admin dashboard behind authentication
- [ ] Using HTTPS with valid certificate
- [ ] Regular backups of database
- [ ] Monitoring and alerting configured
- [ ] Docker images kept up to date
- [ ] Two-factor authentication enabled on LinkedIn

## Questions?

For security-related questions that aren't vulnerabilities, open a GitHub issue with the "security" label.

---

Thank you for helping keep LinkedIn Reposter secure! 🔒
