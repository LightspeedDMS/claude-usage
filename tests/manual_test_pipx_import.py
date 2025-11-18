#!/usr/bin/env python3
"""Manual test for pipx import functionality

This test verifies that the pacemaker integration correctly detects and imports
from pipx installations.

Prerequisites:
- claude-pace-maker installed via pipx
- Active pace-maker configuration in ~/.claude-pace-maker/

Usage:
    python tests/manual_test_pipx_import.py
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_usage.code_mode.pacemaker_integration import (
    PaceMakerReader,
    _is_pipx_installation,
    _find_pipx_site_packages,
)


def test_pipx_detection():
    """Test pipx installation detection"""
    print("\n=== Testing Pipx Installation Detection ===")

    # Test various paths
    test_paths = [
        (
            "/home/user/.local/share/pipx/venvs/claude-pace-maker/share/claude-pace-maker",
            True,
            "pipx installation",
        ),
        ("/home/user/dev/claude-pace-maker", False, "dev installation"),
        ("/usr/local/lib/python3.9/site-packages", False, "system installation"),
    ]

    for path, expected, description in test_paths:
        result = _is_pipx_installation(path)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {description}: {path}")
        print(f"     Expected: {expected}, Got: {result}")

    print()


def test_site_packages_finder():
    """Test site-packages directory finder"""
    print("\n=== Testing Site-Packages Finder ===")

    reader = PaceMakerReader()
    install_source_file = reader.pm_dir / "install_source"

    if not install_source_file.exists():
        print(
            "  ℹ️  No install_source file found - pace-maker not installed or not configured"
        )
        return

    with open(install_source_file) as f:
        source_path = f.read().strip()

    print(f"  Install source path: {source_path}")

    is_pipx = _is_pipx_installation(source_path)
    print(f"  Is pipx installation: {is_pipx}")

    if is_pipx:
        site_packages = _find_pipx_site_packages(source_path)
        if site_packages:
            print(f"  ✓ Found site-packages: {site_packages}")
            # Verify pacemaker module exists
            pacemaker_path = Path(site_packages) / "pacemaker"
            if pacemaker_path.exists():
                print(f"  ✓ pacemaker module exists at: {pacemaker_path}")
            else:
                print(f"  ✗ pacemaker module NOT found at: {pacemaker_path}")
        else:
            print("  ✗ Could not find site-packages directory")
    else:
        print("  ℹ️  Not a pipx installation - using src directory approach")

    print()


def test_full_integration():
    """Test full pacemaker integration with real installation"""
    print("\n=== Testing Full Pacemaker Integration ===")

    reader = PaceMakerReader()

    if not reader.is_installed():
        print("  ℹ️  Pace-maker not installed - skipping integration test")
        return

    print(f"  ✓ Pace-maker installed at: {reader.pm_dir}")
    print(f"  Enabled: {reader.is_enabled()}")

    # Try to get status (this will test the import)
    status = reader.get_status()

    if status:
        if "error" in status:
            print(f"  ✗ Error getting status: {status['error']}")
        else:
            print("  ✓ Successfully imported and got status")
            print(f"     Has data: {status.get('has_data', False)}")
            if status.get("has_data"):
                print(f"     Algorithm: {status.get('algorithm', 'unknown')}")
                print(f"     Should throttle: {status.get('should_throttle', False)}")
                if status.get("should_throttle"):
                    print(f"     Delay: {status.get('delay_seconds', 0)}s")
    else:
        print("  ✗ Failed to get status (returned None)")

    print()


def main():
    """Run all manual tests"""
    print("\n" + "=" * 60)
    print("Manual Test: Pipx Import Functionality")
    print("=" * 60)

    try:
        test_pipx_detection()
        test_site_packages_finder()
        test_full_integration()

        print("=" * 60)
        print("Manual test completed")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
