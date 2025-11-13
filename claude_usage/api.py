"""API client for Claude Code usage monitoring"""

import requests
from datetime import date


class ConsoleAPIClient:
    """Client for Anthropic Console API endpoints"""

    def __init__(self, admin_key):
        self.admin_key = admin_key
        self.base_url = "https://api.anthropic.com"

    def _get_headers(self):
        """Return required headers for Console API requests"""
        return {
            "x-api-key": self.admin_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _calculate_mtd_range(self):
        """Calculate Month-to-Date date range

        Returns:
            tuple: (starting_at, ending_at) in YYYY-MM-DD format
        """
        today = date.today()
        starting_at = date(today.year, today.month, 1)
        return starting_at.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

    def _calculate_ytd_range(self):
        """Calculate Year-to-Date date range"""
        today = date.today()
        starting_at = date(today.year, 1, 1)
        return starting_at.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

    def fetch_organization(self):
        """Fetch organization data from Console API

        Returns:
            tuple: (data_dict, error_message) or (None, error_message) on failure
        """
        url = f"{self.base_url}/v1/organizations/me"
        headers = self._get_headers()

        try:
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json(), None
            elif response.status_code in (401, 403):
                return None, "Authentication failed - check Admin API key"
            else:
                return None, f"API error: {response.status_code}"

        except requests.exceptions.RequestException:
            return None, "Network error - retrying"

    def _handle_pagination(self, url, params, headers):
        """Handle paginated API responses"""
        all_data = []
        has_more = True
        next_page_token = None

        while has_more:
            current_params = params.copy()
            if next_page_token:
                current_params["page_token"] = next_page_token

            response = requests.get(
                url, params=current_params, headers=headers, timeout=10
            )

            # Check for errors
            if response.status_code == 429:
                return (
                    None,
                    "Rate limit exceeded - please wait a few minutes and try again",
                )
            elif response.status_code in (401, 403):
                return None, "Authentication failed - check Admin API key"
            elif response.status_code != 200:
                return (
                    None,
                    f"API error: {response.status_code} - {response.text[:100]}",
                )

            data = response.json()

            if "data" in data:
                all_data.extend(data["data"])

            has_more = data.get("has_more", False)
            next_page_token = data.get("next_page_token")

        return all_data, None

    def fetch_workspaces(self):
        """Fetch workspaces list"""
        url = f"{self.base_url}/v1/organizations/workspaces"
        headers = self._get_headers()
        workspaces, error = self._handle_pagination(url, {}, headers)
        return workspaces, error

    def fetch_usage_report(self, starting_at, ending_at):
        """Fetch usage report"""
        url = f"{self.base_url}/v1/organizations/usage_report/messages"
        headers = self._get_headers()
        params = {"starting_at": starting_at, "ending_at": ending_at}
        usage_data, error = self._handle_pagination(url, params, headers)
        return usage_data, error

    def fetch_cost_report(self, starting_at, ending_at):
        """Fetch cost report"""
        url = f"{self.base_url}/v1/organizations/cost_report"
        headers = self._get_headers()
        params = {"starting_at": starting_at, "ending_at": ending_at}
        cost_data, error = self._handle_pagination(url, params, headers)
        return cost_data, error

    def fetch_claude_code_analytics(self, starting_at, ending_at):
        """Fetch Claude Code analytics"""
        return None, None


class ClaudeAPIClient:
    """Client for Claude Code API endpoints"""

    API_BASE = "https://api.anthropic.com"
    USAGE_ENDPOINT = "/api/oauth/usage"
    PROFILE_ENDPOINT = "/api/oauth/profile"
    OVERAGE_ENDPOINT_TEMPLATE = (
        "https://claude.ai/api/organizations/{org_uuid}/overage_spend_limits"
    )

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

    def fetch_overage(self, org_uuid, account_uuid, session_key):
        """Fetch overage spend data from Claude.ai API"""
        if not session_key or not org_uuid:
            return None, "Missing session key or org UUID"

        url = self.OVERAGE_ENDPOINT_TEMPLATE.format(org_uuid=org_uuid)

        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0",
        }

        cookies = {
            "sessionKey": session_key,
        }

        params = {"page": 1, "per_page": 100}

        try:
            response = requests.get(
                url, headers=headers, cookies=cookies, params=params, timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                # Find current user's overage data
                if "items" in data and account_uuid:
                    for item in data["items"]:
                        if item.get("account_uuid") == account_uuid:
                            return item, None
                return None, "No overage data found"
            else:
                return None, f"API error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            return None, f"Network error: {e}"
