#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
fwupd_policy.py - fwupd update policy management for DGX Spark.

Manages:
  - fwupd-refresh.timer (enable/disable automatic firmware refresh)
  - /etc/fwupd/remotes.d/dgx-spark-local.conf (local firmware mirror)

All functions are idempotent and reversible.
Requires root for state-changing operations.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FWUPD_REMOTES_DIR = Path("/etc/fwupd/remotes.d")
DGX_REMOTE_CONF = FWUPD_REMOTES_DIR / "dgx-spark-local.conf"
FWUPD_TIMER = "fwupd-refresh.timer"
DEFAULT_REMOTE_ID = "dgx-spark-local"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: List[str], timeout: int = 30) -> Tuple[bool, str, str]:
    """Run a command; return (success, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode == 0, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return False, "", str(e)


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_fwupd_available() -> bool:
    """Return True if fwupdmgr is installed and accessible."""
    return shutil.which("fwupdmgr") is not None


# ---------------------------------------------------------------------------
# Timer management
# ---------------------------------------------------------------------------

def get_timer_status() -> Dict:
    """Return active/enabled state for the fwupd-refresh timer."""
    _, stdout_active, _ = _run(["systemctl", "is-active", FWUPD_TIMER])
    _, stdout_enabled, _ = _run(["systemctl", "is-enabled", FWUPD_TIMER])
    return {
        "timer": FWUPD_TIMER,
        "active": stdout_active.strip() == "active",
        "enabled": stdout_enabled.strip() == "enabled",
    }


def enable_timer() -> Tuple[bool, List[str]]:
    """Enable and start fwupd-refresh.timer (idempotent)."""
    if not is_fwupd_available():
        return True, []  # Nothing to enable; not an error
    ok, _, stderr = _run(["systemctl", "enable", "--now", FWUPD_TIMER])
    errors = [f"Failed to enable {FWUPD_TIMER}: {stderr.strip()}"] if not ok else []
    return ok, errors


def disable_timer() -> Tuple[bool, List[str]]:
    """Stop and disable fwupd-refresh.timer (idempotent)."""
    if not is_fwupd_available():
        return True, []
    ok, _, stderr = _run(["systemctl", "disable", "--now", FWUPD_TIMER])
    if not ok and any(
        kw in stderr.lower() for kw in ("not loaded", "not found", "no such")
    ):
        ok = True  # Already disabled
        stderr = ""
    errors = [f"Failed to disable {FWUPD_TIMER}: {stderr.strip()}"] if not ok else []
    return ok, errors


# ---------------------------------------------------------------------------
# Remote configuration
# ---------------------------------------------------------------------------

def get_remote_status() -> Dict:
    """Return current fwupd remote configuration status."""
    status: Dict = {
        "fwupd_available": is_fwupd_available(),
        "dgx_remote_configured": DGX_REMOTE_CONF.exists(),
        "remotes": [],
        "timer": get_timer_status() if is_fwupd_available() else None,
    }

    if not is_fwupd_available():
        return status

    ok, stdout, _ = _run(["fwupdmgr", "get-remotes"], timeout=15)
    if ok:
        current: Optional[Dict] = None
        for line in stdout.split("\n"):
            stripped = line.strip()
            if not stripped:
                if current:
                    status["remotes"].append(current)
                    current = None
                continue
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "Remote ID":
                    if current:
                        status["remotes"].append(current)
                    current = {"id": val}
                elif current:
                    if key == "Enabled":
                        current["enabled"] = val.lower() == "true"
                    elif key == "URI":
                        current["uri"] = val
        if current:
            status["remotes"].append(current)

    return status


def set_local_remote(
    remote_url: str,
    remote_id: str = DEFAULT_REMOTE_ID,
) -> Tuple[bool, List[str]]:
    """
    Write /etc/fwupd/remotes.d/dgx-spark-local.conf pointing at a local mirror.

    Args:
        remote_url: URL to the fwupd metadata, e.g. http://192.168.1.10/fwupd/
        remote_id:  Remote identifier (default: dgx-spark-local)
    """
    errors: List[str] = []

    try:
        FWUPD_REMOTES_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, [f"Cannot create remotes dir {FWUPD_REMOTES_DIR}: {e}"]

    content = (
        "[fwupd Remote]\n"
        "# DGX Spark Management - Local Firmware Mirror\n"
        "# Managed by spark_updatectl. Do not edit manually.\n"
        "Enabled=true\n"
        f"Title=DGX Spark Local Firmware Mirror\n"
        f"MetadataURI={remote_url}\n"
        f"RemoteId={remote_id}\n"
        "AutomaticReports=false\n"
        "AutomaticSecurityReports=false\n"
    )

    try:
        DGX_REMOTE_CONF.write_text(content, encoding="utf-8")
        DGX_REMOTE_CONF.chmod(0o644)
    except Exception as e:
        errors.append(f"Failed to write remote config {DGX_REMOTE_CONF}: {e}")
        return False, errors

    return True, errors


def reset_remote() -> Tuple[bool, List[str]]:
    """Remove the DGX Spark local fwupd remote configuration file."""
    errors: List[str] = []
    if DGX_REMOTE_CONF.exists():
        try:
            DGX_REMOTE_CONF.unlink()
        except Exception as e:
            errors.append(f"Failed to remove remote config: {e}")
            return False, errors
    return True, errors


# ---------------------------------------------------------------------------
# Live update trigger
# ---------------------------------------------------------------------------

def run_fwupd_update(dry_run: bool = False) -> Tuple[bool, str, List[str]]:
    """
    Refresh fwupd metadata and (unless dry_run) apply firmware updates.

    Returns:
        (success, combined_output, errors)
    """
    errors: List[str] = []
    output_lines: List[str] = []

    if not is_fwupd_available():
        return True, "fwupd not available; skipping firmware update", []

    # Refresh metadata
    ok, stdout, stderr = _run(["fwupdmgr", "refresh", "--force"], timeout=120)
    output_lines.append("=== fwupdmgr refresh ===")
    output_lines.append(stdout.strip())
    if not ok:
        errors.append(f"fwupdmgr refresh failed: {stderr.strip()}")
        return False, "\n".join(output_lines), errors

    if dry_run:
        ok, stdout, stderr = _run(["fwupdmgr", "get-updates"], timeout=60)
        output_lines.append("=== fwupdmgr get-updates (dry-run check) ===")
        output_lines.append(stdout.strip())
        if not ok and "nothing to do" not in stderr.lower():
            errors.append(f"fwupdmgr get-updates failed: {stderr.strip()}")
            return False, "\n".join(output_lines), errors
    else:
        ok, stdout, stderr = _run(
            ["fwupdmgr", "update", "-y", "--no-reboot-check"], timeout=600
        )
        output_lines.append("=== fwupdmgr update -y ===")
        output_lines.append(stdout.strip())
        # Exit 2 = nothing to update (not an error)
        if not ok and "nothing to do" not in stderr.lower() and "no devices" not in stdout.lower():
            errors.append(f"fwupdmgr update failed: {stderr.strip()}")
            return False, "\n".join(output_lines), errors

    return True, "\n".join(output_lines), errors
