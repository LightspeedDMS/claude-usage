"""Authentication management for Claude Code mode"""

import json
import logging
import platform
import subprocess
from pathlib import Path
from datetime import datetime


class OAuthManager:
    """Manages OAuth token operations"""

    def __init__(self, credentials_path):
        self.credentials_path = Path(credentials_path)

    def extract_from_macos_keychain(self):
        """Extract OAuth credentials from macOS Keychain

        Returns:
            tuple: (credentials_dict, error_message)
        """
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    "Claude Code-credentials",
                    "-w",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            credentials_json = result.stdout.strip()
            data = json.loads(credentials_json)

            if "claudeAiOauth" not in data:
                return None, "No OAuth credentials found in Keychain"

            return data, None

        except subprocess.CalledProcessError as e:
            return None, f"Failed to extract from Keychain: {e.stderr}"
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON from Keychain: {e}"
        except Exception as e:
            return None, f"Keychain extraction error: {e}"

    def save_credentials_file(self, data):
        """Save credentials data to file

        Args:
            data: Full credentials dictionary to save
        """
        try:
            # Ensure directory exists
            self.credentials_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.credentials_path, "w") as f:
                json.dump(data, f, indent=2)

            return True, None

        except Exception as e:
            return False, f"Failed to save credentials: {e}"

    def load_credentials(self):
        """Load OAuth credentials from Claude Code config

        Automatically extracts from macOS Keychain if:
        - File doesn't exist on macOS, OR
        - File exists but token is expired and we're on macOS
        """
        try:
            # Try reading from file first (works on Linux and macOS if file exists)
            with open(self.credentials_path) as f:
                data = json.load(f)

            if "claudeAiOauth" not in data:
                raise ValueError("No OAuth credentials found")

            credentials = data["claudeAiOauth"]

            # Check if token is expired
            if self.is_token_expired(credentials):
                # Token is expired - try to refresh from Keychain on macOS
                if platform.system() == "Darwin":
                    keychain_data, error = self.extract_from_macos_keychain()

                    if error:
                        # Keychain extraction failed, return expired token with error
                        return credentials, "Token expired. Please run 'claude' to refresh."

                    # Successfully extracted fresh token from Keychain
                    # Save to file for future use
                    save_success, save_error = self.save_credentials_file(keychain_data)
                    if not save_success:
                        logging.getLogger(__name__).warning(
                            f"Extracted from Keychain but couldn't save to file: {save_error}"
                        )

                    return keychain_data["claudeAiOauth"], None
                else:
                    # Linux - no Keychain available, return expired token with error
                    return credentials, "Token expired. Please run 'claude' to refresh."

            # Token is still valid
            return credentials, None

        except FileNotFoundError:
            # File doesn't exist - try macOS Keychain extraction
            if platform.system() == "Darwin":
                data, error = self.extract_from_macos_keychain()

                if error:
                    return None, f"Failed to load credentials: {error}"

                # Save to file for future use
                save_success, save_error = self.save_credentials_file(data)
                if not save_success:
                    logging.getLogger(__name__).warning(
                        f"Extracted from Keychain but couldn't save to file: {save_error}"
                    )

                return data["claudeAiOauth"], None
            else:
                return (
                    None,
                    "Credentials file not found. Please run 'claude' to authenticate.",
                )

        except Exception as e:
            return None, f"Failed to load credentials: {e}"

    def save_credentials(self, credentials):
        """Save updated credentials back to file"""
        try:
            with open(self.credentials_path) as f:
                data = json.load(f)

            data["claudeAiOauth"] = credentials

            with open(self.credentials_path, "w") as f:
                json.dump(data, f, indent=2)

            return True, None

        except Exception as e:
            return False, f"Failed to save credentials: {e}"

    def is_token_expired(self, credentials):
        """Check if OAuth token is expired or close to expiry"""
        if not credentials:
            return True

        expires_at = credentials.get("expiresAt", 0)
        current_time = datetime.now().timestamp() * 1000

        # Consider expired if less than 5 minutes remaining
        buffer = 5 * 60 * 1000
        return current_time >= (expires_at - buffer)

    def refresh_token(self, credentials):
        """Attempt to refresh the OAuth token"""
        if not credentials or "refreshToken" not in credentials:
            return False, "No refresh token available"

        try:
            # Note: The actual refresh endpoint might differ
            # This is a placeholder - Claude Code might handle this internally
            return False, "Token expired. Please run 'claude' to refresh."

        except Exception as e:
            return False, f"Token refresh failed: {e}"

    def get_auth_headers(self, credentials):
        """Get authorization headers for API requests"""
        if not credentials:
            return None

        return {
            "Authorization": f'Bearer {credentials["accessToken"]}',
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-code/2.0.37",
        }
