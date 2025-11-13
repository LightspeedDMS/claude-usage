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
        next_page = None
        page_param_key = None  # Will be determined from first response

        while has_more:
            current_params = params.copy()
            if next_page:
                # Use the appropriate page parameter key
                if page_param_key:
                    current_params[page_param_key] = next_page

            try:
                response = requests.get(
                    url, params=current_params, headers=headers, timeout=(5, 10)
                )
            except requests.exceptions.Timeout:
                return None, "Request timed out"
            except requests.exceptions.RequestException as e:
                return None, f"Network error: {e}"

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

            try:
                data = response.json()
            except Exception as e:
                return None, f"Failed to parse JSON response: {e}"

            if "data" in data:
                all_data.extend(data["data"])

            # Check for pagination - different endpoints use different keys
            has_more = data.get("has_more", False)

            # Determine which pagination style is used
            if "next_page_token" in data:
                next_page = data.get("next_page_token")
                page_param_key = "page_token"
            elif "next_page" in data:
                next_page = data.get("next_page")
                page_param_key = "page"
            else:
                next_page = None

            # If has_more is True but there's no next page token, break to avoid infinite loop
            if has_more and not next_page:
                has_more = False

        return all_data, None

    def fetch_workspaces(self):
        """Fetch workspaces list"""
        url = f"{self.base_url}/v1/organizations/workspaces"
        headers = self._get_headers()
        workspaces, error = self._handle_pagination(url, {}, headers)
        return workspaces, error

    def aggregate_cost_data(self, cost_data):
        """Aggregate cost report data from list of daily items into summary dict

        Args:
            cost_data: List of cost items from API, each with structure:
                {
                    "starting_at": "...",
                    "ending_at": "...",
                    "results": [{"currency": "USD", "amount": "123.45"}, ...]
                }

        Returns:
            dict: Aggregated cost data with structure:
                {"total_cost_usd": 123.45}
        """
        if not cost_data:
            return {"total_cost_usd": 0}

        total_cost = 0.0

        for item in cost_data:
            if not isinstance(item, dict):
                continue

            results = item.get("results", [])
            if not results:
                continue

            for result in results:
                if not isinstance(result, dict):
                    continue

                # Only process USD currency
                if result.get("currency") != "USD":
                    continue

                # Parse amount safely
                try:
                    amount_str = result.get("amount", "0")
                    total_cost += float(amount_str)
                except (ValueError, TypeError):
                    # Skip invalid amounts
                    continue

        return {"total_cost_usd": total_cost}

    def aggregate_usage_data(self, usage_data):
        """Aggregate usage report data from list of daily items into summary dict

        Args:
            usage_data: List of usage items from API, each with structure:
                {
                    "starting_at": "...",
                    "ending_at": "...",
                    "results": [
                        {
                            "model": "claude-sonnet-4-5-20250929",
                            "input_tokens": 10000,
                            "output_tokens": 5000,
                            "cache_creation_input_tokens": 1000,
                            "cache_read_input_tokens": 2000
                        },
                        ...
                    ]
                }

        Returns:
            dict: Aggregated usage data with structure:
                {
                    "by_model": {
                        "model_name": {
                            "input_tokens": 123,
                            "output_tokens": 456,
                            "cache_creation_input_tokens": 78,
                            "cache_read_input_tokens": 90
                        },
                        ...
                    }
                }
        """
        if not usage_data:
            return {"by_model": {}}

        by_model = {}

        for item in usage_data:
            if not isinstance(item, dict):
                continue

            results = item.get("results", [])
            if not results:
                continue

            for result in results:
                if not isinstance(result, dict):
                    continue

                model = result.get("model")
                if not model:
                    continue

                # Initialize model entry if not exists
                if model not in by_model:
                    by_model[model] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    }

                # Accumulate token counts
                by_model[model]["input_tokens"] += result.get("input_tokens", 0)
                by_model[model]["output_tokens"] += result.get("output_tokens", 0)
                by_model[model]["cache_creation_input_tokens"] += result.get(
                    "cache_creation_input_tokens", 0
                )
                by_model[model]["cache_read_input_tokens"] += result.get(
                    "cache_read_input_tokens", 0
                )

        return {"by_model": by_model}

    def fetch_usage_report(self, starting_at, ending_at):
        """Fetch usage report and return aggregated data

        Returns:
            tuple: (aggregated_dict, error_message) or (None, error_message) on failure
        """
        url = f"{self.base_url}/v1/organizations/usage_report/messages"
        headers = self._get_headers()
        params = {"starting_at": starting_at, "ending_at": ending_at}
        usage_data, error = self._handle_pagination(url, params, headers)

        if error:
            return None, error

        # Aggregate the raw list data into summary dict
        aggregated = self.aggregate_usage_data(usage_data)
        return aggregated, None

    def fetch_cost_report(self, starting_at, ending_at):
        """Fetch cost report and return aggregated data

        Returns:
            tuple: (aggregated_dict, error_message) or (None, error_message) on failure
        """
        url = f"{self.base_url}/v1/organizations/cost_report"
        headers = self._get_headers()
        params = {"starting_at": starting_at, "ending_at": ending_at}
        cost_data, error = self._handle_pagination(url, params, headers)

        if error:
            return None, error

        # Aggregate the raw list data into summary dict
        aggregated = self.aggregate_cost_data(cost_data)
        return aggregated, None

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
