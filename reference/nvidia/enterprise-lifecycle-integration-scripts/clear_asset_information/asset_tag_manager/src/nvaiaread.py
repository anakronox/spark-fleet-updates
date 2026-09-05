#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
nvaiaread.py

NVAIAread - Read NVAIA Asset Metadata from UEFI variable.

Command-line tool for on-demand reading and exporting of asset metadata
stored in efivarfs.

Author: DGX Spark Management Team
License: MIT
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

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
import platform_dmi

# ============================================================================
# Constants
# ============================================================================

DEFAULT_VAR_NAME = "NVAIAAssetMeta"
DEFAULT_VAR_GUID = "3b8e3c2a-2f4a-4a4b-8d2d-9f4d0c8b7b2a"

logger = logging.getLogger(__name__)


# ============================================================================
# Filtering Functions
# ============================================================================

def should_exclude_value(value: any, exclude_empty: bool) -> bool:
    """
    Check if value should be excluded based on exclude_empty flag.
    
    Args:
        value: Field value
        exclude_empty: Exclude empty flag
    
    Returns:
        True if should exclude
    """
    if not exclude_empty:
        return False
    
    if value is None:
        return True
    
    if value == "":
        return True
    
    if value == 0:
        return True
    
    return False


def filter_fields(
    fields: Dict[str, any],
    field_names: List[str],
    exclude_empty: bool
) -> Dict[str, any]:
    """
    Filter fields dict based on requested fields and exclude_empty.
    
    Args:
        fields: Dictionary of fields
        field_names: List of field names to include (empty = all)
        exclude_empty: Exclude empty values flag
    
    Returns:
        Filtered dictionary
    """
    filtered = {}
    
    for field, value in fields.items():
        # Skip if specific fields requested and this isn't one
        if field_names and field not in field_names:
            continue
        
        # Skip if exclude_empty and value is empty
        if should_exclude_value(value, exclude_empty):
            continue
        
        filtered[field] = value
    
    return filtered


# ============================================================================
# Output Formatting
# ============================================================================

def format_kv(
    group_name: str,
    fields: Dict[str, any],
    prefix: str
) -> str:
    """
    Format fields as key=value lines.
    
    Args:
        group_name: Group name
        fields: Dictionary of fields
        prefix: Prefix for field names
    
    Returns:
        Formatted string
    """
    lines = []
    for field in sorted(fields.keys()):
        value = fields[field]
        
        # Format value
        if value is None:
            value_str = ""
        elif isinstance(value, bool):
            value_str = str(value).lower()
        else:
            value_str = str(value)
        
        lines.append(f"{prefix}{field}={value_str}")
    
    return "\n".join(lines)


def format_set(
    group_name: str,
    fields: Dict[str, any],
    prefix: str
) -> str:
    """
    Format fields as SET commands.
    
    Args:
        group_name: Group name
        fields: Dictionary of fields
        prefix: Prefix for field names
    
    Returns:
        Formatted string
    """
    lines = []
    for field in sorted(fields.keys()):
        value = fields[field]
        
        # Format value (escape quotes)
        if value is None:
            value_str = ""
        elif isinstance(value, bool):
            value_str = str(value).lower()
        elif isinstance(value, str) and (" " in value or '"' in value):
            value_str = '"' + value.replace('"', '\\"') + '"'
        else:
            value_str = str(value)
        
        lines.append(f"SET {prefix}{field}={value_str}")
    
    return "\n".join(lines)


def format_json_single_group(
    group_name: str,
    fields: Dict[str, any],
    metadata: Dict[str, any],
    platform: Dict[str, any]
) -> str:
    """
    Format single group as JSON.
    
    Args:
        group_name: Group name
        fields: Dictionary of fields
        metadata: Metadata dict
        platform: Platform identity dict
    
    Returns:
        JSON string
    """
    output = {
        "group": group_name,
        "fields": fields,
        "metadata": metadata,
        "platform": platform
    }
    
    return json.dumps(output, indent=2, ensure_ascii=False)


def format_json_all_groups(
    payload: Dict,
    platform: Dict[str, any]
) -> str:
    """
    Format all groups as JSON.
    
    Args:
        payload: Full payload dict
        platform: Platform identity dict
    
    Returns:
        JSON string
    """
    output = {
        "schema": payload.get("schema"),
        "updated_at_utc": payload.get("updated_at_utc"),
        "groups": payload.get("groups", {}),
        "platform": platform
    }
    
    return json.dumps(output, indent=2, ensure_ascii=False)


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
        description="NVAIAread - Read NVAIA Asset Metadata from UEFI variable",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Read all data as JSON
  NVAIAread ALL --format json

  # Read specific group as key=value
  NVAIAread OWNERDATA

  # Read specific fields
  NVAIAread OWNERDATA LOCATION DEPARTMENT

  # Exclude empty fields
  NVAIAread USERASSETDATA --exclude-empty

  # Output as SET commands with prefix
  NVAIAread LEASEDATA --format set --prefix ASSET_

  # Write to file
  NVAIAread ALL --format json --output /tmp/asset_metadata.json

Exit codes:
  0 - Success
  1 - Read error
  2 - Argument error
"""
    )
    
    parser.add_argument(
        "group",
        help="Group name (or ALL for all groups)"
    )
    
    parser.add_argument(
        "fields",
        nargs="*",
        help="Specific fields to read (empty = all fields in group)"
    )
    
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write output to file (default: stdout)"
    )
    
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to output file (requires --output)"
    )
    
    parser.add_argument(
        "--format",
        choices=["kv", "set", "json"],
        default="kv",
        help="Output format (default: kv)"
    )
    
    parser.add_argument(
        "--exclude-empty",
        action="store_true",
        help="Exclude null, empty string, and zero values"
    )
    
    parser.add_argument(
        "--prefix",
        default="",
        help="Prefix for field names (default: none)"
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
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
    )
    
    # Validate group
    canonical_group, err = schema.normalize_group(args.group)
    if err:
        logger.error(err)
        return 2
    
    # Check append without output
    if args.append and not args.output:
        logger.error("--append requires --output")
        return 2
    
    # Check efivarfs availability
    available, err = uefi_store.check_efivarfs_available()
    if not available:
        logger.error(err)
        return 1
    
    # Read UEFI variable
    attrs, payload_bytes, parsed_json, error = uefi_store.read_efivar(args.var_name, args.var_guid)
    
    if error:
        logger.error(f"Failed to read variable: {error}")
        return 1
    
    if parsed_json is None:
        logger.error("Variable payload is not valid JSON")
        return 1
    
    # Validate schema
    is_valid, errors = schema.validate_schema_structure(parsed_json)
    if not is_valid:
        logger.warning("Payload has schema errors:")
        for err in errors:
            logger.warning(f"  - {err}")
    
    # Get platform identity
    platform = platform_dmi.get_platform_identity()
    
    # Generate output
    output_text = ""
    
    if canonical_group == "ALL":
        # Output all groups
        if args.format == "json":
            output_text = format_json_all_groups(parsed_json, platform)
        else:
            # kv or set format for all groups
            groups = parsed_json.get("groups", {})
            output_lines = []
            
            for group_name in sorted(groups.keys()):
                group_fields = groups[group_name]
                
                # Filter fields
                filtered_fields = filter_fields(
                    group_fields,
                    [],  # No specific fields for ALL
                    args.exclude_empty
                )
                
                if not filtered_fields:
                    continue
                
                if args.format == "kv":
                    group_output = format_kv(
                        group_name,
                        filtered_fields,
                        f"{args.prefix}{group_name}."
                    )
                else:  # set
                    group_output = format_set(
                        group_name,
                        filtered_fields,
                        f"{args.prefix}{group_name}."
                    )
                
                output_lines.append(group_output)
            
            output_text = "\n".join(output_lines)
    
    else:
        # Output specific group
        groups = parsed_json.get("groups", {})
        
        if canonical_group not in groups:
            logger.error(f"Group '{canonical_group}' not found in variable")
            return 1
        
        group_fields = groups[canonical_group]
        
        # Normalize requested field names
        requested_fields = []
        if args.fields:
            for field in args.fields:
                canonical_field, err = schema.normalize_field(canonical_group, field, lenient=True)
                if err:
                    logger.error(err)
                    return 2
                requested_fields.append(canonical_field)
        
        # Filter fields
        filtered_fields = filter_fields(
            group_fields,
            requested_fields,
            args.exclude_empty
        )
        
        # Format output
        if args.format == "json":
            metadata = {
                "schema": parsed_json.get("schema"),
                "updated_at_utc": parsed_json.get("updated_at_utc")
            }
            output_text = format_json_single_group(
                canonical_group,
                filtered_fields,
                metadata,
                platform
            )
        elif args.format == "kv":
            output_text = format_kv(canonical_group, filtered_fields, args.prefix)
        else:  # set
            output_text = format_set(canonical_group, filtered_fields, args.prefix)
    
    # Write output
    if args.output:
        try:
            mode = "a" if args.append else "w"
            with open(args.output, mode, encoding="utf-8") as f:
                f.write(output_text)
                f.write("\n")
            logger.info(f"Output written to {args.output}")
        except Exception as e:
            logger.error(f"Failed to write output file: {e}")
            return 1
    else:
        print(output_text)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
