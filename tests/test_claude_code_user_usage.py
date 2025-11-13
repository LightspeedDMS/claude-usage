"""Tests for Claude Code per-user usage tracking in Console mode"""

import unittest
from datetime import date
from unittest.mock import patch, Mock
from claude_usage.api import ConsoleAPIClient


class TestFetchClaudeCodeUserUsage(unittest.TestCase):
    """Test cases for fetch_claude_code_user_usage method"""

    @patch("claude_usage.api.requests.get")
    @patch("claude_usage.api.date")
    def test_fetch_claude_code_user_usage_single_day(self, mock_date, mock_get):
        """Test fetching Claude Code usage for a single day"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock API response for single day
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "starting_at": "2025-11-01",
                    "ending_at": "2025-11-01",
                    "results": [
                        {
                            "actor": {"email_address": "user1@example.com"},
                            "model_breakdown": [
                                {"model": "claude-sonnet-4-5", "estimated_cost": 50.25}
                            ],
                        }
                    ],
                }
            ],
            "has_more": False,
        }
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_user_usage(
            "2025-11-01", "2025-11-01"
        )

        # Verify result format
        self.assertIsNone(error)
        self.assertIsInstance(result, dict)
        self.assertIn("users", result)
        self.assertEqual(len(result["users"]), 1)
        self.assertEqual(result["users"][0]["email"], "user1@example.com")
        self.assertEqual(result["users"][0]["cost_usd"], 50.25)

    @patch("claude_usage.api.requests.get")
    @patch("claude_usage.api.date")
    def test_fetch_claude_code_user_usage_multiple_days(self, mock_date, mock_get):
        """Test fetching Claude Code usage across multiple days"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock API responses for two days
        responses = [
            # Day 1: 2025-11-01
            Mock(
                status_code=200,
                json=Mock(
                    return_value={
                        "data": [
                            {
                                "starting_at": "2025-11-01",
                                "ending_at": "2025-11-01",
                                "results": [
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
                                "starting_at": "2025-11-02",
                                "ending_at": "2025-11-02",
                                "results": [
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

        result, error = client.fetch_claude_code_user_usage(
            "2025-11-01", "2025-11-02"
        )

        # Verify aggregation across days
        self.assertIsNone(error)
        self.assertEqual(len(result["users"]), 1)
        self.assertEqual(result["users"][0]["email"], "user1@example.com")
        self.assertEqual(result["users"][0]["cost_usd"], 125.0)  # 50 + 75

    @patch("claude_usage.api.requests.get")
    @patch("claude_usage.api.date")
    def test_fetch_claude_code_user_usage_multiple_users(self, mock_date, mock_get):
        """Test fetching Claude Code usage for multiple users"""
        # Mock date to ensure deterministic behavior
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        # Mock API response with multiple users
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "starting_at": "2025-11-01",
                    "ending_at": "2025-11-01",
                    "results": [
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
                }
            ],
            "has_more": False,
        }
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_user_usage(
            "2025-11-01", "2025-11-01"
        )

        # Verify multiple users
        self.assertIsNone(error)
        self.assertEqual(len(result["users"]), 2)

        # Sort by email for consistent testing
        users_sorted = sorted(result["users"], key=lambda u: u["email"])
        self.assertEqual(users_sorted[0]["email"], "user1@example.com")
        self.assertEqual(users_sorted[0]["cost_usd"], 50.0)
        self.assertEqual(users_sorted[1]["email"], "user2@example.com")
        self.assertEqual(users_sorted[1]["cost_usd"], 100.0)

    @patch("claude_usage.api.requests.get")
    @patch("claude_usage.api.date")
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

        result, error = client.fetch_claude_code_user_usage(
            "2025-11-01", "2025-11-01"
        )

        # Verify error handling
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("Rate limit", error)

    @patch("claude_usage.api.requests.get")
    @patch("claude_usage.api.date")
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

        result, error = client.fetch_claude_code_user_usage(
            "2025-11-01", "2025-11-01"
        )

        # Verify empty results handling
        self.assertIsNone(error)
        self.assertEqual(result["users"], [])


class TestGetCurrentUserEmail(unittest.TestCase):
    """Test cases for get_current_user_email method"""

    @patch("claude_usage.api.ConsoleAPIClient._handle_pagination")
    def test_get_current_user_email_success(self, mock_pagination):
        """Test successful retrieval of current user email"""
        # Mock users list from API
        mock_pagination.return_value = (
            [
                {
                    "id": "user_1",
                    "email": "user1@example.com",
                    "role": "owner",
                    "is_current_user": True,
                },
                {
                    "id": "user_2",
                    "email": "user2@example.com",
                    "role": "member",
                    "is_current_user": False,
                },
            ],
            None,
        )

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        email, error = client.get_current_user_email()

        # Verify current user identified
        self.assertIsNone(error)
        self.assertEqual(email, "user1@example.com")

    @patch("claude_usage.api.ConsoleAPIClient._handle_pagination")
    def test_get_current_user_email_caches_result(self, mock_pagination):
        """Test that current user email is cached after first call"""
        # Mock users list from API
        mock_pagination.return_value = (
            [
                {
                    "id": "user_1",
                    "email": "user1@example.com",
                    "role": "owner",
                    "is_current_user": True,
                }
            ],
            None,
        )

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        # First call
        email1, _ = client.get_current_user_email()

        # Second call should use cache
        email2, _ = client.get_current_user_email()

        # Verify pagination only called once (cached on second call)
        self.assertEqual(mock_pagination.call_count, 1)
        self.assertEqual(email1, "user1@example.com")
        self.assertEqual(email2, "user1@example.com")

    @patch("claude_usage.api.ConsoleAPIClient._handle_pagination")
    def test_get_current_user_email_handles_api_error(self, mock_pagination):
        """Test error handling when API fails"""
        # Mock API error
        mock_pagination.return_value = (None, "Authentication failed")

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        email, error = client.get_current_user_email()

        # Verify error handling
        self.assertIsNone(email)
        self.assertEqual(error, "Authentication failed")

    @patch("claude_usage.api.ConsoleAPIClient._handle_pagination")
    def test_get_current_user_email_no_current_user_found(self, mock_pagination):
        """Test handling when no current user is marked"""
        # Mock users list without current user flag
        mock_pagination.return_value = (
            [
                {
                    "id": "user_1",
                    "email": "user1@example.com",
                    "role": "member",
                    "is_current_user": False,
                }
            ],
            None,
        )

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        email, error = client.get_current_user_email()

        # Verify appropriate error
        self.assertIsNone(email)
        self.assertIn("Current user not found", error)


if __name__ == "__main__":
    unittest.main()
