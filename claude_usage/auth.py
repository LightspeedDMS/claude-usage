"""Authentication management for Claude Code usage monitor"""

import json
import sqlite3
import shutil
import tempfile
from pathlib import Path
from datetime import datetime


class OAuthManager:
    """Manages OAuth token operations"""

    def __init__(self, credentials_path):
        self.credentials_path = Path(credentials_path)

    def load_credentials(self):
        """Load OAuth credentials from Claude Code config"""
        try:
            with open(self.credentials_path) as f:
                data = json.load(f)

            if "claudeAiOauth" not in data:
                raise ValueError("No OAuth credentials found")

            return data["claudeAiOauth"], None

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


class FirefoxSessionManager:
    """Manages Firefox session key extraction"""

    SESSION_REFRESH_INTERVAL = 300  # 5 minutes

    def __init__(self):
        self.last_refresh = None

    def extract_session_key(self):
        """Extract sessionKey from Firefox cookies"""
        try:
            firefox_dir = Path.home() / ".mozilla" / "firefox"
            if not firefox_dir.exists():
                return None

            # Find profile with cookies
            for profile in firefox_dir.glob("*.*/"):
                cookies_db = profile / "cookies.sqlite"
                if not cookies_db.exists():
                    continue

                # Copy database (Firefox locks it when running)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
                    tmp_path = tmp.name

                try:
                    shutil.copy2(cookies_db, tmp_path)
                    conn = sqlite3.connect(tmp_path)
                    cursor = conn.cursor()

                    # Query for sessionKey cookie
                    cursor.execute(
                        """
                        SELECT value, expiry
                        FROM moz_cookies
                        WHERE host LIKE '%claude.ai%' AND name = 'sessionKey'
                        ORDER BY expiry DESC
                        LIMIT 1
                    """
                    )

                    result = cursor.fetchone()
                    conn.close()

                    if result:
                        return result[0]  # Return the session key value

                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            return None

        except Exception:
            return None

    def should_refresh(self):
        """Check if session key should be refreshed"""
        if not self.last_refresh:
            return True

        now = datetime.now()
        elapsed = (now - self.last_refresh).total_seconds()
        return elapsed >= self.SESSION_REFRESH_INTERVAL

    def refresh_session_key(self):
        """Refresh session key from Firefox if needed"""
        if not self.should_refresh():
            return None

        session_key = self.extract_session_key()
        if session_key:
            self.last_refresh = datetime.now()
            return session_key

        return None
