# Claude Usage Monitor

## Overview

Live-updating terminal dashboard for monitoring Claude Code and Anthropic Console account usage. Supports dual-mode operation:
- **Code Mode**: 5-hour and 7-day rate limits, utilization tracking (30-second polling)
- **Console Mode**: Personal Claude Code usage, MTD cost tracking, EOM projections (5-minute polling)

## Architecture

**Modular design with 5 components:**

- **auth.py**: Authentication management
  - `OAuthManager`: Claude Code OAuth tokens
  - `AdminAuthManager`: Anthropic Console Admin API keys

- **api.py**: API client wrapper
  - `ClaudeAPIClient`: Code mode - Usage and profile endpoints
  - `ConsoleAPIClient`: Console mode - Organization info, per-user Claude Code usage

- **storage.py**: Database and analytics
  - `UsageStorage`: SQLite operations for both Code and Console snapshots
  - `UsageAnalytics`: Rate calculation and projections for both modes

- **display.py**: UI rendering
  - `UsageRenderer`: Code mode - 5-hour and 7-day limits display
  - `ConsoleRenderer`: Console mode - Current user's Claude Code usage only

- **monitor.py**: Main orchestration
  - Dual-mode support with automatic detection
  - Mode-specific polling: 30s (Code) / 5min (Console)
  - Entry point

## Key Features

### Code Mode
- **OAuth Authentication**: Claude Code OAuth tokens for usage/profile data
- **5-Hour Limit Tracking**: Real-time utilization percentage and reset countdown
- **7-Day Limit Tracking**: Extended rate limit when active
- **Polling**: Every 30 seconds

### Console Mode
- **Admin API Key**: Environment variable or credentials file
- **Mode Detection**: Automatic based on Admin API key presence
- **Current User Claude Code Usage Only**: Personal usage tracking via `/v1/organizations/usage_report/claude_code` endpoint
  - Day-by-day aggregation of costs by user email
  - Current user identification via system username matching or OAuth profile
  - Displays "Your Claude Code Usage: $X.XX" for current user only
  - **NOT organization-wide** - only your personal costs
- **MTD Tracking**: Month-to-date personal spending
- **EOM Projections**: End-of-month cost forecasting based on progressive window rate calculation
- **Error Display**: Rate limits and API errors shown prominently
- **Polling**: Every 5 minutes (respects Admin API rate limits)

## Data Flow

### Code Mode
1. OAuth token → usage/profile APIs
2. Usage data displayed with 5-hour and 7-day limits
3. Updates every 30 seconds

### Console Mode
1. Admin API key → organization and usage APIs
2. MTD date ranges calculated automatically
3. Per-user Claude Code usage fetched via day-by-day parallel iteration
4. Current user email identified via system username or OAuth profile
5. ONLY current user's cost displayed (not organization-wide)
6. Progressive window rate calculation for EOM projections
7. Updates every 5 minutes
8. Errors displayed with red border and warning messages

## Technologies

- **Rich**: Terminal UI with progress bars and live updates
- **SQLite**: Local usage history storage
- **Requests**: HTTP client for API calls
- **Python 3.6+**: Core language
