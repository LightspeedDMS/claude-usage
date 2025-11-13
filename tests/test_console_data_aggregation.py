"""Tests for Console API data aggregation logic"""

import unittest
from claude_usage.api import ConsoleAPIClient


class TestCostDataAggregation(unittest.TestCase):
    """Test cases for aggregating cost report data"""

    def setUp(self):
        """Set up test fixtures"""
        self.admin_key = "sk-ant-admin-test-key-12345"
        self.client = ConsoleAPIClient(self.admin_key)

    def test_aggregate_cost_data_single_day(self):
        """Test aggregating cost data from single day response"""
        # Mock API response with single day
        cost_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {
                        "currency": "USD",
                        "amount": "125.45",
                    }
                ],
            }
        ]

        result = self.client.aggregate_cost_data(cost_data)

        self.assertIsInstance(result, dict)
        self.assertIn("total_cost_usd", result)
        self.assertEqual(result["total_cost_usd"], 125.45)

    def test_aggregate_cost_data_multiple_days(self):
        """Test aggregating cost data across multiple days"""
        cost_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [{"currency": "USD", "amount": "100.00"}],
            },
            {
                "starting_at": "2025-01-02T00:00:00Z",
                "ending_at": "2025-01-02T23:59:59Z",
                "results": [{"currency": "USD", "amount": "200.50"}],
            },
            {
                "starting_at": "2025-01-03T00:00:00Z",
                "ending_at": "2025-01-03T23:59:59Z",
                "results": [{"currency": "USD", "amount": "50.75"}],
            },
        ]

        result = self.client.aggregate_cost_data(cost_data)

        self.assertEqual(result["total_cost_usd"], 351.25)

    def test_aggregate_cost_data_empty_list(self):
        """Test aggregating empty cost data list"""
        cost_data = []

        result = self.client.aggregate_cost_data(cost_data)

        self.assertEqual(result["total_cost_usd"], 0)

    def test_aggregate_cost_data_missing_results(self):
        """Test aggregating cost data with missing results field"""
        cost_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                # No results field
            }
        ]

        result = self.client.aggregate_cost_data(cost_data)

        self.assertEqual(result["total_cost_usd"], 0)

    def test_aggregate_cost_data_empty_results(self):
        """Test aggregating cost data with empty results array"""
        cost_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [],
            }
        ]

        result = self.client.aggregate_cost_data(cost_data)

        self.assertEqual(result["total_cost_usd"], 0)

    def test_aggregate_cost_data_non_usd_currency(self):
        """Test aggregating cost data with non-USD currency (should skip)"""
        cost_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [{"currency": "EUR", "amount": "100.00"}],  # Non-USD
            }
        ]

        result = self.client.aggregate_cost_data(cost_data)

        # Should skip non-USD and return 0
        self.assertEqual(result["total_cost_usd"], 0)

    def test_aggregate_cost_data_mixed_currencies(self):
        """Test aggregating cost data with mixed currencies"""
        cost_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {"currency": "USD", "amount": "100.00"},
                    {"currency": "EUR", "amount": "50.00"},  # Should be skipped
                ],
            }
        ]

        result = self.client.aggregate_cost_data(cost_data)

        # Should only count USD
        self.assertEqual(result["total_cost_usd"], 100.00)

    def test_aggregate_cost_data_invalid_amount_format(self):
        """Test aggregating cost data with invalid amount format"""
        cost_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [{"currency": "USD", "amount": "invalid"}],  # Invalid format
            }
        ]

        result = self.client.aggregate_cost_data(cost_data)

        # Should handle gracefully and return 0
        self.assertEqual(result["total_cost_usd"], 0)

    def test_aggregate_cost_data_none_input(self):
        """Test aggregating None as input"""
        result = self.client.aggregate_cost_data(None)

        self.assertEqual(result["total_cost_usd"], 0)

    def test_aggregate_cost_data_malformed_structure(self):
        """Test aggregating cost data with completely malformed structure"""
        cost_data = [
            {"unexpected": "field"},
            None,
            "not_a_dict",
        ]

        result = self.client.aggregate_cost_data(cost_data)

        # Should handle gracefully
        self.assertEqual(result["total_cost_usd"], 0)


class TestUsageDataAggregation(unittest.TestCase):
    """Test cases for aggregating usage report data"""

    def setUp(self):
        """Set up test fixtures"""
        self.admin_key = "sk-ant-admin-test-key-12345"
        self.client = ConsoleAPIClient(self.admin_key)

    def test_aggregate_usage_data_single_day_single_model(self):
        """Test aggregating usage data from single day, single model"""
        usage_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "input_tokens": 10000,
                        "output_tokens": 5000,
                        "cache_creation_input_tokens": 1000,
                        "cache_read_input_tokens": 2000,
                    }
                ],
            }
        ]

        result = self.client.aggregate_usage_data(usage_data)

        self.assertIsInstance(result, dict)
        self.assertIn("by_model", result)
        self.assertIn("claude-sonnet-4-5-20250929", result["by_model"])

        model_data = result["by_model"]["claude-sonnet-4-5-20250929"]
        self.assertEqual(model_data["input_tokens"], 10000)
        self.assertEqual(model_data["output_tokens"], 5000)
        self.assertEqual(model_data["cache_creation_input_tokens"], 1000)
        self.assertEqual(model_data["cache_read_input_tokens"], 2000)

    def test_aggregate_usage_data_multiple_days_same_model(self):
        """Test aggregating usage data across multiple days for same model"""
        usage_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "input_tokens": 10000,
                        "output_tokens": 5000,
                        "cache_creation_input_tokens": 1000,
                        "cache_read_input_tokens": 2000,
                    }
                ],
            },
            {
                "starting_at": "2025-01-02T00:00:00Z",
                "ending_at": "2025-01-02T23:59:59Z",
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "input_tokens": 15000,
                        "output_tokens": 7500,
                        "cache_creation_input_tokens": 500,
                        "cache_read_input_tokens": 1000,
                    }
                ],
            },
        ]

        result = self.client.aggregate_usage_data(usage_data)

        model_data = result["by_model"]["claude-sonnet-4-5-20250929"]
        self.assertEqual(model_data["input_tokens"], 25000)
        self.assertEqual(model_data["output_tokens"], 12500)
        self.assertEqual(model_data["cache_creation_input_tokens"], 1500)
        self.assertEqual(model_data["cache_read_input_tokens"], 3000)

    def test_aggregate_usage_data_multiple_models(self):
        """Test aggregating usage data for multiple models"""
        usage_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "input_tokens": 10000,
                        "output_tokens": 5000,
                        "cache_creation_input_tokens": 1000,
                        "cache_read_input_tokens": 2000,
                    },
                    {
                        "model": "claude-opus-4-20250514",
                        "input_tokens": 5000,
                        "output_tokens": 2500,
                        "cache_creation_input_tokens": 500,
                        "cache_read_input_tokens": 1000,
                    },
                    {
                        "model": "claude-3-5-haiku-20241022",
                        "input_tokens": 20000,
                        "output_tokens": 10000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                ],
            }
        ]

        result = self.client.aggregate_usage_data(usage_data)

        self.assertEqual(len(result["by_model"]), 3)
        self.assertIn("claude-sonnet-4-5-20250929", result["by_model"])
        self.assertIn("claude-opus-4-20250514", result["by_model"])
        self.assertIn("claude-3-5-haiku-20241022", result["by_model"])

    def test_aggregate_usage_data_empty_list(self):
        """Test aggregating empty usage data list"""
        usage_data = []

        result = self.client.aggregate_usage_data(usage_data)

        self.assertEqual(result["by_model"], {})

    def test_aggregate_usage_data_missing_results(self):
        """Test aggregating usage data with missing results field"""
        usage_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                # No results field
            }
        ]

        result = self.client.aggregate_usage_data(usage_data)

        self.assertEqual(result["by_model"], {})

    def test_aggregate_usage_data_missing_token_fields(self):
        """Test aggregating usage data with missing token fields"""
        usage_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "input_tokens": 10000,
                        # Missing output_tokens and cache fields
                    }
                ],
            }
        ]

        result = self.client.aggregate_usage_data(usage_data)

        model_data = result["by_model"]["claude-sonnet-4-5-20250929"]
        self.assertEqual(model_data["input_tokens"], 10000)
        self.assertEqual(model_data["output_tokens"], 0)
        self.assertEqual(model_data["cache_creation_input_tokens"], 0)
        self.assertEqual(model_data["cache_read_input_tokens"], 0)

    def test_aggregate_usage_data_none_input(self):
        """Test aggregating None as input"""
        result = self.client.aggregate_usage_data(None)

        self.assertEqual(result["by_model"], {})

    def test_aggregate_usage_data_malformed_structure(self):
        """Test aggregating usage data with malformed structure"""
        usage_data = [
            {"unexpected": "field"},
            None,
            "not_a_dict",
        ]

        result = self.client.aggregate_usage_data(usage_data)

        # Should handle gracefully
        self.assertEqual(result["by_model"], {})


class TestFetchMethodsReturnAggregatedData(unittest.TestCase):
    """Test that fetch_cost_report and fetch_usage_report return aggregated data"""

    def setUp(self):
        """Set up test fixtures"""
        self.admin_key = "sk-ant-admin-test-key-12345"
        self.client = ConsoleAPIClient(self.admin_key)

    def test_fetch_cost_report_returns_aggregated_data(self):
        """Test that fetch_cost_report returns aggregated cost data structure"""
        from unittest.mock import patch

        # Mock pagination to return raw API response
        raw_api_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [{"currency": "USD", "amount": "100.00"}],
            }
        ]

        with patch.object(
            self.client, "_handle_pagination", return_value=(raw_api_data, None)
        ):
            result, error = self.client.fetch_cost_report("2025-01-01", "2025-01-01")

            # Should return aggregated structure, not raw list
            self.assertIsInstance(result, dict)
            self.assertIn("total_cost_usd", result)
            self.assertEqual(result["total_cost_usd"], 100.00)
            self.assertIsNone(error)

    def test_fetch_usage_report_returns_aggregated_data(self):
        """Test that fetch_usage_report returns aggregated usage data structure"""
        from unittest.mock import patch

        # Mock pagination to return raw API response
        raw_api_data = [
            {
                "starting_at": "2025-01-01T00:00:00Z",
                "ending_at": "2025-01-01T23:59:59Z",
                "results": [
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "input_tokens": 10000,
                        "output_tokens": 5000,
                        "cache_creation_input_tokens": 1000,
                        "cache_read_input_tokens": 2000,
                    }
                ],
            }
        ]

        with patch.object(
            self.client, "_handle_pagination", return_value=(raw_api_data, None)
        ):
            result, error = self.client.fetch_usage_report("2025-01-01", "2025-01-01")

            # Should return aggregated structure, not raw list
            self.assertIsInstance(result, dict)
            self.assertIn("by_model", result)
            self.assertIn("claude-sonnet-4-5-20250929", result["by_model"])
            self.assertIsNone(error)

    def test_fetch_cost_report_propagates_api_errors(self):
        """Test that fetch_cost_report propagates API errors"""
        from unittest.mock import patch

        with patch.object(
            self.client, "_handle_pagination", return_value=(None, "API error: 500")
        ):
            result, error = self.client.fetch_cost_report("2025-01-01", "2025-01-01")

            self.assertIsNone(result)
            self.assertEqual(error, "API error: 500")

    def test_fetch_usage_report_propagates_api_errors(self):
        """Test that fetch_usage_report propagates API errors"""
        from unittest.mock import patch

        with patch.object(
            self.client, "_handle_pagination", return_value=(None, "API error: 500")
        ):
            result, error = self.client.fetch_usage_report("2025-01-01", "2025-01-01")

            self.assertIsNone(result)
            self.assertEqual(error, "API error: 500")


if __name__ == "__main__":
    unittest.main()
