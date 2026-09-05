#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
repo_manager.py - Central repository management coordinator for DGX Spark.

Provides a unified interface over apt_policy and fwupd_policy so that
spark_updatectl commands that span both subsystems (e.g. repo set/reset/status)
have a single call-site.

All state mutations are returned as dicts to be merged into state.json by
the caller (spark_updatectl).  No direct I/O to state.json here.
"""

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def get_status(
    apt_mod: Any,
    fwupd_mod: Any,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Return a combined repo/internet status snapshot.

    Args:
        apt_mod:    apt_policy module
        fwupd_mod:  fwupd_policy module
        state:      current persisted state dict
    """
    return {
        "apt":              apt_mod.get_repo_status(),
        "apt_timers":       apt_mod.timers_status(),
        "fwupd":            fwupd_mod.get_remote_status(),
        "internet_mode":    state.get("internet_mode", "allow"),
        "local_mirror_url": state.get("local_mirror_url"),
        "fwupd_remote_url": state.get("fwupd_remote_url"),
    }


# ---------------------------------------------------------------------------
# Set
# ---------------------------------------------------------------------------

def set_repo(
    apt_mod: Any,
    fwupd_mod: Any,
    mirror_url: Optional[str],
    fwupd_url:  Optional[str],
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Configure local mirror URLs for APT and/or fwupd.

    Returns:
        (success, errors, state_update)
        where state_update is a dict to be merged into state.json
    """
    errors: List[str] = []
    state_update: Dict[str, Any] = {}

    if mirror_url:
        ok, errs = apt_mod.set_mirror(mirror_url)
        errors.extend(errs)
        if ok:
            state_update["local_mirror_url"] = mirror_url

    if fwupd_url:
        ok, errs = fwupd_mod.set_local_remote(fwupd_url)
        errors.extend(errs)
        if ok:
            state_update["fwupd_remote_url"] = fwupd_url

    return len(errors) == 0, errors, state_update


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def reset_repo(
    apt_mod: Any,
    fwupd_mod: Any,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Remove all DGX Spark-managed repo/remote configuration and re-enable
    any APT sources that were disabled.

    Returns:
        (success, errors, state_update)
    """
    errors: List[str] = []
    state_update: Dict[str, Any] = {
        "local_mirror_url": None,
        "fwupd_remote_url": None,
    }

    ok1, errs1 = apt_mod.reset_mirror()
    errors.extend(errs1)

    ok2, errs2 = apt_mod.allow_internet()
    errors.extend(errs2)

    ok3, errs3 = fwupd_mod.reset_remote()
    errors.extend(errs3)

    return len(errors) == 0, errors, state_update
