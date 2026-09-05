#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Hardware Inventory Collector - Device Identity Module

Collects stable device identity from DMI/SMBIOS and generates canonical JSON
identity file for asset tracking and management.

Requirements:
    - Python 3.6+
    - Standard library only (no external dependencies)
    - Read access to /sys/class/dmi/id/
    - Write access to output directory (when not using --print)

Exit Codes:
    0 - Success
    Non-zero - Unexpected failure

Author: DGX Spark Management Team
Version: 1.0.0
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# Add common module to path (works from both src/ and bin/ locations)
script_dir = Path(__file__).parent
# Check if we're in bin/ or in src/
if script_dir.name == 'bin':
    # Running from bin/, common is at bin/common/
    common_path = script_dir / "common"
else:
    # Running from src/, common is at project root
    common_path = script_dir.parent.parent.parent / "common"
sys.path.insert(0, str(common_path))

from cli_base import (
    format_envelope,
    create_base_parser,
    setup_logging as cli_setup_logging,
    write_output,
    ExitCode,
)
from output import (emit_ok, emit_error, log as olog, route_output, set_quiet,
                    make_error, EC_GENERAL, EC_INTERRUPTED, WC_NO_ASSET_ID,
                    EXIT_SUCCESS, EXIT_GENERAL_ERROR, EXIT_INTERRUPTED)
from asset_id import resolve_asset_id, get_platform_dmi

__version__ = "1.1.0"  # Bumped for CLI standardization
_TOOL = "device_identity"
_FUNCTIONAL_AREA = "clear_asset_information"

# Constants
DMI_BASE = Path("/sys/class/dmi/id")
DMI_FIELDS = {
    "product_serial": DMI_BASE / "product_serial",
    "product_uuid": DMI_BASE / "product_uuid",
    "board_serial": DMI_BASE / "board_serial",
    "chassis_serial": DMI_BASE / "chassis_serial",
    "sys_vendor": DMI_BASE / "sys_vendor",
    "product_name": DMI_BASE / "product_name",
    "product_version": DMI_BASE / "product_version",
}

MACHINE_ID_FILE = Path("/etc/machine-id")
DEFAULT_OUTPUT_PATH = Path(f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.json")
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"

# Validation constants
NULL_UUID = "00000000-0000-0000-0000-000000000000"
INVALID_VALUES = {
    "none",
    "not specified",
    "to be filled by o.e.m.",
    "to be filled by o.e.m",
    "default string",
    "system serial number",
    "system product name",
}


def is_valid_value(value: str, field_name: str = "") -> bool:
    """
    Check if a DMI value is valid (not a placeholder or empty).
    
    Args:
        value: The value to validate
        field_name: Optional field name for UUID-specific validation
        
    Returns:
        True if valid, False if invalid
    """
    if not value or not value.strip():
        return False
    
    # Check against invalid patterns (case-insensitive)
    if value.lower().strip() in INVALID_VALUES:
        return False
    
    # UUID-specific validation
    if field_name == "product_uuid":
        if value.lower().strip() == NULL_UUID.lower():
            return False
    
    return True


def read_dmi_field(field_path: Path) -> str:
    """
    Read a DMI field from sysfs and normalize it.
    
    Args:
        field_path: Path to the DMI sysfs file
        
    Returns:
        Normalized value, or empty string if unavailable/invalid
    """
    try:
        if not field_path.exists() or not field_path.is_file():
            return ""
        
        # Read and clean value
        value = field_path.read_text(encoding='utf-8', errors='ignore')
        value = value.replace('\x00', '').strip()
        
        # Normalize UUID to lowercase
        if field_path.name == "product_uuid":
            value = value.lower()
        
        return value
        
    except (OSError, IOError, PermissionError):
        return ""


def read_machine_id() -> str:
    """
    Read OS machine ID from /etc/machine-id.
    
    Returns:
        Machine ID string, or empty if unavailable
    """
    try:
        if MACHINE_ID_FILE.exists():
            machine_id = MACHINE_ID_FILE.read_text(encoding='utf-8').strip()
            machine_id = machine_id.replace('\x00', '').replace(' ', '')
            return machine_id
    except (OSError, IOError, PermissionError):
        pass
    
    return ""


def collect_dmi_data() -> Dict[str, str]:
    """
    Collect all DMI fields from sysfs.
    
    Returns:
        Dictionary of field names to values (empty string if invalid)
    """
    data = {}
    
    for field_name, field_path in DMI_FIELDS.items():
        value = read_dmi_field(field_path)
        
        # Validate the value
        if not is_valid_value(value, field_name):
            value = ""
        
        data[field_name] = value
    
    return data


def select_asset_id(dmi_data: Dict[str, str], machine_id: str) -> tuple:
    """
    Select asset ID based on priority rules.
    
    Priority:
        1. product_serial (SMBIOS serial) -> asset_id_source="smbios_serial"
        2. product_uuid (SMBIOS UUID) -> asset_id_source="smbios_uuid"
        3. machine_id (OS machine ID) -> asset_id_source="machine_id"
    
    Args:
        dmi_data: Dictionary of DMI field values
        machine_id: OS machine ID
        
    Returns:
        Tuple of (asset_id, asset_id_source)
    """
    # Priority 1: product_serial
    if dmi_data.get("product_serial"):
        return dmi_data["product_serial"], "smbios_serial"
    
    # Priority 2: product_uuid
    if dmi_data.get("product_uuid"):
        return dmi_data["product_uuid"], "smbios_uuid"
    
    # Priority 3: machine_id
    if machine_id:
        return machine_id, "machine_id"
    
    # If nothing available, return empty (shouldn't happen in practice)
    return "", "unknown"


def load_config(config_path: Optional[Path] = None) -> Dict:
    """
    Load configuration from JSON file.
    
    Args:
        config_path: Path to config file, or None for default
        
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    
    try:
        if config_path.exists():
            with config_path.open('r') as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load config from {config_path}: {e}", file=sys.stderr)
    
    return {}


def generate_device_identity() -> Dict[str, str]:
    """
    Generate complete device identity dictionary.

    Returns:
        Device identity as dictionary with all fields
    """
    # Use canonical shared module for asset_id and platform_dmi
    asset_id, asset_id_source = resolve_asset_id()
    platform = get_platform_dmi()

    # Read machine ID for legacy field (also used in fallback chain inside resolve_asset_id)
    machine_id = read_machine_id()

    # Get current timestamp in UTC
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    identity = {
        "asset_id": asset_id,
        "asset_id_source": asset_id_source,
        "product_serial": platform.get("product_serial", ""),
        "product_uuid": platform.get("product_uuid", ""),
        "board_serial": platform.get("board_serial", ""),
        "chassis_serial": platform.get("chassis_serial", ""),
        "sys_vendor": platform.get("sys_vendor", ""),
        "product_name": platform.get("product_name", ""),
        "product_version": platform.get("product_version", ""),
        "os_machine_id": machine_id,
        "platform_dmi": platform,
        "collected_at_utc": timestamp,
    }

    return identity


def write_identity_file(identity: Dict[str, str], output_path: Path) -> None:
    """
    Write identity to JSON file atomically with proper permissions.
    
    Args:
        identity: Device identity dictionary
        output_path: Path to output file
        
    Raises:
        OSError: If cannot write file
    """
    # Create directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    
    # Write to temporary file in same directory
    temp_path = output_path.parent / f".{output_path.name}.tmp"
    
    try:
        with temp_path.open('w', encoding='utf-8') as f:
            json.dump(identity, f, indent=2, ensure_ascii=False)
            f.write('\n')  # Trailing newline
        
        # Set permissions (best-effort, don't crash if fails)
        try:
            os.chmod(temp_path, 0o644)
        except OSError:
            pass  # Non-fatal if not root
        
        # Atomic move
        temp_path.replace(output_path)
        
    finally:
        # Clean up temp file if it still exists
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def format_human_output(envelope: Dict) -> str:
    """
    Format envelope as human-readable text.

    Args:
        envelope: Output envelope with device identity data

    Returns:
        Human-readable formatted string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("Device Identity Report")
    lines.append("=" * 60)

    if not envelope["ok"]:
        lines.append("\nERRORS:")
        for error in envelope["errors"]:
            lines.append(f"  - {error}")
        return "\n".join(lines)

    data = envelope["data"]

    lines.append(f"\nAsset ID:       {data.get('asset_id', 'N/A')}")
    lines.append(f"Source:         {data.get('asset_id_source', 'N/A')}")
    lines.append(f"\nProduct Serial: {data.get('product_serial', 'N/A')}")
    lines.append(f"Board Serial:   {data.get('board_serial', 'N/A')}")
    lines.append(f"Product UUID:   {data.get('product_uuid', 'N/A')}")
    lines.append(f"\nVendor:         {data.get('sys_vendor', 'N/A')}")
    lines.append(f"Product:        {data.get('product_name', 'N/A')}")
    lines.append(f"Version:        {data.get('product_version', 'N/A')}")
    lines.append(f"\nMachine ID:     {data.get('machine_id', 'N/A')}")
    lines.append(f"Collected:      {data.get('collected_at_utc', 'N/A')}")
    lines.append("=" * 60)

    return "\n".join(lines)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    # Create parser with shared CLI infrastructure
    parser = create_base_parser(
        tool_name="device_identity",
        description="Collect stable device identity from DMI/SMBIOS",
        version=__version__,
        add_print=True,  # Backward compatibility
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print identity to stdout only (envelope format)
  python3 device_identity.py --print

  # Print human-readable format
  python3 device_identity.py --human

  # Write to default location
  sudo python3 device_identity.py

  # Write to custom location
  python3 device_identity.py --output /tmp/device_identity.json

Output:
  Default path: /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json
  Format: Standard JSON envelope {ok, data, errors, meta}

For more information, see:
  clear_asset_information/hardware_inventory_collector/README.md
        """
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_arguments()
    set_quiet(args.quiet)

    # Load config if provided (for output path, logging)
    config = {}
    if hasattr(args, 'config') and args.config:
        try:
            config = load_config(Path(args.config))
        except Exception:
            pass  # Use defaults if config fails to load

    # Setup logging if verbose flag is present
    if hasattr(args, 'verbose') and args.verbose:
        log_path = config.get("log_path") if hasattr(args, 'log') and not args.log else getattr(args, 'log', None)
        cli_setup_logging(log_path, args.verbose, tool_name="device_identity")

    try:
        if hasattr(args, 'verbose') and args.verbose:
            olog("Collecting device identity...")

        identity = generate_device_identity()

        errors = []
        if not identity.get("asset_id"):
            errors.append(make_error(WC_NO_ASSET_ID, "No valid asset identifier found",
                                     hint="Check DMI/SMBIOS or /etc/machine-id",
                                     severity="warning"))

        if hasattr(args, 'human') and args.human:
            # Human-readable output: build envelope for formatter, print to stdout
            envelope = format_envelope(ok=True, data=identity, errors=errors,
                                       meta={"tool": _TOOL, "version": __version__})
            print(format_human_output(envelope))
        else:
            # File write_fn wraps data in the full envelope (device_identity writes envelope to file)
            def _write_fn(data, path):
                env = format_envelope(ok=True, data=data, errors=errors,
                                      meta={"tool": _TOOL, "version": __version__})
                write_output(env, path)

            if not config:
                config = load_config()
            default_path = str(
                Path(args.output) if (hasattr(args, 'output') and args.output)
                else Path(config.get("output_path", str(DEFAULT_OUTPUT_PATH)))
            )
            route_output(identity, args, _TOOL, __version__, default_path, _write_fn, errors=errors)
            if identity.get("asset_id"):
                olog(f"Asset ID: {identity['asset_id']}")

        return EXIT_SUCCESS

    except KeyboardInterrupt:
        olog("\nInterrupted")
        return emit_error(
            [make_error(EC_INTERRUPTED, "Interrupted by user", severity="warning")],
            _TOOL, __version__, rc=EXIT_INTERRUPTED,
        )

    except Exception as e:
        olog(f"Error: {e}")
        return emit_error(
            [make_error(EC_GENERAL, str(e), detail=type(e).__name__,
                        hint="Check logs for details")],
            _TOOL, __version__, rc=EXIT_GENERAL_ERROR,
        )


if __name__ == "__main__":
    sys.exit(main())
