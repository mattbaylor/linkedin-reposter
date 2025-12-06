# Caddy Configuration for LinkedIn Reposter with Authelia

## Complete Caddyfile Configuration

Add this to your Caddyfile on TrueNAS:

```caddy
liposter.example.com {
	# Protect all routes except webhooks and health checks
	@protected {
		not path /webhook* /health
	}
	
	handle @protected {
		# Authelia forward auth
		forward_auth http://localhost:9091 {
			uri /api/verify?rd=https://auth.example.com
			copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
		}
		
		# Handle websockify WebSocket separately after auth
		handle /websockify* {
			uri strip_prefix /websockify
			reverse_proxy localhost:6080
		}
		
		# Everything else goes to the app
		reverse_proxy http://192.0.2.10:8080 {
			header_up Host {http.request.host}
			header_up X-Real-IP {remote_host}
		}
	}
	
	# Public routes (webhooks, health checks)
	reverse_proxy http://192.0.2.10:8080 {
		header_up Host {http.request.host}
		header_up X-Real-IP {remote_host}
	}
	
	encode gzip
}
```

## What Gets Protected

### Requires Authelia Login:

- `/admin/dashboard` - Main admin dashboard
- `/admin/vnc` - VNC viewer
- `/admin/posts/*` - Post management API
- `/websockify` - VNC WebSocket
- `/stats` - Statistics
- `/docs` - API documentation  
- `/test/*` - Test endpoints
- `/schedule/*` - Schedule management
- All other routes except those below

### Public (No Auth Required):

- `/webhook/approve/*` - Email approval links
- `/webhook/reject/*` - Email rejection links
- `/health` - Health check endpoint

## Why This Configuration?

### 1. Webhooks Must Be Public

Email approval links look like:
```
https://liposter.example.com/webhook/approve/abc123?variant_id=456
```

These links are clicked from email and **cannot require login** or they won't work.

### 2. Health Checks Must Be Public

Monitoring tools (uptime checkers, Docker health checks) need to access `/health` without authentication.

### 3. Everything Else Should Be Protected

Admin dashboard, VNC access, stats, and management endpoints should require authentication to prevent unauthorized access.

## Testing After Deployment

### 1. Test Public Routes (No Auth)

```bash
# Health check - should work without login
curl https://liposter.example.com/health

# Webhook - should work (though will fail without valid token)
curl https://liposter.example.com/webhook/approve/test123
```

### 2. Test Protected Routes (Require Auth)

```bash
# Dashboard - should redirect to Authelia
curl -I https://liposter.example.com/admin/dashboard

# Should see: HTTP 302 redirect to auth.example.com

# Stats - should redirect to Authelia
curl -I https://liposter.example.com/stats

# VNC - should redirect to Authelia  
curl -I https://liposter.example.com/admin/vnc
```

### 3. Test in Browser

1. **Unauthenticated**:
   - Visit: `https://liposter.example.com/admin/dashboard`
   - Should redirect to: `https://auth.example.com`
   - Log in with your Authelia credentials
   - Should redirect back to dashboard

2. **Authenticated**:
   - After login, visit any protected route
   - Should work without additional prompts
   - Session persists across admin routes

3. **Public Routes**:
   - Visit: `https://liposter.example.com/health`
   - Should show JSON immediately (no login)

## Alternative: More Restrictive (Admin-Only Paths)

If you want ONLY `/admin/*` protected and everything else public:

```caddy
liposter.example.com {
	# Only protect /admin paths
	@admin {
		path /admin* /websockify*
	}
	
	handle @admin {
		forward_auth http://localhost:9091 {
			uri /api/verify?rd=https://auth.example.com
			copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
		}
		
		handle /websockify* {
			uri strip_prefix /websockify
			reverse_proxy localhost:6080
		}
		
		reverse_proxy http://192.0.2.10:8080 {
			header_up Host {http.request.host}
			header_up X-Real-IP {remote_host}
		}
	}
	
	# Everything else is public
	reverse_proxy http://192.0.2.10:8080 {
		header_up Host {http.request.host}
		header_up X-Real-IP {remote_host}
	}
	
	encode gzip
}
```

This would make `/stats`, `/docs`, `/test/*` public.

## Recommended: Everything Protected (Default Config Above)

Pros:
- Maximum security
- Only webhooks and health are public (necessary)
- Stats, docs, test endpoints require login

Cons:
- Must log in to see stats
- API docs require authentication

## Applying the Configuration

### On TrueNAS:

```bash
# SSH to TrueNAS
ssh your-truenas-server

# Edit Caddyfile
sudo nano /opt/caddy/Caddyfile

# Add the liposter.example.com block

# Test configuration
caddy validate --config /opt/caddy/Caddyfile

# Reload Caddy (no downtime)
caddy reload --config /opt/caddy/Caddyfile

# Or restart Caddy service
systemctl restart caddy
```

### Verify Configuration:

```bash
# Check Caddy is running
systemctl status caddy

# Check Caddy logs
journalctl -u caddy -f

# Test from laptop
curl -I https://liposter.example.com/admin/dashboard
```

## Troubleshooting

### Dashboard Shows Login Error

**Symptom**: Redirected to Authelia, but after login shows error

**Check**:
```bash
# Verify Authelia is running
docker ps | grep authelia

# Check Authelia logs
docker logs authelia

# Verify forward_auth is working
curl -I https://liposter.example.com/admin/dashboard
```

### WebSocket Not Working After Auth

**Symptom**: VNC shows "failed to connect" even after login

**Fix**: Ensure `handle /websockify*` is INSIDE the `handle @protected` block so auth applies first.

### Webhooks Require Login (WRONG!)

**Symptom**: Email approval links redirect to Authelia

**Fix**: Ensure `/webhook*` is in the excluded paths:
```caddy
@protected {
    not path /webhook* /health
}
```

### Health Check Fails

**Symptom**: Docker health check failing, container shows unhealthy

**Fix**: Ensure `/health` is publicly accessible (in excluded paths).

## Security Notes

1. **Session Persistence**: Authelia sessions last based on your Authelia config (typically hours or days)

2. **Multiple Users**: If you have multiple admins, each logs in with their own Authelia credentials

3. **VNC Security**: VNC is protected by Authelia, so only logged-in users can access the browser session

4. **Webhook Security**: Webhooks use secure tokens (generated by the app) so they can't be guessed

5. **HTTPS Only**: All traffic uses HTTPS via Caddy's automatic Let's Encrypt certificates

## Example: Full Working Configuration

```caddy
# Authelia service (already configured)
auth.example.com {
    reverse_proxy http://localhost:9091
    encode gzip
}

# LinkedIn Reposter with Authelia protection
liposter.example.com {
    @protected {
        not path /webhook* /health
    }
    
    handle @protected {
        forward_auth http://localhost:9091 {
            uri /api/verify?rd=https://auth.example.com
            copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
        }
        
        handle /websockify* {
            uri strip_prefix /websockify
            reverse_proxy localhost:6080
        }
        
        reverse_proxy http://192.0.2.10:8080 {
            header_up Host {http.request.host}
            header_up X-Real-IP {remote_host}
        }
    }
    
    reverse_proxy http://192.0.2.10:8080 {
        header_up Host {http.request.host}
        header_up X-Real-IP {remote_host}
    }
    
    encode gzip
}
```

---

**Status**: Ready for production deployment  
**Date**: December 5, 2025  
**Tested**: Configuration validated but not yet deployed to TrueNAS
