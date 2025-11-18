"""API client for Claude Code usage monitoring"""

import requests


class ClaudeAPIClient:
    """Client for Claude Code API endpoints"""

    API_BASE = "https://api.anthropic.com"
    USAGE_ENDPOINT = "/api/oauth/usage"
    PROFILE_ENDPOINT = "/api/oauth/profile"

    def fetch_usage(self, auth_headers):
        """Fetch current usage data from Claude Code API"""
        if not auth_headers:
            return None, "No authentication headers"

        url = f"{self.API_BASE}{self.USAGE_ENDPOINT}"

        try:
            response = requests.get(url, headers=auth_headers, timeout=10)

            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 401:
                return None, "Token expired. Run 'claude' to refresh."
            else:
                return None, f"API error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            return None, f"Network error: {e}"

    def fetch_profile(self, auth_headers):
        """Fetch profile data from Claude Code API"""
        if not auth_headers:
            return None, "No authentication headers"

        url = f"{self.API_BASE}{self.PROFILE_ENDPOINT}"

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

                return profile_data, org_uuid, account_uuid, None
            else:
                return None, None, None, f"API error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            return None, None, None, f"Network error: {e}"
