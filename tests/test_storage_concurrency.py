"""Tests for SQLite concurrency handling in storage modules.

These tests verify that database connections are configured with:
1. Timeout parameter to prevent immediate locking failures
2. WAL mode for better concurrent access
3. Proper context manager usage for connection lifecycle
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from claude_usage.shared.storage import BaseStorage
from claude_usage.code_mode.pacemaker_integration import PaceMakerReader


class TestBaseStorageConcurrency:
    """Tests for BaseStorage concurrency handling"""

    def test_get_connection_uses_timeout(self, tmp_path):
        """Test that get_connection() uses timeout parameter"""
        db_path = tmp_path / "test.db"

        class TestStorage(BaseStorage):
            def _create_tables(self, conn):
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")

        storage = TestStorage(db_path)

        # Mock sqlite3.connect to verify timeout parameter
        with patch('claude_usage.shared.storage.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Use context manager
            with storage.get_connection() as conn:
                pass

            # Verify connect was called with timeout
            mock_connect.assert_called_once()
            call_args = mock_connect.call_args

            # Check that timeout parameter was provided
            assert 'timeout' in call_args.kwargs or len(call_args.args) >= 2
            if 'timeout' in call_args.kwargs:
                assert call_args.kwargs['timeout'] > 0
            else:
                assert call_args.args[1] > 0

    def test_get_connection_enables_wal_mode(self, tmp_path):
        """Test that get_connection() enables WAL journal mode"""
        db_path = tmp_path / "test.db"

        class TestStorage(BaseStorage):
            def _create_tables(self, conn):
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")

        storage = TestStorage(db_path)

        # Use real connection to verify WAL mode is set
        with storage.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode")
            result = cursor.fetchone()

            # WAL mode should be enabled
            assert result[0].lower() == 'wal'

    def test_get_connection_context_manager(self, tmp_path):
        """Test that get_connection() works as context manager"""
        db_path = tmp_path / "test.db"

        class TestStorage(BaseStorage):
            def _create_tables(self, conn):
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")

        storage = TestStorage(db_path)

        # Verify context manager protocol
        with storage.get_connection() as conn:
            assert conn is not None
            assert isinstance(conn, sqlite3.Connection)

            # Should be able to execute queries
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1

    def test_get_connection_commits_on_exit(self, tmp_path):
        """Test that context manager commits on normal exit"""
        db_path = tmp_path / "test.db"

        class TestStorage(BaseStorage):
            def _create_tables(self, conn):
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")

        storage = TestStorage(db_path)

        # Insert data in context manager
        with storage.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO test (id) VALUES (42)")

        # Verify data was committed
        with storage.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM test WHERE id = 42")
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == 42

    def test_get_connection_readonly_mode(self, tmp_path):
        """Test that readonly mode sets read_uncommitted pragma"""
        db_path = tmp_path / "test.db"

        class TestStorage(BaseStorage):
            def _create_tables(self, conn):
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")

        storage = TestStorage(db_path)

        # Mock to verify read_uncommitted pragma is set
        with patch('claude_usage.shared.storage.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Use readonly mode
            with storage.get_connection(readonly=True) as conn:
                pass

            # Verify read_uncommitted was set
            execute_calls = [str(call) for call in mock_conn.execute.call_args_list]
            assert any('read_uncommitted' in str(call) for call in execute_calls)


class TestPacemakerReaderConcurrency:
    """Tests for PacemakerReader concurrency handling"""

    @pytest.fixture
    def mock_pm_dir(self, tmp_path):
        """Create mock pace-maker directory structure"""
        pm_dir = tmp_path / ".claude-pace-maker"
        pm_dir.mkdir()

        # Create config file
        config_path = pm_dir / "config.json"
        config_path.write_text('{"enabled": true}')

        # Create database with required tables
        db_path = pm_dir / "usage.db"
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE usage_snapshots (
                timestamp INTEGER PRIMARY KEY,
                five_hour_util REAL,
                five_hour_resets_at TEXT,
                seven_day_util REAL,
                seven_day_resets_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE blockage_events (
                timestamp INTEGER,
                category TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE langfuse_metrics (
                bucket_timestamp REAL,
                sessions_count INTEGER,
                traces_count INTEGER,
                spans_count INTEGER
            )
        """)

        conn.commit()
        conn.close()

        return pm_dir

    def test_get_latest_usage_uses_timeout(self, mock_pm_dir, monkeypatch):
        """Test that _get_latest_usage() uses timeout parameter"""
        # Mock Path.home() to return our test directory
        monkeypatch.setattr(Path, 'home', lambda: mock_pm_dir.parent)

        reader = PaceMakerReader()

        with patch('claude_usage.code_mode.pacemaker_integration.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            reader._get_latest_usage()

            # Verify connect was called with timeout
            mock_connect.assert_called_once()
            call_args = mock_connect.call_args

            # Check timeout parameter
            assert 'timeout' in call_args.kwargs or len(call_args.args) >= 2
            if 'timeout' in call_args.kwargs:
                assert call_args.kwargs['timeout'] > 0
            else:
                assert call_args.args[1] > 0

    def test_get_latest_usage_enables_wal(self, mock_pm_dir, monkeypatch):
        """Test that _get_latest_usage() enables WAL mode"""
        monkeypatch.setattr(Path, 'home', lambda: mock_pm_dir.parent)

        reader = PaceMakerReader()

        with patch('claude_usage.code_mode.pacemaker_integration.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            reader._get_latest_usage()

            # Verify WAL mode was enabled
            execute_calls = [str(call) for call in mock_conn.execute.call_args_list]
            assert any('journal_mode' in str(call) and 'WAL' in str(call) for call in execute_calls)

    def test_get_blockage_stats_uses_timeout(self, mock_pm_dir, monkeypatch):
        """Test that get_blockage_stats() uses timeout parameter"""
        monkeypatch.setattr(Path, 'home', lambda: mock_pm_dir.parent)

        reader = PaceMakerReader()

        with patch('claude_usage.code_mode.pacemaker_integration.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            reader.get_blockage_stats()

            # Verify timeout parameter
            call_args = mock_connect.call_args
            assert 'timeout' in call_args.kwargs or len(call_args.args) >= 2

    def test_get_blockage_stats_enables_wal(self, mock_pm_dir, monkeypatch):
        """Test that get_blockage_stats() enables WAL mode"""
        monkeypatch.setattr(Path, 'home', lambda: mock_pm_dir.parent)

        reader = PaceMakerReader()

        with patch('claude_usage.code_mode.pacemaker_integration.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            reader.get_blockage_stats()

            # Verify WAL mode
            execute_calls = [str(call) for call in mock_conn.execute.call_args_list]
            assert any('journal_mode' in str(call) and 'WAL' in str(call) for call in execute_calls)

    def test_get_langfuse_metrics_uses_timeout(self, mock_pm_dir, monkeypatch):
        """Test that get_langfuse_metrics() uses timeout parameter"""
        monkeypatch.setattr(Path, 'home', lambda: mock_pm_dir.parent)

        reader = PaceMakerReader()

        with patch('claude_usage.code_mode.pacemaker_integration.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (0, 0, 0)
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            reader.get_langfuse_metrics()

            # Verify timeout parameter
            call_args = mock_connect.call_args
            assert 'timeout' in call_args.kwargs or len(call_args.args) >= 2

    def test_get_langfuse_metrics_enables_wal(self, mock_pm_dir, monkeypatch):
        """Test that get_langfuse_metrics() enables WAL mode"""
        monkeypatch.setattr(Path, 'home', lambda: mock_pm_dir.parent)

        reader = PaceMakerReader()

        with patch('claude_usage.code_mode.pacemaker_integration.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (0, 0, 0)
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            reader.get_langfuse_metrics()

            # Verify WAL mode
            execute_calls = [str(call) for call in mock_conn.execute.call_args_list]
            assert any('journal_mode' in str(call) and 'WAL' in str(call) for call in execute_calls)
