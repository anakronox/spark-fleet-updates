#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
platform_dmi.py

Platform identity helper - reads DMI/SMBIOS information from sysfs.

Used by NVAIAread to include platform correlation in JSON output.

Author: DGX Spark Management Team
License: MIT
"""

from pathlib import Path
from typing import Dict, Optional

DMI_SYSFS_BASE = Path("/sys/class/dmi/id")


def read_dmi_field(field_name: str) -> Optional[str]:
    """
    Read a single DMI sysfs field.
    
    Args:
        field_name: DMI field name (e.g., 'product_serial')
    
    Returns:
        Field value as string, or None if not readable
    """
    try:
        path = DMI_SYSFS_BASE / field_name
        value = path.read_text(encoding="utf-8", errors="ignore").strip()
        return value if value else None
    except Exception:
        return None


def is_valid_dmi_value(value: Optional[str]) -> bool:
    """
    Check if a DMI value is valid (not placeholder/empty).
    
    Args:
        value: DMI field value
    
    Returns:
        True if valid, False otherwise
    """
    if not value:
        return False
    
    invalid_patterns = [
        "none",
        "not specified",
        "to be filled by o.e.m.",
        "default string",
    ]
    
    normalized = value.lower().strip()
    if normalized in invalid_patterns:
        return False
    
    return True


def get_platform_identity() -> Dict[str, Optional[str]]:
    """
    Get platform identity from DMI sysfs.
    
    Returns:
        Dictionary with platform fields
    """
    fields = [
        "sys_vendor",
        "product_name",
        "product_version",
        "product_serial",
        "product_uuid",
        "chassis_asset_tag",
        "board_asset_tag",
    ]
    
    platform = {}
    
    for field in fields:
        value = read_dmi_field(field)
        if field == "product_uuid" and value:
            value = value.lower()
        platform[field] = value if is_valid_dmi_value(value) else None
    
    return platform


if __name__ == "__main__":
    # Self-test
    print("Platform Identity (DMI/SMBIOS)")
    print("-" * 40)
    
    identity = get_platform_identity()
    for field, value in identity.items():
        print(f"{field:20s}: {value or '(not set)'}")
