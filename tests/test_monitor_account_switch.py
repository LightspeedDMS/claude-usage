"""Issue #10: CodeMonitor must follow a Claude account switch.

Simulated: the `security` subprocess (OS boundary), platform.system(),
Path.home() (redirected to a temp dir) and the API client's network calls.
Credentials files and profile_cache.json are real temp files.
"""

import json
import shutil
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from claude_usage.code_mode.auth import token_fingerprint
from claude_usage.code_mode.monitor import CodeMonitor


def _blob(access, tier, subscription):
    """Credentials with FAKE tokens only."""
    expires = datetime.now().timestamp() * 1000 + 4 * 3600 * 1000
    return {
        "claudeAiOauth": {
            "accessToken": access,
            "refreshToken": f"refresh-{access}",
            "expiresAt": int(expires),
            "subscriptionType": subscription,
            "rateLimitTier": tier,
        }
    }


def _profile(tier):
    return {"organization": {"rate_limit_tier": tier}}


class MonitorAccountSwitchBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.home = self.temp_dir / "home"
        (self.home / ".claude-pace-maker").mkdir(parents=True)
        self.credentials_path = self.temp_dir / ".credentials.json"
        self.cache_path = self.home / ".claude-pace-maker" / "profile_cache.json"

        self.account_a = _blob("fake-token-A", "default_claude_max_5x", "enterprise")
        self.account_b = _blob("fake-token-B", "default_claude_max_20x", "max")
        self.keychain = self.account_a

        for p in (
            patch("platform.system", return_value="Darwin"),
            patch("pathlib.Path.home", return_value=self.home),
            patch(
                "claude_usage.code_mode.auth.subprocess.run",
                side_effect=self._fake_security,
            ),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _fake_security(self, *args, **kwargs):
        return subprocess.CompletedProcess([], 0, json.dumps(self.keychain), "")

    def _write_cache(self, profile, age_seconds=0, fingerprint=None, timestamp=True):
        data = {"profile": profile}
        if timestamp:
            data["timestamp"] = time.time() - age_seconds
        if fingerprint is not None:
            data["token_fingerprint"] = fingerprint
        self.cache_path.write_text(json.dumps(data))


class TestMonitorFollowsAccountSwitch(MonitorAccountSwitchBase):
    def _monitor_on_a(self):
        monitor = CodeMonitor(credentials_path=self.credentials_path)
        monitor.last_profile = _profile("default_claude_max_5x")
        return monitor

    def test_switch_drops_old_profile_even_when_pacemaker_model_succeeds(self):
        monitor = self._monitor_on_a()
        self.assertEqual(monitor.credentials["accessToken"], "fake-token-A")
        self.keychain = self.account_b  # user runs `claude /login` as account B

        with patch.object(monitor, "_refresh_from_model", return_value=True):
            with patch.object(
                monitor.api_client,
                "fetch_profile",
                return_value=(_profile("default_claude_max_20x"), "org", "acct", None),
            ):
                self.assertTrue(monitor.fetch_usage())

        self.assertEqual(monitor.credentials["accessToken"], "fake-token-B")
        self.assertEqual(
            monitor.last_profile["organization"]["rate_limit_tier"],
            "default_claude_max_20x",
        )
        saved = json.loads(self.credentials_path.read_text())["claudeAiOauth"]
        self.assertEqual(saved["accessToken"], "fake-token-B")

    def test_switch_with_failing_profile_api_does_not_keep_old_account_profile(self):
        monitor = self._monitor_on_a()
        self.keychain = self.account_b

        with patch.object(monitor, "_refresh_from_model", return_value=True):
            with patch.object(
                monitor.api_client,
                "fetch_profile",
                return_value=(None, None, None, "boom"),
            ):
                monitor.fetch_usage()

        self.assertIsNone(monitor.last_profile)

    def test_unchanged_token_keeps_profile_and_does_not_refetch(self):
        monitor = self._monitor_on_a()

        with patch.object(monitor, "_refresh_from_model", return_value=True):
            with patch.object(monitor.api_client, "fetch_profile") as fetch_profile:
                monitor.fetch_usage()

        fetch_profile.assert_not_called()
        self.assertEqual(
            monitor.last_profile["organization"]["rate_limit_tier"],
            "default_claude_max_5x",
        )

    def test_profile_recovers_next_cycle_when_api_recovers(self):
        monitor = self._monitor_on_a()
        self.keychain = self.account_b
        failing = (None, None, None, "boom")
        working = (_profile("default_claude_max_20x"), "org", "acct", None)

        with patch.object(monitor, "_refresh_from_model", return_value=True):
            with patch.object(
                monitor.api_client, "fetch_profile", return_value=failing
            ):
                monitor.fetch_usage()
            self.assertIsNone(monitor.last_profile)

            with patch.object(
                monitor.api_client, "fetch_profile", return_value=working
            ):
                monitor.fetch_usage()

        self.assertEqual(
            monitor.last_profile["organization"]["rate_limit_tier"],
            "default_claude_max_20x",
        )

    def test_profile_recovers_next_cycle_from_matching_fingerprint_cache(self):
        monitor = self._monitor_on_a()
        self.keychain = self.account_b
        failing = (None, None, None, "boom")

        with patch.object(monitor, "_refresh_from_model", return_value=True):
            with patch.object(
                monitor.api_client, "fetch_profile", return_value=failing
            ):
                monitor.fetch_usage()
                self.assertIsNone(monitor.last_profile)

                self._write_cache(
                    _profile("default_claude_max_20x"),
                    fingerprint=token_fingerprint("fake-token-B"),
                )
                monitor.fetch_usage()

        self.assertEqual(
            monitor.last_profile["organization"]["rate_limit_tier"],
            "default_claude_max_20x",
        )

    def test_switch_ignores_old_accounts_cached_profile(self):
        monitor = self._monitor_on_a()
        self._write_cache(
            _profile("default_claude_max_5x"),
            fingerprint=token_fingerprint("fake-token-A"),
        )
        self.keychain = self.account_b

        with patch.object(monitor, "_refresh_from_model", return_value=True):
            with patch.object(
                monitor.api_client,
                "fetch_profile",
                return_value=(None, None, None, "boom"),
            ):
                monitor.fetch_usage()

        self.assertIsNone(monitor.last_profile)


class TestProfileCacheValidation(MonitorAccountSwitchBase):
    def _monitor(self):
        return CodeMonitor(credentials_path=self.credentials_path)

    def test_stale_cache_is_ignored(self):
        monitor = self._monitor()
        age = CodeMonitor.PROFILE_CACHE_MAX_AGE_SECONDS + 60
        self._write_cache(_profile("t"), age_seconds=age)
        self.assertIsNone(monitor._load_profile_cache())

    def test_default_max_age_is_24_hours(self):
        self.assertEqual(CodeMonitor.PROFILE_CACHE_MAX_AGE_SECONDS, 24 * 60 * 60)

    def test_mismatched_fingerprint_is_ignored(self):
        monitor = self._monitor()
        self._write_cache(_profile("t"), fingerprint=token_fingerprint("other-token"))
        self.assertIsNone(monitor._load_profile_cache())

    def test_matching_fingerprint_within_age_is_used(self):
        monitor = self._monitor()
        self._write_cache(
            _profile("t"),
            age_seconds=3600,
            fingerprint=token_fingerprint("fake-token-A"),
        )
        self.assertEqual(monitor._load_profile_cache(), _profile("t"))

    def test_legacy_cache_without_fingerprint_within_age_is_used(self):
        monitor = self._monitor()
        self._write_cache(_profile("t"), age_seconds=3600)
        self.assertEqual(monitor._load_profile_cache(), _profile("t"))

    def test_legacy_cache_without_fingerprint_but_stale_is_ignored(self):
        monitor = self._monitor()
        self._write_cache(
            _profile("t"), age_seconds=CodeMonitor.PROFILE_CACHE_MAX_AGE_SECONDS + 1
        )
        self.assertIsNone(monitor._load_profile_cache())

    def test_cache_without_timestamp_is_ignored(self):
        monitor = self._monitor()
        self._write_cache(_profile("t"), timestamp=False)
        self.assertIsNone(monitor._load_profile_cache())

    def test_corrupt_cache_is_ignored_and_logged_at_debug(self):
        monitor = self._monitor()
        self.cache_path.write_text("{not json")

        with self.assertLogs(level="DEBUG") as logs:
            result = monitor._load_profile_cache()

        self.assertIsNone(result)
        self.assertTrue(any("JSONDecodeError" in line for line in logs.output))

    def test_monitor_never_writes_the_cache(self):
        monitor = self._monitor()
        self._write_cache(_profile("t"), fingerprint=token_fingerprint("other-token"))
        before = self.cache_path.read_text()
        monitor._load_profile_cache()
        self.assertEqual(self.cache_path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
