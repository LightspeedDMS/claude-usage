"""Tests for Console mode settings panel and pace-maker integration.

TDD spec: Console mode should render settings info (email, org, role, billing,
API key status) and pace-maker bottom section even when the admin API fails.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from claude_usage.console_mode.display import ConsoleRenderer
from claude_usage.console_mode.monitor import ConsoleMonitor


# ---------------------------------------------------------------------------
# Fake, non-sensitive placeholders used throughout
# ---------------------------------------------------------------------------
FAKE_EMAIL = "test-user@example.com"
FAKE_ORG_NAME = "Test Org Inc"
FAKE_ORG_ROLE = "admin"
FAKE_BILLING_TYPE = "usage_based"
FAKE_ACCOUNT_CREATED = "2024-01-15T10:00:00Z"
FAKE_PRIMARY_KEY = "fake-primary-api-key-for-testing"


def _render_to_str(renderable, width: int = 120) -> str:
    """Render any Rich renderable to a plain string via Console capture."""
    from rich.console import Console

    con = Console(file=StringIO(), width=width, force_terminal=True)
    with con.capture() as capture:
        con.print(renderable)
    return capture.get()


def _make_settings_info(
    email=FAKE_EMAIL,
    org_name=FAKE_ORG_NAME,
    org_role=FAKE_ORG_ROLE,
    billing_type=FAKE_BILLING_TYPE,
    account_created_at=FAKE_ACCOUNT_CREATED,
    primary_api_key_present=True,
    primary_api_key_suffix="aB3x",
    admin_api_key_source=None,
):
    """Build a full settings_info dict for test use."""
    return {
        "email": email,
        "org_name": org_name,
        "org_role": org_role,
        "billing_type": billing_type,
        "account_created_at": account_created_at,
        "primary_api_key_present": primary_api_key_present,
        "primary_api_key_suffix": primary_api_key_suffix,
        "admin_api_key_source": admin_api_key_source,
    }


class TestConsoleMonitorLoadsSettingsInfo(unittest.TestCase):
    """ConsoleMonitor._load_settings_info() reads oauthAccount from ~/.claude.json."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"
        self.fake_home = Path(self.temp_dir) / "home"
        self.fake_home.mkdir()
        # Write a minimal credentials file (no admin key)
        with open(self.credentials_path, "w") as f:
            json.dump({"mcpOAuth": {"token": "irrelevant"}}, f)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_claude_json(self, data):
        """Write JSON to fake ~/.claude.json."""
        p = self.fake_home / ".claude.json"
        with open(p, "w") as f:
            json.dump(data, f)

    def test_console_monitor_loads_settings_info(self):
        """_load_settings_info() returns all expected fields from oauthAccount."""
        self._write_claude_json({
            "primaryApiKey": FAKE_PRIMARY_KEY,
            "oauthAccount": {
                "emailAddress": FAKE_EMAIL,
                "organizationName": FAKE_ORG_NAME,
                "organizationRole": FAKE_ORG_ROLE,
                "billingType": FAKE_BILLING_TYPE,
                "createdAt": FAKE_ACCOUNT_CREATED,
            },
        })

        with patch(
            "claude_usage.console_mode.monitor.Path.home",
            return_value=self.fake_home,
        ):
            with patch(
                "claude_usage.console_mode.auth.Path.home",
                return_value=self.fake_home,
            ):
                monitor = ConsoleMonitor(self.credentials_path)
                info = monitor._load_settings_info()

        self.assertEqual(info["email"], FAKE_EMAIL)
        self.assertEqual(info["org_name"], FAKE_ORG_NAME)
        self.assertEqual(info["org_role"], FAKE_ORG_ROLE)
        self.assertEqual(info["billing_type"], FAKE_BILLING_TYPE)
        self.assertEqual(info["account_created_at"], FAKE_ACCOUNT_CREATED)
        self.assertTrue(info["primary_api_key_present"])
        # Last 4 chars of FAKE_PRIMARY_KEY = "fake-primary-api-key-for-testing" → "ting"
        self.assertEqual(info["primary_api_key_suffix"], FAKE_PRIMARY_KEY[-4:])
        # No claude_json_primary fallback — source is None when no admin key configured
        self.assertIsNone(info["admin_api_key_source"])

    def test_console_monitor_loads_settings_info_when_claude_json_missing(self):
        """_load_settings_info() returns empty/None fields when ~/.claude.json absent."""
        # fake_home has no .claude.json
        with patch(
            "claude_usage.console_mode.monitor.Path.home",
            return_value=self.fake_home,
        ):
            with patch(
                "claude_usage.console_mode.auth.Path.home",
                return_value=self.fake_home,
            ):
                monitor = ConsoleMonitor(self.credentials_path)
                info = monitor._load_settings_info()

        self.assertIsNone(info.get("email"))
        self.assertIsNone(info.get("org_name"))
        self.assertIsNone(info.get("org_role"))
        self.assertIsNone(info.get("billing_type"))
        self.assertIsNone(info.get("account_created_at"))
        self.assertFalse(info.get("primary_api_key_present", True))
        self.assertIsNone(info.get("primary_api_key_suffix"))
        self.assertIsNone(info.get("admin_api_key_source"))


class TestConsoleRendererSettingsPanel(unittest.TestCase):
    """ConsoleRenderer.render_settings_panel() renders all settings fields."""

    def setUp(self):
        self.renderer = ConsoleRenderer()

    def test_console_renderer_settings_panel_shows_all_fields(self):
        """render_settings_panel shows email, org, role, billing, key status."""
        info = _make_settings_info(
            admin_api_key_source="environment",
        )
        renderable = self.renderer.render_settings_panel(info)
        text = _render_to_str(renderable)

        self.assertIn(FAKE_EMAIL, text)
        self.assertIn(FAKE_ORG_NAME, text)
        self.assertIn(FAKE_ORG_ROLE, text)
        self.assertIn(FAKE_BILLING_TYPE, text)
        # Primary API key present → new honest label with location and suffix
        self.assertIn("set in ~/.claude.json", text)
        self.assertIn("aB3x", text)
        # Admin key source shown
        self.assertIn("environment", text)

    def test_console_renderer_settings_panel_handles_none_fields(self):
        """render_settings_panel shows fallback strings for all-None dict."""
        info = {
            "email": None,
            "org_name": None,
            "org_role": None,
            "billing_type": None,
            "account_created_at": None,
            "primary_api_key_present": False,
            "primary_api_key_suffix": None,
            "admin_api_key_source": None,
        }
        renderable = self.renderer.render_settings_panel(info)
        text = _render_to_str(renderable)

        # Should not crash and should show fallback text
        self.assertIn("unavailable", text)
        self.assertIn("not set", text)


class TestConsoleRendererErrorBehavior(unittest.TestCase):
    """ConsoleRenderer.render() error branch behavior based on admin key presence."""

    def setUp(self):
        self.renderer = ConsoleRenderer()

    def test_console_renderer_friendly_admin_key_error_when_missing(self):
        """When error set AND admin_api_key_source is None → show friendly hint."""
        info = _make_settings_info(
            primary_api_key_present=True,
            admin_api_key_source=None,
        )
        renderable = self.renderer.render(
            org_data=None,
            mtd_data=None,
            workspaces=None,
            last_update=None,
            projection=None,
            error="Authentication failed",
            settings_info=info,
        )
        text = _render_to_str(renderable)

        self.assertIn("Admin API key", text)
        self.assertIn("platform.claude.com/settings/admin-keys", text)
        self.assertIn("anthropicConsole", text)
        self.assertIn("adminApiKey", text)

    def test_console_renderer_generic_error_when_admin_key_present(self):
        """When error set AND admin_api_key_source is not None → generic error, no hint."""
        info = _make_settings_info(
            primary_api_key_present=True,
            admin_api_key_source="environment",
        )
        renderable = self.renderer.render(
            org_data=None,
            mtd_data=None,
            workspaces=None,
            last_update=None,
            projection=None,
            error="Authentication failed",
            settings_info=info,
        )
        text = _render_to_str(renderable)

        # Friendly hint must NOT appear
        self.assertNotIn("platform.claude.com/settings/admin-keys", text)
        # But error must still be visible
        self.assertIn("Authentication failed", text)

    def test_console_renderer_generic_error_when_claude_json_primary_source(self):
        """When source is 'claude_json_primary' (non-None), show generic error — no friendly hint."""
        info = _make_settings_info(
            primary_api_key_present=True,
            admin_api_key_source="claude_json_primary",
        )
        renderable = self.renderer.render(
            org_data=None,
            mtd_data=None,
            workspaces=None,
            last_update=None,
            projection=None,
            error="Authentication failed",
            settings_info=info,
        )
        text = _render_to_str(renderable)

        # Friendly hint must NOT appear — only None source triggers it now
        self.assertNotIn("platform.claude.com/settings/admin-keys", text)
        # Generic error must still be visible
        self.assertIn("Authentication failed", text)


class TestConsoleMonitorIntegratesPaceMakerReader(unittest.TestCase):
    """ConsoleMonitor fetches pace-maker data independent of admin API success."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"
        self.fake_home = Path(self.temp_dir) / "home"
        self.fake_home.mkdir()
        with open(self.credentials_path, "w") as f:
            json.dump({"mcpOAuth": {"token": "irrelevant"}}, f)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_console_monitor_integrates_pacemaker_reader(self):
        """Pace-maker data is captured even when admin API fetch fails."""
        fake_status = {"enabled": True, "has_data": True}
        fake_blockage = {"Intent": 3, "TDD": 1}
        fake_langfuse = {"total_traces": 10}
        fake_secrets = {"total": 2}
        fake_events = [{"ts": 1000, "decision": "allow", "feedback": "ok"}]

        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = True
        mock_reader.get_status.return_value = fake_status
        mock_reader.get_blockage_stats_with_labels.return_value = fake_blockage
        mock_reader.get_langfuse_metrics.return_value = fake_langfuse
        mock_reader.get_secrets_metrics.return_value = fake_secrets
        mock_reader.get_governance_events.return_value = fake_events
        mock_reader.get_langfuse_status.return_value = False
        mock_reader.test_langfuse_connection.return_value = {"connected": False}
        mock_reader.get_recent_activity.return_value = []

        with patch(
            "claude_usage.console_mode.monitor.Path.home",
            return_value=self.fake_home,
        ):
            with patch(
                "claude_usage.console_mode.auth.Path.home",
                return_value=self.fake_home,
            ):
                with patch(
                    "claude_usage.console_mode.monitor.PaceMakerReader",
                    return_value=mock_reader,
                ):
                    monitor = ConsoleMonitor(self.credentials_path)
                    # fetch_console_data will fail (no admin API key) but pace-maker
                    # data must still be loaded
                    monitor.fetch_console_data()

        # Pace-maker attributes must be populated despite admin API failure
        self.assertIsNotNone(monitor.pacemaker_status)
        self.assertIsNotNone(monitor.blockage_stats)
        self.assertIsNotNone(monitor.langfuse_metrics)
        self.assertIsNotNone(monitor.secrets_metrics)
        self.assertIsNotNone(monitor.governance_events)
        self.assertEqual(monitor.pacemaker_status, fake_status)
        self.assertEqual(monitor.blockage_stats, fake_blockage)


if __name__ == "__main__":
    unittest.main()
