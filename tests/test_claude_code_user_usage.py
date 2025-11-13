"""Tests for Claude Code per-user usage tracking in Console mode"""

import unittest
from datetime import date
from unittest.mock import patch, Mock
from claude_usage.api import ConsoleAPIClient


class TestFetchClaudeCodeUserUsage(unittest.TestCase):
    """Test cases for fetch_claude_code_user_usage method"""

    @patch("claude_usage.console_mode.api.requests.get")
    @patch("claude_usage.console_mode.api.date")
    def test_fetch_claude_code_user_usage_single_day(self, mock_date, mock_get):
        """Test fetching Claude Code usage for a single day"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock API response for single day (flat list structure)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "actor": {"email_address": "user1@example.com"},
                    "model_breakdown": [
                        {"model": "claude-sonnet-4-5", "estimated_cost": 50.25}
                    ],
                }
            ],
            "has_more": False,
        }
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_user_usage("2025-11-01", "2025-11-01")

        # Verify result format
        self.assertIsNone(error)
        self.assertIsInstance(result, dict)
        self.assertIn("users", result)
        self.assertEqual(len(result["users"]), 1)
        self.assertEqual(result["users"][0]["email"], "user1@example.com")
        self.assertEqual(result["users"][0]["cost_usd"], 50.25)

    @patch("claude_usage.console_mode.api.requests.get")
    @patch("claude_usage.console_mode.api.date")
    def test_fetch_claude_code_user_usage_multiple_days(self, mock_date, mock_get):
        """Test fetching Claude Code usage across multiple days"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock API responses for two days (flat list structure)
        responses = [
            # Day 1: 2025-11-01
            Mock(
                status_code=200,
                json=Mock(
                    return_value={
                        "data": [
                            {
                                "actor": {"email_address": "user1@example.com"},
                                "model_breakdown": [
                                    {
                                        "model": "claude-sonnet-4-5",
                                        "estimated_cost": 50.0,
                                    }
                                ],
                            }
                        ],
                        "has_more": False,
                    }
                ),
            ),
            # Day 2: 2025-11-02
            Mock(
                status_code=200,
                json=Mock(
                    return_value={
                        "data": [
                            {
                                "actor": {"email_address": "user1@example.com"},
                                "model_breakdown": [
                                    {
                                        "model": "claude-sonnet-4-5",
                                        "estimated_cost": 75.0,
                                    }
                                ],
                            }
                        ],
                        "has_more": False,
                    }
                ),
            ),
        ]
        mock_get.side_effect = responses

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_user_usage("2025-11-01", "2025-11-02")

        # Verify aggregation across days
        self.assertIsNone(error)
        self.assertEqual(len(result["users"]), 1)
        self.assertEqual(result["users"][0]["email"], "user1@example.com")
        self.assertEqual(result["users"][0]["cost_usd"], 125.0)  # 50 + 75

    @patch("claude_usage.console_mode.api.requests.get")
    @patch("claude_usage.console_mode.api.date")
    def test_fetch_claude_code_user_usage_multiple_users(self, mock_date, mock_get):
        """Test fetching Claude Code usage for multiple users"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock API response with multiple users (flat list structure)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "actor": {"email_address": "user1@example.com"},
                    "model_breakdown": [
                        {"model": "claude-sonnet-4-5", "estimated_cost": 50.0}
                    ],
                },
                {
                    "actor": {"email_address": "user2@example.com"},
                    "model_breakdown": [
                        {"model": "claude-opus-4", "estimated_cost": 100.0}
                    ],
                },
            ],
            "has_more": False,
        }
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_user_usage("2025-11-01", "2025-11-01")

        # Verify multiple users
        self.assertIsNone(error)
        self.assertEqual(len(result["users"]), 2)

        # Sort by email for consistent testing
        users_sorted = sorted(result["users"], key=lambda u: u["email"])
        self.assertEqual(users_sorted[0]["email"], "user1@example.com")
        self.assertEqual(users_sorted[0]["cost_usd"], 50.0)
        self.assertEqual(users_sorted[1]["email"], "user2@example.com")
        self.assertEqual(users_sorted[1]["cost_usd"], 100.0)

    @patch("claude_usage.console_mode.api.requests.get")
    @patch("claude_usage.console_mode.api.date")
    def test_fetch_claude_code_user_usage_handles_api_error(self, mock_date, mock_get):
        """Test error handling for API failures"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_user_usage("2025-11-01", "2025-11-01")

        # Verify error handling
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("Rate limit", error)

    @patch("claude_usage.console_mode.api.requests.get")
    @patch("claude_usage.console_mode.api.date")
    def test_fetch_claude_code_user_usage_empty_results(self, mock_date, mock_get):
        """Test handling of empty results"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock empty API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [], "has_more": False}
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_user_usage("2025-11-01", "2025-11-01")

        # Verify empty results handling
        self.assertIsNone(error)
        self.assertEqual(result["users"], [])


if __name__ == "__main__":
    unittest.main()
