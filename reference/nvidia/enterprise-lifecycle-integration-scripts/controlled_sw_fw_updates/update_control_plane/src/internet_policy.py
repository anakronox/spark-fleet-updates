#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
internet_policy.py - Internet access policy for DGX Spark update channels.

Enforces "allow" or "deny" internet mode by coordinating apt_policy and
fwupd_policy.  State is persisted in the caller's state.json via the
returned state-mutation dict.

This module is intentionally thin — all filesystem side-effects live in
apt_policy and fwupd_policy so that each concern can be tested independently.
"""

from typing import Any, Dict, List, Tuple

INTERNET_MODE_ALLOW = "allow"
INTERNET_MODE_DENY  = "deny"


def get_status(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return current internet policy status as read from persisted state.

    Args:
        state: The full state dict loaded from state.json

    Returns:
        Dict with mode, changed_at, changed_by
    """
    return {
        "mode":        state.get("internet_mode", INTERNET_MODE_ALLOW),
        "changed_at":  state.get("internet_mode_changed_at"),
        "changed_by":  state.get("internet_mode_changed_by", "unknown"),
    }


def apply_allow(apt_mod: Any, _fwupd_mod: Any) -> Tuple[bool, List[str]]:
    """
    Apply internet-allow policy:
      - Re-enable any APT sources that were disabled by deny_internet()

    Args:
        apt_mod:   apt_policy module (injected for testability)
        _fwupd_mod: fwupd_policy module (reserved for future use)
    """
    ok, errors = apt_mod.allow_internet()
    return ok, errors


def apply_deny(apt_mod: Any, _fwupd_mod: Any) -> Tuple[bool, List[str]]:
    """
    Apply internet-deny policy:
      - Disable non-DGX APT sources (rename *.list -> *.list.disabled)

    Args:
        apt_mod:   apt_policy module (injected for testability)
        _fwupd_mod: fwupd_policy module (reserved for future use)
    """
    ok, errors = apt_mod.deny_internet()
    return ok, errors


def state_update_for_allow(actor: str, timestamp: str) -> Dict[str, Any]:
    """Return the state dict fields to merge when switching to 'allow'."""
    return {
        "internet_mode":            INTERNET_MODE_ALLOW,
        "internet_mode_changed_at": timestamp,
        "internet_mode_changed_by": actor,
    }


def state_update_for_deny(actor: str, timestamp: str) -> Dict[str, Any]:
    """Return the state dict fields to merge when switching to 'deny'."""
    return {
        "internet_mode":            INTERNET_MODE_DENY,
        "internet_mode_changed_at": timestamp,
        "internet_mode_changed_by": actor,
    }
