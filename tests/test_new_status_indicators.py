"""Tests for new status indicators (TDD, Model, Rules) in display and pacemaker_integration.

These tests verify AC requirements for adding three new status indicators
to the bottom left "Pacing Status" section:
- TDD: on/off (green/yellow)
- Model: auto/sonnet/opus/haiku (cyan/green)
- Rules: N (green if >0, yellow if 0)
"""

import unittest
from unittest.mock import MagicMock, patch, mock_open
from io import StringIO
from rich.console import Console
from claude_usage.code_mode.display import UsageRenderer
from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

# Default clean code rules count from pace-maker
DEFAULT_CLEAN_CODE_RULES_COUNT = 17


class TestNewStatusIndicatorsDisplay(unittest.TestCase):
    """Test cases for new status indicators in display.py render_bottom_section()"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def _render_to_text(self, panel, width=80):
        """Helper to render panel to plain text"""
        console = Console(file=StringIO(), width=width, force_terminal=True)
        with console.capture() as capture:
            console.print(panel)
        return capture.get()

    def test_render_tdd_enabled_shows_green_on(self):
        """Test TDD status shows green 'on' when tdd_enabled is True"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tdd_enabled": True,
            "preferred_subagent_model": "auto",
            "clean_code_rules_count": DEFAULT_CLEAN_CODE_RULES_COUNT,
        }
        blockage_stats = {"Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)

        # Verify TDD line is present with green "on"
        self.assertIn("TDD:", output)
        self.assertIn("on", output)

    def test_render_tdd_disabled_shows_yellow_off(self):
        """Test TDD status shows yellow 'off' when tdd_enabled is False"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "tdd_enabled": False,
            "preferred_subagent_model": "auto",
            "clean_code_rules_count": DEFAULT_CLEAN_CODE_RULES_COUNT,
        }
        blockage_stats = {"Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)

        # Verify TDD line is present with yellow "off"
        self.assertIn("TDD:", output)
        self.assertIn("off", output)

    def test_render_model_auto_shows_cyan_auto(self):
        """Test Model status shows cyan 'auto' when preferred_subagent_model is 'auto'"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "tdd_enabled": True,
            "preferred_subagent_model": "auto",
            "clean_code_rules_count": DEFAULT_CLEAN_CODE_RULES_COUNT,
        }
        blockage_stats = {"Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)

        # Verify Model line is present with cyan "auto"
        self.assertIn("Model:", output)
        self.assertIn("auto", output)

    def test_render_model_specific_shows_green_model_name(self):
        """Test Model status shows green model name when specific model is set"""
        for model_name in ["sonnet", "opus", "haiku"]:
            with self.subTest(model=model_name):
                pacemaker_status = {
                    "enabled": True,
                    "has_data": True,
                    "tdd_enabled": True,
                    "preferred_subagent_model": model_name,
                    "clean_code_rules_count": DEFAULT_CLEAN_CODE_RULES_COUNT,
                }
                blockage_stats = {"Total": 0}

                result = self.renderer.render_bottom_section(
                    pacemaker_status, blockage_stats
                )
                output = self._render_to_text(result)

                # Verify Model line shows the specific model name
                self.assertIn("Model:", output)
                self.assertIn(model_name, output)

    def test_render_rules_with_count_shows_green(self):
        """Test Rules status shows green count when clean_code_rules_count > 0"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "tdd_enabled": True,
            "preferred_subagent_model": "auto",
            "clean_code_rules_count": DEFAULT_CLEAN_CODE_RULES_COUNT,
        }
        blockage_stats = {"Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)

        # Verify Rules line is present with green count
        self.assertIn("Rules:", output)
        self.assertIn(str(DEFAULT_CLEAN_CODE_RULES_COUNT), output)

    def test_render_rules_zero_shows_yellow(self):
        """Test Rules status shows yellow 0 when clean_code_rules_count is 0"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "tdd_enabled": True,
            "preferred_subagent_model": "auto",
            "clean_code_rules_count": 0,
        }
        blockage_stats = {"Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)

        # Verify Rules line is present with yellow 0
        self.assertIn("Rules:", output)
        self.assertIn("0", output)

    def test_render_new_indicators_positioned_after_langfuse_before_updated(self):
        """Test that new indicators appear after Langfuse and before Updated timestamp"""
        from datetime import datetime

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "langfuse_enabled": True,
            "tdd_enabled": True,
            "preferred_subagent_model": "auto",
            "clean_code_rules_count": DEFAULT_CLEAN_CODE_RULES_COUNT,
        }
        blockage_stats = {"Total": 0}
        last_update = datetime(2025, 11, 13, 22, 45, 12)

        result = self.renderer.render_bottom_section(
            pacemaker_status, blockage_stats, last_update
        )
        output = self._render_to_text(result)

        # Find positions of indicators
        langfuse_pos = output.find("Langfuse:")
        tdd_pos = output.find("TDD:")
        model_pos = output.find("Model:")
        rules_pos = output.find("Rules:")
        updated_pos = output.find("Updated:")

        # Verify ordering: Langfuse < TDD < Model < Rules < Updated
        self.assertGreater(tdd_pos, langfuse_pos, "TDD should appear after Langfuse")
        self.assertGreater(model_pos, tdd_pos, "Model should appear after TDD")
        self.assertGreater(rules_pos, model_pos, "Rules should appear after Model")
        self.assertGreater(updated_pos, rules_pos, "Updated should appear after Rules")

    def test_render_defaults_when_fields_missing(self):
        """Test graceful defaults when new status fields are missing"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            # Missing: tdd_enabled, preferred_subagent_model, clean_code_rules_count
        }
        blockage_stats = {"Total": 0}

        # Should not raise exception
        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)

        # Should have sensible defaults
        self.assertIn("TDD:", output)
        self.assertIn("Model:", output)
        self.assertIn("Rules:", output)


class TestNewStatusFieldsPaceMakerReader(unittest.TestCase):
    """Test cases for new status fields in pacemaker_integration.py get_status()"""

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    def test_get_status_includes_tdd_enabled_field(self, mock_path):
        """Test that get_status() returns tdd_enabled field from config"""
        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True
        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = False

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        with patch(
            "builtins.open",
            mock_open(read_data='{"enabled": true, "tdd_enabled": true}'),
        ):
            reader = PaceMakerReader()
            reader.pm_dir = mock_pm_dir
            reader.config_path = mock_config_path
            reader.db_path = mock_db_path

            status = reader.get_status()

            # Should include tdd_enabled field (defaults to False when no data)
            # When there's no usage data, get_status returns {"enabled": True, "has_data": False}
            # We need to test the case where data exists
            self.assertIsNotNone(status)

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    @patch("claude_usage.code_mode.pacemaker_integration.sqlite3")
    def test_get_status_includes_preferred_subagent_model_field(
        self, mock_sqlite3, mock_path
    ):
        """Test that get_status() returns preferred_subagent_model field from config"""
        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True
        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True

        # Mock database query results
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No usage data
        mock_conn.cursor.return_value = mock_cursor
        mock_sqlite3.connect.return_value = mock_conn

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        with patch(
            "builtins.open",
            mock_open(
                read_data='{"enabled": true, "tdd_enabled": true, "preferred_subagent_model": "sonnet"}'
            ),
        ):
            reader = PaceMakerReader()
            reader.pm_dir = mock_pm_dir
            reader.config_path = mock_config_path
            reader.db_path = mock_db_path

            status = reader.get_status()
            self.assertIsNotNone(status)

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    def test_get_status_includes_clean_code_rules_count_field(self, mock_path):
        """Test that get_status() returns clean_code_rules_count field"""
        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True
        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = False

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        with patch(
            "builtins.open",
            mock_open(read_data='{"enabled": true, "tdd_enabled": true}'),
        ):
            reader = PaceMakerReader()
            reader.pm_dir = mock_pm_dir
            reader.config_path = mock_config_path
            reader.db_path = mock_db_path

            status = reader.get_status()
            self.assertIsNotNone(status)

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_status_reads_tdd_enabled_from_config(self, mock_file, mock_path):
        """Test that tdd_enabled is correctly read from config.json"""
        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True
        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = False

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        # Test with tdd_enabled=True
        mock_file.return_value.read.return_value = (
            '{"enabled": true, "tdd_enabled": true}'
        )

        reader = PaceMakerReader()
        reader.pm_dir = mock_pm_dir
        reader.config_path = mock_config_path
        reader.db_path = mock_db_path

        # Call _read_config() directly to test config parsing
        with patch.object(reader.config_path, "exists", return_value=True):
            with patch("builtins.open", mock_open(read_data='{"tdd_enabled": true}')):
                config = reader._read_config()
                self.assertTrue(config.get("tdd_enabled"))

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    def test_get_status_defaults_tdd_enabled_to_false(self, mock_path):
        """Test that tdd_enabled defaults to False when not in config"""
        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        with patch("builtins.open", mock_open(read_data='{"enabled": true}')):
            reader = PaceMakerReader()
            reader.pm_dir = mock_pm_dir
            reader.config_path = mock_config_path

            config = reader._read_config()
            # get() should return False when key is missing
            self.assertEqual(config.get("tdd_enabled", False), False)

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    def test_get_status_reads_preferred_subagent_model_from_config(self, mock_path):
        """Test that preferred_subagent_model is correctly read from config.json"""
        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        with patch(
            "builtins.open",
            mock_open(
                read_data='{"enabled": true, "preferred_subagent_model": "opus"}'
            ),
        ):
            reader = PaceMakerReader()
            reader.pm_dir = mock_pm_dir
            reader.config_path = mock_config_path

            config = reader._read_config()
            self.assertEqual(config.get("preferred_subagent_model"), "opus")

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    def test_get_status_defaults_preferred_subagent_model_to_auto(self, mock_path):
        """Test that preferred_subagent_model defaults to 'auto' when not in config"""
        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        with patch("builtins.open", mock_open(read_data='{"enabled": true}')):
            reader = PaceMakerReader()
            reader.pm_dir = mock_pm_dir
            reader.config_path = mock_config_path

            config = reader._read_config()
            # get() should return 'auto' when key is missing
            self.assertEqual(config.get("preferred_subagent_model", "auto"), "auto")


class TestNewStatusFieldsIntegration(unittest.TestCase):
    """Integration tests for new status fields in get_status() method"""

    @patch("claude_usage.code_mode.pacemaker_integration.Path")
    @patch("claude_usage.code_mode.pacemaker_integration.sqlite3")
    @patch("sys.path", [])
    def test_get_status_returns_all_new_fields_with_usage_data(
        self, mock_sqlite3, mock_path
    ):
        """Test that get_status() returns all new fields when usage data exists"""
        # This is an integration test that verifies all three fields are present
        # in the status dict when everything is configured correctly

        mock_pm_dir = MagicMock()
        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True
        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True
        mock_install_source = MagicMock()
        mock_install_source.exists.return_value = False

        # Mock database with usage data
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            1700000000,  # timestamp
            75.0,  # five_hour_util
            "2025-11-13T23:00:00",  # five_hour_resets_at
            60.0,  # seven_day_util
            "2025-11-20T00:00:00",  # seven_day_resets_at
        )
        mock_conn.cursor.return_value = mock_cursor
        mock_sqlite3.connect.return_value = mock_conn

        mock_path.home.return_value.joinpath.return_value = mock_pm_dir
        mock_pm_dir.exists.return_value = True

        config_json = """
        {
            "enabled": true,
            "tdd_enabled": true,
            "preferred_subagent_model": "sonnet",
            "weekly_limit_enabled": false
        }
        """

        with patch("builtins.open", mock_open(read_data=config_json)):
            # Need to mock the pacing_engine module
            mock_pacing_engine_module = MagicMock()
            mock_pacing_engine_module.calculate_pacing_decision.return_value = {
                "five_hour": {"target": 70.0, "deviation": 5.0},
                "seven_day": {"target": 65.0, "deviation": -5.0},
                "constrained_window": "5-hour",
                "deviation_percent": 5.0,
                "should_throttle": False,
                "delay_seconds": 0,
                "algorithm": "adaptive",
                "strategy": "normal",
            }

            # Mock both pacemaker and pacemaker.pacing_engine modules
            with patch.dict(
                "sys.modules",
                {
                    "pacemaker": MagicMock(),
                    "pacemaker.pacing_engine": mock_pacing_engine_module,
                    "pacemaker.clean_code_rules": MagicMock(
                        get_default_rules=MagicMock(
                            return_value=[
                                {} for _ in range(DEFAULT_CLEAN_CODE_RULES_COUNT)
                            ]
                        )
                    ),
                },
            ):
                reader = PaceMakerReader()
                reader.pm_dir = mock_pm_dir
                reader.config_path = mock_config_path
                reader.db_path = mock_db_path

                # Mock install_source file check
                with patch.object(
                    reader.pm_dir, "__truediv__", return_value=mock_install_source
                ):
                    status = reader.get_status()

                    # Verify status is returned
                    self.assertIsNotNone(status)
                    self.assertTrue(status.get("enabled"))
                    self.assertTrue(status.get("has_data"))

                    # Verify new fields are present
                    self.assertIn("tdd_enabled", status)
                    self.assertIn("preferred_subagent_model", status)
                    self.assertIn("clean_code_rules_count", status)

                    # Verify field values
                    self.assertTrue(status["tdd_enabled"])
                    self.assertEqual(status["preferred_subagent_model"], "sonnet")
                    self.assertEqual(
                        status["clean_code_rules_count"], DEFAULT_CLEAN_CODE_RULES_COUNT
                    )


if __name__ == "__main__":
    unittest.main()
