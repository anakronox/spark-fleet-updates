#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Driver Inventory Reporter for DGX Spark

Enumerates device-to-driver bindings across PCI, NIC interfaces, storage, USB devices, and GPUs.
Builds a comprehensive driver manifest showing which modules are used by which devices.

Output: Canonical JSON suitable for enterprise asset inventory, driver troubleshooting,
and compliance verification.

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
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add common module to path (works from both src/ and bin/ locations)
_script_dir = Path(__file__).parent
_common_path = _script_dir / "common" if _script_dir.name == "bin" else _script_dir.parent.parent.parent / "common"
sys.path.insert(0, str(_common_path))
from output import (emit_ok, emit_error, log as olog, route_output, set_quiet,
                    add_standard_output_flags, make_error,
                    EC_GENERAL, EC_INTERRUPTED, EXIT_GENERAL_ERROR, EXIT_INTERRUPTED)
from asset_id import resolve_asset_id, get_platform_dmi

_TOOL = "driver_inventory_reporter"
_VERSION = "1.0.0"
_FUNCTIONAL_AREA = "clear_asset_information"

# Default paths
DEFAULT_OUTPUT_PATH = f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.json"
DEFAULT_LOG_PATH = f"/var/log/dgx_spark/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.log"
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"

# Constants
MAX_RAW_BYTES_DEFAULT = 200000


def setup_logging(log_path: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """Setup logging to file and/or stderr."""
    logger = logging.getLogger("driver_inventory")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    if log_path:
        try:
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (PermissionError, OSError):
            pass
    
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


def run_command(cmd: List[str], logger: logging.Logger, timeout: int = 30) -> Tuple[bool, str, str]:
    """Run a command and return success status, stdout, stderr."""
    try:
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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


def collect_platform_identity(logger: logging.Logger) -> Tuple[Dict[str, Optional[str]], Optional[str], Optional[str]]:
    """Collect platform identity using canonical shared module."""
    logger.info("Collecting platform identity...")

    platform = get_platform_dmi()
    asset_id, asset_id_source = resolve_asset_id()

    logger.info(f"Platform: {platform.get('sys_vendor')} {platform.get('product_name')}, asset_id={asset_id}")
    return platform, asset_id, asset_id_source


def collect_kernel_identity(logger: logging.Logger) -> Dict[str, Optional[str]]:
    """Collect kernel identity."""
    logger.info("Collecting kernel identity...")
    
    kernel = {"uname_r": None, "uname_a": None}
    
    success, stdout, _ = run_command(["uname", "-r"], logger, timeout=5)
    if success:
        kernel["uname_r"] = stdout.strip()
    
    success, stdout, _ = run_command(["uname", "-a"], logger, timeout=5)
    if success:
        kernel["uname_a"] = stdout.strip()
    
    logger.info(f"Kernel: {kernel['uname_r']}")
    return kernel


def parse_lspci_nnk(output: str, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Parse lspci -D -nnk output into device list."""
    devices = []
    current_device = None
    
    for line in output.split("\n"):
        line_stripped = line.strip()
        
        # Device header line (starts with PCI address)
        if line and not line.startswith(("\t", " ")):
            # Save previous device
            if current_device:
                devices.append(current_device)
            
            # Parse new device header
            # Format: 0000:01:00.0 Ethernet controller [0200]: Vendor Device [vvvv:dddd] (rev XX)
            match = re.match(r'^([0-9a-f:\.]+)\s+(.+?):\s+(.+?)\s+\[([0-9a-f:]+)\](.*)$', line, re.IGNORECASE)
            
            if match:
                pci_addr = match.group(1)
                class_text = match.group(2)
                description = match.group(3)
                vendor_device_id = f"[{match.group(4)}]"
                remainder = match.group(5)
                
                current_device = {
                    "pci_addr": pci_addr,
                    "class_text": class_text,
                    "vendor_device_id": vendor_device_id,
                    "subsystem_vendor_device_id": None,
                    "description": description,
                    "kernel_driver_in_use": None,
                    "kernel_modules": []
                }
            else:
                # Fallback for unusual format
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    current_device = {
                        "pci_addr": parts[0],
                        "class_text": None,
                        "vendor_device_id": None,
                        "subsystem_vendor_device_id": None,
                        "description": parts[1],
                        "kernel_driver_in_use": None,
                        "kernel_modules": []
                    }
        
        # Subsystem line
        elif line_stripped.startswith("Subsystem:") and current_device:
            # Format: Subsystem: Vendor Device [vvvv:dddd]
            match = re.search(r'\[([0-9a-f:]+)\]', line_stripped, re.IGNORECASE)
            if match:
                current_device["subsystem_vendor_device_id"] = f"[{match.group(1)}]"
        
        # Kernel driver in use
        elif line_stripped.startswith("Kernel driver in use:") and current_device:
            driver = line_stripped.split(":", 1)[1].strip()
            current_device["kernel_driver_in_use"] = driver
        
        # Kernel modules
        elif line_stripped.startswith("Kernel modules:") and current_device:
            modules_str = line_stripped.split(":", 1)[1].strip()
            # Comma-separated list
            modules = [m.strip() for m in modules_str.split(",") if m.strip()]
            current_device["kernel_modules"] = modules
    
    # Don't forget last device
    if current_device:
        devices.append(current_device)
    
    # Sort by PCI address for determinism
    devices.sort(key=lambda d: d["pci_addr"])
    
    logger.info(f"Parsed {len(devices)} PCI devices")
    return devices


def collect_pci_devices(logger: logging.Logger) -> Tuple[List[Dict[str, Any]], str]:
    """Collect PCI device-driver bindings."""
    logger.info("Collecting PCI device-driver bindings...")
    
    if not shutil.which("lspci"):
        logger.warning("lspci not found")
        return [], "none"
    
    success, stdout, stderr = run_command(["lspci", "-D", "-nnk"], logger)
    
    if not success or not stdout.strip():
        logger.warning("lspci -D -nnk failed")
        return [], "none"
    
    devices = parse_lspci_nnk(stdout, logger)
    return devices, "lspci_-D_-nnk"


def collect_nics(pci_devices: List[Dict[str, Any]], logger: logging.Logger) -> Tuple[List[Dict[str, Any]], str]:
    """Collect NIC interface drivers."""
    logger.info("Collecting NIC interface drivers...")
    
    nics = []
    sources = []
    
    net_path = Path("/sys/class/net")
    if not net_path.exists():
        logger.warning("/sys/class/net not found")
        return nics, "none"
    
    for iface_path in net_path.iterdir():
        ifname = iface_path.name
        
        # Skip loopback
        if ifname == "lo":
            continue
        
        logger.debug(f"Checking interface: {ifname}")
        
        nic = {
            "ifname": ifname,
            "mac": None,
            "mtu": None,
            "operstate": None,
            "is_virtual": False,
            "is_wireless": False,
            "driver": None,
            "driver_version": None,
            "firmware_version": None,
            "bus_info": None,
            "pci_device": None
        }
        
        # Determine if virtual
        virtual_path = Path(f"/sys/devices/virtual/net/{ifname}")
        if virtual_path.exists() or ifname.startswith(("docker", "veth", "br-", "virbr")):
            nic["is_virtual"] = True
        
        # Determine if wireless
        wireless_path = iface_path / "wireless"
        nic["is_wireless"] = wireless_path.exists()
        
        # Read sysfs attributes
        try:
            address_path = iface_path / "address"
            if address_path.exists():
                nic["mac"] = address_path.read_text().strip()
        except (OSError, IOError):
            pass
        
        try:
            mtu_path = iface_path / "mtu"
            if mtu_path.exists():
                nic["mtu"] = int(mtu_path.read_text().strip())
        except (OSError, IOError, ValueError):
            pass
        
        try:
            operstate_path = iface_path / "operstate"
            if operstate_path.exists():
                nic["operstate"] = operstate_path.read_text().strip()
        except (OSError, IOError):
            pass
        
        # Try ethtool
        if shutil.which("ethtool"):
            success, stdout, stderr = run_command(["ethtool", "-i", ifname], logger, timeout=5)
            
            if success and stdout.strip():
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
                
                if "ethtool_-i" not in sources:
                    sources.append("ethtool_-i")
        
        # Correlate to PCI device by bus-info
        if nic["bus_info"] and pci_devices:
            for pci_dev in pci_devices:
                if pci_dev["pci_addr"] == nic["bus_info"]:
                    nic["pci_device"] = pci_dev["pci_addr"]
                    break
        
        nics.append(nic)
    
    if not sources:
        sources.append("sysfs")
    
    logger.info(f"Collected {len(nics)} NICs")
    return nics, "|".join(sources)


def collect_storage(logger: logging.Logger) -> Tuple[List[Dict[str, Any]], str]:
    """Collect storage device drivers."""
    logger.info("Collecting storage device drivers...")
    
    storage = []
    
    # Try lsblk JSON
    if shutil.which("lsblk"):
        success, stdout, stderr = run_command(
            ["lsblk", "-J", "-b", "-o", "NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,ROTA,WWN,MOUNTPOINT,FSTYPE"],
            logger
        )
        
        if success and stdout.strip():
            try:
                lsblk_data = json.loads(stdout)
                devices_list = lsblk_data.get("blockdevices", [])
                
                for dev in devices_list:
                    if dev.get("type") not in ("disk", "rom"):
                        continue
                    
                    dev_name = dev.get("name")
                    
                    storage_entry = {
                        "name": dev_name,
                        "type": dev.get("type"),
                        "size_bytes": dev.get("size"),
                        "model": dev.get("model"),
                        "serial": dev.get("serial"),
                        "tran": dev.get("tran"),
                        "driver": None,
                        "driver_sysfs_path": None
                    }
                    
                    # Resolve driver from sysfs
                    driver_link = Path(f"/sys/block/{dev_name}/device/driver")
                    if driver_link.exists():
                        try:
                            driver_target = driver_link.resolve()
                            storage_entry["driver"] = driver_target.name
                            storage_entry["driver_sysfs_path"] = str(driver_target)
                        except (OSError, IOError):
                            pass
                    
                    storage.append(storage_entry)
                
                logger.info(f"Collected {len(storage)} storage devices from lsblk")
                return storage, "lsblk_json"
            
            except json.JSONDecodeError:
                logger.warning("Failed to parse lsblk JSON")
    
    # Fallback to sysfs
    block_path = Path("/sys/block")
    if block_path.exists():
        for dev_path in block_path.iterdir():
            dev_name = dev_path.name
            
            # Skip loop devices and partitions
            if dev_name.startswith("loop") or any(c.isdigit() for c in dev_name[-1:]):
                continue
            
            storage_entry = {
                "name": dev_name,
                "type": "disk",
                "size_bytes": None,
                "model": None,
                "serial": None,
                "tran": None,
                "driver": None,
                "driver_sysfs_path": None
            }
            
            # Resolve driver
            driver_link = dev_path / "device" / "driver"
            if driver_link.exists():
                try:
                    driver_target = driver_link.resolve()
                    storage_entry["driver"] = driver_target.name
                    storage_entry["driver_sysfs_path"] = str(driver_target)
                except (OSError, IOError):
                    pass
            
            storage.append(storage_entry)
        
        logger.info(f"Collected {len(storage)} storage devices from sysfs")
        return storage, "sysfs"
    
    return storage, "none"


def collect_gpu(logger: logging.Logger) -> Tuple[List[Dict[str, Any]], str]:
    """Collect GPU driver information."""
    logger.info("Collecting GPU driver information...")
    
    gpus = []
    
    if not shutil.which("nvidia-smi"):
        logger.info("nvidia-smi not found")
        return gpus, "none"
    
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,driver_version,vbios_version,pci.bus_id",
        "--format=csv,noheader,nounits"
    ]
    
    success, stdout, stderr = run_command(cmd, logger)
    
    if not success or not stdout.strip():
        logger.warning("nvidia-smi query failed")
        return gpus, "none"
    
    for line in stdout.strip().split("\n"):
        fields = [f.strip() for f in line.split(",")]
        
        if len(fields) < 6:
            continue
        
        def clean_na(value):
            return None if value.upper() in ("N/A", "[N/A]", "") else value
        
        gpu = {
            "index": int(fields[0]) if fields[0].isdigit() else None,
            "uuid": clean_na(fields[1]),
            "name": clean_na(fields[2]),
            "driver_version": clean_na(fields[3]),
            "vbios_version": clean_na(fields[4]),
            "pci_bus_id": clean_na(fields[5])
        }
        
        gpus.append(gpu)
    
    logger.info(f"Collected {len(gpus)} GPUs")
    return gpus, "nvidia_smi"


def parse_lsusb_tree(output: str, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Parse lsusb -t output."""
    tree = []
    
    for line in output.split("\n"):
        line = line.strip()
        if not line or not "Driver=" in line:
            continue
        
        # Extract components
        # Example: /:  Bus 01.Port 1: Dev 1, Class=root_hub, Driver=xhci-hcd/1p, 480M
        
        path = None
        usb_class = None
        driver = None
        speed = None
        
        # Extract path (everything before "Class=")
        if "Class=" in line:
            path = line.split("Class=")[0].strip()
        
        # Extract class
        class_match = re.search(r'Class=([^,]+)', line)
        if class_match:
            usb_class = class_match.group(1).strip()
        
        # Extract driver
        driver_match = re.search(r'Driver=([^,/\s]+)', line)
        if driver_match:
            driver_str = driver_match.group(1).strip()
            if driver_str and driver_str != "[none]":
                driver = driver_str
        
        # Extract speed (at end of line, e.g., "480M", "5000M")
        speed_match = re.search(r'(\d+M)\s*$', line)
        if speed_match:
            speed = speed_match.group(1)
        
        tree.append({
            "path": path or line,
            "class": usb_class,
            "driver": driver,
            "speed": speed
        })
    
    logger.debug(f"Parsed {len(tree)} USB tree entries with drivers")
    return tree


def collect_usb(enable: bool, max_raw_bytes: int, logger: logging.Logger) -> Tuple[Dict[str, Any], str]:
    """Collect USB driver bindings."""
    logger.info("Collecting USB driver bindings...")
    
    usb_data = {
        "available": False,
        "tree": [],
        "devices": [],
        "raw_tree_text": None
    }
    
    if not enable:
        logger.info("USB collection disabled")
        return usb_data, "none"
    
    if not shutil.which("lsusb"):
        logger.info("lsusb not found")
        return usb_data, "none"
    
    usb_data["available"] = True
    
    # Get tree view with drivers
    success, stdout, stderr = run_command(["lsusb", "-t"], logger)
    
    if success and stdout.strip():
        usb_data["tree"] = parse_lsusb_tree(stdout, logger)
        
        # Store truncated raw text
        if len(stdout) > max_raw_bytes:
            usb_data["raw_tree_text"] = stdout[:max_raw_bytes] + f"\n... [truncated, {len(stdout)} total bytes]"
        else:
            usb_data["raw_tree_text"] = stdout
    
    # Get device list (simple)
    success, stdout, stderr = run_command(["lsusb"], logger)
    
    if success and stdout.strip():
        for line in stdout.strip().split("\n")[:100]:  # Cap at 100 devices
            # Format: Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
            match = re.match(r'Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-f:]+)\s+(.+)', line, re.IGNORECASE)
            if match:
                usb_data["devices"].append({
                    "bus": match.group(1),
                    "device": match.group(2),
                    "id": match.group(3),
                    "description": match.group(4)
                })
    
    logger.info(f"Collected {len(usb_data['tree'])} USB tree entries, {len(usb_data['devices'])} devices")
    return usb_data, "lsusb_-t"


def collect_lsmod(logger: logging.Logger) -> Dict[str, Dict[str, Any]]:
    """Collect loaded modules from lsmod."""
    logger.info("Collecting loaded modules from lsmod...")
    
    modules = {}
    
    if not shutil.which("lsmod"):
        logger.warning("lsmod not found")
        return modules
    
    success, stdout, stderr = run_command(["lsmod"], logger)
    
    if not success or not stdout.strip():
        logger.warning("lsmod failed")
        return modules
    
    lines = stdout.strip().split("\n")
    
    for i, line in enumerate(lines):
        if i == 0:  # Skip header
            continue
        
        parts = line.split()
        if len(parts) < 3:
            continue
        
        module_name = parts[0]
        size = parts[1]
        used_by_count = parts[2]
        
        modules[module_name] = {
            "loaded": True,
            "size": size,
            "used_by_count": used_by_count
        }
    
    logger.info(f"Collected {len(modules)} loaded modules")
    return modules


def collect_modinfo(module: str, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """Collect module information from modinfo."""
    if not shutil.which("modinfo"):
        return None
    
    success, stdout, stderr = run_command(["modinfo", module], logger, timeout=5)
    
    if not success:
        logger.debug(f"modinfo {module} failed (may be built-in)")
        return None
    
    modinfo_data = {}
    
    for line in stdout.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        
        # Map common fields
        if key == "filename":
            modinfo_data["filename"] = value
        elif key == "version":
            modinfo_data["version"] = value
        elif key == "description":
            modinfo_data["description"] = value
        elif key == "author":
            modinfo_data["author"] = value
        elif key == "license":
            modinfo_data["license"] = value
        elif key == "signer":
            modinfo_data["signer"] = value
        elif key == "sig_key":
            modinfo_data["sig_key"] = value
        elif key == "vermagic":
            modinfo_data["vermagic"] = value
        elif key == "srcversion":
            modinfo_data["srcversion"] = value
        elif key == "depends":
            modinfo_data["depends"] = value
    
    return modinfo_data if modinfo_data else None


def build_drivers_manifest(
    pci_devices: List[Dict[str, Any]],
    nics: List[Dict[str, Any]],
    storage: List[Dict[str, Any]],
    usb_data: Dict[str, Any],
    lsmod_modules: Dict[str, Dict[str, Any]],
    enable_modinfo: bool,
    logger: logging.Logger
) -> List[Dict[str, Any]]:
    """Build comprehensive driver manifest."""
    logger.info("Building driver manifest...")
    
    # Collect all referenced drivers/modules
    referenced_modules: Set[str] = set()
    
    # From PCI
    for dev in pci_devices:
        if dev.get("kernel_driver_in_use"):
            referenced_modules.add(dev["kernel_driver_in_use"])
        for mod in dev.get("kernel_modules", []):
            referenced_modules.add(mod)
    
    # From NICs
    for nic in nics:
        if nic.get("driver") and not nic.get("is_virtual"):
            referenced_modules.add(nic["driver"])
    
    # From storage
    for stor in storage:
        if stor.get("driver"):
            referenced_modules.add(stor["driver"])
    
    # From USB
    for usb_entry in usb_data.get("tree", []):
        if usb_entry.get("driver"):
            referenced_modules.add(usb_entry["driver"])
    
    # Add known NVIDIA modules if loaded
    nvidia_modules = ["nvidia", "nvidia_drm", "nvidia_modeset", "nvidia_uvm", "nvidiafb"]
    for mod in nvidia_modules:
        if mod in lsmod_modules:
            referenced_modules.add(mod)
    
    logger.info(f"Found {len(referenced_modules)} referenced modules")
    
    # Build manifest entries
    manifest = []
    
    for module in sorted(referenced_modules):
        entry = {
            "module": module,
            "modinfo": None,
            "loaded": lsmod_modules.get(module, {}).get("loaded", None),
            "used_by": {
                "pci_devices": [],
                "net_ifaces": [],
                "storage": [],
                "usb": []
            }
        }
        
        # Enrich with modinfo
        if enable_modinfo:
            modinfo_data = collect_modinfo(module, logger)
            if modinfo_data:
                entry["modinfo"] = modinfo_data
        
        # Track which devices use this module
        
        # PCI devices
        for dev in pci_devices:
            if dev.get("kernel_driver_in_use") == module or module in dev.get("kernel_modules", []):
                entry["used_by"]["pci_devices"].append(dev["pci_addr"])
        
        # NICs
        for nic in nics:
            if nic.get("driver") == module and not nic.get("is_virtual"):
                entry["used_by"]["net_ifaces"].append(nic["ifname"])
        
        # Storage
        for stor in storage:
            if stor.get("driver") == module:
                entry["used_by"]["storage"].append(stor["name"])
        
        # USB
        for usb_entry in usb_data.get("tree", []):
            if usb_entry.get("driver") == module:
                entry["used_by"]["usb"].append(usb_entry.get("path", "unknown"))
        
        # Sort lists for determinism
        entry["used_by"]["pci_devices"].sort()
        entry["used_by"]["net_ifaces"].sort()
        entry["used_by"]["storage"].sort()
        entry["used_by"]["usb"].sort()
        
        manifest.append(entry)
    
    logger.info(f"Built manifest with {len(manifest)} modules")
    return manifest


def collect_driver_inventory(
    config: Dict[str, Any],
    args: argparse.Namespace,
    logger: logging.Logger
) -> Dict[str, Any]:
    """Main collection orchestrator."""
    
    logger.info("=" * 60)
    logger.info("Starting driver inventory collection")
    logger.info("=" * 60)
    
    # Platform and kernel identity
    platform, asset_id, asset_id_source = collect_platform_identity(logger)
    kernel = collect_kernel_identity(logger)
    
    # Collect device-driver bindings
    pci_devices, pci_source = collect_pci_devices(logger)
    nics, nics_source = collect_nics(pci_devices, logger)
    storage, storage_source = collect_storage(logger)
    gpu, gpu_source = collect_gpu(logger)
    
    enable_usb = config.get("enable_usb", True) and not args.no_usb
    max_raw_bytes = args.max_raw_bytes or config.get("max_raw_bytes", MAX_RAW_BYTES_DEFAULT)
    usb_data, usb_source = collect_usb(enable_usb, max_raw_bytes, logger)
    
    # Collect loaded modules
    lsmod_modules = collect_lsmod(logger)
    
    # Build driver manifest
    enable_modinfo = config.get("enable_modinfo", True) and not args.no_modinfo
    drivers_manifest = build_drivers_manifest(
        pci_devices, nics, storage, usb_data, lsmod_modules, enable_modinfo, logger
    )
    
    # Build output
    output = {
        "collected_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "asset_id": asset_id,
        "asset_id_source": asset_id_source,
        "platform_dmi": platform,
        "kernel": kernel,
        "pci": pci_devices,
        "nics": nics,
        "storage": storage,
        "gpu": gpu,
        "usb": usb_data,
        "drivers_manifest": drivers_manifest,
        "sources": {
            "pci": pci_source,
            "nics": nics_source,
            "storage": storage_source,
            "gpu": gpu_source,
            "usb": usb_source,
            "modules": "lsmod|modinfo" if enable_modinfo else "lsmod"
        }
    }
    
    logger.info("=" * 60)
    logger.info("Driver inventory collection complete")
    logger.info(f"  PCI devices: {len(pci_devices)}")
    logger.info(f"  NICs: {len(nics)}")
    logger.info(f"  Storage: {len(storage)}")
    logger.info(f"  GPUs: {len(gpu)}")
    logger.info(f"  USB entries: {len(usb_data.get('tree', []))}")
    logger.info(f"  Driver manifest: {len(drivers_manifest)} modules")
    logger.info("=" * 60)
    
    return output


def write_output(data: Dict[str, Any], output_path: str, logger: logging.Logger) -> None:
    """Write output JSON atomically."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    temp_file = output_file.parent / f".{output_file.name}.tmp"
    
    try:
        with temp_file.open("w") as f:
            json.dump(data, f, indent=2, sort_keys=False)
        
        temp_file.replace(output_file)
        
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
        description="Driver Inventory Reporter for DGX Spark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print driver inventory to stdout
  %(prog)s --print
  
  # Write to default location (requires sudo)
  sudo %(prog)s
  
  # Write to custom location
  %(prog)s --output /tmp/driver_inventory.json
  
  # Skip USB collection
  %(prog)s --no_usb --print
  
  # Skip modinfo enrichment (faster)
  %(prog)s --no_modinfo --print
        """
    )
    
    parser.add_argument("--print", action="store_true",
                        help="Print JSON to stdout only (do not write file)")
    parser.add_argument("--output", metavar="PATH",
                        help="Override output file path")
    parser.add_argument("--config", metavar="PATH",
                        help="Override config file path")
    parser.add_argument("--no_usb", action="store_true",
                        help="Skip USB collection")
    parser.add_argument("--no_modinfo", action="store_true",
                        help="Skip modinfo enrichment")
    parser.add_argument("--max_raw_bytes", type=int, metavar="N",
                        help="Cap raw text fields (default 200000)")
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

    logger.info(f"Driver Inventory Reporter starting...")
    logger.info(f"Config: {config_path} (exists: {config_path.exists()})")

    try:
        # Collect inventory
        inventory = collect_driver_inventory(config, args, logger)

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
