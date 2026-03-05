"""API client for Claude Code usage monitoring"""

import random
import time
import requests


class ClaudeAPIClient:
    """Client for Claude Code API endpoints"""

    API_BASE = "https://api.anthropic.com"
    USAGE_ENDPOINT = "/api/oauth/usage"
    PROFILE_ENDPOINT = "/api/oauth/profile"

    # Backoff formula: min(300 * 2^consecutive_429s, 3600) — same as pace-maker
    _BACKOFF_BASE = 300
    _BACKOFF_MAX = 3600

    def __init__(self):
        self._consecutive_429s = 0
        self._backoff_until = 0.0

    def is_in_backoff(self) -> bool:
        """Return True if currently in exponential backoff period."""
        return time.time() < self._backoff_until

    def _record_429(self):
        """Record a 429 failure and compute next backoff duration.

        Formula: min(300 * 2^consecutive_429s, 3600) — identical to pace-maker.
        consecutive_429s is read BEFORE incrementing so first backoff is 300s (5min).
        """
        duration = min(
            self._BACKOFF_BASE * (2**self._consecutive_429s), self._BACKOFF_MAX
        )
        self._backoff_until = time.time() + duration
        self._consecutive_429s += 1

    def _record_success(self):
        """Reset backoff state after a successful API call."""
        self._consecutive_429s = 0
        self._backoff_until = 0.0

    def get_backoff_remaining_seconds(self) -> float:
        """Return seconds remaining in current backoff, or 0 if not in backoff."""
        remaining = self._backoff_until - time.time()
        return max(remaining, 0.0)

    def fetch_usage(self, auth_headers):
        """Fetch current usage data from Claude Code API"""
        if not auth_headers:
            return None, "No authentication headers"

        if self.is_in_backoff():
            remaining = self.get_backoff_remaining_seconds()
            return None, f"API backoff: {remaining:.0f}s remaining"

        url = f"{self.API_BASE}{self.USAGE_ENDPOINT}"

        for attempt in range(3):
            try:
                response = requests.get(url, headers=auth_headers, timeout=10)

                if response.status_code == 200:
                    self._record_success()
                    return response.json(), None
                elif response.status_code == 429:
                    if attempt < 2:
                        delay = 4 * (2**attempt) + random.uniform(0, 2)
                        time.sleep(delay)
                        continue
                    # Last attempt exhausted — record persistent backoff
                    self._record_429()
                    return None, "API rate limited (429) after retries"
                elif response.status_code == 401:
                    return None, "Token expired. Run 'claude' to refresh."
                else:
                    return None, f"API error: {response.status_code}"

            except requests.exceptions.RequestException as e:
                return None, f"Network error: {e}"

        return None, "API rate limited (429) after retries"

    def fetch_profile(self, auth_headers):
        """Fetch profile data from Claude Code API"""
        if not auth_headers:
            return None, None, None, "No authentication headers"

        if self.is_in_backoff():
            remaining = self.get_backoff_remaining_seconds()
            return None, None, None, f"API backoff: {remaining:.0f}s remaining"

        url = f"{self.API_BASE}{self.PROFILE_ENDPOINT}"

        for attempt in range(3):
            try:
                response = requests.get(url, headers=auth_headers, timeout=10)

                if response.status_code == 200:
                    profile_data = response.json()

                    # Extract org and account UUIDs
                    org_uuid = None
                    account_uuid = None
                    if profile_data:
                        org = profile_data.get("organization", {})
                        account = profile_data.get("account", {})
                        org_uuid = org.get("uuid")
                        account_uuid = account.get("uuid")

                    self._record_success()
                    return profile_data, org_uuid, account_uuid, None
                elif response.status_code == 429:
                    if attempt < 2:
                        delay = 4 * (2**attempt) + random.uniform(0, 2)
                        time.sleep(delay)
                        continue
                    self._record_429()
                    return None, None, None, "API rate limited (429) after retries"
                else:
                    return None, None, None, f"API error: {response.status_code}"

            except requests.exceptions.RequestException as e:
                return None, None, None, f"Network error: {e}"

        return None, None, None, "API rate limited (429) after retries"
