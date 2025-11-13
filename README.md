# Claude Code Usage Monitor

A live-updating terminal dashboard for monitoring Claude Code account usage and rate limits.

## Overview

This tool continuously monitors your Claude Code account usage through the Claude Code API, displaying real-time usage statistics and reset timers directly in your terminal.

## Features

- **Live Updates**: Continuously polls usage data every 30 seconds
- **Profile Information**: Display name, email, organization name
- **Account Badges**: Shows Enterprise, Pro, or Max account status
- **Rate Limit Tier**: Displays your current rate limit tier
- **Progress Bars**: Visual representation of usage percentage with color coding
- **Multiple Rate Limits**: Shows 5-hour and 7-day limits when active
- **Reset Timer**: Countdown to next rate limit reset
- **Overage Tracking**: Displays overage spending in dollars (requires Firefox session)
- **Usage Projection**: Projects overage costs to next reset with rate calculation
- **Historical Tracking**: Stores usage snapshots locally for trend analysis
- **In-Place Refresh**: Clean display that updates without scrolling
- **Auto Token Detection**: Automatically loads OAuth credentials from Claude Code
- **Firefox Session Integration**: Automatically extracts session key for overage data
- **Token Expiry Handling**: Detects expired tokens and prompts for refresh
- **Narrow Console Friendly**: Compact display optimized for small terminal windows
- **Ctrl+C Handling**: Clean exit on interrupt

## Requirements

- Python 3.6+
- Claude Code CLI installed and authenticated

## Installation

### Option 1: Install with pipx (Recommended)

Install directly from GitHub using pipx for isolated installation:

```bash
pipx install git+https://github.com/LightspeedDMS/claude-usage.git
```

### Option 2: Install with pip

Install directly from GitHub using pip:

```bash
pip install git+https://github.com/LightspeedDMS/claude-usage.git
```

### Option 3: Install from Local Clone

Clone the repository and install:

```bash
git clone https://github.com/LightspeedDMS/claude-usage.git
cd claude-usage
pip install .
```

### Option 4: Development Installation

For development with editable install:

```bash
git clone https://github.com/LightspeedDMS/claude-usage.git
cd claude-usage
pip install -e .
```

## Usage

After installation, run the monitor from anywhere:

```bash
claude-usage
```

The command is globally accessible from any directory.

Press `Ctrl+C` to stop monitoring.

### Example Output

**Basic Display (OAuth only):**
```
Claude Code Usage Monitor
Press Ctrl+C to stop

┌ Claude Code Usage ──────────────────────────┐
│ 👤 User (user@example.com)                  │
│ 🏢 Company Name ENTERPRISE                  │
│ ⚡ Tier: default_claude_max_5x              │
│                                             │
│ 5-Hour Limit: ████████████████░░ 96%       │
│ ⏰ Resets in: 1h 40m                        │
│                                             │
│ Updated: 20:19:18                           │
└─────────────────────────────────────────────┘
```

**Full Display with Monthly Overage Limit (Firefox session):**
```
Claude Code Usage Monitor
Press Ctrl+C to stop

✓ Firefox session key detected - overage data enabled

┌ Claude Code Usage ──────────────────────────────────────┐
│ 👤 John Doe (john@company.com)                          │
│ 🏢 Acme Corporation ENTERPRISE                          │
│ ⚡ Tier: default_claude_max_5x                          │
│                                                          │
│ 5-Hour Limit: ████████████████████ 100%                 │
│ ⏰ Resets in: 2h 15m                                    │
│                                                          │
│ Overage: ████████░░░░░░░░░░ $110.26/$500.00             │
│ 📊 Projected by reset: $125.40 (+$15.14)                │
│ 📈 Rate: $6.73/hour                                     │
│                                                          │
│ Updated: 21:04:36                                       │
└──────────────────────────────────────────────────────────┘
```

**Full Display with Unlimited Overage (Firefox session):**
```
┌ Claude Code Usage ──────────────────────────────────────┐
│ 👤 John Doe (john@company.com)                          │
│ 🏢 Acme Corporation ENTERPRISE                          │
│ ⚡ Tier: default_claude_max_5x                          │
│                                                          │
│ 5-Hour Limit: ████████████████████ 100%                 │
│ ⏰ Resets in: 2h 15m                                    │
│                                                          │
│ 💳 Overage: $110.26                                     │
│ 📊 Projected by reset: $125.40 (+$15.14)                │
│ 📈 Rate: $6.73/hour                                     │
│                                                          │
│ Updated: 21:04:36                                       │
└──────────────────────────────────────────────────────────┘
```

**Progress Bar Color Coding:**
- 🟢 **0-50%**: Green
- 🟡 **51-80%**: Yellow
- 🟠 **81-99%**: Orange
- 🔴 **100%**: Red

## How It Works

### API Endpoints

This tool uses multiple Claude API endpoints:

**Usage Data (OAuth):**
```
GET https://api.anthropic.com/api/oauth/usage
```
Returns 5-hour and 7-day rate limit utilization percentages.

**Profile Information (OAuth):**
```
GET https://api.anthropic.com/api/oauth/profile
```
Returns user account details, organization info, and badges.

**Overage Spending (Session-based):**
```
GET https://claude.ai/api/organizations/{org_uuid}/overage_spend_limits
```
Returns overage credit usage and monthly limits. Requires browser session authentication (not OAuth).

### Authentication

The monitor uses two authentication methods:

**1. OAuth Authentication (Primary):**
- **Location**: `~/.claude/.credentials.json`
- **Token**: `claudeAiOauth.accessToken`
- **Used for**: Usage data and profile information

Required headers:
```http
Authorization: Bearer {accessToken}
Content-Type: application/json
anthropic-beta: oauth-2025-04-20
User-Agent: claude-code/2.0.37
```

**2. Firefox Session Authentication (Optional):**
- **Source**: Firefox cookie database `~/.mozilla/firefox/*/cookies.sqlite`
- **Cookie**: `sessionKey` from `claude.ai` domain
- **Used for**: Overage spending and projection data
- **Auto-refresh**: Every 5 minutes from active Firefox session

The monitor automatically extracts the session key from Firefox if you're logged into claude.ai in Firefox. No manual configuration needed.

### API Response Formats

**Usage Response:**
```json
{
  "five_hour": {
    "utilization": 78.0,
    "resets_at": "2025-11-13T04:00:00+00:00"
  },
  "seven_day": null,
  "seven_day_oauth_apps": null,
  "seven_day_opus": null
}
```

**Profile Response:**
```json
{
  "account": {
    "uuid": "...",
    "full_name": "User Name",
    "display_name": "User",
    "email": "user@example.com",
    "has_claude_max": false,
    "has_claude_pro": false
  },
  "organization": {
    "uuid": "...",
    "name": "Company Name",
    "organization_type": "claude_enterprise",
    "billing_type": "stripe_subscription_contracted",
    "rate_limit_tier": "default_claude_max_5x"
  }
}
```

**Overage Response:**
```json
{
  "items": [
    {
      "account_uuid": "...",
      "used_credits": 11026,
      "monthly_credit_limit": 50000
    }
  ]
}
```

Note: Credits are converted to dollars at 1 credit = $0.01 (100 credits = $1.00)

## Technical Details

### Rate Limits

Claude Code implements multiple rate limit windows:
- **5-Hour Window**: Primary rate limit shown in the monitor
- **7-Day Window**: Extended rate limit (not always active)
- **Organization-specific limits**: Based on subscription tier

### Overage Projection System

The monitor includes a sophisticated projection system that predicts overage costs:

**How It Works:**
1. **Data Collection**: Stores usage snapshots every 30 seconds to `~/.claude-usage/usage_history.db`
2. **Rate Calculation**: Calculates spending rate from 30-minute historical window
3. **Projection**: Projects total overage by reset time using formula: `current + (rate × hours_until_reset)`
4. **Display**: Shows current overage, projected total, and hourly rate

**Database Schema:**
```sql
CREATE TABLE usage_snapshots (
    timestamp INTEGER PRIMARY KEY,
    credits_used INTEGER,
    utilization_percent REAL,
    resets_at TEXT
)
```

**Requirements:**
- Projection appears after ~30 minutes of data collection
- Automatic cleanup of data older than 24 hours
- Non-blocking storage (failures don't affect monitoring)

### Token Management

OAuth tokens have an expiration time tracked in the credentials file:
- Tokens are checked for expiry before each API call
- 5-minute buffer applied to prevent edge cases
- User prompted to refresh via `claude` command when expired

### Firefox Cookie Extraction

Session key extraction from Firefox:
- Reads from `~/.mozilla/firefox/*/cookies.sqlite`
- Copies database to temp file (Firefox locks it when running)
- Queries `moz_cookies` table for `sessionKey` cookie
- Refreshes every 5 minutes automatically
- Fallback to OAuth-only mode if Firefox not available

## Troubleshooting

### "Token expired" Error

If you see a token expiration error:
```bash
claude
```

Run any Claude Code command to refresh your authentication.

### "Failed to load credentials" Error

Ensure Claude Code is installed and you're authenticated:
```bash
which claude
claude --version
```

### Network Errors

Check your internet connection and verify you can reach the API:
```bash
curl -I https://api.anthropic.com
```

## Limitations

- Requires valid Claude Code authentication
- Token refresh must be done manually via Claude Code CLI
- API endpoints are undocumented and may change
- Overage tracking requires Firefox with active claude.ai session
- Projection requires 30 minutes of historical data
- Only monitors 5-hour rate limit window (primary limit)

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## License

MIT License - See LICENSE file for details.

## Acknowledgments

Built with the excellent [Rich](https://github.com/Textualize/rich) library for terminal UI.
