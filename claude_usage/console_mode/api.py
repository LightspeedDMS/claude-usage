"""API client for Anthropic Console usage monitoring"""

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
                {"total_cost_usd": 123.45, "period_label": "November 2025"}
        """
        if not cost_data:
            return {"total_cost_usd": 0, "period_label": ""}

        total_cost = 0.0
        period_label = ""

        # Extract period label from first item (all items should be same month for MTD)
        if cost_data and isinstance(cost_data[0], dict):
            starting_at = cost_data[0].get("starting_at", "")
            if starting_at:
                try:
                    from datetime import datetime

                    # Handle both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SSZ" formats
                    if "T" in starting_at:
                        # ISO format with time: 2025-11-01T00:00:00Z
                        start_date = datetime.fromisoformat(
                            starting_at.replace("Z", "+00:00")
                        )
                    else:
                        # Simple date format: 2025-11-01
                        start_date = datetime.strptime(starting_at, "%Y-%m-%d")

                    period_label = start_date.strftime("%B %Y")  # e.g., "November 2025"
                except (ValueError, AttributeError):
                    period_label = ""

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

        return {"total_cost_usd": total_cost, "period_label": period_label}

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
