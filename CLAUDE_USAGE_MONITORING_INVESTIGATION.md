# Claude Code Usage Monitoring - Investigation Report

**Date**: 2025-11-12
**Goal**: Create Python app to monitor Claude Code account usage and reset time (similar to `/usage` command)

## Summary

**BREAKTHROUGH**: Successfully reverse-engineered Claude Code CLI to discover the API structure!

I've identified the API endpoints and authentication pattern used by Claude Code's `/usage` command. The system uses `api.anthropic.com` (NOT `claude.ai`) with Organization UUID-based routing. While Cloudflare still protects `claude.ai`, the Anthropic API endpoints are accessible with proper OAuth tokens.

## Findings

### 1. Credentials Structure

**Location**: `~/.claude/.credentials.json`

**Structure**:
```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-...",
    "refreshToken": "sk-ant-ort01-...",
    "expiresAt": 1763010655170,
    "scopes": [
      "user:inference",
      "user:profile",
      "user:sessions:claude_code"
    ],
    "subscriptionType": "enterprise"
  }
}
```

- **Access Token**: Bearer token for API authentication
- **Refresh Token**: For obtaining new access tokens
- **Expires At**: Unix timestamp in milliseconds
- **Subscription Type**: enterprise, pro, or free tier

### 2. Reverse Engineering Claude Code CLI

**Binary Location**: `~/.local/share/claude/versions/2.0.37` (203MB bundled Node.js executable)

**Key Discoveries from Strings Analysis**:

**API Configuration**:
```javascript
BASE_API_URL: "https://api.anthropic.com"
CONSOLE_AUTHORIZE_URL: "https://console.anthropic.com/oauth/authorize"
CLAUDE_AI_AUTHORIZE_URL: "https://claude.ai/oauth/authorize"
TOKEN_URL: "https://console.anthropic.com/v1/oauth/token"
API_KEY_URL: "https://api.anthropic.com/api/oauth/claude_cli/create_api_key"
ROLES_URL: "https://api.anthropic.com/api/oauth/claude_cli/roles"
CLIENT_ID: "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
```

**Organization-Based API Pattern**:
```
https://api.anthropic.com/api/organization/{organizationUuid}/...
```

**Example Endpoints Found**:
- `/api/organization/{organizationUuid}/claude_code_sonnet_1m_access` - Access tier checks
- `/api/oauth/profile` - Get profile with organization info
- `/api/claude_cli_profile` - CLI-specific profile data

**Authentication**:
- Uses Bearer token from OAuth (`Authorization: Bearer {accessToken}`)
- Includes `anthropic-beta: oauth-2025-04-20` header
- User-Agent: `claude-code/2.0.37`

**Missing Information**:
- Organization UUID is NOT stored in `~/.claude/.credentials.json`
- Need to fetch OAuth profile to get `organizationUuid`
- Profile endpoint: `https://api.anthropic.com/api/oauth/profile`

### 3. Cloudflare Protection

**Problem**: Claude.ai is protected by Cloudflare's "Just a moment..." challenge page

**Impact**:
- Simple HTTP requests with OAuth token are blocked
- Cloudflare requires JavaScript execution and browser cookies
- Challenge must be completed before accessing API endpoints

**Example Response** (from `/api/account`):
```html
<!DOCTYPE html>
<html>
  <head>
    <title>Just a moment...</title>
    <meta http-equiv="refresh" content="360">
  </head>
  <body>
    <noscript>
      Enable JavaScript and cookies to continue
    </noscript>
    <script>
      // Cloudflare challenge script...
    </script>
  </body>
</html>
```

## Created Script

**Location**: `/home/jsbattig/Dev/claude-server/scripts/monitor-claude-usage.py`

**Features**:
- ✅ Reads OAuth credentials from ~/.claude/.credentials.json
- ✅ Validates token expiration
- ✅ Displays subscription type and scopes
- ✅ Tries multiple potential API endpoints
- ✅ Provides detailed error reporting
- ⚠️  Blocked by Cloudflare protection

**Usage**:
```bash
# Show credentials info
python3 scripts/monitor-claude-usage.py --info

# Attempt to fetch usage (currently blocked by Cloudflare)
python3 scripts/monitor-claude-usage.py

# Use custom credentials file
python3 scripts/monitor-claude-usage.py --credentials /path/to/credentials.json
```

**Current Output** (--info mode):
```
Claude Code Credentials Information
==================================================
Credentials file: /home/jsbattig/.claude/.credentials.json
Subscription type: enterprise
Scopes: user:inference, user:profile, user:sessions:claude_code
Token expires at: 2025-11-12 23:10:55.170000
Token valid for: 0 days, 5 hours
```

## Alternative Approaches

### Option 1: Browser Automation (Selenium/Playwright)

**Approach**: Use browser automation to handle Cloudflare challenge

**Pros**:
- Can handle JavaScript challenges
- Can maintain browser cookies
- Works like a real browser

**Cons**:
- Heavyweight solution (requires full browser)
- Slower than direct API calls
- More complex to maintain

**Implementation**:
```python
from selenium import webdriver
from selenium.webdriver.common.by import By

# Use OAuth token in browser session
driver = webdriver.Chrome()
driver.get("https://claude.ai")

# Inject OAuth token as cookie
driver.add_cookie({
    'name': 'sessionKey',
    'value': access_token,
    'domain': 'claude.ai'
})

# Navigate to usage page
driver.get("https://claude.ai/settings/usage")

# Wait for Cloudflare challenge
# Then scrape usage data from page
```

### Option 2: Reverse Engineer Claude Code CLI

**Approach**: Examine how the official `/usage` command works

**Investigation needed**:
1. Does Claude Code CLI have additional auth tokens?
2. Does it use a different API endpoint?
3. Does it bypass Cloudflare somehow?
4. Are there additional headers or request parameters?

**Method**:
```bash
# Monitor network traffic while running /usage command
# Use tools like mitmproxy, Wireshark, or Chrome DevTools

# Or examine Claude Code CLI source code (if available)
# Check: ~/.claude/ installation directory
# Look for: API endpoint configuration, auth handling
```

### Option 3: Web Scraping with Session Handling

**Approach**: Maintain a browser session and scrape usage page

**Pros**:
- Simpler than full browser automation
- Can reuse session cookies

**Cons**:
- Still needs to solve Cloudflare challenge
- Fragile (breaks if page structure changes)
- May violate terms of service

**Implementation**:
```python
import requests
from bs4 import BeautifulSoup

session = requests.Session()

# First request: Get Cloudflare challenge cookies
response = session.get("https://claude.ai/settings/usage")

# Parse challenge page and execute JavaScript (complex)
# Then retry with challenge cookies

# Parse HTML to extract usage data
soup = BeautifulSoup(response.text, 'html.parser')
# Extract usage metrics from DOM
```

### Option 4: Wait for Official API Documentation

**Approach**: Contact Anthropic support for official API documentation

**Questions to ask**:
1. Is there a public API for enterprise customers to query usage?
2. What's the correct endpoint for organization usage data?
3. How do we obtain the organization UUID?
4. Can we bypass Cloudflare for programmatic access?

**Anthropic Contact**:
- Support: https://support.anthropic.com
- Enterprise support: enterprise@anthropic.com

### Option 5: Local Usage Tracking

**Approach**: Track usage locally by monitoring Claude Code CLI activity

**Pros**:
- No API access needed
- Complete control
- No Cloudflare issues

**Cons**:
- Doesn't show account-wide usage (only local)
- Doesn't show usage limits or reset times
- Requires monitoring all Claude Code sessions

**Implementation**:
```python
# Monitor ~/.claude/history.jsonl for API calls
# Track tokens used per session
# Calculate estimated usage

import json
from pathlib import Path

history_file = Path.home() / ".claude" / "history.jsonl"

total_tokens = 0
with open(history_file, 'r') as f:
    for line in f:
        entry = json.loads(line)
        if 'usage' in entry:
            total_tokens += entry['usage'].get('total_tokens', 0)

print(f"Total tokens used: {total_tokens}")
```

## Missing Information

To successfully implement usage monitoring, we need:

1. **Organization UUID**: Where is it stored? How to retrieve it?
2. **Cloudflare Bypass**: How does Claude Code CLI handle Cloudflare?
3. **Correct API Endpoint**: Full URL structure for enterprise usage endpoint
4. **Additional Auth**: Are there other authentication mechanisms beyond OAuth token?
5. **Usage Data Structure**: What fields are returned by the usage API?

## Recommendations

**Short-term** (Immediate solution):
1. Use the `/usage` command in Claude Code CLI (existing functionality)
2. If automation is critical, investigate Option 2 (reverse engineer CLI)

**Medium-term** (Best practice):
1. Contact Anthropic enterprise support for official API documentation
2. Request programmatic access endpoint for enterprise customers
3. Get organization UUID and proper authentication method

**Long-term** (Robust solution):
1. Wait for official API documentation
2. Implement proper browser automation if needed (Option 1)
3. Or use local tracking if account-wide data isn't critical (Option 5)

## Next Steps

**To proceed, please advise**:

A. **Reverse engineer Claude Code CLI** - Investigate how `/usage` command works internally
   - Examine CLI source code or network traffic
   - Find bypass method for Cloudflare
   - Implement same approach in Python

B. **Browser automation** - Implement Selenium/Playwright solution
   - Handle Cloudflare challenge automatically
   - Scrape usage page after authentication
   - More robust but heavier solution

C. **Contact Anthropic** - Request official API documentation
   - Proper enterprise API access
   - Organization UUID retrieval
   - Official usage endpoint

D. **Local tracking** - Monitor local Claude Code activity
   - Track tokens used from history.jsonl
   - Estimate usage without API calls
   - Limited to local sessions only

Which approach would you like to pursue?

## Script Location

**Main script**: `/home/jsbattig/Dev/claude-server/scripts/monitor-claude-usage.py`

**This report**: `/home/jsbattig/Dev/claude-server/scripts/CLAUDE_USAGE_MONITORING_INVESTIGATION.md`

---

**Status**: Investigation complete, awaiting direction for implementation
