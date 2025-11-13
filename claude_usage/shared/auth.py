"""Shared authentication components"""

import logging
import sqlite3
import shutil
import tempfile
from pathlib import Path
from datetime import datetime


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

        except Exception as e:
            logging.getLogger(__name__).error(
                f"Failed to extract session key: {e}", exc_info=True
            )
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
