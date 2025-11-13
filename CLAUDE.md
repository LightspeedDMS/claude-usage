# Claude Usage Monitor

## Overview

Live-updating terminal dashboard for monitoring Claude Code and Anthropic Console account usage. Supports dual-mode operation:
- **Code Mode**: 5-hour rate limits, monthly overage tracking, projection system (30-second polling)
- **Console Mode**: Organization-wide usage, MTD/YTD cost tracking, per-model breakdowns (2-minute polling)

## Architecture

**Modular design with 5 components:**

- **auth.py**: Authentication management
  - `OAuthManager`: Claude Code OAuth tokens
  - `FirefoxSessionManager`: Browser session key extraction
  - `AdminAuthManager`: Anthropic Console Admin API keys

- **api.py**: API client wrapper
  - `ClaudeAPIClient`: Code mode - Usage, profile, and overage endpoints
  - `ConsoleAPIClient`: Console mode - Organization, workspaces, MTD/YTD reports

- **storage.py**: Database and analytics
  - `UsageStorage`: SQLite operations for both Code and Console snapshots
  - `UsageAnalytics`: Rate calculation and projections for both modes

- **display.py**: UI rendering
  - `UsageRenderer`: Code mode - 5-hour limits, overage display
  - `ConsoleRenderer`: Console mode - MTD/YTD, model breakdowns, workspaces

- **monitor.py**: Main orchestration
  - Dual-mode support with automatic detection
  - Mode-specific polling: 30s (Code) / 2min (Console)
  - Entry point

## Key Features

### Code Mode
- **OAuth + Firefox Session**: Dual authentication for usage and overage data
- **Monthly overage tracking**: Cumulative display, even when not actively accruing
- **Projection system**: Spending rate from 30-minute history window
- **Smart display**: Rate/projection only shown when utilization >= 100%
- **Auto-refresh**: Session key refreshed every 5 minutes
- **Polling**: Every 30 seconds

### Console Mode
- **Admin API Key**: Environment variable or credentials file
- **Mode Detection**: Automatic based on Admin API key presence
- **MTD/YTD Tracking**: Month-to-date and year-to-date cost reports
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
2. MTD/YTD date ranges calculated automatically
3. Console snapshots stored to database every 2 minutes
4. Rate calculated for end-of-month projection
5. Errors displayed with red border and warning messages

## Technologies

- **Rich**: Terminal UI with progress bars and live updates
- **SQLite**: Local usage history storage
- **Requests**: HTTP client for API calls
- **Python 3.6+**: Core language
