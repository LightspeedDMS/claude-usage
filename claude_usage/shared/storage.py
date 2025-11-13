"""Base storage class for usage tracking"""

import sqlite3
from pathlib import Path


class BaseStorage:
    """Base class for SQLite database management"""

    HISTORY_RETENTION = 604800  # Keep 7 days of history

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        """Initialize storage directory and database - override in subclasses"""
        try:
            # Create storage directory if it doesn't exist
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Subclasses should override to create their specific tables
            conn = sqlite3.connect(self.db_path)
            self._create_tables(conn)
            conn.commit()
            conn.close()

        except Exception:
            # Non-fatal error - continue without storage
            pass

    def _create_tables(self, conn):
        """Create database tables - must be overridden by subclasses"""
        pass

    def get_connection(self):
        """Get a database connection"""
        return sqlite3.connect(self.db_path)
