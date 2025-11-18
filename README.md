# Claude Usage Monitor

A live-updating terminal dashboard for monitoring Claude account usage and rate limits. Supports dual-mode operation for both Claude Code users and organization administrators.

## Overview

This tool monitors Claude account usage through multiple APIs, displaying real-time usage statistics and cost tracking directly in your terminal. Automatically detects and switches between Code mode (personal usage) and Console mode (organization-wide tracking).

## Features

- **Dual Mode Support**: Automatic detection between Code mode and Console mode
- **Live Updates**: Polls every 30 seconds (Code mode) or 2 minutes (Console mode)
- **Code Mode**:
  - Profile Information: Display name, email, organization name
  - Account Badges: Shows Enterprise, Pro, or Max account status
  - Rate Limit Tier: Displays your current rate limit tier
  - Progress Bars: Visual representation of usage percentage with color coding
  - Multiple Rate Limits: Shows 5-hour and 7-day limits when active
  - Reset Timer: Countdown to next rate limit reset
  - Pace-Maker Integration: Displays throttling status and tempo tracking when Claude Pace Maker installed
- **Console Mode**:
  - Organization-wide MTD cost tracking
  - Per-User Tracking: Shows your individual Claude Code usage
  - Cost Projections: End-of-month cost forecasting based on current usage rate
  - Current user identification and personalized display
- **In-Place Refresh**: Clean display that updates without scrolling
- **Auto Token Detection**: Automatically loads OAuth credentials from Claude Code
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

### Mode Selection

The monitor automatically detects which mode to use based on available credentials:
- **Code Mode**: Uses Claude Code OAuth tokens (default for Claude Code users)
- **Console Mode**: Uses Anthropic Admin API key (for organization administrators)

Override automatic detection:
```bash
claude-usage --mode code    # Force Code mode
claude-usage --mode console # Force Console mode
```

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

**With Pace-Maker Integration (when installed):**
```
┌ Claude Code Usage ──────────────────────────────────────┐
│ 👤 John Doe (john@company.com)                          │
│ 🏢 Acme Corporation                                     │
│    Plan: ENTERPRISE                                     │
│ ⚡ Tier: default_claude_max_5x                          │
│                                                          │
│ 5-Hour Usage:  ████████████████░░░░ 78%                 │
│ ⏰ Resets in: 3h 45m                                    │
│                                                          │
│ 🎯 Pace Maker: ⚠️ THROTTLING                            │
│ 5-Hour Target: ████████████░░░░░░░░ 62%                 │
│ Deviation: +15.2% (over budget)                         │
│ ⏱️  Next delay: 45s per tool use                        │
│ Algorithm: adaptive/preload                             │
│ Tempo: enabled                                          │
│                                                          │
│ Updated: 21:04:36                                       │
└──────────────────────────────────────────────────────────┘
```

**Progress Bar Color Coding:**
- 🟢 **0-50%**: Green
- 🟡 **51-80%**: Yellow
- 🟠 **81-99%**: Orange
- 🔴 **100%**: Red

**Console Mode (Admin API):**
```
┌ Console Usage ──────────────────────────────┐
│ 🏢 Acme Corporation                         │
│                                             │
│ ═══ Month-to-Date (Nov 1-18) ═══           │
│ Your Claude Code Usage: $45.23             │
│ (john@company.com)                         │
│                                             │
│ Projected by end of month: $75.50 (+$30.27)│
│ Rate: $2.51/hour                           │
│                                             │
│ Updated: 14:23:15                          │
└─────────────────────────────────────────────┘
```

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

**Console API Endpoints (Admin API):**
```
GET https://api.anthropic.com/v1/organizations/{org_id}
GET https://api.anthropic.com/v1/organizations/{org_id}/workspaces
GET https://api.anthropic.com/v1/organizations/{org_id}/cost-report
GET https://api.anthropic.com/v1/organizations/{org_id}/usage_report/claude_code
GET https://api.anthropic.com/v1/organizations/users
```

### Authentication

The monitor supports multiple authentication methods:

**OAuth Authentication (Code Mode):**
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

**Admin API Authentication (Console Mode):**
- **Environment Variable**: `ANTHROPIC_ADMIN_API_KEY=sk-ant-admin-...`
- **Credentials File**: `~/.claude/.credentials.json` with `anthropicConsole.adminApiKey`
- **Used for**: Organization usage, MTD cost reports, per-user Claude Code tracking

Required headers:
```http
x-api-key: {adminApiKey}
anthropic-version: 2023-06-01
```

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

## Technical Details

### Rate Limits

Claude Code implements multiple rate limit windows:
- **5-Hour Window**: Primary rate limit shown in the monitor
- **7-Day Window**: Extended rate limit (not always active)
- **Organization-specific limits**: Based on subscription tier

### Token Management

OAuth tokens have an expiration time tracked in the credentials file:
- Tokens are checked for expiry before each API call
- 5-minute buffer applied to prevent edge cases
- User prompted to refresh via `claude` command when expired

### Pace-Maker Integration

Optional integration with [Claude Pace Maker](https://github.com/LightspeedDMS/claude-pace-maker):
- Automatically detects Pace-Maker installation in `~/.claude-pace-maker`
- Reads throttling status from Pace-Maker database and config
- Displays real-time throttling decisions and delay timings
- Shows deviation from target pace and constrained window
- Shows tempo tracking status (enabled/disabled) with color coding
- No installation required - read-only integration
- Supports both adaptive and legacy pacing algorithms

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

- Requires valid Claude Code authentication (Code mode) or Admin API key (Console mode)
- Token refresh must be done manually via Claude Code CLI
- API endpoints are undocumented and may change
- Console mode limited to MTD period (current month only)
- Console mode shows only current user's Claude Code usage, not organization-wide
- Pace-Maker integration requires separate installation of Claude Pace Maker

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## License

MIT License - See LICENSE file for details.

## Acknowledgments

Built with the excellent [Rich](https://github.com/Textualize/rich) library for terminal UI.
