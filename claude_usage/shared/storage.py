"""Base storage class for usage tracking"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class BaseStorage:
    """Base class for SQLite database management"""

    HISTORY_RETENTION = 604800  # Keep 7 days of history

    # Concurrency constants
    DB_TIMEOUT = 5.0
    MAX_RETRIES = 3
    RETRY_DELAY = 0.1

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        """Initialize storage directory and database - override in subclasses"""
        try:
            # Create storage directory if it doesn't exist
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Subclasses should override to create their specific tables
            conn = sqlite3.connect(self.db_path, timeout=self.DB_TIMEOUT)
            conn.execute("PRAGMA journal_mode=WAL")
            self._create_tables(conn)
            conn.commit()
            conn.close()

        except Exception:
            # Non-fatal error - continue without storage
            pass

    def _create_tables(self, conn):
        """Create database tables - must be overridden by subclasses"""
        pass

    @contextmanager
    def get_connection(self, readonly: bool = False):
        """Get database connection with proper concurrency handling.

        Args:
            readonly: If True, enable read_uncommitted for better concurrency

        Yields:
            sqlite3.Connection: Database connection with timeout and WAL mode enabled
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=self.DB_TIMEOUT)
            conn.execute("PRAGMA journal_mode=WAL")
            if readonly:
                conn.execute("PRAGMA read_uncommitted=1")
            yield conn
            if not readonly:
                conn.commit()
        finally:
            if conn:
                conn.close()
