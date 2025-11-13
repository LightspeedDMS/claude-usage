"""API client for Claude Code usage monitoring"""

import requests


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
        """Fetch overage spend data from Claude.ai API

        WARNING: This endpoint is currently blocked by Cloudflare bot protection.
        Anthropic has enabled advanced bot detection that prevents programmatic access.
        This method is kept for reference but will consistently return 403 Forbidden.

        Disabled by default in CodeMonitor.fetch_overage() to avoid spamming
        failed API requests.
        """
        if not session_key or not org_uuid:
            return None, "Missing session key or org UUID"

        url = self.OVERAGE_ENDPOINT_TEMPLATE.format(org_uuid=org_uuid)

        # Extract all claude.ai cookies from Firefox (includes Cloudflare tokens)
        cookies = self._extract_claude_cookies(session_key)

        # Extract Anthropic-specific values from cookies
        anthropic_device_id = cookies.get("anthropic-device-id", "")
        ajs_anonymous_id = cookies.get("ajs_anonymous_id", "")

        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "referer": "https://claude.ai/admin-settings/usage",
            "anthropic-client-sha": "10e111d9b6974eaf6e21cfd99ea3009a4aaf95c2",
            "anthropic-client-version": "1.0.0",
            "anthropic-client-platform": "web_claude_ai",
            "anthropic-anonymous-id": ajs_anonymous_id,
            "anthropic-device-id": anthropic_device_id,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
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

    def _extract_claude_cookies(self, session_key):
        """Extract all claude.ai cookies from Firefox

        The Claude.ai API requires multiple cookies including Cloudflare tokens.
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
                    WHERE host LIKE '%claude.ai%'
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
