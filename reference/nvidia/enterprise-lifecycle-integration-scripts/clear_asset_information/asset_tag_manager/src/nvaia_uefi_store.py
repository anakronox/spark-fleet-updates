#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
nvaia_uefi_store.py

Low-level efivarfs read/write handler for NVAIA Asset Metadata.

Handles:
- Reading/writing UEFI variables via /sys/firmware/efi/efivars
- First 4 bytes: little-endian uint32 attributes
- Remainder: UTF-8 JSON payload
- Immutable flag handling (chattr -i/+i)
- Payload size enforcement

Safety Features:
- Only touches exactly one configured var_name+var_guid
- Requires root for writes
- Enforces max payload size
- Best-effort immutable flag handling

Author: DGX Spark Management Team
License: MIT
"""

import json
import logging
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

# ============================================================================
# Constants
# ============================================================================

EFIVARFS_BASE = Path("/sys/firmware/efi/efivars")

# Default UEFI variable attributes (NV|BS|RT)
DEFAULT_ATTRIBUTES = 0x00000007

# Hard upper bound for payload size (confirmed on DGX Spark)
HARD_MAX_PAYLOAD_BYTES = 32768

# Default max payload (conservative)
DEFAULT_MAX_PAYLOAD_BYTES = 8192

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def build_efivar_path(var_name: str, var_guid: str) -> Path:
    """
    Build efivarfs file path.
    
    Args:
        var_name: Variable name
        var_guid: Variable GUID (with hyphens)
    
    Returns:
        Path to efivar file
    """
    filename = f"{var_name}-{var_guid}"
    return EFIVARFS_BASE / filename


def is_immutable(path: Path) -> bool:
    """
    Check if file has immutable flag set (best-effort).
    
    Args:
        path: File path
    
    Returns:
        True if immutable flag detected
    """
    try:
        lsattr = shutil.which("lsattr")
        if not lsattr:
            return False
        
        result = subprocess.run(
            [lsattr, str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )
        
        # lsattr output: "----i--------e----- /path/to/file"
        # Check for 'i' flag
        output = result.stdout.strip()
        if output:
            flags = output.split()[0]
            return 'i' in flags
    
    except Exception as e:
        logger.debug(f"lsattr check failed: {e}")
    
    return False


def remove_immutable(path: Path) -> bool:
    """
    Remove immutable flag from file (best-effort).
    
    Args:
        path: File path
    
    Returns:
        True if successful or already not immutable
    """
    if not path.exists():
        return True
    
    try:
        chattr = shutil.which("chattr")
        if not chattr:
            logger.debug("chattr not found, skipping immutable flag removal")
            return True
        
        subprocess.run(
            [chattr, "-i", str(path)],
            capture_output=True,
            timeout=5,
            check=True
        )
        
        logger.debug(f"Removed immutable flag from {path}")
        return True
    
    except subprocess.CalledProcessError as e:
        logger.warning(f"chattr -i failed: {e}")
        return False
    except Exception as e:
        logger.warning(f"remove_immutable error: {e}")
        return False


def set_immutable(path: Path) -> bool:
    """
    Set immutable flag on file (best-effort).
    
    Args:
        path: File path
    
    Returns:
        True if successful
    """
    if not path.exists():
        return False
    
    try:
        chattr = shutil.which("chattr")
        if not chattr:
            logger.debug("chattr not found, skipping immutable flag setting")
            return True
        
        subprocess.run(
            [chattr, "+i", str(path)],
            capture_output=True,
            timeout=5,
            check=True
        )
        
        logger.debug(f"Set immutable flag on {path}")
        return True
    
    except subprocess.CalledProcessError as e:
        logger.debug(f"chattr +i failed (non-fatal): {e}")
        return False
    except Exception as e:
        logger.debug(f"set_immutable error (non-fatal): {e}")
        return False


# ============================================================================
# Read Functions
# ============================================================================

def read_efivar(
    var_name: str,
    var_guid: str
) -> Tuple[Optional[int], Optional[bytes], Optional[Dict], Optional[str]]:
    """
    Read UEFI variable and parse payload.
    
    Args:
        var_name: Variable name
        var_guid: Variable GUID
    
    Returns:
        Tuple of:
        - attributes (uint32 or None)
        - payload_bytes (bytes or None)
        - parsed_json (dict or None)
        - error (str or None)
    """
    path = build_efivar_path(var_name, var_guid)
    
    if not path.exists():
        return None, None, None, f"Variable not found: {path}"
    
    try:
        with open(path, "rb") as f:
            raw_data = f.read()
        
        if len(raw_data) < 4:
            return None, None, None, "Variable data too short (< 4 bytes)"
        
        # First 4 bytes: little-endian uint32 attributes
        attributes = struct.unpack("<I", raw_data[:4])[0]
        
        # Remainder: payload
        payload_bytes = raw_data[4:]
        
        # Try to parse as UTF-8 JSON
        parsed_json = None
        error = None
        
        if payload_bytes:
            try:
                payload_str = payload_bytes.decode("utf-8")
                parsed_json = json.loads(payload_str)
            except UnicodeDecodeError as e:
                error = f"Payload not valid UTF-8: {e}"
            except json.JSONDecodeError as e:
                error = f"Payload not valid JSON: {e}"
        
        logger.debug(f"Read efivar {var_name}: {len(payload_bytes)} bytes, attrs=0x{attributes:08x}")
        
        return attributes, payload_bytes, parsed_json, error
    
    except PermissionError:
        return None, None, None, f"Permission denied reading {path}"
    except Exception as e:
        return None, None, None, f"Read error: {e}"


# ============================================================================
# Write Functions
# ============================================================================

def write_efivar(
    var_name: str,
    var_guid: str,
    payload_dict: Dict,
    attributes: int = DEFAULT_ATTRIBUTES,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
) -> Tuple[bool, Optional[str]]:
    """
    Write UEFI variable with JSON payload.
    
    Args:
        var_name: Variable name
        var_guid: Variable GUID
        payload_dict: Python dict to serialize as JSON
        attributes: UEFI variable attributes
        max_payload_bytes: Maximum payload size
    
    Returns:
        Tuple of (success, error_message)
    """
    # Check root
    if os.geteuid() != 0:
        return False, "Write requires root permissions (run with sudo)"
    
    # Enforce hard max
    if max_payload_bytes > HARD_MAX_PAYLOAD_BYTES:
        return False, f"max_payload_bytes {max_payload_bytes} exceeds hard limit {HARD_MAX_PAYLOAD_BYTES}"
    
    # Serialize payload (deterministic, compact)
    try:
        payload_str = json.dumps(
            payload_dict,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':')
        )
        payload_bytes = payload_str.encode("utf-8")
    except Exception as e:
        return False, f"JSON serialization error: {e}"
    
    # Check payload size
    if len(payload_bytes) > max_payload_bytes:
        return False, (
            f"Payload size {len(payload_bytes)} exceeds max {max_payload_bytes} bytes. "
            f"Consider removing data or increasing --max-payload-bytes (hard limit {HARD_MAX_PAYLOAD_BYTES})"
        )
    
    # Build efivar blob: 4-byte attrs + payload
    attrs_bytes = struct.pack("<I", attributes)
    efivar_blob = attrs_bytes + payload_bytes
    
    path = build_efivar_path(var_name, var_guid)
    
    logger.info(f"Writing efivar {var_name} ({len(payload_bytes)} bytes payload, attrs=0x{attributes:08x})")
    
    # Handle immutable flag
    if path.exists():
        if is_immutable(path):
            logger.debug(f"Immutable flag detected on {path}, attempting removal")
            if not remove_immutable(path):
                return False, f"Could not remove immutable flag from {path}. Try manually: sudo chattr -i {path}"
    
    # Write efivar
    try:
        with open(path, "wb") as f:
            f.write(efivar_blob)
        
        logger.info(f"Successfully wrote efivar {var_name}")
    
    except PermissionError:
        return False, f"Permission denied writing {path} (run with sudo)"
    except OSError as e:
        if e.errno == 28:  # ENOSPC
            return False, f"No space left in NVRAM. Try removing other variables or reducing payload size"
        else:
            return False, f"Write error: {e}"
    except Exception as e:
        return False, f"Write error: {e}"
    
    # Best-effort: set immutable flag
    set_immutable(path)
    
    return True, None


def verify_write(
    var_name: str,
    var_guid: str,
    expected_payload_dict: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Verify that written UEFI variable matches expected payload.
    
    Args:
        var_name: Variable name
        var_guid: Variable GUID
        expected_payload_dict: Expected payload
    
    Returns:
        Tuple of (success, error_message)
    """
    attrs, payload_bytes, parsed_json, error = read_efivar(var_name, var_guid)
    
    if error:
        return False, f"Verification read failed: {error}"
    
    if parsed_json is None:
        return False, "Verification failed: payload not valid JSON"
    
    # Compare dictionaries
    # Normalize both to JSON strings for comparison (handles ordering)
    expected_str = json.dumps(expected_payload_dict, sort_keys=True)
    actual_str = json.dumps(parsed_json, sort_keys=True)
    
    if expected_str != actual_str:
        return False, "Verification failed: payload mismatch"
    
    logger.info(f"Verification successful: {var_name}")
    return True, None


# ============================================================================
# Utility Functions
# ============================================================================

def delete_efivar(var_name: str, var_guid: str) -> Tuple[bool, Optional[str]]:
    """
    Delete UEFI variable (USE WITH CAUTION).
    
    Args:
        var_name: Variable name
        var_guid: Variable GUID
    
    Returns:
        Tuple of (success, error_message)
    """
    if os.geteuid() != 0:
        return False, "Delete requires root permissions (run with sudo)"
    
    path = build_efivar_path(var_name, var_guid)
    
    if not path.exists():
        return True, None  # Already deleted
    
    # Remove immutable flag if present
    if is_immutable(path):
        logger.debug(f"Removing immutable flag before delete")
        if not remove_immutable(path):
            return False, f"Could not remove immutable flag. Try: sudo chattr -i {path}"
    
    try:
        path.unlink()
        logger.info(f"Deleted efivar {var_name}")
        return True, None
    
    except PermissionError:
        return False, f"Permission denied deleting {path} (run with sudo)"
    except Exception as e:
        return False, f"Delete error: {e}"


def check_efivarfs_available() -> Tuple[bool, Optional[str]]:
    """
    Check if efivarfs is available and mounted.
    
    Returns:
        Tuple of (available, error_message)
    """
    if not EFIVARFS_BASE.exists():
        return False, f"efivarfs not mounted at {EFIVARFS_BASE}"
    
    if not EFIVARFS_BASE.is_dir():
        return False, f"{EFIVARFS_BASE} is not a directory"
    
    # Check if writable (needs root)
    if os.geteuid() == 0:
        if not os.access(EFIVARFS_BASE, os.W_OK):
            return False, f"{EFIVARFS_BASE} is not writable (check mount options)"
    
    return True, None


if __name__ == "__main__":
    # Self-test
    print("NVAIA UEFI Store - Self Test")
    print(f"efivarfs base: {EFIVARFS_BASE}")
    
    available, error = check_efivarfs_available()
    if available:
        print("✓ efivarfs is available")
    else:
        print(f"✗ efivarfs not available: {error}")
    
    print(f"Default attributes: 0x{DEFAULT_ATTRIBUTES:08x}")
    print(f"Default max payload: {DEFAULT_MAX_PAYLOAD_BYTES} bytes")
    print(f"Hard max payload: {HARD_MAX_PAYLOAD_BYTES} bytes")
