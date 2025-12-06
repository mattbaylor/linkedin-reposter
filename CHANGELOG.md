# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2025-12-05

### Added
- Smart scheduling system with priority-based queue (URGENT > GOOD > OK > STALE)
- URGENT post bumping to jump queue ahead of lower-priority posts
- Automatic schedule conflict resolution after each approval
- Manual schedule management (delete posts, scrub conflicts, regenerate)
- Human-like scraping delays (1-3 min random between profiles)
- Schedule scraping times updated to 5:30 AM and 1:00 PM MST
- Admin dashboard delete button (🗑️) for scheduled posts
- Admin dashboard "Scrub Schedule" button for manual conflict resolution
- Priority display in schedule table
- Session persistence with cookie management for LinkedIn
- Stale lock file cleanup for Chrome stability
- Timezone support in Docker container
- MIT License
- Comprehensive documentation (CONTRIBUTING.md, SECURITY.md, CHANGELOG.md)

### Changed
- Scheduler completely rewritten with URGENT bumping logic
- Scraping loop now uses enumeration for proper profile delay tracking
- Scrape schedule changed from 11:00 AM & 4:00 PM to 5:30 AM & 1:00 PM MST
- LinkedIn login flow improved with better re-authentication detection
- README updated with smart scheduling and human-like scraping sections

### Fixed
- URGENT priority posts now actually jump to front of queue
- Schedule conflicts (duplicates, spacing violations) auto-fixed after approvals
- Profile scraping delays now work regardless of scrape success/failure
- Chrome browser lock files cleaned up before starting

### Security
- Removed `.env.bak` from git history completely
- Redacted Infisical service token from all git history
- Removed LinkedIn password characters from logs/docs
- Added comprehensive SECURITY.md with best practices
- Repository made public after thorough security audit

## [0.9.0] - 2025-11-30

### Added
- GitHub Copilot GPT-4o integration (unlimited, primary AI)
- Infisical Machine Identity for auto-syncing Copilot tokens
- Cross-project secret access (LinkedInReposter + OpenCode projects)
- Bulk variant regeneration endpoint
- Manual scrape trigger in admin dashboard

### Changed
- AI service now uses Copilot as primary with GitHub Models fallback
- Token management fully automated via Machine Identity

### Fixed
- Chrome temp directory permissions for Selenium
- Machine Identity authentication flow

## [0.8.0] - 2025-11-25

### Added
- Admin Dashboard web UI for post management
- Approve posts with one click
- Regenerate variants via web interface
- Filter posts by status (All, Pending, Approved, Rejected, Published)
- View publishing schedule in dashboard
- Email approval workflow (optional, dashboard preferred)

### Changed
- Admin dashboard is now primary approval method
- Email approvals retained for backward compatibility

## [0.7.0] - 2025-11-20

### Added
- Selenium-based LinkedIn automation (replaces Playwright)
- Web-based VNC access for manual authentication
- noVNC integration for browser-based VNC client
- Session persistence in `/app/data/browser_data`
- Chrome headless automation with stealth techniques

### Changed
- Switched from Playwright to Selenium for better stability
- Added VNC server for CAPTCHA/2FA handling

### Fixed
- LinkedIn authentication now supports manual intervention
- CAPTCHA handling via VNC

## [0.6.0] - 2025-11-15

### Added
- Scheduled monitoring (11am & 4pm MST/MDT)
- APScheduler for background jobs
- Automatic post scraping on schedule
- Health monitoring with last successful scrape tracking

### Changed
- Timezone set to America/Denver (MST/MDT)
- Scraping runs automatically, no manual trigger needed

## [0.5.0] - 2025-11-10

### Added
- AI-powered post generation using GitHub Models
- Generate 3 unique variants per original post
- Fallback AI providers (Claude, OpenAI)
- Author attribution in generated posts
- LinkedIn engagement optimization

### Changed
- AI prompts optimized for LinkedIn format
- Variant quality improved with better instructions

## [0.4.0] - 2025-11-05

### Added
- Email approval workflow via Postal
- Approval tokens for secure email links
- Email templates with post preview
- Approval expiration (7 days)
- Rejection workflow

### Changed
- Postal integration for reliable email delivery
- HTML email templates with styling

## [0.3.0] - 2025-11-01

### Added
- SQLite database for post tracking
- Post variants storage
- Approval requests table
- Scheduled posts table
- Database migrations

### Changed
- All data now persisted in database
- State tracked across restarts

## [0.2.0] - 2025-10-25

### Added
- FastAPI application framework
- Health check endpoint
- API documentation (Swagger/OpenAPI)
- Request/response models (Pydantic)
- Error handling and logging

### Changed
- RESTful API structure
- JSON responses for all endpoints

## [0.1.0] - 2025-10-20

### Added
- Infisical integration for secret management
- Service Token authentication
- Environment-based configuration
- Docker containerization
- Multi-architecture builds (arm64 + amd64)
- GitHub Actions CI/CD pipeline
- GitHub Container Registry publishing

### Security
- All secrets stored in Infisical
- No hardcoded credentials
- Environment variable validation

---

## Release Notes Format

Each version includes:
- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security improvements

## Versioning

- **Major** (X.0.0): Breaking changes
- **Minor** (0.X.0): New features, backward compatible
- **Patch** (0.0.X): Bug fixes, backward compatible

[Unreleased]: https://github.com/mattbaylor/linkedin-reposter/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/mattbaylor/linkedin-reposter/releases/tag/v1.0.0
