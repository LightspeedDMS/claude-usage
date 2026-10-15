"""Authentication management for Claude Code mode"""

import hashlib
import json
import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Max seconds to wait for the `security` CLI (an open Keychain prompt blocks it)
KEYCHAIN_TIMEOUT_SECONDS = 3

TOKEN_EXPIRED_MESSAGE = "Token expired. Please run 'claude' to refresh."

# Credential fields whose drift between Keychain and file triggers a file rewrite
_SYNC_FIELDS = ("accessToken", "subscriptionType", "rateLimitTier")

# Hex chars of sha256(accessToken) used as account-match key (shared with
# pace-maker's profile_cache.json "token_fingerprint")
TOKEN_FINGERPRINT_LENGTH = 16


def token_fingerprint(access_token):
    """Non-secret account-match key: first 16 hex chars of sha256(accessToken)."""
    digest = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    return digest[:TOKEN_FINGERPRINT_LENGTH]


class OAuthManager:
    """Manages OAuth token operations"""

    def __init__(self, credentials_path):
        self.credentials_path = Path(credentials_path)
        # Last warning message per kind, so a persistent failure logs once
        self._last_warnings = {}

    def _warn_once(self, kind, message):
        """Log a warning only when it differs from the last one of this kind."""
        if self._last_warnings.get(kind) != message:
            self._last_warnings[kind] = message
            logger.warning(message)

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
                timeout=KEYCHAIN_TIMEOUT_SECONDS,
            )

            credentials_json = result.stdout.strip()
            data = json.loads(credentials_json)

            if not isinstance(data, dict) or not isinstance(
                data.get("claudeAiOauth"), dict
            ):
                return None, "No OAuth credentials found in Keychain"

            return data, None

        except subprocess.TimeoutExpired:
            return (
                None,
                f"Keychain read timed out after {KEYCHAIN_TIMEOUT_SECONDS}s "
                "(is a Keychain prompt open?)",
            )
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
        tmp_name = None
        try:
            parent = self.credentials_path.parent
            parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: mkstemp creates the file 0600 in the same directory,
            # os.replace then swaps it in so readers never see a partial file.
            fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".credentials-")
            try:
                tmp_file = os.fdopen(fd, "w")
            except BaseException:
                os.close(fd)
                raise
            with tmp_file:
                json.dump(data, tmp_file, indent=2)
            os.replace(tmp_name, self.credentials_path)
            tmp_name = None

            return True, None

        except Exception as e:
            return False, f"Failed to save credentials: {e}"
        finally:
            if tmp_name is not None and os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def load_credentials(self):
        """Load OAuth credentials from Claude Code config

        On macOS the Keychain is the source of truth (Claude Code's current
        login) and the credentials file is only a cache: the file is used
        solely when the Keychain read fails. On Linux the file is used.
        """
        if platform.system() == "Darwin":
            keychain_data, error = self.extract_from_macos_keychain()
            if not error:
                self._last_warnings.pop("keychain", None)
                self._sync_file_with_keychain(keychain_data)
                credentials = keychain_data["claudeAiOauth"]
                if self.is_token_expired(credentials):
                    return credentials, TOKEN_EXPIRED_MESSAGE
                return credentials, None
            self._warn_once(
                "keychain",
                f"Keychain read failed, falling back to credentials file: {error}",
            )
        return self._load_from_file()

    def _sync_file_with_keychain(self, keychain_data):
        """Rewrite the credentials file when it differs from the Keychain."""
        try:
            with open(self.credentials_path) as f:
                file_oauth = json.load(f).get("claudeAiOauth") or {}
        except (OSError, ValueError, AttributeError) as e:
            logger.debug(f"Could not read existing credentials file: {e}")
            file_oauth = {}

        keychain_oauth = keychain_data["claudeAiOauth"]
        if all(file_oauth.get(k) == keychain_oauth.get(k) for k in _SYNC_FIELDS):
            return

        save_success, save_error = self.save_credentials_file(keychain_data)
        if save_success:
            self._last_warnings.pop("save", None)
        else:
            self._warn_once(
                "save",
                f"Extracted from Keychain but couldn't save to file: {save_error}",
            )

    def _load_from_file(self):
        """Load OAuth credentials from the credentials file."""
        try:
            with open(self.credentials_path) as f:
                data = json.load(f)

            if "claudeAiOauth" not in data:
                raise ValueError("No OAuth credentials found")

            credentials = data["claudeAiOauth"]

            if self.is_token_expired(credentials):
                return credentials, TOKEN_EXPIRED_MESSAGE

            return credentials, None

        except FileNotFoundError:
            if platform.system() == "Darwin":
                return (
                    None,
                    "Credentials not found. Please run 'claude' to authenticate.",
                )
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
