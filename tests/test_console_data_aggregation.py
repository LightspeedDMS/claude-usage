"""Tests for Console API data aggregation logic"""

import unittest
from claude_usage.console_mode.api import ConsoleAPIClient


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


if __name__ == "__main__":
    unittest.main()
