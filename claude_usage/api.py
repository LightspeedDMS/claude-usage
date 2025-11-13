"""API client for Claude Code usage monitoring"""

import requests
from datetime import date


class ConsoleAPIClient:
    """Client for Anthropic Console API endpoints"""

    def __init__(self, admin_key):
        self.admin_key = admin_key
        self.base_url = "https://api.anthropic.com"
        self._current_user_email_cache = None

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

    def _extract_console_cookies(self, session_key):
        """Extract all console.anthropic.com cookies from Firefox

        The Console API requires multiple cookies including Cloudflare tokens.
        """
        import sqlite3
        import tempfile
        import shutil
        from pathlib import Path

        cookies_dict = {"sessionKey": session_key}

        try:
            # Find Firefox profile
            firefox_dir = Path.home() / ".mozilla" / "firefox"
            profiles = list(firefox_dir.glob("*.default*"))
            if not profiles:
                return cookies_dict

            profile = profiles[0]
            cookies_db = profile / "cookies.sqlite"

            # Copy to temp file (Firefox locks the original)
            temp_db = tempfile.mktemp(suffix=".sqlite")
            shutil.copy2(cookies_db, temp_db)

            try:
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT name, value FROM moz_cookies
                    WHERE host LIKE '%console.anthropic.com%'
                """
                )

                for name, value in cursor.fetchall():
                    cookies_dict[name] = value

                conn.close()
            finally:
                import os

                os.unlink(temp_db)
        except Exception:
            # If extraction fails, just use sessionKey
            pass

        return cookies_dict

    def fetch_claude_code_analytics(
        self, starting_at, ending_at, session_key=None, org_uuid=None
    ):
        """Fetch Claude Code analytics from Console API

        Requires session key from Firefox cookies to access Console API.
        Returns user-specific Claude Code usage metrics.
        """
        if not session_key:
            return None, "No session key available"

        if not org_uuid:
            return None, "Organization UUID required"

        # Console API endpoint for Claude Code metrics
        url = "https://console.anthropic.com/api/claude_code/metrics_aggs/users"

        # Convert YYYY-MM-DD to YYYY-MM-DD format for console API
        params = {
            "start_date": starting_at,
            "end_date": ending_at,
            "limit": 10,
            "offset": 0,
            "sort_by": "total_lines_accepted",
            "sort_order": "desc",
            "organization_uuid": org_uuid,
        }

        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "anthropic-client-platform": "web_console",
            "referer": "https://console.anthropic.com/claude-code",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

        # Extract all console.anthropic.com cookies from Firefox
        cookies = self._extract_console_cookies(session_key)

        try:
            response = requests.get(
                url, params=params, headers=headers, cookies=cookies, timeout=(5, 10)
            )

            if response.status_code == 401:
                return None, "Session key expired or invalid"
            elif response.status_code != 200:
                return None, f"API error: {response.status_code}"

            return response.json(), None
        except requests.exceptions.Timeout:
            return None, "Request timed out"
        except requests.exceptions.RequestException as e:
            return None, f"Network error: {e}"
        except Exception as e:
            return None, f"Failed to parse response: {e}"

    def fetch_claude_code_user_usage(self, starting_at, ending_at):
        """Fetch per-user Claude Code usage from Admin API endpoint

        The claude_code endpoint returns single day data only, so we must
        iterate day-by-day and aggregate results by user email.
        Uses parallel fetching for speed (10x faster than sequential).

        Args:
            starting_at: Start date in YYYY-MM-DD format
            ending_at: End date in YYYY-MM-DD format

        Returns:
            tuple: (dict with {"users": [{"email": str, "cost_usd": float}, ...]}, error_message)
                   or (None, error_message) on failure
        """
        from datetime import datetime, timedelta
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Parse dates
        try:
            start_date = datetime.strptime(starting_at, "%Y-%m-%d").date()
            end_date = datetime.strptime(ending_at, "%Y-%m-%d").date()
        except ValueError as e:
            return None, f"Invalid date format: {e}"

        url = f"{self.base_url}/v1/organizations/usage_report/claude_code"
        headers = self._get_headers()

        # Generate list of dates to fetch
        dates_to_fetch = []
        current_date = start_date
        while current_date <= end_date:
            dates_to_fetch.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        # Fetch all days in parallel
        def fetch_single_day(date_str):
            """Fetch data for a single day"""
            params = {"starting_at": date_str, "limit": 1000}
            day_data, error = self._handle_pagination(url, params, headers)
            return date_str, day_data, error

        # Use ThreadPoolExecutor for parallel requests (max 10 concurrent)
        user_costs = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all day fetches
            future_to_date = {
                executor.submit(fetch_single_day, date_str): date_str
                for date_str in dates_to_fetch
            }

            # Process results as they complete
            for future in as_completed(future_to_date):
                date_str, day_data, error = future.result()

                if error:
                    return None, f"Error fetching {date_str}: {error}"

                # Process day's results
                # Note: claude_code endpoint returns flat list, not wrapped in "results"
                if day_data:
                    for item in day_data:
                        if not isinstance(item, dict):
                            continue

                        # Extract user email
                        actor = item.get("actor", {})
                        email = actor.get("email_address")
                        if not email:
                            continue

                        # Extract and sum costs from model breakdown
                        model_breakdown = item.get("model_breakdown", [])
                        for model_data in model_breakdown:
                            if not isinstance(model_data, dict):
                                continue

                            # estimated_cost is {"currency": "USD", "amount": 964} where amount is in cents
                            estimated_cost = model_data.get("estimated_cost", {})
                            if isinstance(estimated_cost, dict):
                                # Real API: amount is in cents
                                cost_cents = estimated_cost.get("amount", 0)
                                try:
                                    cost_dollars = float(cost_cents) / 100.0
                                except (ValueError, TypeError):
                                    continue
                            else:
                                # Test data: direct dollar amount
                                try:
                                    cost_dollars = float(estimated_cost)
                                except (ValueError, TypeError):
                                    continue

                            # Accumulate by user email
                            if email not in user_costs:
                                user_costs[email] = 0.0
                            user_costs[email] += cost_dollars

        # Convert to list format
        users_list = [
            {"email": email, "cost_usd": cost} for email, cost in user_costs.items()
        ]

        return {"users": users_list}, None

    def get_current_user_email(self):
        """Get current user's email address from Admin API

        Uses the /v1/organizations/users endpoint to identify the current user.
        Result is cached after first successful call.

        Returns:
            tuple: (email_string, error_message) or (None, error_message) on failure
        """
        # Return cached value if available
        if self._current_user_email_cache:
            return self._current_user_email_cache, None

        url = f"{self.base_url}/v1/organizations/users"
        headers = self._get_headers()

        users_data, error = self._handle_pagination(url, {}, headers)

        if error:
            return None, error

        # Find current user
        if users_data:
            for user in users_data:
                if not isinstance(user, dict):
                    continue

                # Check if this is the current user
                if user.get("is_current_user"):
                    email = user.get("email")
                    if email:
                        # Cache the result
                        self._current_user_email_cache = email
                        return email, None

        return None, "Current user not found in organization users list"


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
