"""Authentication management for Console mode"""

import json
from pathlib import Path


class AdminAuthManager:
    """Manages Admin API key authentication for Anthropic Console"""

    def __init__(self, credentials_path):
        self.credentials_path = Path(credentials_path)

    def load_admin_credentials(self):
        """Load Admin API key from environment variable or credentials file"""
        import os

        # Check environment variable first
        env_key = os.environ.get("ANTHROPIC_ADMIN_API_KEY")
        if env_key:
            # Validate format
            is_valid, validation_error = self.validate_admin_key(env_key)
            if not is_valid:
                return None, None, f"Invalid Admin API key format: {validation_error}"
            return env_key, "environment", None

        # Fall back to credentials file.
        # Missing file, corrupt JSON, non-dict root, or I/O error all mean
        # "source not available" — discard and fall through to the next source.
        try:
            if self.credentials_path.exists():
                with open(self.credentials_path) as f:
                    data = json.load(f)

                if isinstance(data, dict):
                    console_config = data.get("anthropicConsole", {})
                    if isinstance(console_config, dict):
                        file_key = console_config.get("adminApiKey", "")
                        if file_key:
                            is_valid, validation_error = self.validate_admin_key(
                                file_key
                            )
                            if not is_valid:
                                return (
                                    None,
                                    None,
                                    f"Invalid Admin API key format: {validation_error}",
                                )
                            return file_key, "credentials_file", None

        except FileNotFoundError:
            pass  # credentials file absent — source not available, try next source
        except json.JSONDecodeError:
            pass  # credentials file malformed — source not usable, try next source
        except OSError:
            pass  # permission/I/O error — source not accessible, try next source

        return None, None, "Admin API key not found"

    def validate_admin_key(self, key):
        """Validate Admin API key format

        Returns:
            tuple: (is_valid, error_message)
        """
        if not key:
            return False, "Admin API key is empty"

        if not key.startswith("sk-ant-admin"):
            return False, "Admin API key must start with sk-ant-admin"

        if len(key) < 20:
            return False, "Admin API key is too short"

        return True, None

    def get_admin_headers(self, admin_key):
        """Get authorization headers for Console API requests

        Returns:
            dict: Headers required for all Console API requests
        """
        return {
            "x-api-key": admin_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
