#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Shared asset identity resolution for DGX Spark Management Tools.

Provides:
  - resolve_asset_id()    canonical asset ID + source via priority chain
  - get_platform_dmi()    standardized platform_dmi summary dict
  - load_identity_file()  load device_identity.json, unwrapping envelope if present

Priority chain for resolve_asset_id():
  1. SMBIOS product serial
  2. SMBIOS product UUID
  3. Baseboard serial
  4. OS machine-id (/etc/machine-id)
  5. Primary NIC MAC address
  6. Persisted UUID (generated once, stored at PERSISTED_UUID_PATH)

Author: DGX Spark Management Team
Version: 1.0.0
"""

import json
import os
import re
import socket
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

__version__ = "1.0.0"

# ── Paths ────────────────────────────────────────────────────────────────────

DMI_BASE = Path("/sys/class/dmi/id")
MACHINE_ID_FILE = Path("/etc/machine-id")
PERSISTED_UUID_PATH = Path("/var/lib/dgx_spark_management/asset_id.uuid")

# ── Validation ────────────────────────────────────────────────────────────────

NULL_UUID = "00000000-0000-0000-0000-000000000000"
INVALID_VALUES = {
    "none",
    "not specified",
    "to be filled by o.e.m.",
    "to be filled by o.e.m",
    "default string",
    "system serial number",
    "system product name",
    "base board serial number",
}


def _is_valid(value: str, field: str = "") -> bool:
    if not value or not value.strip():
        return False
    v = value.lower().strip()
    if v in INVALID_VALUES:
        return False
    if field == "product_uuid" and v == NULL_UUID.lower():
        return False
    return True


# ── Low-level readers ─────────────────────────────────────────────────────────

def _read_dmi(field: str) -> str:
    """Read a single DMI sysfs field, returning '' on any failure."""
    path = DMI_BASE / field
    try:
        if not path.exists() or not path.is_file():
            return ""
        value = path.read_text(encoding="utf-8", errors="ignore")
        value = value.replace("\x00", "").strip()
        if field == "product_uuid":
            value = value.lower()
        return value if _is_valid(value, field) else ""
    except (OSError, IOError, PermissionError):
        return ""


def _read_machine_id() -> str:
    """Read /etc/machine-id."""
    try:
        if MACHINE_ID_FILE.exists():
            mid = MACHINE_ID_FILE.read_text(encoding="utf-8").strip()
            mid = mid.replace("\x00", "").replace(" ", "")
            return mid if mid else ""
    except (OSError, IOError, PermissionError):
        pass
    return ""


def _get_primary_nic_mac() -> str:
    """
    Return the MAC address of the first stable physical NIC.

    Reads /sys/class/net/<iface>/address and skips loopback, virtual,
    and all-zero MACs.  Returns '' if nothing usable is found.
    """
    net_dir = Path("/sys/class/net")
    if not net_dir.exists():
        return ""

    candidates = []
    for iface_path in sorted(net_dir.iterdir()):
        iface = iface_path.name
        if iface == "lo":
            continue
        # Skip virtual/container interfaces that lack a real device link
        device_link = iface_path / "device"
        if not device_link.exists():
            continue
        addr_file = iface_path / "address"
        try:
            mac = addr_file.read_text(encoding="utf-8").strip().lower()
        except (OSError, IOError):
            continue
        if not mac or mac in ("", "00:00:00:00:00:00"):
            continue
        # Prefer non-infiniband, non-USB interfaces (ib*, usb*)
        if not re.match(r"^(ib|usb)", iface):
            candidates.insert(0, mac)
        else:
            candidates.append(mac)

    return candidates[0] if candidates else ""


def _load_or_create_persisted_uuid() -> str:
    """
    Return a persisted UUID for this host, generating one if needed.

    Stored at PERSISTED_UUID_PATH.  Generation failures are silently
    ignored and a fresh UUID is returned without persisting.
    """
    try:
        if PERSISTED_UUID_PATH.exists():
            stored = PERSISTED_UUID_PATH.read_text(encoding="utf-8").strip()
            if stored:
                return stored
    except (OSError, IOError, PermissionError):
        pass

    new_uuid = str(uuid.uuid4())
    try:
        PERSISTED_UUID_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        PERSISTED_UUID_PATH.write_text(new_uuid + "\n", encoding="utf-8")
        try:
            PERSISTED_UUID_PATH.chmod(0o644)
        except OSError:
            pass
    except (OSError, IOError, PermissionError):
        pass  # Return UUID even if we couldn't persist it

    return new_uuid


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_asset_id() -> Tuple[str, str]:
    """
    Return (asset_id, asset_id_source) using the canonical priority chain.

    Chain:
      1. SMBIOS product serial  -> "smbios_serial"
      2. SMBIOS product UUID    -> "smbios_uuid"
      3. Baseboard serial       -> "board_serial"
      4. OS machine-id          -> "machine_id"
      5. Primary NIC MAC        -> "nic_mac"
      6. Persisted UUID         -> "persisted_uuid"
    """
    serial = _read_dmi("product_serial")
    if serial:
        return serial, "smbios_serial"

    prod_uuid = _read_dmi("product_uuid")
    if prod_uuid:
        return prod_uuid, "smbios_uuid"

    board_serial = _read_dmi("board_serial")
    if board_serial:
        return board_serial, "board_serial"

    machine_id = _read_machine_id()
    if machine_id:
        return machine_id, "machine_id"

    mac = _get_primary_nic_mac()
    if mac:
        return mac, "nic_mac"

    persisted = _load_or_create_persisted_uuid()
    return persisted, "persisted_uuid"


def get_platform_dmi() -> Dict[str, str]:
    """
    Return a standardized platform_dmi summary dict.

    Keys always present (empty string when unavailable):
      sys_vendor, product_name, product_version,
      product_serial, product_uuid,
      board_vendor, board_name, board_serial,
      chassis_serial
    """
    return {
        "sys_vendor": _read_dmi("sys_vendor"),
        "product_name": _read_dmi("product_name"),
        "product_version": _read_dmi("product_version"),
        "product_serial": _read_dmi("product_serial"),
        "product_uuid": _read_dmi("product_uuid"),
        "board_vendor": _read_dmi("board_vendor"),
        "board_name": _read_dmi("board_name"),
        "board_serial": _read_dmi("board_serial"),
        "chassis_serial": _read_dmi("chassis_serial"),
    }


def load_identity_file(path: str) -> Dict:
    """
    Load a device_identity JSON file, unwrapping envelope format if present.

    Supports both:
      - Legacy flat format:   {"asset_id": ..., "product_serial": ..., ...}
      - Envelope format:      {"ok": true, "data": {"asset_id": ..., ...}, ...}

    Returns the inner data dict, or {} on any failure.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {}
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            # Unwrap envelope format
            if "ok" in raw and "data" in raw and isinstance(raw["data"], dict):
                return raw["data"]
            return raw
    except (OSError, IOError, PermissionError, json.JSONDecodeError):
        pass
    return {}
