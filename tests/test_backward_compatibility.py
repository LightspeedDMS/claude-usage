"""
Test Backward Compatibility - AC5
Verify Code mode still works when no Admin API credentials available
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from claude_usage.monitor import ClaudeUsageMonitor


class TestBackwardCompatibility:
    """AC5: Code mode must work when no Admin API credentials present"""

    @pytest.fixture
    def oauth_only_credentials_file(self):
        """Create temporary credentials file with only OAuth, no Admin API"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            credentials = {
                "claudeAiOauth": {
                    "accessToken": "oauth_token_abc123",
                    "refreshToken": "oauth_refresh_xyz789",
                    "expiresAt": 9999999999000,
                }
            }
            json.dump(credentials, f)
            path = Path(f.name)
        yield path
        path.unlink()

    def test_code_mode_works_without_admin_api_credentials(
        self, oauth_only_credentials_file
    ):
        """
        GIVEN credentials file contains only OAuth tokens (no Admin API key)
        AND no ANTHROPIC_ADMIN_API_KEY environment variable
        WHEN monitor is initialized
        THEN it should operate in Code mode successfully
        """
        # Ensure no Admin API key in environment
        import os

        env_without_admin_key = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"
        }

        with patch.dict("os.environ", env_without_admin_key, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=oauth_only_credentials_file)
            mode = monitor.detect_mode()

            assert mode == "code", "Should detect Code mode when only OAuth available"
            assert monitor.credentials is not None, "Should load OAuth credentials"

    def test_code_mode_uses_existing_usage_renderer(self, oauth_only_credentials_file):
        """
        GIVEN Code mode is active (no Admin API)
        WHEN rendering display
        THEN it should use the existing UsageRenderer (not ConsoleRenderer)
        """
        import os

        env_without_admin_key = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"
        }

        with patch.dict("os.environ", env_without_admin_key, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=oauth_only_credentials_file)

            from claude_usage.display import UsageRenderer

            assert isinstance(
                monitor.renderer, UsageRenderer
            ), "Code mode should use existing UsageRenderer"

    def test_code_mode_fetches_usage_via_oauth(self, oauth_only_credentials_file):
        """
        GIVEN Code mode is active
        WHEN fetch_usage is called
        THEN it should use OAuth authentication (not Admin API)
        """
        import os

        env_without_admin_key = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"
        }

        with patch.dict("os.environ", env_without_admin_key, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=oauth_only_credentials_file)

            with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
                mock_fetch.return_value = (
                    {"usage_tier": {"current_usage_tokens": 1000}},
                    None,
                )

                success = monitor.fetch_usage()

                assert success, "Should successfully fetch usage in Code mode"
                assert mock_fetch.called, "Should call api_client.fetch_usage"
                # Verify OAuth headers were used
                call_args = mock_fetch.call_args
                headers = call_args[0][0]
                assert (
                    "Authorization" in headers
                ), "Should pass OAuth authorization headers"
                assert headers["Authorization"].startswith(
                    "Bearer "
                ), "Should use Bearer token authentication"

    def test_no_admin_api_dependencies_in_code_mode(self, oauth_only_credentials_file):
        """
        GIVEN Code mode is active
        WHEN monitor is initialized
        THEN it should not instantiate any Admin API components
        """
        import os

        env_without_admin_key = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"
        }

        with patch.dict("os.environ", env_without_admin_key, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=oauth_only_credentials_file)

            # Code mode should NOT have these attributes
            assert not hasattr(
                monitor, "admin_auth_manager"
            ), "Code mode should not have admin_auth_manager"
            assert not hasattr(
                monitor, "console_client"
            ), "Code mode should not have console_client"
            assert not hasattr(
                monitor, "console_renderer"
            ), "Code mode should not have console_renderer"
