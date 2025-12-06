# GitHub Copilot AI Integration - Machine Identity Setup

This document explains how to use GitHub Copilot for AI variant generation with automatic token updates from your OpenCode project.

## Why Use GitHub Copilot?

**GitHub Models** (current default):
- ✅ Free tier
- ❌ Rate limits (429 errors)
- ❌ Limited requests per hour

**GitHub Copilot** (via OpenCode project):
- ✅ Higher rate limits (with paid subscription)
- ✅ Better availability
- ✅ Same model quality (GPT-4o)
- ✅ **Tokens auto-update** as you use OpenCode (no manual copying!)

## Setup Instructions

### Step 1: Create Machine Identity in Infisical

1. Go to https://infisical.example.com/
2. Navigate to **Settings** → **Access Control** → **Machine Identities**
3. Click **Create Machine Identity**
4. Configure:
   - **Name**: `linkedin-reposter-copilot` (or your choice)
   - **Description**: "Access to linkedin-reposter and OpenCode for Copilot tokens"

5. After creation, click on the identity and go to **Projects** tab
6. Add access to BOTH projects:
   - **linkedin-reposter** (`4627ccea-f94c-4f19-9605-6892dfd37ee0`)
     - Environment: `dev`
     - Role: `Developer` or `Viewer` (read access to secrets)
   - **OpenCode** (`your-opencode-project-id`)
     - Environment: `dev`
     - Role: `Developer` or `Viewer` (read access to secrets)

7. Go to **Authentication** tab and create **Universal Auth** credentials:
   - Click **Configure Universal Auth**
   - Copy the **Client ID** (starts with something like `mui_...`)
   - Copy the **Client Secret** (long string)

### Step 2: Update .env File

Edit `/Users/matt/repo/linkedin-reposter/.env`:

```bash
# OpenCode Project (for GitHub Copilot tokens)
OPENCODE_INFISICAL_PROJECT_ID=your-opencode-project-id

# Machine Identity for cross-project access
# Create this in Infisical: Settings → Machine Identities
INFISICAL_MACHINE_IDENTITY_CLIENT_ID=mui_xxxxxxxxxxxxx
INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET=your-client-secret-here
```

**Important**: Keep the existing `INFISICAL_TOKEN` - it's still used for the linkedin-reposter project.

### Step 3: Verify OpenCode Project Has Required Secrets

Make sure your OpenCode Infisical project (in `dev` environment) has:
- `GITHUB_COPILOT_ACCESS_TOKEN`
- `GITHUB_COPILOT_REFRESH_TOKEN`

These tokens are automatically updated by OpenCode, so linkedin-reposter will always have fresh tokens!

### Step 4: Rebuild and Restart

```bash
cd /Users/matt/repo/linkedin-reposter
docker compose build app
docker compose up -d
```

### Step 5: Verify It's Working

Check the logs on startup:

```bash
docker logs linkedin-reposter | grep -A 10 "Copilot"
```

You should see:
```
🔐 Loading GitHub Copilot tokens from OpenCode project...
   Using Machine Identity for cross-project access...
   ✓ GITHUB_COPILOT_ACCESS_TOKEN: ghu_xxxx...
   ✓ GITHUB_COPILOT_REFRESH_TOKEN: ghr_xxxx...
✅ Loaded 2 GitHub Copilot tokens from OpenCode project
```

Later in the logs:
```
🤖 GitHub Copilot AI Service initialized
   Model: gpt-4o
   API: GitHub Copilot
✅ Using GitHub Copilot AI service
```

## How Machine Identity Works

```
┌──────────────────────┐
│  linkedin-reposter   │
│    (Service Token)   │
└──────────┬───────────┘
           │
           ├─> Load linkedin-reposter secrets
           │   (Service Token: st.xxx)
           │
           └─> Load OpenCode Copilot tokens
               ├─> Use Machine Identity
               │   (Client ID + Secret)
               └─> Access OpenCode project
                   ├─> GITHUB_COPILOT_ACCESS_TOKEN
                   └─> GITHUB_COPILOT_REFRESH_TOKEN
```

## Benefits of Machine Identity

✅ **Cross-project access**: One identity, multiple projects  
✅ **Auto-updating tokens**: As OpenCode refreshes tokens, linkedin-reposter gets them automatically  
✅ **Secure**: Scoped permissions per project  
✅ **No manual copying**: Tokens sync automatically  

## Fallback Behavior

The system has intelligent fallback:

1. **Try Machine Identity** (if configured)
   - Load Copilot tokens from OpenCode project
   - Use GitHub Copilot API (higher limits)
   
2. **Fall back to GitHub Models** (if Machine Identity not configured or fails)
   - Use existing GitHub token from linkedin-reposter project
   - Use GitHub Models API (free tier with limits)

## Testing

Test variant regeneration:

```bash
# Should work without 429 errors
curl -X POST http://localhost:8080/admin/posts/1/regenerate
```

**With Copilot**: Fast, no rate limits  
**Without Copilot**: May hit 429 errors during heavy testing

## Troubleshooting

### "Could not load OpenCode project tokens"

**Possible causes**:
1. Machine Identity not configured
2. Machine Identity doesn't have access to OpenCode project
3. Wrong Client ID or Secret

**Check logs**:
```bash
docker logs linkedin-reposter 2>&1 | grep "OpenCode"
```

### Still seeing "Using GitHub Models AI service"

**Cause**: Copilot tokens not loaded

**Verify**:
```bash
# Check if Machine Identity vars are set
docker exec linkedin-reposter env | grep MACHINE_IDENTITY

# Check if OpenCode project ID is set
docker exec linkedin-reposter env | grep OPENCODE
```

### "You are not allowed to access this resource (403)"

**Cause**: Machine Identity doesn't have read access to OpenCode project

**Solution**: 
1. Go to Machine Identity in Infisical
2. Ensure OpenCode project is added with read permissions
3. Environment should be `dev`

## Environment Variables Summary

```bash
# Existing (keep these)
INFISICAL_TOKEN=st.xxx...           # Service token for linkedin-reposter project
INFISICAL_PROJECT_ID=4627ccea...    # linkedin-reposter project ID

# New (add these)
OPENCODE_INFISICAL_PROJECT_ID=bd790468...                 # OpenCode project ID
INFISICAL_MACHINE_IDENTITY_CLIENT_ID=mui_xxx...           # Machine Identity client ID
INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET=your-secret...   # Machine Identity secret
```

## Cost Comparison

| Service | Cost | Rate Limits | Token Updates | Recommended For |
|---------|------|-------------|---------------|-----------------|
| GitHub Models | Free | Low (~10 req/hr) | N/A | Testing, light usage |
| GitHub Copilot | $10-20/mo | High (~100+ req/hr) | Automatic | Production use |

## Notes

- Machine Identity is the recommended way for cross-project access in Infisical
- Tokens from OpenCode are kept fresh automatically as OpenCode updates them
- The same tokens you use in OpenCode are shared with linkedin-reposter
- Both services use the same prompt template for consistency
- Both use GPT-4o model
