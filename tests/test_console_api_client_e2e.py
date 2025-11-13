"""E2E tests for ConsoleAPIClient using real ANTHROPIC_ADMIN_API_KEY"""

import unittest
import os
from claude_usage.api import ConsoleAPIClient


class TestConsoleAPIClientE2E(unittest.TestCase):
    """End-to-end tests against real Console API"""

    def setUp(self):
        """Set up test fixtures"""
        self.admin_key = os.environ.get("ANTHROPIC_ADMIN_API_KEY")
        if not self.admin_key:
            self.skipTest("ANTHROPIC_ADMIN_API_KEY environment variable not set")

    def test_fetch_organization_real_api(self):
        """Test fetch_organization against real Console API"""
        client = ConsoleAPIClient(self.admin_key)

        result, error = client.fetch_organization()

        # Should succeed with real API key
        self.assertIsNone(error, f"API call failed with error: {error}")
        self.assertIsNotNone(result)
        self.assertIn("id", result)


if __name__ == "__main__":
    unittest.main()
