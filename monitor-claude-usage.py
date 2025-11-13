#!/usr/bin/env python3
"""
Claude Code Usage Monitor

Monitors Claude Code account usage and reset time programmatically.
Similar to the /usage command in Claude Code CLI.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
import requests


class ClaudeUsageMonitor:
    """Monitor Claude Code account usage via API"""

    def __init__(self, credentials_path=None):
        """
        Initialize the usage monitor

        Args:
            credentials_path: Path to .credentials.json file
                            (default: ~/.claude/.credentials.json)
        """
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"
        else:
            credentials_path = Path(credentials_path)

        self.credentials_path = credentials_path
        self.credentials = self._load_credentials()

    def _load_credentials(self):
        """Load OAuth credentials from file"""
        try:
            with open(self.credentials_path, 'r') as f:
                data = json.load(f)

            if 'claudeAiOauth' not in data:
                raise ValueError("No claudeAiOauth section found in credentials")

            oauth = data['claudeAiOauth']

            # Check if token is expired
            expires_at = oauth.get('expiresAt', 0)
            if expires_at < (datetime.now().timestamp() * 1000):
                print("Warning: Access token appears to be expired", file=sys.stderr)
                print(f"Expired at: {datetime.fromtimestamp(expires_at/1000)}", file=sys.stderr)

            return oauth

        except FileNotFoundError:
            print(f"Error: Credentials file not found at {self.credentials_path}", file=sys.stderr)
            print("Please ensure Claude Code is properly authenticated", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in credentials file: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error loading credentials: {e}", file=sys.stderr)
            sys.exit(1)

    def _get_auth_headers(self):
        """Get authorization headers for API requests"""
        return {
            'Authorization': f'Bearer {self.credentials["accessToken"]}',
            'Content-Type': 'application/json',
            'User-Agent': 'Claude-Usage-Monitor/1.0'
        }

    def _try_endpoint(self, url, method='GET', data=None):
        """
        Try to fetch data from an endpoint

        Returns:
            tuple: (success, response_data or error_message)
        """
        try:
            headers = self._get_auth_headers()

            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=10)
            else:
                return False, f"Unsupported method: {method}"

            if response.status_code == 200:
                try:
                    return True, response.json()
                except json.JSONDecodeError:
                    return True, response.text
            else:
                return False, f"HTTP {response.status_code}: {response.text}"

        except requests.exceptions.RequestException as e:
            return False, f"Request failed: {e}"

    def fetch_usage(self):
        """
        Fetch usage data from Claude.ai API

        Tries multiple potential endpoints to find the correct one

        Returns:
            dict: Usage data if successful, None otherwise
        """
        # List of potential API endpoints to try
        endpoints = [
            'https://api.claude.ai/api/organizations/usage',
            'https://api.claude.ai/v1/usage',
            'https://claude.ai/api/organizations/usage',
            'https://claude.ai/api/usage',
            'https://api.anthropic.com/v1/usage',
            'https://claude.ai/api/account/usage',
            'https://api.claude.ai/api/account/usage',
        ]

        print("Attempting to fetch usage data...", file=sys.stderr)
        print(f"Subscription type: {self.credentials.get('subscriptionType', 'unknown')}", file=sys.stderr)
        print(f"Scopes: {', '.join(self.credentials.get('scopes', []))}", file=sys.stderr)
        print("", file=sys.stderr)

        for endpoint in endpoints:
            print(f"Trying: {endpoint}", file=sys.stderr)
            success, result = self._try_endpoint(endpoint)

            if success:
                print(f"✓ Success!", file=sys.stderr)
                print("", file=sys.stderr)
                return result
            else:
                print(f"✗ {result}", file=sys.stderr)

        print("", file=sys.stderr)
        print("Error: Could not find valid usage API endpoint", file=sys.stderr)
        print("", file=sys.stderr)
        print("Note: The API endpoint structure may have changed or may require", file=sys.stderr)
        print("additional authentication steps. You may need to inspect the", file=sys.stderr)
        print("Claude Code CLI network traffic to determine the correct endpoint.", file=sys.stderr)

        return None

    def format_usage_output(self, usage_data):
        """
        Format usage data for display (similar to /usage command)

        Args:
            usage_data: Raw usage data from API

        Returns:
            str: Formatted usage information
        """
        # This will need to be adjusted based on actual API response structure
        # For now, just pretty-print the JSON
        return json.dumps(usage_data, indent=2)

    def display_credentials_info(self):
        """Display information about loaded credentials"""
        print("Claude Code Credentials Information")
        print("=" * 50)
        print(f"Credentials file: {self.credentials_path}")
        print(f"Subscription type: {self.credentials.get('subscriptionType', 'unknown')}")
        print(f"Scopes: {', '.join(self.credentials.get('scopes', []))}")

        expires_at = self.credentials.get('expiresAt', 0)
        expires_dt = datetime.fromtimestamp(expires_at / 1000)
        now = datetime.now()

        print(f"Token expires at: {expires_dt}")

        if expires_dt > now:
            time_left = expires_dt - now
            days = time_left.days
            hours = time_left.seconds // 3600
            print(f"Token valid for: {days} days, {hours} hours")
        else:
            print("⚠️  Token is EXPIRED")

        print("")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Monitor Claude Code account usage and reset time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Fetch and display usage data
  %(prog)s --info             # Show credentials information only
  %(prog)s --credentials PATH # Use custom credentials file
        """
    )

    parser.add_argument(
        '--credentials',
        type=str,
        help='Path to credentials file (default: ~/.claude/.credentials.json)'
    )

    parser.add_argument(
        '--info',
        action='store_true',
        help='Show credentials information only (no API call)'
    )

    parser.add_argument(
        '--json',
        action='store_true',
        help='Output raw JSON response'
    )

    args = parser.parse_args()

    # Initialize monitor
    monitor = ClaudeUsageMonitor(credentials_path=args.credentials)

    # Show info mode
    if args.info:
        monitor.display_credentials_info()
        return 0

    # Fetch usage data
    usage_data = monitor.fetch_usage()

    if usage_data is None:
        return 1

    # Display results
    print("=" * 50)
    print("Claude Code Usage Data")
    print("=" * 50)

    if args.json:
        print(json.dumps(usage_data, indent=2))
    else:
        print(monitor.format_usage_output(usage_data))

    return 0


if __name__ == '__main__':
    sys.exit(main())
