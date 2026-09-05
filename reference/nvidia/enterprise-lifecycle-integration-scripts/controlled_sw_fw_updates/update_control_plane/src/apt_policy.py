#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
apt_policy.py - APT update policy management for DGX Spark.

Manages:
  - apt-daily.timer and apt-daily-upgrade.timer (enable/disable automatic updates)
  - /etc/apt/sources.list.d/dgx-spark-local-mirror.list (local mirror configuration)
  - Internet source enforcement: rename *.list -> *.list.disabled to enforce local-only mode

All functions are idempotent and reversible.
Requires root for state-changing operations.
"""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APT_SOURCES_DIR = Path("/etc/apt/sources.list.d")
DGX_MIRROR_LIST = APT_SOURCES_DIR / "dgx-spark-local-mirror.list"
APT_TIMERS = ["apt-daily.timer", "apt-daily-upgrade.timer"]


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
# Timer management
# ---------------------------------------------------------------------------

def get_timer_status(timer: str) -> Dict:
    """Return active/enabled state for a single systemd timer."""
    _, stdout_active, _ = _run(["systemctl", "is-active", timer])
    _, stdout_enabled, _ = _run(["systemctl", "is-enabled", timer])
    return {
        "timer": timer,
        "active": stdout_active.strip() == "active",
        "enabled": stdout_enabled.strip() == "enabled",
    }


def timers_status() -> Dict:
    """Return status dict for all managed APT timers."""
    return {t: get_timer_status(t) for t in APT_TIMERS}


def enable_timers() -> Tuple[bool, List[str]]:
    """Enable and start all APT automatic update timers (idempotent)."""
    errors: List[str] = []
    for timer in APT_TIMERS:
        ok, _, stderr = _run(["systemctl", "enable", "--now", timer])
        if not ok:
            errors.append(f"Failed to enable {timer}: {stderr.strip()}")
    return len(errors) == 0, errors


def disable_timers() -> Tuple[bool, List[str]]:
    """Stop and disable all APT automatic update timers (idempotent)."""
    errors: List[str] = []
    for timer in APT_TIMERS:
        ok, _, stderr = _run(["systemctl", "disable", "--now", timer])
        # "not loaded" / "not found" means already disabled — treat as success
        if not ok and not any(
            kw in stderr.lower() for kw in ("not loaded", "not found", "no such")
        ):
            errors.append(f"Failed to disable {timer}: {stderr.strip()}")
    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Mirror / repo management
# ---------------------------------------------------------------------------

def get_repo_status() -> Dict:
    """Return current APT source configuration status."""
    mirror_disabled_path = Path(str(DGX_MIRROR_LIST) + ".disabled")
    disabled_sources = [
        str(f) for f in APT_SOURCES_DIR.glob("*.list.disabled")
        if "dgx-spark" not in f.name
    ]
    internet_sources = [
        str(f) for f in APT_SOURCES_DIR.glob("*.list")
        if "dgx-spark" not in f.name
    ]
    return {
        "mirror_file": str(DGX_MIRROR_LIST),
        "mirror_configured": DGX_MIRROR_LIST.exists(),
        "mirror_disabled_file_exists": mirror_disabled_path.exists(),
        "internet_sources_active": internet_sources,
        "internet_sources_disabled": disabled_sources,
    }


def set_mirror(mirror_url: str) -> Tuple[bool, List[str]]:
    """
    Create/overwrite the DGX Spark local-mirror APT source list.

    Args:
        mirror_url: APT mirror base URL, e.g. http://192.168.1.10/ubuntu
    """
    errors: List[str] = []
    content = (
        "# DGX Spark Management - Local Mirror\n"
        "# Managed by spark_updatectl. Do not edit manually.\n"
        f"deb {mirror_url} noble main restricted universe multiverse\n"
    )
    try:
        APT_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
        DGX_MIRROR_LIST.write_text(content, encoding="utf-8")
        DGX_MIRROR_LIST.chmod(0o644)
    except Exception as e:
        errors.append(f"Failed to write mirror list {DGX_MIRROR_LIST}: {e}")
        return False, errors
    return True, errors


def reset_mirror() -> Tuple[bool, List[str]]:
    """Remove the DGX Spark mirror list file (re-enable disabled sources separately)."""
    errors: List[str] = []
    if DGX_MIRROR_LIST.exists():
        try:
            DGX_MIRROR_LIST.unlink()
        except Exception as e:
            errors.append(f"Failed to remove mirror list: {e}")
            return False, errors
    return True, errors


# ---------------------------------------------------------------------------
# Internet allow / deny (reversible .list -> .list.disabled renaming)
# ---------------------------------------------------------------------------

def deny_internet(exclude_dgx: bool = True) -> Tuple[bool, List[str]]:
    """
    Disable non-DGX APT sources by renaming *.list -> *.list.disabled.

    Idempotent: files already renamed are skipped.
    """
    errors: List[str] = []
    for src in APT_SOURCES_DIR.glob("*.list"):
        if exclude_dgx and "dgx-spark" in src.name:
            continue
        disabled = Path(str(src) + ".disabled")
        try:
            src.rename(disabled)
        except Exception as e:
            errors.append(f"Failed to disable {src.name}: {e}")
    return len(errors) == 0, errors


def allow_internet() -> Tuple[bool, List[str]]:
    """
    Re-enable internet APT sources by renaming *.list.disabled -> *.list.

    Skips dgx-spark managed files.  Idempotent.
    """
    errors: List[str] = []
    for disabled in APT_SOURCES_DIR.glob("*.list.disabled"):
        if "dgx-spark" in disabled.name:
            continue
        original = Path(str(disabled)[: -len(".disabled")])
        try:
            disabled.rename(original)
        except Exception as e:
            errors.append(f"Failed to re-enable {disabled.name}: {e}")
    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Live update trigger
# ---------------------------------------------------------------------------

def run_apt_update(dry_run: bool = False) -> Tuple[bool, str, List[str]]:
    """
    Run apt-get update and (unless dry_run) apt-get upgrade -y.

    Returns:
        (success, combined_output, errors)
    """
    errors: List[str] = []
    output_lines: List[str] = []

    # Always refresh package index
    ok, stdout, stderr = _run(["apt-get", "update"], timeout=120)
    output_lines.append("=== apt-get update ===")
    output_lines.append(stdout.strip())
    if not ok:
        errors.append(f"apt-get update failed: {stderr.strip()}")
        return False, "\n".join(output_lines), errors

    if dry_run:
        # Simulate upgrade (no changes)
        ok, stdout, stderr = _run(
            ["apt-get", "upgrade", "--dry-run"], timeout=120
        )
        output_lines.append("=== apt-get upgrade --dry-run ===")
        output_lines.append(stdout.strip())
        if not ok:
            errors.append(f"apt-get upgrade --dry-run failed: {stderr.strip()}")
            return False, "\n".join(output_lines), errors
    else:
        ok, stdout, stderr = _run(
            ["apt-get", "upgrade", "-y"], timeout=600
        )
        output_lines.append("=== apt-get upgrade -y ===")
        output_lines.append(stdout.strip())
        if not ok:
            errors.append(f"apt-get upgrade failed: {stderr.strip()}")
            return False, "\n".join(output_lines), errors

    return True, "\n".join(output_lines), errors
