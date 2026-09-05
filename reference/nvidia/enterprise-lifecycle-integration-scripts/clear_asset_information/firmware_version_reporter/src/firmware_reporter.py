#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Firmware Version Reporter for DGX Spark

Collects comprehensive firmware inventory from multiple sources:
- BIOS/UEFI via DMI sysfs
- fwupd inventory (EC, TPM, UEFI devices, dbx, NVMe, NICs)
- NIC/Wi-Fi firmware via ethtool
- NVMe firmware via sysfs and nvme-cli
- GPU firmware via nvidia-smi
- PCI device correlation via lspci

Output: Canonical JSON suitable for enterprise asset tracking and Redfish mapping.

Requirements:
- Python 3 stdlib only (no external dependencies)
- Read-only system queries
- Graceful degradation if tools are missing
- Atomic file writes
"""

import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add common module to path (works from both src/ and bin/ locations)
_script_dir = Path(__file__).parent
_common_path = _script_dir / "common" if _script_dir.name == "bin" else _script_dir.parent.parent.parent / "common"
sys.path.insert(0, str(_common_path))
from output import (emit_ok, emit_error, log as olog, route_output, set_quiet,
                    add_standard_output_flags, make_error,
                    EC_GENERAL, EC_INTERRUPTED, EXIT_GENERAL_ERROR, EXIT_INTERRUPTED)
from asset_id import resolve_asset_id, load_identity_file

_TOOL = "firmware_version_reporter"
_VERSION = "1.0.0"
_FUNCTIONAL_AREA = "clear_asset_information"

# Default paths
DEFAULT_OUTPUT_PATH = f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.json"
DEFAULT_IDENTITY_PATH = f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/device_identity/device_identity.json"
DEFAULT_LOG_PATH = f"/var/log/dgx_spark/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.log"
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"

# Constants
MAX_RAW_TEXT_DEFAULT = 200000  # 200KB


def setup_logging(log_path: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """
    Setup logging to file and/or stderr.
    
    Args:
        log_path: Path to log file (if None or fails, log to stderr)
        verbose: Enable DEBUG level logging
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("firmware_reporter")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Try to setup file handler
    if log_path:
        try:
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (PermissionError, OSError) as e:
            # Fall back to stderr
            pass
    
    # Always add stderr handler for warnings and errors
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)
    
    return logger


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    if not config_path.exists():
        return {}
    
    try:
        with config_path.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_identity(identity_path: str, logger: logging.Logger) -> Tuple[Optional[str], Optional[str]]:
    """
    Load device identity from JSON file (supports both flat and envelope formats).

    Falls back to resolve_asset_id() if file is missing or has no asset_id.

    Returns:
        Tuple of (asset_id, asset_id_source)
    """
    identity = load_identity_file(identity_path)
    asset_id = identity.get("asset_id") if identity else None
    asset_id_source = identity.get("asset_id_source") if identity else None

    if asset_id:
        logger.info(f"Loaded identity: asset_id={asset_id}, source={asset_id_source}")
        return asset_id, asset_id_source

    logger.info("Identity file missing or incomplete; resolving asset_id from DMI/sysfs")
    asset_id, asset_id_source = resolve_asset_id()
    return asset_id, asset_id_source


def read_dmi_field(field: str) -> Optional[str]:
    """Read a single DMI field from sysfs."""
    try:
        path = Path(f"/sys/class/dmi/id/{field}")
        if path.exists():
            value = path.read_text().strip()
            return value if value else None
        return None
    except (OSError, IOError):
        return None


def collect_platform_dmi(logger: logging.Logger) -> Dict[str, Optional[str]]:
    """Collect platform and BIOS information from DMI sysfs."""
    logger.info("Collecting platform DMI information...")
    
    fields = [
        "sys_vendor", "product_name", "product_version", "product_serial", "product_uuid",
        "bios_vendor", "bios_version", "bios_date",
        "board_vendor", "board_name", "board_version", "board_serial"
    ]
    
    dmi = {}
    for field in fields:
        dmi[field] = read_dmi_field(field)
    
    logger.debug(f"DMI fields collected: {sum(1 for v in dmi.values() if v)} / {len(fields)}")
    return dmi


def run_command(cmd: List[str], logger: logging.Logger, timeout: int = 30) -> Tuple[bool, str, str]:
    """
    Run a command and return success status, stdout, stderr.
    
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        success = result.returncode == 0
        return success, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.warning(f"Command timed out: {' '.join(cmd)}")
        return False, "", "Timeout"
    except FileNotFoundError:
        logger.debug(f"Command not found: {cmd[0]}")
        return False, "", "Command not found"
    except Exception as e:
        logger.warning(f"Command failed: {' '.join(cmd)}: {e}")
        return False, "", str(e)


def parse_fwupd_text(text: str, logger: logging.Logger) -> List[Dict[str, Any]]:
    """
    Parse fwupdmgr get-devices text output into structured devices.
    
    Format:
    Device Name
    ├─Field Name:         Value
    ├─Another Field:      Value
    ...
    """
    devices = []
    current_device = None
    
    lines = text.split("\n")
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check if this is a device header (no leading special chars)
        if not line.startswith(("├", "│", "└")) and ":" not in line:
            # Save previous device
            if current_device and current_device.get("name"):
                devices.append(current_device)
            
            # Start new device
            current_device = {
                "name": stripped,
                "device_id": None,
                "summary": None,
                "current_version": None,
                "minimum_version": None,
                "vendor": None,
                "serial_number": None,
                "guid": None,
                "guids": [],
                "update_state": None,
                "device_flags": [],
                "device_requests": []
            }
            continue
        
        # Parse field lines
        if current_device and ":" in line:
            # Remove tree characters
            clean_line = line.replace("├─", "").replace("│ ", "").replace("└─", "").strip()
            
            if ":" not in clean_line:
                continue
            
            key, value = clean_line.split(":", 1)
            key = key.strip()
            value = value.strip()
            
            # Map fields
            key_lower = key.lower()
            
            if "device id" in key_lower:
                current_device["device_id"] = value
            elif key_lower == "summary":
                current_device["summary"] = value
            elif "current version" in key_lower or key_lower == "version":
                current_device["current_version"] = value
            elif "minimum version" in key_lower:
                current_device["minimum_version"] = value
            elif key_lower == "vendor":
                current_device["vendor"] = value
            elif "serial number" in key_lower:
                current_device["serial_number"] = value
            elif key_lower == "guid":
                current_device["guid"] = value
                current_device["guids"].append(value)
            elif "update state" in key_lower:
                current_device["update_state"] = value
            elif "device flags" in key_lower or "flags" in key_lower:
                # Flags are often comma-separated or on multiple lines
                flags = [f.strip() for f in value.split(",") if f.strip()]
                current_device["device_flags"].extend(flags)
            elif "device requests" in key_lower or "requests" in key_lower:
                requests = [r.strip() for r in value.split(",") if r.strip()]
                current_device["device_requests"].extend(requests)
    
    # Don't forget the last device
    if current_device and current_device.get("name"):
        devices.append(current_device)
    
    logger.info(f"Parsed {len(devices)} fwupd devices from text output")
    return devices


def collect_fwupd(enable: bool, logger: logging.Logger, max_raw_bytes: int) -> Dict[str, Any]:
    """Collect firmware inventory from fwupd."""
    result = {
        "available": False,
        "fwupdmgr_version": None,
        "parse_mode": "none",
        "devices": [],
        "raw_devices_text": None
    }
    
    if not enable:
        logger.info("fwupd collection disabled by config/CLI")
        return result
    
    # Check if fwupdmgr is available
    if not shutil.which("fwupdmgr"):
        logger.info("fwupdmgr not found in PATH")
        return result
    
    result["available"] = True
    
    # Get fwupdmgr version
    success, stdout, _ = run_command(["fwupdmgr", "--version"], logger)
    if success:
        result["fwupdmgr_version"] = stdout.strip().split("\n")[0].strip()
        logger.info(f"fwupdmgr version: {result['fwupdmgr_version']}")
    
    # Try JSON output first
    logger.info("Attempting fwupdmgr get-devices --json...")
    success, stdout, stderr = run_command(["fwupdmgr", "get-devices", "--json"], logger)
    
    if success and stdout.strip():
        try:
            devices_data = json.loads(stdout)
            result["parse_mode"] = "json"
            
            # Extract device list (structure may vary by version)
            if isinstance(devices_data, dict) and "Devices" in devices_data:
                devices_list = devices_data["Devices"]
            elif isinstance(devices_data, list):
                devices_list = devices_data
            else:
                devices_list = []
            
            # Normalize JSON structure to our schema
            for dev in devices_list:
                device = {
                    "name": dev.get("Name", dev.get("DeviceId", "Unknown")),
                    "device_id": dev.get("DeviceId"),
                    "summary": dev.get("Summary"),
                    "current_version": dev.get("Version", dev.get("CurrentVersion")),
                    "minimum_version": dev.get("MinimumVersion"),
                    "vendor": dev.get("Vendor"),
                    "serial_number": dev.get("Serial", dev.get("SerialNumber")),
                    "guid": dev.get("Guid"),
                    "guids": dev.get("Guids", []),
                    "update_state": dev.get("UpdateState"),
                    "device_flags": dev.get("Flags", []),
                    "device_requests": dev.get("Requests", [])
                }
                result["devices"].append(device)
            
            logger.info(f"Parsed {len(result['devices'])} devices from JSON")
            return result
        
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from fwupdmgr: {e}")
            # Fall through to text parsing
    
    # Fallback to text parsing
    logger.info("Falling back to fwupdmgr get-devices text parsing...")
    success, stdout, stderr = run_command(["fwupdmgr", "get-devices"], logger)
    
    if success and stdout.strip():
        result["parse_mode"] = "text"
        result["devices"] = parse_fwupd_text(stdout, logger)
        
        # Store truncated raw text for troubleshooting
        if len(stdout) > max_raw_bytes:
            result["raw_devices_text"] = stdout[:max_raw_bytes] + f"\n... [truncated, {len(stdout)} total bytes]"
        else:
            result["raw_devices_text"] = stdout
    else:
        logger.warning("fwupdmgr get-devices failed or returned no output")
    
    return result


def collect_nics(enable: bool, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Collect NIC firmware information via ethtool."""
    nics = []
    
    if not enable:
        logger.info("NIC collection (ethtool) disabled by config/CLI")
        return nics
    
    if not shutil.which("ethtool"):
        logger.info("ethtool not found in PATH")
        return nics
    
    logger.info("Collecting NIC firmware via ethtool...")
    
    # Enumerate interfaces from /sys/class/net
    net_path = Path("/sys/class/net")
    if not net_path.exists():
        logger.warning("/sys/class/net not found")
        return nics
    
    for iface_path in net_path.iterdir():
        ifname = iface_path.name
        
        # Skip loopback
        if ifname == "lo":
            continue
        
        logger.debug(f"Checking interface: {ifname}")
        
        nic = {
            "ifname": ifname,
            "mac": None,
            "is_wireless": None,
            "driver": None,
            "driver_version": None,
            "firmware_version": None,
            "bus_info": None
        }
        
        # Read MAC address
        mac_path = iface_path / "address"
        if mac_path.exists():
            try:
                nic["mac"] = mac_path.read_text().strip()
            except (OSError, IOError):
                pass
        
        # Check if wireless
        wireless_path = iface_path / "wireless"
        nic["is_wireless"] = wireless_path.exists()
        
        # Run ethtool -i
        success, stdout, stderr = run_command(["ethtool", "-i", ifname], logger, timeout=5)
        
        if success and stdout.strip():
            # Parse key-value lines
            for line in stdout.split("\n"):
                line = line.strip()
                if not line or ":" not in line:
                    continue
                
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                
                if not value:
                    continue
                
                if key == "driver":
                    nic["driver"] = value
                elif key == "version":
                    nic["driver_version"] = value
                elif key == "firmware-version":
                    nic["firmware_version"] = value
                elif key == "bus-info":
                    nic["bus_info"] = value
        else:
            logger.debug(f"ethtool -i failed for {ifname} (may be virtual)")
        
        nics.append(nic)
    
    logger.info(f"Collected {len(nics)} NICs")
    return nics


def collect_nvme(enable_sysfs: bool, enable_cli: bool, fwupd_devices: List[Dict], logger: logging.Logger) -> List[Dict[str, Any]]:
    """Collect NVMe firmware from sysfs, nvme-cli, and correlate with fwupd."""
    nvme_devices = {}
    
    # Collect from sysfs
    if enable_sysfs:
        logger.info("Collecting NVMe firmware from sysfs...")
        nvme_path = Path("/sys/class/nvme")
        
        if nvme_path.exists():
            for ctrl_path in nvme_path.iterdir():
                if not ctrl_path.name.startswith("nvme"):
                    continue
                
                controller = ctrl_path.name
                
                model = None
                serial = None
                firmware_rev = None
                
                # Read sysfs files
                model_path = ctrl_path / "model"
                if model_path.exists():
                    try:
                        model = model_path.read_text().strip()
                    except (OSError, IOError):
                        pass
                
                serial_path = ctrl_path / "serial"
                if serial_path.exists():
                    try:
                        serial = serial_path.read_text().strip()
                    except (OSError, IOError):
                        pass
                
                fw_path = ctrl_path / "firmware_rev"
                if fw_path.exists():
                    try:
                        firmware_rev = fw_path.read_text().strip()
                    except (OSError, IOError):
                        pass
                
                nvme_devices[controller] = {
                    "controller": controller,
                    "model": model,
                    "serial": serial,
                    "firmware_rev": firmware_rev,
                    "sources": ["sysfs"]
                }
                
                logger.debug(f"NVMe {controller}: model={model}, serial={serial}, fw={firmware_rev}")
    
    # Enrich from nvme-cli
    if enable_cli and shutil.which("nvme"):
        logger.info("Enriching NVMe data from nvme-cli...")
        success, stdout, stderr = run_command(["nvme", "list"], logger)
        
        if success and stdout.strip():
            lines = stdout.split("\n")
            
            # Skip header lines
            for line in lines:
                line = line.strip()
                
                # Look for device lines (starts with /dev/nvme)
                if not line.startswith("/dev/nvme"):
                    continue
                
                # Parse columns (space-separated, but values may contain spaces)
                # Typical format: /dev/nvme0n1  S5GXNX...  Samsung...  NXHB202Q  476.94GB  ...
                parts = line.split()
                
                if len(parts) < 4:
                    continue
                
                node = parts[0]  # /dev/nvme0n1
                serial = parts[1]
                # Model could be multiple parts
                # FW Rev is typically after model
                
                # Extract controller name from node
                if "nvme" in node:
                    # /dev/nvme0n1 -> nvme0
                    ctrl = "nvme" + node.split("nvme")[1].split("n")[0]
                    
                    if ctrl in nvme_devices:
                        # Enrich existing entry
                        if serial and serial != nvme_devices[ctrl].get("serial"):
                            nvme_devices[ctrl]["serial"] = serial
                        
                        # Try to extract firmware rev (usually 4th or 5th column)
                        if len(parts) >= 4:
                            fw_candidate = parts[3]
                            if fw_candidate and len(fw_candidate) < 20:  # Sanity check
                                if nvme_devices[ctrl]["firmware_rev"] is None:
                                    nvme_devices[ctrl]["firmware_rev"] = fw_candidate
                        
                        if "nvme_cli" not in nvme_devices[ctrl]["sources"]:
                            nvme_devices[ctrl]["sources"].append("nvme_cli")
                    else:
                        # New device discovered by nvme-cli only
                        nvme_devices[ctrl] = {
                            "controller": ctrl,
                            "model": None,
                            "serial": serial,
                            "firmware_rev": parts[3] if len(parts) >= 4 else None,
                            "sources": ["nvme_cli"]
                        }
    
    # Correlate with fwupd
    if fwupd_devices:
        logger.info("Correlating NVMe with fwupd devices...")
        for fwupd_dev in fwupd_devices:
            name = fwupd_dev.get("name", "").lower()
            summary = (fwupd_dev.get("summary") or "").lower()
            
            if "nvme" in name or "nvme" in summary or "ssd" in summary:
                # Try to match with existing nvme devices by serial or model
                serial = fwupd_dev.get("serial_number")
                fw_version = fwupd_dev.get("current_version")
                
                matched = False
                for ctrl, nvme_dev in nvme_devices.items():
                    if serial and nvme_dev.get("serial") == serial:
                        # Match by serial
                        if fw_version and nvme_dev["firmware_rev"] is None:
                            nvme_dev["firmware_rev"] = fw_version
                        if "fwupd" not in nvme_dev["sources"]:
                            nvme_dev["sources"].append("fwupd")
                        matched = True
                        break
                
                if not matched:
                    # Add as new device from fwupd
                    ctrl_name = f"fwupd_{len(nvme_devices)}"
                    nvme_devices[ctrl_name] = {
                        "controller": fwupd_dev.get("name"),
                        "model": fwupd_dev.get("summary"),
                        "serial": serial,
                        "firmware_rev": fw_version,
                        "sources": ["fwupd"]
                    }
    
    result = list(nvme_devices.values())
    logger.info(f"Collected {len(result)} NVMe devices")
    return result


def collect_gpu(enable: bool, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Collect GPU firmware information from nvidia-smi."""
    gpus = []
    
    if not enable:
        logger.info("GPU collection (nvidia-smi) disabled by config/CLI")
        return gpus
    
    if not shutil.which("nvidia-smi"):
        logger.info("nvidia-smi not found in PATH")
        return gpus
    
    logger.info("Collecting GPU firmware from nvidia-smi...")
    
    # Query GPUs via CSV
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,driver_version,vbios_version,pci.bus_id",
        "--format=csv,noheader,nounits"
    ]
    
    success, stdout, stderr = run_command(cmd, logger)
    
    if not success or not stdout.strip():
        logger.warning("nvidia-smi query failed or returned no output")
        return gpus
    
    # Parse CSV
    for line in stdout.strip().split("\n"):
        fields = [f.strip() for f in line.split(",")]
        
        if len(fields) < 6:
            continue
        
        index_str = fields[0]
        uuid = fields[1]
        name = fields[2]
        driver_version = fields[3]
        vbios_version = fields[4]
        pci_bus_id = fields[5]
        
        # Convert N/A to None
        def clean_na(value):
            return None if value.upper() in ("N/A", "[N/A]", "") else value
        
        gpu = {
            "index": int(index_str) if index_str.isdigit() else None,
            "uuid": clean_na(uuid),
            "name": clean_na(name),
            "driver_version": clean_na(driver_version),
            "vbios_version": clean_na(vbios_version),
            "gsp_firmware_version": None,
            "pci_bus_id": clean_na(pci_bus_id),
            "inforom": None
        }
        
        gpus.append(gpu)
    
    logger.info(f"Collected {len(gpus)} GPUs from CSV")
    
    # Enrich with nvidia-smi -q (best-effort)
    if gpus:
        logger.debug("Attempting to enrich GPU data from nvidia-smi -q...")
        success, stdout, stderr = run_command(["nvidia-smi", "-q"], logger, timeout=10)
        
        if success and stdout.strip():
            # Simple line-by-line grep for key fields
            gsp_version = None
            inforom = None
            vbios_alt = None
            
            for line in stdout.split("\n"):
                line = line.strip()
                
                if "GSP Firmware Version" in line and ":" in line:
                    gsp_version = line.split(":", 1)[1].strip()
                elif "Inforom Version" in line and ":" in line:
                    inforom = line.split(":", 1)[1].strip()
                elif "VBIOS Version" in line and ":" in line:
                    vbios_alt = line.split(":", 1)[1].strip()
            
            # Attach to first GPU (simple approach)
            if gpus and (gsp_version or inforom or vbios_alt):
                if gsp_version:
                    gpus[0]["gsp_firmware_version"] = gsp_version
                if inforom:
                    gpus[0]["inforom"] = inforom
                if vbios_alt and not gpus[0]["vbios_version"]:
                    gpus[0]["vbios_version"] = vbios_alt
                
                logger.debug(f"Enriched GPU 0 with GSP/Inforom/VBIOS from -q output")
                
                if len(gpus) > 1:
                    logger.warning("Multiple GPUs detected; GSP/Inforom enrichment applied to GPU 0 only")
    
    return gpus


def collect_pci(enable: bool, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Collect PCI device information for correlation."""
    pci_devices = []
    
    if not enable:
        logger.info("PCI collection (lspci) disabled by config/CLI")
        return pci_devices
    
    if not shutil.which("lspci"):
        logger.info("lspci not found in PATH")
        return pci_devices
    
    logger.info("Collecting PCI devices from lspci...")
    
    success, stdout, stderr = run_command(["lspci", "-D", "-nn"], logger)
    
    if not success or not stdout.strip():
        logger.warning("lspci failed or returned no output")
        return pci_devices
    
    # Filter to relevant devices
    keywords = [
        "ethernet", "network", "vga", "3d controller", "display",
        "nvme", "storage", "nvidia", "mellanox", "connectx",
        "realtek", "mediatek", "broadcom"
    ]
    
    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        
        line_lower = line.lower()
        
        # Check if any keyword matches
        if not any(kw in line_lower for kw in keywords):
            continue
        
        # Parse format: 0001:00:00.0 Class [code]: Vendor Device [vvvv:dddd] Description
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        
        pci_addr = parts[0]
        rest = parts[1]
        
        # Extract vendor:device ID
        vendor_device_id = None
        if "[" in rest and "]" in rest:
            # Find last [xxxx:yyyy]
            brackets = [part for part in rest.split() if part.startswith("[") and ":" in part]
            if brackets:
                vendor_device_id = brackets[-1]
        
        # Extract class (first [code])
        class_text = None
        if "[" in rest:
            first_bracket = rest.split("[", 1)[1].split("]", 1)
            if len(first_bracket) >= 1:
                class_text = rest.split("]", 1)[0] + "]"
        
        # Description is the rest
        description = rest
        
        pci_devices.append({
            "pci_addr": pci_addr,
            "vendor_device_id": vendor_device_id,
            "class_text": class_text,
            "description": description
        })
    
    logger.info(f"Collected {len(pci_devices)} relevant PCI devices")
    return pci_devices


def collect_firmware_inventory(
    config: Dict[str, Any],
    args: argparse.Namespace,
    logger: logging.Logger
) -> Dict[str, Any]:
    """Main collection orchestrator."""
    
    logger.info("=" * 60)
    logger.info("Starting firmware inventory collection")
    logger.info("=" * 60)
    
    # Load identity
    identity_path = args.identity or config.get("identity_path", DEFAULT_IDENTITY_PATH)
    asset_id, asset_id_source = load_identity(identity_path, logger)
    
    # Determine which collectors to run
    enable_fwupd = config.get("enable_fwupd", True) and not args.no_fwupd
    enable_ethtool = config.get("enable_ethtool", True) and not args.no_vendor_tools
    enable_nvme_sysfs = config.get("enable_nvme_sysfs", True) and not args.no_vendor_tools
    enable_nvme_cli = config.get("enable_nvme_cli", True) and not args.no_vendor_tools
    enable_nvidia_smi = config.get("enable_nvidia_smi", True) and not args.no_vendor_tools
    enable_lspci = config.get("enable_lspci", True) and not args.no_vendor_tools
    
    max_raw_bytes = config.get("max_raw_text_bytes", MAX_RAW_TEXT_DEFAULT)
    
    # Collect from all sources
    platform_dmi = collect_platform_dmi(logger)
    fwupd = collect_fwupd(enable_fwupd, logger, max_raw_bytes)
    nics = collect_nics(enable_ethtool, logger)
    nvme = collect_nvme(enable_nvme_sysfs, enable_nvme_cli, fwupd.get("devices", []), logger)
    gpu = collect_gpu(enable_nvidia_smi, logger)
    pci = collect_pci(enable_lspci, logger)
    
    # Determine sources used
    sources = {
        "platform_dmi": "dmi_sysfs",
        "fwupd": fwupd.get("parse_mode", "none"),
        "nics": "ethtool" if enable_ethtool and nics else "none",
        "nvme": "sysfs" if nvme else "none",
        "gpu": "nvidia_smi" if enable_nvidia_smi and gpu else "none",
        "pci": "lspci" if enable_lspci and pci else "none"
    }
    
    # Build output
    output = {
        "collected_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "asset_id": asset_id,
        "asset_id_source": asset_id_source,
        "platform_dmi": platform_dmi,
        "fwupd": fwupd,
        "nics": nics,
        "nvme": nvme,
        "gpu": gpu,
        "pci": pci,
        "sources": sources
    }
    
    logger.info("=" * 60)
    logger.info("Firmware inventory collection complete")
    logger.info(f"  Platform DMI: {sum(1 for v in platform_dmi.values() if v)} fields")
    logger.info(f"  fwupd: {len(fwupd['devices'])} devices")
    logger.info(f"  NICs: {len(nics)} interfaces")
    logger.info(f"  NVMe: {len(nvme)} devices")
    logger.info(f"  GPUs: {len(gpu)} devices")
    logger.info(f"  PCI: {len(pci)} devices")
    logger.info("=" * 60)
    
    return output


def write_output(data: Dict[str, Any], output_path: str, logger: logging.Logger) -> None:
    """Write output JSON atomically."""
    output_file = Path(output_path)
    
    # Ensure directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file
    temp_file = output_file.parent / f".{output_file.name}.tmp"
    
    try:
        with temp_file.open("w") as f:
            json.dump(data, f, indent=2, sort_keys=False)
        
        # Atomic replace
        temp_file.replace(output_file)
        
        # Best-effort chmod
        try:
            output_file.chmod(0o644)
        except (OSError, PermissionError):
            pass
        
        logger.info(f"Output written to: {output_path}")
    
    except Exception as e:
        logger.error(f"Failed to write output: {e}")
        if temp_file.exists():
            temp_file.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Firmware Version Reporter for DGX Spark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print firmware inventory to stdout
  %(prog)s --print
  
  # Write to default location (requires sudo)
  sudo %(prog)s
  
  # Write to custom location
  %(prog)s --output /tmp/firmware.json
  
  # Disable fwupd collection
  %(prog)s --no_fwupd
  
  # Disable all vendor tools (ethtool, nvme, nvidia-smi, lspci)
  %(prog)s --no_vendor_tools
        """
    )
    
    parser.add_argument("--print", action="store_true",
                        help="Print JSON to stdout only (do not write file)")
    parser.add_argument("--output", metavar="PATH",
                        help="Override output file path")
    parser.add_argument("--identity", metavar="PATH",
                        help="Override identity file path")
    parser.add_argument("--config", metavar="PATH",
                        help="Override config file path")
    parser.add_argument("--no_fwupd", action="store_true",
                        help="Skip fwupdmgr collection")
    parser.add_argument("--no_vendor_tools", action="store_true",
                        help="Skip ethtool, nvme-cli, nvidia-smi, lspci")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose (DEBUG) logging")
    parser.add_argument("--log", metavar="PATH",
                        help="Override log file path")
    add_standard_output_flags(parser)

    args = parser.parse_args()
    set_quiet(args.quiet)

    # Load config
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    # Setup logging
    log_path = args.log or (None if args.print else DEFAULT_LOG_PATH)
    logger = setup_logging(log_path, args.verbose)

    logger.info(f"Firmware Version Reporter starting...")
    logger.info(f"Config: {config_path} (exists: {config_path.exists()})")

    try:
        # Collect inventory
        inventory = collect_firmware_inventory(config, args, logger)

        default_path = args.output or config.get("output_path", DEFAULT_OUTPUT_PATH)
        route_output(
            inventory, args, _TOOL, _VERSION, default_path,
            lambda data, path: write_output(data, path, logger),
        )

        return 0

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return emit_error(
            [make_error(EC_INTERRUPTED, "Interrupted by user", severity="warning")],
            _TOOL, _VERSION, rc=EXIT_INTERRUPTED,
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return emit_error(
            [make_error(EC_GENERAL, str(e), detail=type(e).__name__,
                        hint="Check logs for details")],
            _TOOL, _VERSION, rc=EXIT_GENERAL_ERROR,
        )


if __name__ == "__main__":
    sys.exit(main())
