#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
nvaiawrite.py

NVAIAwrite - Write NVAIA Asset Metadata to UEFI variable.

Command-line tool for deployment-time writes and updates of asset metadata
stored in efivarfs.

Author: DGX Spark Management Team
License: MIT
"""

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add module directory to path (works from both src/ and bin/ locations)
script_path = Path(__file__).resolve()
script_dir = script_path.parent

# If script is in bin/, look for modules in same directory
# If script is in src/, modules are in same directory
if script_dir.name == 'bin':
    # Installed location: modules should be in bin/
    sys.path.insert(0, str(script_dir))
else:
    # Development location: modules are in src/
    sys.path.insert(0, str(script_dir))

import nvaia_schema as schema
import nvaia_uefi_store as uefi_store

# ============================================================================
# Constants
# ============================================================================

DEFAULT_VAR_NAME = "NVAIAAssetMeta"
DEFAULT_VAR_GUID = "3b8e3c2a-2f4a-4a4b-8d2d-9f4d0c8b7b2a"
DEFAULT_ATTRIBUTES = 0x00000007
DEFAULT_MAX_PAYLOAD = 8192
DEFAULT_COMPACT_MAX_LEN = 64

logger = logging.getLogger(__name__)


# ============================================================================
# Payload Management
# ============================================================================

def create_empty_payload() -> Dict:
    """
    Create an empty payload with schema structure.
    
    Returns:
        Empty payload dictionary
    """
    return {
        "schema": schema.SCHEMA_VERSION,
        "updated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "groups": {}
    }


def load_current_payload(var_name: str, var_guid: str) -> Tuple[Dict, Optional[str]]:
    """
    Load current payload from UEFI variable.
    
    Args:
        var_name: Variable name
        var_guid: Variable GUID
    
    Returns:
        Tuple of (payload_dict, error_message)
    """
    attrs, payload_bytes, parsed_json, error = uefi_store.read_efivar(var_name, var_guid)
    
    if error and "not found" in error.lower():
        # Variable doesn't exist yet; start with empty
        logger.info("Variable not found, starting with empty payload")
        return create_empty_payload(), None
    
    if error:
        return {}, f"Failed to read current variable: {error}"
    
    if parsed_json is None:
        logger.warning("Current variable payload is not valid JSON, starting fresh")
        return create_empty_payload(), None
    
    # Validate schema structure
    is_valid, errors = schema.validate_schema_structure(parsed_json)
    if not is_valid:
        logger.warning(f"Current payload has schema errors: {errors}")
        logger.warning("Starting with empty payload")
        return create_empty_payload(), None
    
    logger.info("Loaded current payload")
    return parsed_json, None


# ============================================================================
# Field Operations
# ============================================================================

def parse_field_value_pair(arg: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse FIELD=VALUE argument.
    
    Args:
        arg: Argument string
    
    Returns:
        Tuple of (field, value, error)
    """
    if "=" not in arg:
        return None, None, f"Invalid argument format (expected FIELD=VALUE): {arg}"
    
    field, _, value = arg.partition("=")
    
    if not field:
        return None, None, f"Empty field name in: {arg}"
    
    return field, value, None


def apply_field_update(
    payload: Dict,
    group: str,
    field: str,
    value: Optional[str],
    operation: str,  # "set", "unset", "null"
    lenient: bool
) -> Optional[str]:
    """
    Apply a field update to payload.
    
    Args:
        payload: Payload dictionary
        group: Canonical group name
        field: Canonical field name
        value: Field value (for "set" operation)
        operation: Operation type
        lenient: Lenient mode flag
    
    Returns:
        Error message or None
    """
    # Ensure groups dict exists
    if "groups" not in payload:
        payload["groups"] = {}
    
    # Ensure group exists
    if group not in payload["groups"]:
        payload["groups"][group] = {}
    
    group_data = payload["groups"][group]
    
    if operation == "set":
        # Validate field value if not lenient
        if not lenient:
            is_valid, err = schema.validate_field_value(group, field, value, lenient)
            if not is_valid:
                return err
        
        # Coerce value to appropriate type
        coerced_value = schema.coerce_field_value(field, value)
        group_data[field] = coerced_value
        logger.debug(f"Set {group}.{field} = {coerced_value}")
    
    elif operation == "unset":
        if field in group_data:
            del group_data[field]
            logger.debug(f"Unset {group}.{field}")
    
    elif operation == "null":
        group_data[field] = None
        logger.debug(f"Set {group}.{field} = null")
    
    # Validate USERDEVICE count
    if group == schema.VARIABLE_GROUP:
        is_valid, err = schema.validate_userdevice_count(group_data)
        if not is_valid:
            return err
    
    return None


def load_field_updates_from_file(file_path: str) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """
    Load FIELD=VALUE pairs from file.
    
    Args:
        file_path: Path to file
    
    Returns:
        Tuple of (list of (field, value) tuples, error)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        pairs = []
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            
            field, value, error = parse_field_value_pair(line)
            if error:
                return [], f"Line {line_num}: {error}"
            
            pairs.append((field, value))
        
        return pairs, None
    
    except FileNotFoundError:
        return [], f"File not found: {file_path}"
    except Exception as e:
        return [], f"Error reading file: {e}"


# ============================================================================
# Compact Tag Generation
# ============================================================================

def generate_compact_tag(
    payload: Dict,
    max_len: int,
    include_owner: bool
) -> str:
    """
    Generate compact tag string from payload.
    
    Format: DGXAT1;id=...;loc=...;cc=...;role=...
    
    Args:
        payload: Payload dictionary
        max_len: Maximum length
        include_owner: Include owner name (may contain PII)
    
    Returns:
        Compact tag string
    """
    groups = payload.get("groups", {})
    
    # Extract fields
    asset_number = groups.get("USERASSETDATA", {}).get("ASSET_NUMBER", "")
    location = groups.get("OWNERDATA", {}).get("LOCATION", "")
    owner_position = groups.get("OWNERDATA", {}).get("OWNERPOSITION", "")
    cost_center = groups.get("USERDEVICE", {}).get("COST_CENTER", "")
    
    # Build tag components
    components = ["DGXAT1"]  # Version prefix
    
    if asset_number:
        components.append(f"id={asset_number}")
    
    if location:
        components.append(f"loc={location}")
    
    if cost_center:
        components.append(f"cc={cost_center}")
    
    if owner_position:
        components.append(f"role={owner_position}")
    
    # Join and truncate if needed
    tag = ";".join(components)
    
    if len(tag) > max_len:
        # Drop optional components deterministically
        if cost_center:
            components = [c for c in components if not c.startswith("cc=")]
            tag = ";".join(components)
        
        if len(tag) > max_len and owner_position:
            components = [c for c in components if not c.startswith("role=")]
            tag = ";".join(components)
        
        if len(tag) > max_len:
            tag = tag[:max_len]
    
    return tag


# ============================================================================
# Main Logic
# ============================================================================

def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="NVAIAwrite - Write NVAIA Asset Metadata to UEFI variable",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set owner location
  sudo NVAIAwrite OWNERDATA LOCATION=RDU1 DEPARTMENT=Engineering

  # Set lease data from file
  sudo NVAIAwrite LEASEDATA --file lease_data.txt

  # Unset a field
  sudo NVAIAwrite USERASSETDATA --unset WARRANTY_END

  # Set a field to null
  sudo NVAIAwrite OWNERDATA --null PHONE_NUMBER

  # Dry run (no write)
  NVAIAwrite OWNERDATA LOCATION=RDU1 --dry-run

  # Emit compact tag
  sudo NVAIAwrite USERASSETDATA ASSET_NUMBER=DGX12345 --emit-compact

Exit codes:
  0 - Success
  2 - Argument error
  3 - Validation error
  4 - UEFI write error
  5 - Verification error
"""
    )
    
    parser.add_argument(
        "group",
        help="Group name (PRELOADPROFILE, USERASSETDATA, LEASEDATA, OWNERDATA, USERDEVICE)"
    )
    
    parser.add_argument(
        "field_values",
        nargs="*",
        help="FIELD=VALUE pairs"
    )
    
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Load FIELD=VALUE pairs from file (one per line)"
    )
    
    parser.add_argument(
        "--unset",
        metavar="FIELD",
        action="append",
        default=[],
        help="Remove field from group (can be repeated)"
    )
    
    parser.add_argument(
        "--null",
        metavar="FIELD",
        action="append",
        default=[],
        help="Set field to JSON null (can be repeated)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing"
    )
    
    parser.add_argument(
        "--emit-compact",
        action="store_true",
        help="Print compact tag string after write"
    )
    
    parser.add_argument(
        "--var-name",
        default=DEFAULT_VAR_NAME,
        help=f"UEFI variable name (default: {DEFAULT_VAR_NAME})"
    )
    
    parser.add_argument(
        "--var-guid",
        default=DEFAULT_VAR_GUID,
        help=f"UEFI variable GUID (default: {DEFAULT_VAR_GUID})"
    )
    
    parser.add_argument(
        "--max-payload-bytes",
        type=int,
        default=DEFAULT_MAX_PAYLOAD,
        help=f"Maximum payload size in bytes (default: {DEFAULT_MAX_PAYLOAD})"
    )
    
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="Allow unknown fields and skip type validation"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
    )
    
    # Validate group
    canonical_group, err = schema.normalize_group(args.group)
    if err:
        logger.error(err)
        return 2
    
    if canonical_group == "ALL":
        logger.error("Cannot write to pseudo-group 'ALL'")
        return 2
    
    # Check efivarfs availability
    available, err = uefi_store.check_efivarfs_available()
    if not available:
        logger.error(err)
        return 4
    
    # Load current payload
    payload, err = load_current_payload(args.var_name, args.var_guid)
    if err:
        logger.error(err)
        return 4
    
    # Collect field updates
    field_updates = []
    
    # From command line
    for arg in args.field_values:
        field, value, err = parse_field_value_pair(arg)
        if err:
            logger.error(err)
            return 2
        field_updates.append((field, value))
    
    # From file
    if args.file:
        file_updates, err = load_field_updates_from_file(args.file)
        if err:
            logger.error(err)
            return 2
        field_updates.extend(file_updates)
    
    # Check if any updates provided
    if not field_updates and not args.unset and not args.null:
        logger.error("No field updates specified (provide FIELD=VALUE, --unset, or --null)")
        return 2
    
    # Apply updates
    changes_made = False
    
    for field, value in field_updates:
        # Normalize field
        canonical_field, err = schema.normalize_field(canonical_group, field, args.lenient)
        if err:
            logger.error(err)
            return 3
        
        # Apply
        err = apply_field_update(
            payload,
            canonical_group,
            canonical_field,
            value,
            "set",
            args.lenient
        )
        if err:
            logger.error(err)
            return 3
        
        changes_made = True
    
    # Apply --unset
    for field in args.unset:
        canonical_field, err = schema.normalize_field(canonical_group, field, args.lenient)
        if err:
            logger.error(err)
            return 3
        
        err = apply_field_update(
            payload,
            canonical_group,
            canonical_field,
            None,
            "unset",
            args.lenient
        )
        if err:
            logger.error(err)
            return 3
        
        changes_made = True
    
    # Apply --null
    for field in args.null:
        canonical_field, err = schema.normalize_field(canonical_group, field, args.lenient)
        if err:
            logger.error(err)
            return 3
        
        err = apply_field_update(
            payload,
            canonical_group,
            canonical_field,
            None,
            "null",
            args.lenient
        )
        if err:
            logger.error(err)
            return 3
        
        changes_made = True
    
    # Update timestamp
    payload["updated_at_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
    
    # Validate final structure
    is_valid, errors = schema.validate_schema_structure(payload)
    if not is_valid:
        logger.error("Payload validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return 3
    
    # Estimate payload size
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    payload_size = len(payload_json.encode("utf-8"))
    
    logger.info(f"Payload size: {payload_size} bytes (max: {args.max_payload_bytes})")
    
    if payload_size > args.max_payload_bytes:
        logger.error(f"Payload exceeds max size ({payload_size} > {args.max_payload_bytes})")
        return 3
    
    # Dry run?
    if args.dry_run:
        print("=== DRY RUN (no write) ===")
        print()
        print(f"Group: {canonical_group}")
        print(f"Changes: {len(field_updates) + len(args.unset) + len(args.null)}")
        print(f"Payload size: {payload_size} bytes")
        print()
        print("Updated payload:")
        print(json.dumps(payload, indent=2))
        return 0
    
    # Write to UEFI variable
    logger.info(f"Writing UEFI variable {args.var_name}")
    success, err = uefi_store.write_efivar(
        args.var_name,
        args.var_guid,
        payload,
        DEFAULT_ATTRIBUTES,
        args.max_payload_bytes
    )
    
    if not success:
        logger.error(f"Write failed: {err}")
        return 4
    
    # Verify write
    logger.info("Verifying write...")
    success, err = uefi_store.verify_write(args.var_name, args.var_guid, payload)
    if not success:
        logger.error(f"Verification failed: {err}")
        return 5
    
    logger.info("✓ Write successful and verified")
    
    # Emit compact tag?
    if args.emit_compact:
        compact_tag = generate_compact_tag(payload, DEFAULT_COMPACT_MAX_LEN, False)
        print()
        print("Compact tag:")
        print(compact_tag)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
