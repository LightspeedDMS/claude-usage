"""Tests for ConsoleAPIClient - Anthropic Console API integration"""

import unittest
from datetime import date
from unittest.mock import patch, Mock
from claude_usage.api import ConsoleAPIClient


class TestConsoleAPIClientInit(unittest.TestCase):
    """Test cases for ConsoleAPIClient initialization"""

    def test_init_stores_admin_key(self):
        """Test that __init__ stores the admin API key"""
        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        self.assertEqual(client.admin_key, admin_key)

    def test_init_sets_base_url(self):
        """Test that __init__ sets the correct base URL"""
        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        self.assertEqual(client.base_url, "https://api.anthropic.com")


class TestConsoleAPIClientHeaders(unittest.TestCase):
    """Test cases for ConsoleAPIClient header generation"""

    def test_get_headers_returns_required_headers(self):
        """Test that _get_headers returns all required Console API headers"""
        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        headers = client._get_headers()

        self.assertIn("x-api-key", headers)
        self.assertIn("anthropic-version", headers)
        self.assertIn("Content-Type", headers)
        self.assertEqual(headers["x-api-key"], admin_key)
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["Content-Type"], "application/json")


class TestConsoleAPIClientDateHelpers(unittest.TestCase):
    """Test cases for date range calculation helpers"""

    @patch("claude_usage.api.date")
    def test_calculate_mtd_range_returns_month_to_date_range(self, mock_date):
        """Test that _calculate_mtd_range returns correct month-to-date range"""
        # Mock today's date as November 12, 2025
        mock_date.today.return_value = date(2025, 11, 12)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        starting_at, ending_at = client._calculate_mtd_range()

        self.assertEqual(starting_at, "2025-11-01")
        self.assertEqual(ending_at, "2025-11-12")


class TestConsoleAPIClientFetchOrganization(unittest.TestCase):
    """Test cases for fetch_organization method"""

    @patch("claude_usage.api.requests.get")
    def test_fetch_organization_success(self, mock_get):
        """Test that fetch_organization returns org data on success"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "org_123", "name": "Test Organization"}
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_organization()

        # Verify correct endpoint was called
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertEqual(
            call_args[0][0], "https://api.anthropic.com/v1/organizations/me"
        )

        # Verify headers were set correctly
        headers = call_args[1]["headers"]
        self.assertEqual(headers["x-api-key"], admin_key)
        self.assertEqual(headers["anthropic-version"], "2023-06-01")

        # Verify result
        self.assertEqual(result["id"], "org_123")
        self.assertIsNone(error)


class TestConsoleAPIClientPagination(unittest.TestCase):
    """Test cases for pagination handling"""

    @patch("claude_usage.api.requests.get")
    def test_handle_pagination_single_page(self, mock_get):
        """Test _handle_pagination with single page response"""
        # Mock single page response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": 1}, {"id": 2}],
            "has_more": False,
        }
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client._handle_pagination(
            "https://api.anthropic.com/v1/test", {}, client._get_headers()
        )

        # Should only call once
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(len(result), 2)
        self.assertIsNone(error)

    @patch("claude_usage.api.requests.get")
    def test_handle_pagination_multiple_pages(self, mock_get):
        """Test _handle_pagination with multiple pages"""
        # Mock two-page response
        page1_response = Mock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "data": [{"id": 1}, {"id": 2}],
            "has_more": True,
            "next_page_token": "token_123",
        }

        page2_response = Mock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            "data": [{"id": 3}, {"id": 4}],
            "has_more": False,
        }

        mock_get.side_effect = [page1_response, page2_response]

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client._handle_pagination(
            "https://api.anthropic.com/v1/test", {}, client._get_headers()
        )

        # Should call twice
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(result), 4)
        self.assertIsNone(error)


class TestConsoleAPIClientFetchWorkspaces(unittest.TestCase):
    """Test cases for fetch_workspaces method"""

    @patch("claude_usage.api.ConsoleAPIClient._handle_pagination")
    def test_fetch_workspaces_success(self, mock_pagination):
        """Test that fetch_workspaces returns workspaces list on success"""
        mock_pagination.return_value = (
            [
                {"id": "ws_1", "name": "Workspace 1"},
                {"id": "ws_2", "name": "Workspace 2"},
            ],
            None,
        )

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_workspaces()

        # Verify pagination was called with correct endpoint
        mock_pagination.assert_called_once()
        call_args = mock_pagination.call_args[0]
        self.assertIn("/v1/organizations/workspaces", call_args[0])

        self.assertEqual(len(result), 2)
        self.assertIsNone(error)


class TestConsoleAPIClientFetchUsageReport(unittest.TestCase):
    """Test cases for fetch_usage_report method"""

    @patch("claude_usage.api.ConsoleAPIClient._handle_pagination")
    def test_fetch_usage_report_success(self, mock_pagination):
        """Test that fetch_usage_report returns aggregated usage data on success"""
        # Mock pagination returns raw API response
        raw_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_creation_input_tokens": 10,
                        "cache_read_input_tokens": 20,
                    }
                ],
            }
        ]
        mock_pagination.return_value = (raw_data, None)

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_usage_report("2025-01-01", "2025-01-31")

        # Verify pagination was called with correct endpoint and params
        mock_pagination.assert_called_once()
        call_args = mock_pagination.call_args[0]
        self.assertIn("/v1/organizations/usage_report/messages", call_args[0])

        # Verify date parameters
        params = call_args[1]
        self.assertEqual(params["starting_at"], "2025-01-01")
        self.assertEqual(params["ending_at"], "2025-01-31")

        # Verify result is aggregated dict, not raw list
        self.assertIsInstance(result, dict)
        self.assertIn("by_model", result)
        self.assertIsNone(error)


class TestConsoleAPIClientFetchCostReport(unittest.TestCase):
    """Test cases for fetch_cost_report method"""

    @patch("claude_usage.api.ConsoleAPIClient._handle_pagination")
    def test_fetch_cost_report_success(self, mock_pagination):
        """Test that fetch_cost_report returns aggregated cost data on success"""
        # Mock pagination returns raw API response
        raw_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [{"currency": "USD", "amount": "10.50"}],
            }
        ]
        mock_pagination.return_value = (raw_data, None)

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_cost_report("2025-01-01", "2025-01-31")

        # Verify pagination was called with correct endpoint
        mock_pagination.assert_called_once()
        call_args = mock_pagination.call_args[0]
        self.assertIn("/v1/organizations/cost_report", call_args[0])

        # Verify result is aggregated dict, not raw list
        self.assertIsInstance(result, dict)
        self.assertIn("total_cost_usd", result)
        self.assertEqual(result["total_cost_usd"], 10.50)
        self.assertIsNone(error)


class TestConsoleAPIClientFetchClaudeCodeAnalytics(unittest.TestCase):
    """Test cases for fetch_claude_code_analytics method"""

    @patch("claude_usage.api.requests.get")
    def test_fetch_claude_code_analytics_returns_none_on_404(self, mock_get):
        """Test that fetch_claude_code_analytics returns None with error on 404"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        admin_key = "sk-ant-admin-test-key-12345"
        client = ConsoleAPIClient(admin_key)

        result, error = client.fetch_claude_code_analytics(
            "2025-01-01",
            "2025-01-31",
            session_key="test-session-key",
            org_uuid="test-org-uuid",
        )

        self.assertIsNone(result)
        self.assertEqual(error, "API error: 404")


if __name__ == "__main__":
    unittest.main()
