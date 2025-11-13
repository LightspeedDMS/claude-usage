# Claude Usage Monitor

## Overview

Live-updating terminal dashboard for monitoring Claude Code account usage and overage spending. Displays 5-hour rate limits, monthly overage accumulation, and projects overage costs to next reset using historical rate calculation.

## Architecture

**Modular design with 5 components:**

- **auth.py**: Authentication management
  - `OAuthManager`: Claude Code OAuth tokens
  - `FirefoxSessionManager`: Browser session key extraction

- **api.py**: API client wrapper
  - `ClaudeAPIClient`: Usage, profile, and overage endpoints

- **storage.py**: Database and analytics
  - `UsageStorage`: SQLite operations, snapshot storage
  - `UsageAnalytics`: Rate calculation and projections

- **display.py**: UI rendering
  - `UsageRenderer`: Rich library formatting and display logic

- **monitor.py**: Main orchestration
  - Coordinates all modules
  - Main polling loop (30-second intervals)
  - Entry point

## Key Features

- **Dual authentication**: OAuth (usage/profile) + Firefox session (overage)
- **Monthly overage tracking**: Cumulative, shows even when not actively accruing
- **Projection system**: Calculates spending rate from 30-minute history window
- **Smart display**: Only shows rate/projection when utilization >= 100%
- **Auto-refresh**: Firefox session key refreshed every 5 minutes

## Data Flow

1. OAuth token → usage/profile APIs
2. Firefox cookies → overage API
3. Snapshots stored to `~/.claude-usage/usage_history.db` every 30s
4. Rate calculated from last 30 minutes of snapshots
5. Projection = current + (rate × hours_until_reset)

## Technologies

- **Rich**: Terminal UI with progress bars and live updates
- **SQLite**: Local usage history storage
- **Requests**: HTTP client for API calls
- **Python 3.6+**: Core language
# Test
