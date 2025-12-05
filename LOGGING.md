# Logging Strategy - LinkedIn Reposter

## Overview

Comprehensive logging has been implemented across the application to help identify and debug errors when they occur.

## Logging Levels

### Production (INFO)
- Application lifecycle events (startup, shutdown)
- Configuration loading
- Database initialization
- API requests and responses
- Workflow steps (scraping, AI generation, approvals, posting)
- Email sending
- Successful operations

### Debug (DEBUG)
- SQL queries
- Detailed API payloads
- Token validation details
- Email template generation
- Internal state changes

### Error (ERROR)
- Configuration failures
- Database connection errors
- API call failures
- Email sending failures
- Validation errors
- Webhook processing errors

## Log Output

### Console (Colored)
- Color-coded by log level
- Emoji prefixes for quick scanning
- Human-readable format
- Suitable for Docker logs

### File (`/app/data/linkedin_reposter.log`)
- All log levels (DEBUG and above)
- Plain text format
- Persistent across container restarts
- Useful for debugging and auditing

## Logging Features

### 1. Request Logging Middleware
Every HTTP request is logged with:
- HTTP method and path
- Query parameters
- Client IP
- Response status code
- Request duration (in seconds)

Example:
```
🌐 GET /webhook/approve/abc123...
✅ GET /webhook/approve/abc123... → 200 (0.25s)
```

### 2. Operation Tracking
Common operations use helper functions:
- `log_operation_start()` - Log when operation begins
- `log_operation_success()` - Log successful completion with duration
- `log_operation_error()` - Log failures with full exception trace

Example:
```
▶️  Starting: send_approval_email post_id=5 author=johndoe
✅ Completed: send_approval_email (took 1.23s) message_id=xyz789
```

### 3. Workflow Steps
Post processing workflow is logged at each stage:
- `log_workflow_step()` - Track progress through the system

Example:
```
📋 Workflow [Post 5]: SCRAPING
📋 Workflow [Post 5]: GENERATING_VARIANTS
📋 Workflow [Post 5]: SENDING_APPROVAL
📋 Workflow [Post 5]: AWAITING_APPROVAL
📋 Workflow [Post 5]: APPROVED variant_id=12
📋 Workflow [Post 5]: POSTING
📋 Workflow [Post 5]: POSTED
```

### 4. Database Operations
All database operations can be traced (when DEBUG enabled):
- `log_database_operation()` - Track INSERT, UPDATE, DELETE, SELECT

Example:
```
🗄️  DB INSERT: linkedin_posts id=5 author=johndoe
🗄️  DB UPDATE: post_variants id=12 status=approved
```

### 5. External API Calls
All external API calls are logged:
- `log_api_call()` - Track HTTP method, URL, status code

Example:
```
🌐 API POST https://dlvr.rehosted.us/api/v1/send/message → 200
🌐 API GET https://www.linkedin.com/in/johndoe → 200
```

### 6. Email Service Logging
Detailed email operation logging:
- Service initialization
- Email preparation
- Postal API calls
- Delivery status
- Error details with response bodies

Example:
```
📧 Postal Email Service initialized
   Server: https://dlvr.rehosted.us
   From: matt@example.com
   To: matt@example.com
📤 Sending email to matt@example.com: 📝 Approve LinkedIn Post from John Doe
✅ Email sent successfully. Message ID: msg_abc123xyz
```

### 7. Webhook Processing
Detailed approval/rejection webhook logging:
- Token validation
- Request lookups
- Status checks
- Database updates
- Workflow transitions

Example:
```
🔍 Looking up approval request by token: abc123...
✅ Found approval request for post 5
🔍 Looking up variant 12 for post 5
✅ Found variant 12 (option 2)
📋 Workflow [Post 5]: APPROVING variant_id=12
📝 Marked 2 other variants as rejected
✅ Post 5 approved (variant 12, option 2)
```

## Error Handling

### Exception Logging
All exceptions are logged with:
- Exception type
- Error message
- Full stack trace
- Contextual information (post ID, user, etc.)

Example:
```
❌ Failed: send_approval_email - HTTPError: 500 Server Error post_id=5
   Response status: 500
   Response body: {"error": "SMTP connection failed"}
Traceback (most recent call last):
  ...full stack trace...
```

### Error Context
Errors include relevant context:
- Post ID
- User email
- Operation being performed
- Timestamp

## Log Rotation

Logs are stored in `/app/data/linkedin_reposter.log`:
- Persistent across container restarts
- Part of Docker volume mount
- TODO: Implement log rotation (daily/weekly)

## Viewing Logs

### Docker Container Logs
```bash
# View live logs (console output)
docker logs linkedin-reposter -f

# View last 100 lines
docker logs linkedin-reposter --tail 100

# View logs with timestamps
docker logs linkedin-reposter -t
```

### Log File
```bash
# View log file inside container
docker exec linkedin-reposter tail -f /app/data/linkedin_reposter.log

# View from host (data volume is mounted)
tail -f /Users/matt/repo/linkedin-reposter/data/linkedin_reposter.log

# Search for errors
docker exec linkedin-reposter grep "ERROR" /app/data/linkedin_reposter.log
```

## Monitoring & Alerting (Future)

Future enhancements:
1. **Structured Logging**: Switch to JSON format for better parsing
2. **Log Aggregation**: Send logs to external service (e.g., Loki, ELK)
3. **Metrics**: Export Prometheus metrics for monitoring
4. **Alerts**: Configure alerts for error rates, latency, failures
5. **Log Retention**: Implement automatic log rotation and archival

## Debug Mode

To enable debug logging:

1. Update `app/main.py`:
```python
setup_logging(log_level="DEBUG", log_file="/app/data/linkedin_reposter.log")
```

2. Rebuild container:
```bash
docker compose up -d --build
```

Debug mode will show:
- SQL queries
- API request/response bodies
- Internal state changes
- Detailed workflow steps

## Best Practices

1. **Consistent Format**: Use helper functions for common operations
2. **Contextual Info**: Always include relevant IDs (post_id, variant_id, etc.)
3. **Actionable Messages**: Errors should indicate what went wrong and why
4. **No Secrets**: Never log passwords, API keys, or full tokens
5. **Performance**: Avoid excessive logging in hot paths
6. **Emoji Usage**: Use emojis for quick visual scanning

## Log Examples by Module

### Config Loading
```
🔐 Connecting to Infisical...
   URL: https://infisical.example.com
   Project: 4627ccea-f94c-4f19-9605-6892dfd37ee0
✅ Connected to Infisical successfully
📦 Loading 9 secrets from Infisical...
   ✓ APPROVAL_EMAIL: matt@example.com
   ✓ LINKEDIN_PASSWORD: ***
✅ Loaded 9 secrets from Infisical
```

### Database Operations
```
🗄️  Initializing database: sqlite+aiosqlite:///./data/linkedin_reposter.db
✅ Database initialized successfully
🗄️  DB INSERT: linkedin_posts id=5
🗄️  DB UPDATE: linkedin_posts id=5 status=awaiting_approval
```

### HTTP Requests
```
🌐 GET /posts
✅ GET /posts → 200 (0.05s)
🌐 GET /webhook/approve/abc123
✅ GET /webhook/approve/abc123 → 200 (0.25s)
```

### Email Operations
```
▶️  Starting: send_approval_email post_id=5 author=johndoe
📧 Sending approval email for post 5
   Author: John Doe (@johndoe)
   Variants: [12, 13, 14]
   Token: abc123...
📤 Sending email to matt@example.com: 📝 Approve LinkedIn Post from John Doe
✅ Email sent successfully. Message ID: msg_xyz
✅ Completed: send_approval_email (took 1.23s) post_id=5
```

### Error Scenarios
```
❌ Failed: send_email - ConnectionError: Failed to connect to Postal server
   Response status: 503
   Response body: Service temporarily unavailable
Traceback (most recent call last):
  File "/app/app/email.py", line 85, in send_email
    response = await client.post(...)
  ...
```

## Summary

Comprehensive logging is now in place to:
- ✅ Track all operations from start to finish
- ✅ Identify errors quickly with full context
- ✅ Monitor performance (request duration)
- ✅ Audit user actions (approvals, rejections)
- ✅ Debug issues with detailed traces
- ✅ Provide visibility into the system state
