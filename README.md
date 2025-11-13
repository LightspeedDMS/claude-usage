# Claude Code Usage Monitor

A live-updating terminal dashboard for monitoring Claude Code account usage and rate limits.

## Overview

This tool continuously monitors your Claude Code account usage through the officially discovered API endpoint, displaying real-time usage statistics and reset timers directly in your terminal.

## Features

- **Live Updates**: Continuously polls usage data every 10 seconds
- **In-Place Refresh**: Clean display that updates without scrolling
- **Progress Bars**: Visual representation of usage percentage
- **Reset Timer**: Countdown to next rate limit reset
- **Auto Token Detection**: Automatically loads OAuth credentials from Claude Code
- **Token Expiry Handling**: Detects expired tokens and prompts for refresh
- **Narrow Console Friendly**: Compact display optimized for small terminal windows
- **Ctrl+C Handling**: Clean exit on interrupt

## Requirements

- Python 3.6+
- Claude Code CLI installed and authenticated
- Python packages:
  - `requests`
  - `rich`

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd claude-usage-reporting
```

2. Install required Python packages:
```bash
pip install requests rich
```

## Usage

Run the monitor:
```bash
./monitor-usage.py
```

Or with Python:
```bash
python3 monitor-usage.py
```

Press `Ctrl+C` to stop monitoring.

### Example Output

```
Claude Code Usage Monitor
Press Ctrl+C to stop

┌ Claude Code Usage ──────────────┐
│ 5-Hour Limit: ████████████░░░ 78%│
│ ⏰ Resets in: 2h 11m             │
│                                  │
│ Updated: 19:45:23                │
└──────────────────────────────────┘
```

## How It Works

### API Discovery

This tool uses the Claude Code usage API endpoint discovered through reverse engineering and SSL traffic interception:

```
GET https://api.anthropic.com/api/oauth/usage
```

### Authentication

The monitor automatically reads OAuth credentials from Claude Code's configuration:
- **Location**: `~/.claude/.credentials.json`
- **Token**: `claudeAiOauth.accessToken`

Required headers:
```http
Authorization: Bearer {accessToken}
Content-Type: application/json
anthropic-beta: oauth-2025-04-20
User-Agent: claude-code/2.0.37
```

### API Response Format

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

## Discovery Process

The API endpoint was discovered through:
1. Binary reverse engineering (strings extraction from Claude Code executable)
2. SSL interception using mitmproxy
3. Traffic analysis to identify the usage endpoint

Full discovery documentation available in `FINAL_FINDINGS.md`.

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

## Files

- `monitor-usage.py` - Main monitoring script
- `FINAL_FINDINGS.md` - Complete API discovery documentation
- `CLAUDE_USAGE_MONITORING_INVESTIGATION.md` - Investigation notes

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
- API endpoint is undocumented and may change
- Only monitors 5-hour rate limit window (primary limit)

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## License

MIT License - See LICENSE file for details.

## Acknowledgments

- API endpoint discovered through reverse engineering the Claude Code CLI
- Built with the excellent [Rich](https://github.com/Textualize/rich) library for terminal UI
