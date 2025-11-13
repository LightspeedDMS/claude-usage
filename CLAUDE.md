# Claude Usage Monitor

## Overview

Live-updating terminal dashboard for monitoring Claude Code and Anthropic Console account usage. Supports dual-mode operation:
- **Code Mode**: 5-hour rate limits, monthly overage tracking, projection system (30-second polling)
- **Console Mode**: Organization-wide usage, MTD cost tracking, per-model breakdowns (2-minute polling)

## Architecture

**Modular design with 5 components:**

- **auth.py**: Authentication management
  - `OAuthManager`: Claude Code OAuth tokens
  - `FirefoxSessionManager`: Browser session key extraction
  - `AdminAuthManager`: Anthropic Console Admin API keys

- **api.py**: API client wrapper
  - `ClaudeAPIClient`: Code mode - Usage, profile, and overage endpoints
  - `ConsoleAPIClient`: Console mode - Organization, workspaces, MTD reports

- **storage.py**: Database and analytics
  - `UsageStorage`: SQLite operations for both Code and Console snapshots
  - `UsageAnalytics`: Rate calculation and projections for both modes

- **display.py**: UI rendering
  - `UsageRenderer`: Code mode - 5-hour limits, overage display
  - `ConsoleRenderer`: Console mode - MTD, model breakdowns, workspaces

- **monitor.py**: Main orchestration
  - Dual-mode support with automatic detection
  - Mode-specific polling: 30s (Code) / 2min (Console)
  - Entry point

## Key Features

### Code Mode
- **OAuth Authentication**: Claude Code OAuth tokens for usage/profile data
- **5-Hour Limit Tracking**: Real-time utilization percentage and reset countdown
- **~~Monthly Overage Tracking~~**: **DISABLED** - Cloudflare bot protection blocks access
  - Anthropic added advanced bot detection to overage API
  - Returns 403 Forbidden with challenge page
  - Code kept for reference but disabled to avoid spamming failed requests
- **7-Day Data Retention**: Smart rate calculation with progressive fallback windows
- **Polling**: Every 30 seconds

### Console Mode
- **Admin API Key**: Environment variable or credentials file
- **Mode Detection**: Automatic based on Admin API key presence
- **MTD Tracking**: Month-to-date cost reports
- **Per-User Claude Code Usage**: Individual user tracking via `/v1/organizations/usage_report/claude_code` endpoint
  - Day-by-day aggregation of costs by user email
  - Current user identification via `/v1/organizations/users` endpoint
  - Displays "Your Claude Code Usage: $X.XX" for authenticated user only
- **Model Breakdown**: Per-model usage (Sonnet, Opus, Haiku) with token counts
- **Workspace Limits**: Spending vs limits for each workspace
- **Error Display**: Rate limits and API errors shown prominently
- **Polling**: Every 2 minutes (respects Admin API rate limits)

## Data Flow

### Code Mode
1. OAuth token → usage/profile APIs
2. Firefox cookies → overage API
3. Snapshots stored to `~/.claude-usage/usage_history.db` every 30s
4. Rate calculated from last 30 minutes of snapshots
5. Projection = current + (rate × hours_until_reset)

### Console Mode
1. Admin API key → organization/workspaces/reports APIs
2. MTD date ranges calculated automatically
3. Per-user Claude Code usage fetched via day-by-day iteration
4. Current user email identified and matched against usage data
5. Console snapshots stored to database every 2 minutes
6. Rate calculated for end-of-month projection
7. Errors displayed with red border and warning messages

## Technologies

- **Rich**: Terminal UI with progress bars and live updates
- **SQLite**: Local usage history storage
- **Requests**: HTTP client for API calls
- **Python 3.6+**: Core language
