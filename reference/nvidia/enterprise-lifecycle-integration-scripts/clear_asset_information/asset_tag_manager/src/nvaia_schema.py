#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
nvaia_schema.py

Schema definition and validation for NVAIA Asset Metadata stored in UEFI variables.

Defines:
- Canonical group names and their valid fields
- Field aliases (e.g., LESE_END_DATE -> LEASE_END_DATE)
- Optional type hints for validation
- Normalization functions

Schema Version: NVAIA_ASSETMETA_V1

Author: DGX Spark Management Team
License: MIT
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

# ============================================================================
# Schema Constants
# ============================================================================

SCHEMA_VERSION = "NVAIA_ASSETMETA_V1"

# Maximum keys allowed in USERDEVICE group
MAX_USERDEVICE_KEYS = 5

# ============================================================================
# Group and Field Definitions
# ============================================================================

# Fixed groups with their allowed fields (all uppercase canonical forms)
FIXED_GROUPS: Dict[str, Set[str]] = {
    "PRELOADPROFILE": {
        "IMAGEDATE",
        "IMAGE"
    },
    "USERASSETDATA": {
        "PURCHASE_DATE",
        "LAST_INVENTORIED",
        "WARRANTY_END",
        "WARRANTY_DURATION",
        "AMOUNT",
        "ASSET_NUMBER"
    },
    "LEASEDATA": {
        "LEASE_START_DATE",
        "LEASE_END_DATE",
        "LEASE_TERM",
        "LEASE_AMOUNT",
        "LESSOR"
    },
    "OWNERDATA": {
        "OWNERNAME",
        "DEPARTMENT",
        "LOCATION",
        "PHONE_NUMBER",
        "OWNERPOSITION"
    }
}

# Variable group (user-defined keys, case-sensitive)
VARIABLE_GROUP = "USERDEVICE"

# All canonical group names
ALL_GROUPS = set(FIXED_GROUPS.keys()) | {VARIABLE_GROUP}

# Field aliases (input -> canonical)
FIELD_ALIASES: Dict[str, str] = {
    "LESE_END_DATE": "LEASE_END_DATE",  # Common typo
}

# ============================================================================
# Type Hints for Validation
# ============================================================================

# Fields that should be ISO date strings (YYYY-MM-DD) or ISO datetime
DATE_FIELDS: Set[str] = {
    "IMAGEDATE",
    "PURCHASE_DATE",
    "LAST_INVENTORIED",
    "WARRANTY_END",
    "LEASE_START_DATE",
    "LEASE_END_DATE"
}

# Fields that should be integers when parseable
INTEGER_FIELDS: Set[str] = {
    "WARRANTY_DURATION",
    "LEASE_TERM"
}

# Fields that should be floats when parseable
FLOAT_FIELDS: Set[str] = {
    "AMOUNT",
    "LEASE_AMOUNT"
}


# ============================================================================
# Normalization Functions
# ============================================================================

def normalize_group(group_name: str) -> Tuple[str, Optional[str]]:
    """
    Normalize group name to canonical form.
    
    Args:
        group_name: Input group name (case-insensitive for fixed groups)
    
    Returns:
        Tuple of (canonical_name, error_message)
        If error_message is not None, group is invalid
    """
    normalized = group_name.upper()
    
    if normalized in ALL_GROUPS:
        return normalized, None
    
    # Special case: accept "ALL" as a pseudo-group for reading
    if normalized == "ALL":
        return "ALL", None
    
    return normalized, f"Unknown group: {group_name}"


def normalize_field(group: str, field_name: str, lenient: bool = False) -> Tuple[str, Optional[str]]:
    """
    Normalize field name to canonical form within a group.
    
    Args:
        group: Canonical group name
        field_name: Input field name
        lenient: If True, allow unknown fields in fixed groups
    
    Returns:
        Tuple of (canonical_name, error_message)
        If error_message is not None, field is invalid
    """
    # USERDEVICE fields are case-sensitive (user-defined)
    if group == VARIABLE_GROUP:
        # No normalization for USERDEVICE
        # Validate field name is reasonable (no special chars, reasonable length)
        if not field_name:
            return field_name, "USERDEVICE field name cannot be empty"
        if len(field_name) > 64:
            return field_name, "USERDEVICE field name too long (max 64 chars)"
        if not re.match(r'^[A-Za-z0-9_-]+$', field_name):
            return field_name, "USERDEVICE field name contains invalid characters (use A-Z, a-z, 0-9, _, -)"
        return field_name, None
    
    # Fixed groups: case-insensitive normalization
    normalized = field_name.upper()
    
    # Check aliases
    if normalized in FIELD_ALIASES:
        normalized = FIELD_ALIASES[normalized]
    
    # Check if field is valid for this group
    if group in FIXED_GROUPS:
        if normalized in FIXED_GROUPS[group]:
            return normalized, None
        elif lenient:
            # Allow unknown field in lenient mode
            return normalized, None
        else:
            valid_fields = ", ".join(sorted(FIXED_GROUPS[group]))
            return normalized, f"Unknown field '{field_name}' for group {group}. Valid: {valid_fields}"
    
    # Unknown group (shouldn't happen if normalize_group was called first)
    return normalized, f"Cannot normalize field for unknown group: {group}"


# ============================================================================
# Validation Functions
# ============================================================================

def validate_date_field(field_name: str, value: str, lenient: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate a date field value.
    
    Args:
        field_name: Field name
        value: Field value
        lenient: If True, skip validation
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if lenient:
        return True, None
    
    if not value:
        return True, None  # Empty is allowed
    
    # Try ISO date (YYYY-MM-DD)
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True, None
    except ValueError:
        pass
    
    # Try ISO datetime
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True, None
    except ValueError:
        pass
    
    return False, f"{field_name}: Invalid date format (expected YYYY-MM-DD or ISO datetime)"


def validate_integer_field(field_name: str, value: str, lenient: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate an integer field value.
    
    Args:
        field_name: Field name
        value: Field value
        lenient: If True, skip validation
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if lenient:
        return True, None
    
    if not value:
        return True, None  # Empty is allowed
    
    try:
        int(value)
        return True, None
    except ValueError:
        return False, f"{field_name}: Invalid integer value"


def validate_float_field(field_name: str, value: str, lenient: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate a float field value.
    
    Args:
        field_name: Field name
        value: Field value
        lenient: If True, skip validation
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if lenient:
        return True, None
    
    if not value:
        return True, None  # Empty is allowed
    
    try:
        float(value)
        return True, None
    except ValueError:
        return False, f"{field_name}: Invalid numeric value"


def validate_field_value(
    group: str,
    field: str,
    value: str,
    lenient: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Validate a field value based on type hints.
    
    Args:
        group: Canonical group name
        field: Canonical field name
        value: Field value (as string)
        lenient: If True, skip validation
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if field in DATE_FIELDS:
        return validate_date_field(field, value, lenient)
    elif field in INTEGER_FIELDS:
        return validate_integer_field(field, value, lenient)
    elif field in FLOAT_FIELDS:
        return validate_float_field(field, value, lenient)
    else:
        # No type constraint; any string is valid
        return True, None


def coerce_field_value(field: str, value: str) -> any:
    """
    Coerce a field value to appropriate Python type for JSON serialization.
    
    Args:
        field: Canonical field name
        value: Field value (as string)
    
    Returns:
        Coerced value (int, float, or str)
    """
    if not value:
        return value
    
    # Try integer coercion
    if field in INTEGER_FIELDS:
        try:
            return int(value)
        except ValueError:
            pass
    
    # Try float coercion
    if field in FLOAT_FIELDS:
        try:
            return float(value)
        except ValueError:
            pass
    
    # Default: keep as string
    return value


# ============================================================================
# Schema Validation
# ============================================================================

def validate_userdevice_count(fields: Dict[str, any]) -> Tuple[bool, Optional[str]]:
    """
    Validate USERDEVICE field count (max 5 keys).
    
    Args:
        fields: Dictionary of fields in USERDEVICE group
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(fields) > MAX_USERDEVICE_KEYS:
        return False, f"USERDEVICE group has {len(fields)} keys (max {MAX_USERDEVICE_KEYS})"
    
    return True, None


def validate_schema_structure(data: Dict) -> Tuple[bool, List[str]]:
    """
    Validate overall schema structure.
    
    Args:
        data: Parsed JSON payload
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check schema version
    if "schema" not in data:
        errors.append("Missing 'schema' field")
    elif data["schema"] != SCHEMA_VERSION:
        errors.append(f"Unknown schema version: {data['schema']}")
    
    # Check updated_at_utc
    if "updated_at_utc" not in data:
        errors.append("Missing 'updated_at_utc' field")
    
    # Check groups
    if "groups" not in data:
        errors.append("Missing 'groups' field")
    elif not isinstance(data["groups"], dict):
        errors.append("'groups' must be a dictionary")
    else:
        # Validate each group
        for group_name, group_data in data["groups"].items():
            canonical_group, err = normalize_group(group_name)
            if err:
                errors.append(err)
                continue
            
            if not isinstance(group_data, dict):
                errors.append(f"Group '{group_name}' must be a dictionary")
                continue
            
            # Validate USERDEVICE count
            if canonical_group == VARIABLE_GROUP:
                is_valid, err = validate_userdevice_count(group_data)
                if not is_valid:
                    errors.append(err)
    
    return (len(errors) == 0), errors


# ============================================================================
# Helper Functions
# ============================================================================

def get_all_field_names(group: str) -> List[str]:
    """
    Get all valid field names for a group.
    
    Args:
        group: Canonical group name
    
    Returns:
        List of field names (empty for USERDEVICE)
    """
    if group in FIXED_GROUPS:
        return sorted(FIXED_GROUPS[group])
    elif group == VARIABLE_GROUP:
        return []  # User-defined
    else:
        return []


def get_field_description(field: str) -> str:
    """
    Get human-readable description of a field's expected type.
    
    Args:
        field: Canonical field name
    
    Returns:
        Description string
    """
    if field in DATE_FIELDS:
        return "Date (YYYY-MM-DD or ISO datetime)"
    elif field in INTEGER_FIELDS:
        return "Integer"
    elif field in FLOAT_FIELDS:
        return "Numeric (float)"
    else:
        return "String"


if __name__ == "__main__":
    # Self-test
    print("NVAIA Schema Definition")
    print(f"Schema Version: {SCHEMA_VERSION}")
    print()
    
    print("Fixed Groups and Fields:")
    for group in sorted(FIXED_GROUPS.keys()):
        print(f"  {group}:")
        for field in sorted(FIXED_GROUPS[group]):
            desc = get_field_description(field)
            print(f"    - {field} ({desc})")
    
    print()
    print(f"Variable Group: {VARIABLE_GROUP} (max {MAX_USERDEVICE_KEYS} user-defined keys)")
    print()
    
    print("Field Aliases:")
    for alias, canonical in FIELD_ALIASES.items():
        print(f"  {alias} -> {canonical}")
