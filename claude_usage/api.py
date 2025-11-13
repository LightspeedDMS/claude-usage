"""API client for Claude Code usage monitoring"""

import requests


class ClaudeAPIClient:
    """Client for Claude Code API endpoints"""

    API_BASE = "https://api.anthropic.com"
    USAGE_ENDPOINT = "/api/oauth/usage"
    PROFILE_ENDPOINT = "/api/oauth/profile"
    OVERAGE_ENDPOINT_TEMPLATE = "https://claude.ai/api/organizations/{org_uuid}/overage_spend_limits"

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
                    org = profile_data.get('organization', {})
                    account = profile_data.get('account', {})
                    org_uuid = org.get('uuid')
                    account_uuid = account.get('uuid')

                return profile_data, org_uuid, account_uuid, None
            else:
                return None, None, None, f"API error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            return None, None, None, f"Network error: {e}"

    def fetch_overage(self, org_uuid, account_uuid, session_key):
        """Fetch overage spend data from Claude.ai API"""
        if not session_key or not org_uuid:
            return None, "Missing session key or org UUID"

        url = self.OVERAGE_ENDPOINT_TEMPLATE.format(org_uuid=org_uuid)

        headers = {
            'accept': '*/*',
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0',
        }

        cookies = {
            'sessionKey': session_key,
        }

        params = {
            'page': 1,
            'per_page': 100
        }

        try:
            response = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                # Find current user's overage data
                if 'items' in data and account_uuid:
                    for item in data['items']:
                        if item.get('account_uuid') == account_uuid:
                            return item, None
                return None, "No overage data found"
            else:
                return None, f"API error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            return None, f"Network error: {e}"
