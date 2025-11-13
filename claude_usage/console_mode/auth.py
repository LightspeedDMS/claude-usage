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

        # Fall back to credentials file
        try:
            if not self.credentials_path.exists():
                return None, None, "Admin API key not found"

            with open(self.credentials_path) as f:
                data = json.load(f)

            if "anthropicConsole" not in data:
                return None, None, "Admin API key not found"

            console_config = data["anthropicConsole"]
            if "adminApiKey" not in console_config:
                return None, None, "Admin API key not found"

            file_key = console_config["adminApiKey"]

            # Validate format
            is_valid, validation_error = self.validate_admin_key(file_key)
            if not is_valid:
                return None, None, f"Invalid Admin API key format: {validation_error}"

            return file_key, "credentials_file", None

        except Exception as e:
            return None, None, f"Failed to load credentials: {e}"

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
