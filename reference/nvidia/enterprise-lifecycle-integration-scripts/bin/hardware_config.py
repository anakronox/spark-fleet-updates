#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Hardware Inventory Collector - Hardware Configuration Enumeration

Enumerates CPU, memory, storage, network interfaces, GPUs, and PCI devices
for enterprise asset inventory and management.

Requirements:
    - Python 3.6+
    - Standard library only (no external dependencies)
    - Optional tools: lscpu, lsblk, ip, ethtool, nvidia-smi, lspci

Exit Codes:
    0 - Success
    Non-zero - Unexpected failure

Author: DGX Spark Management Team
Version: 1.0.0
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

__version__ = "1.0.0"
_TOOL = "hardware_config"
_FUNCTIONAL_AREA = "clear_asset_information"

# Add common module to path (works from both src/ and bin/ locations)
_script_dir = Path(__file__).parent
_common_path = _script_dir / "common" if _script_dir.name == "bin" else _script_dir.parent.parent.parent / "common"
sys.path.insert(0, str(_common_path))
from output import (emit_ok, emit_error, log as olog, route_output, set_quiet,
                    add_standard_output_flags, make_error,
                    EC_GENERAL, EC_INTERRUPTED, EXIT_GENERAL_ERROR, EXIT_INTERRUPTED)
from asset_id import resolve_asset_id, get_platform_dmi, load_identity_file

# Default paths
DEFAULT_OUTPUT_PATH = Path(f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.json")
DEFAULT_IDENTITY_PATH = Path(f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/device_identity/device_identity.json")
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "hardware_config.conf"

# DMI sysfs base
DMI_BASE = Path("/sys/class/dmi/id")


def run_command(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """
    Run a command and return stdout, or None if command fails.
    
    Args:
        cmd: Command and arguments as list
        timeout: Timeout in seconds
        
    Returns:
        Command stdout as string, or None if failed
    """
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return None


def load_config(config_path: Path) -> Dict[str, str]:
    """
    Load configuration from key=value file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary
    """
    config = {}
    try:
        if config_path.exists():
            with config_path.open('r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
    except (OSError, IOError):
        pass
    return config


def load_device_identity(identity_path: Path) -> Dict[str, Any]:
    """
    Load device identity from previous requirement.

    Args:
        identity_path: Path to device_identity.json

    Returns:
        Identity dictionary (envelope unwrapped), or empty dict if unavailable
    """
    return load_identity_file(str(identity_path))


def read_dmi_field(field_name: str) -> Optional[str]:
    """
    Read a DMI field from sysfs.
    
    Args:
        field_name: Name of DMI field
        
    Returns:
        Field value or None
    """
    field_path = DMI_BASE / field_name
    try:
        if field_path.exists():
            value = field_path.read_text(encoding='utf-8', errors='ignore').strip()
            value = value.replace('\x00', '').strip()
            if value:
                return value
    except (OSError, IOError):
        pass
    return None


def collect_platform_identity(identity: Dict[str, Any]) -> tuple:
    """
    Collect platform identity, preferring loaded identity file.

    Args:
        identity: Loaded device identity dict (already envelope-unwrapped)

    Returns:
        Tuple of (platform_dict, asset_id, asset_id_source, source_used)
    """
    # Always read live platform_dmi from sysfs for completeness
    platform = get_platform_dmi()

    # Prefer asset_id from identity file if available; otherwise use full fallback chain
    asset_id = identity.get("asset_id") if identity else None
    asset_id_source = identity.get("asset_id_source", "unknown") if (identity and asset_id) else "unknown"
    source_used = "device_identity.json" if (identity and asset_id) else "dmi_sysfs"

    if not asset_id:
        asset_id, asset_id_source = resolve_asset_id()
        source_used = "dmi_sysfs"

    return platform, asset_id, asset_id_source, source_used


def collect_cpu_info() -> tuple:
    """
    Collect CPU information.
    
    Returns:
        Tuple of (cpu_dict, source_used)
    """
    cpu = {
        "architecture": None,
        "logical_cpus": None,
        "sockets": None,
        "cores_per_socket": None,
        "threads_per_core": None,
        "model_names": [],
        "max_mhz": None,
        "min_mhz": None,
    }
    
    # Try lscpu -J (JSON)
    output = run_command(["lscpu", "-J"])
    if output:
        try:
            data = json.loads(output)
            lscpu_data = {}
            for item in data.get("lscpu", []):
                lscpu_data[item["field"].rstrip(":")] = item["data"]
            
            cpu["architecture"] = lscpu_data.get("Architecture")
            cpu["logical_cpus"] = int(lscpu_data.get("CPU(s)", 0)) or None
            cpu["sockets"] = int(lscpu_data.get("Socket(s)", 0)) or None
            cpu["cores_per_socket"] = int(lscpu_data.get("Core(s) per socket", 0)) or None
            cpu["threads_per_core"] = int(lscpu_data.get("Thread(s) per core", 0)) or None
            
            model = lscpu_data.get("Model name")
            if model:
                cpu["model_names"] = [model]
            
            # Try to get MHz values
            for key in ["CPU max MHz", "CPU MHz"]:
                if key in lscpu_data:
                    try:
                        cpu["max_mhz"] = float(lscpu_data[key])
                        break
                    except (ValueError, TypeError):
                        pass
            
            for key in ["CPU min MHz"]:
                if key in lscpu_data:
                    try:
                        cpu["min_mhz"] = float(lscpu_data[key])
                    except (ValueError, TypeError):
                        pass
            
            return cpu, "lscpu_json"
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    
    # Fallback to plain lscpu
    output = run_command(["lscpu"])
    if output:
        try:
            for line in output.splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == "Architecture":
                        cpu["architecture"] = value
                    elif key == "CPU(s)":
                        cpu["logical_cpus"] = int(value) or None
                    elif key == "Socket(s)":
                        cpu["sockets"] = int(value) or None
                    elif key == "Core(s) per socket":
                        cpu["cores_per_socket"] = int(value) or None
                    elif key == "Thread(s) per core":
                        cpu["threads_per_core"] = int(value) or None
                    elif key == "Model name":
                        cpu["model_names"] = [value]
            return cpu, "lscpu_text"
        except (ValueError, IndexError):
            pass
    
    # Fallback to /proc/cpuinfo
    try:
        with open("/proc/cpuinfo", "r") as f:
            model_names_seen = set()
            processor_count = 0
            for line in f:
                if line.startswith("processor"):
                    processor_count += 1
                elif line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    model_names_seen.add(model)
            
            cpu["logical_cpus"] = processor_count or None
            cpu["model_names"] = list(model_names_seen)
            return cpu, "procfs"
    except (OSError, IOError):
        pass
    
    return cpu, "procfs"


def collect_memory_info() -> tuple:
    """
    Collect memory information from /proc/meminfo.
    
    Returns:
        Tuple of (memory_dict, source_used)
    """
    memory = {
        "mem_total_bytes": None,
        "mem_free_bytes": None,
        "mem_available_bytes": None,
    }
    
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Parse value (e.g., "12345 kB")
                    parts = value.split()
                    if len(parts) >= 1:
                        try:
                            val = int(parts[0])
                            # Convert kB to bytes
                            val_bytes = val * 1024
                            
                            if key == "MemTotal":
                                memory["mem_total_bytes"] = val_bytes
                            elif key == "MemFree":
                                memory["mem_free_bytes"] = val_bytes
                            elif key == "MemAvailable":
                                memory["mem_available_bytes"] = val_bytes
                        except ValueError:
                            pass
    except (OSError, IOError):
        pass
    
    return memory, "procfs"


def collect_storage_info(include_loop: bool = False, include_rom: bool = True) -> tuple:
    """
    Collect storage device information.
    
    Args:
        include_loop: Include loop devices
        include_rom: Include ROM devices
        
    Returns:
        Tuple of (storage_list, source_used)
    """
    storage = []
    
    # Try lsblk -J
    output = run_command(["lsblk", "-J", "-b", "-o", "NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,ROTA,WWN,MOUNTPOINT,FSTYPE"])
    if output:
        try:
            data = json.loads(output)
            for device in data.get("blockdevices", []):
                dev_type = device.get("type", "")
                
                # Filter loop devices
                if dev_type == "loop" and not include_loop:
                    continue
                
                # Filter ROM if not wanted
                if dev_type == "rom" and not include_rom:
                    continue
                
                # Include disk and rom
                if dev_type in ["disk", "rom"]:
                    storage_item = {
                        "name": device.get("name"),
                        "type": dev_type,
                        "size_bytes": device.get("size"),
                        "model": device.get("model"),
                        "serial": device.get("serial"),
                        "tran": device.get("tran"),
                        "rota": device.get("rota"),
                        "wwn": device.get("wwn"),
                    }
                    
                    # Include children (partitions) if present
                    if "children" in device:
                        storage_item["children"] = device["children"]
                    
                    storage.append(storage_item)
            
            return storage, "lsblk_json"
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Fallback to /sys/block
    try:
        for block_dev in Path("/sys/block").iterdir():
            if block_dev.name.startswith("loop") and not include_loop:
                continue
            
            size_path = block_dev / "size"
            if size_path.exists():
                try:
                    size_sectors = int(size_path.read_text().strip())
                    size_bytes = size_sectors * 512  # Assume 512-byte sectors
                    
                    storage.append({
                        "name": block_dev.name,
                        "type": "disk",
                        "size_bytes": size_bytes,
                        "model": None,
                        "serial": None,
                        "tran": None,
                        "rota": None,
                        "wwn": None,
                    })
                except (ValueError, OSError):
                    pass
        return storage, "sysfs"
    except (OSError, IOError):
        pass
    
    return storage, "sysfs"


def collect_network_info(include_virtual: bool = True) -> tuple:
    """
    Collect network interface information.
    
    Args:
        include_virtual: Include virtual interfaces like docker0
        
    Returns:
        Tuple of (network_list, source_used)
    """
    network = []
    sources = []
    
    # Try ip -j link
    output = run_command(["ip", "-j", "link"])
    if output:
        try:
            interfaces = json.loads(output)
            sources.append("ip_json")
            
            for iface in interfaces:
                ifname = iface.get("ifname", "")
                
                # Skip loopback
                if ifname == "lo":
                    continue
                
                # Determine if virtual
                is_virtual = False
                if ifname.startswith(("docker", "br-", "veth", "virbr")):
                    is_virtual = True
                    if not include_virtual and ifname != "docker0":
                        # Always include docker0, skip others if not wanted
                        continue
                
                net_item = {
                    "ifname": ifname,
                    "is_virtual": is_virtual,
                    "is_wireless": None,
                    "mac": iface.get("address"),
                    "mtu": iface.get("mtu"),
                    "operstate": iface.get("operstate"),
                    "speed_mbps": None,
                    "driver": None,
                    "driver_version": None,
                    "firmware_version": None,
                    "bus_info": None,
                    "pci_vendor_id": None,
                    "pci_device_id": None,
                }
                
                # Try to get speed from sysfs
                speed_path = Path(f"/sys/class/net/{ifname}/speed")
                try:
                    if speed_path.exists():
                        speed = int(speed_path.read_text().strip())
                        if speed > 0:
                            net_item["speed_mbps"] = speed
                except (ValueError, OSError, IOError):
                    pass
                
                # Check if wireless
                wireless_path = Path(f"/sys/class/net/{ifname}/wireless")
                if wireless_path.exists():
                    net_item["is_wireless"] = True
                    sources.append("sysfs")
                
                # Try ethtool -i for driver info
                if not is_virtual:
                    ethtool_output = run_command(["ethtool", "-i", ifname])
                    if ethtool_output:
                        sources.append("ethtool")
                        for line in ethtool_output.splitlines():
                            if ':' in line:
                                key, value = line.split(':', 1)
                                key = key.strip()
                                value = value.strip()
                                
                                if key == "driver":
                                    net_item["driver"] = value
                                    # Check if wireless driver
                                    if "wireless" in value.lower() or "wl" in value.lower():
                                        net_item["is_wireless"] = True
                                elif key == "version":
                                    net_item["driver_version"] = value
                                elif key == "firmware-version":
                                    net_item["firmware_version"] = value
                                elif key == "bus-info":
                                    net_item["bus_info"] = value
                
                # Try to get PCI IDs from sysfs
                vendor_path = Path(f"/sys/class/net/{ifname}/device/vendor")
                device_path = Path(f"/sys/class/net/{ifname}/device/device")
                try:
                    if vendor_path.exists():
                        net_item["pci_vendor_id"] = vendor_path.read_text().strip()
                    if device_path.exists():
                        net_item["pci_device_id"] = device_path.read_text().strip()
                except (OSError, IOError):
                    pass
                
                network.append(net_item)
            
            return network, "|".join(set(sources)) if sources else "ip_json"
        except (json.JSONDecodeError, KeyError):
            pass
    
    return network, "sysfs"


def collect_gpu_info() -> tuple:
    """
    Collect GPU information using nvidia-smi.
    
    Returns:
        Tuple of (gpu_list, source_used)
    """
    gpus = []
    
    # Try nvidia-smi
    output = run_command(["nvidia-smi", "--query-gpu=index,uuid,name,driver_version,pci.bus_id,memory.total", "--format=csv,noheader,nounits"])
    if output:
        for line in output.strip().splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 6:
                gpu = {
                    "index": None,
                    "uuid": None,
                    "name": None,
                    "driver_version": None,
                    "pci_bus_id": None,
                    "memory_total_mib": None,
                }
                
                # Parse fields, treat "N/A" as null
                try:
                    idx = parts[0]
                    gpu["index"] = int(idx) if idx.lower() != "n/a" else None
                except (ValueError, IndexError):
                    pass
                
                uuid = parts[1] if len(parts) > 1 else ""
                gpu["uuid"] = uuid if uuid.lower() != "n/a" else None
                
                name = parts[2] if len(parts) > 2 else ""
                gpu["name"] = name if name.lower() != "n/a" else None
                
                driver = parts[3] if len(parts) > 3 else ""
                gpu["driver_version"] = driver if driver.lower() != "n/a" else None
                
                pci = parts[4] if len(parts) > 4 else ""
                gpu["pci_bus_id"] = pci if pci.lower() != "n/a" else None
                
                try:
                    mem = parts[5] if len(parts) > 5 else ""
                    if mem.lower() != "n/a":
                        gpu["memory_total_mib"] = int(float(mem))
                except (ValueError, IndexError):
                    pass
                
                gpus.append(gpu)
        
        return gpus, "nvidia_smi"
    
    # Fallback to /proc/driver/nvidia
    try:
        nvidia_proc = Path("/proc/driver/nvidia")
        if nvidia_proc.exists():
            # At least we know NVIDIA driver is present
            return gpus, "proc_driver_nvidia"
    except:
        pass
    
    return gpus, "nvidia_smi"


def collect_pci_devices() -> tuple:
    """
    Collect key PCI device information.
    
    Returns:
        Tuple of (pci_list, source_used)
    """
    pci_devices = []
    
    output = run_command(["lspci", "-D", "-nn"])
    if output:
        # Keywords to filter for
        keywords = ["ethernet", "network", "vga", "nvme", "storage", "nvidia", "mellanox", "connectx", "realtek", "mediatek"]
        
        for line in output.splitlines():
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                # Parse line: "DDDD:BB:DD.F Class text [VVVV:DDDD]: Description"
                parts = line.split(maxsplit=1)
                if len(parts) >= 2:
                    pci_addr = parts[0]
                    rest = parts[1]
                    
                    # Extract vendor:device ID in brackets
                    vendor_device = ""
                    if '[' in rest and ']' in rest:
                        start = rest.rfind('[')
                        end = rest.rfind(']')
                        vendor_device = rest[start:end+1]
                    
                    # Class text is before the colon
                    class_text = ""
                    if ':' in rest:
                        class_text = rest.split(':', 1)[0].strip()
                    
                    # Description is after vendor:device
                    description = rest
                    if vendor_device:
                        description = rest.split(vendor_device, 1)[-1].strip().lstrip(':').strip()
                    
                    pci_devices.append({
                        "pci_addr": pci_addr,
                        "class_text": class_text,
                        "vendor_device_id": vendor_device,
                        "description": description,
                    })
        
        return pci_devices, "lspci"
    
    return pci_devices, "lspci"


def generate_hardware_config(identity_path: Path, config: Dict[str, str]) -> Dict[str, Any]:
    """
    Generate complete hardware configuration.
    
    Args:
        identity_path: Path to device identity file
        config: Configuration dictionary
        
    Returns:
        Hardware configuration dictionary
    """
    # Load device identity if available
    identity = load_device_identity(identity_path)
    
    # Collect all information
    platform, asset_id, asset_id_source, platform_source = collect_platform_identity(identity)
    cpu, cpu_source = collect_cpu_info()
    memory, memory_source = collect_memory_info()
    
    include_loop = config.get("include_loop_devices", "false").lower() == "true"
    include_rom = config.get("include_rom_devices", "true").lower() == "true"
    storage, storage_source = collect_storage_info(include_loop, include_rom)
    
    include_virtual = config.get("include_virtual_interfaces", "true").lower() == "true"
    network, network_source = collect_network_info(include_virtual)
    
    gpu, gpu_source = collect_gpu_info()
    pci, pci_source = collect_pci_devices()
    
    # Get timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Build output
    hardware = {
        "collected_at_utc": timestamp,
        "asset_id": asset_id,
        "asset_id_source": asset_id_source,
        "platform_dmi": platform,
        "cpu": cpu,
        "memory": memory,
        "storage": storage,
        "network": network,
        "gpu": gpu,
        "pci": pci,
        "sources": {
            "platform_dmi": platform_source,
            "cpu": cpu_source,
            "memory": memory_source,
            "storage": storage_source,
            "network": network_source,
            "gpu": gpu_source,
            "pci": pci_source,
        }
    }
    
    return hardware


def write_output_file(data: Dict[str, Any], output_path: Path) -> None:
    """
    Write output to JSON file atomically.
    
    Args:
        data: Data to write
        output_path: Output file path
    """
    # Create directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    
    # Write to temp file
    temp_path = output_path.parent / f".{output_path.name}.tmp"
    
    try:
        with temp_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')
        
        # Set permissions (best-effort)
        try:
            os.chmod(temp_path, 0o644)
        except OSError:
            pass
        
        # Atomic move
        temp_path.replace(output_path)
        
    finally:
        # Clean up temp file if exists
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Enumerate hardware configuration (CPU/GPU/SSD/NIC/etc.)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print configuration to stdout
  python3 hardware_config.py --print

  # Write to default location
  sudo python3 hardware_config.py

  # Write to custom location
  python3 hardware_config.py --output /tmp/hardware_config.json

  # Use custom identity file
  python3 hardware_config.py --identity /tmp/device_identity.json

For more information, see:
  clear_asset_information/hardware_inventory_collector/hardware_config.md
        """
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    parser.add_argument(
        '--print',
        action='store_true',
        help='Print JSON to stdout only (do not write file)'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        metavar='PATH',
        help='Override output file path'
    )
    
    parser.add_argument(
        '--identity',
        type=Path,
        metavar='PATH',
        help='Override device identity file path'
    )
    add_standard_output_flags(parser)

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_arguments()
    set_quiet(args.quiet)

    try:
        # Load configuration
        config = load_config(DEFAULT_CONFIG_PATH)

        # Determine identity path
        if args.identity:
            identity_path = args.identity
        else:
            identity_path = Path(config.get("identity_path", str(DEFAULT_IDENTITY_PATH)))

        # Collect hardware configuration
        olog("Collecting hardware configuration...")
        hardware = generate_hardware_config(identity_path, config)

        default_path = str(args.output) if args.output else config.get("output_path", str(DEFAULT_OUTPUT_PATH))
        route_output(
            hardware, args, _TOOL, __version__, default_path,
            lambda data, path: write_output_file(data, Path(path)),
        )

        return 0

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
