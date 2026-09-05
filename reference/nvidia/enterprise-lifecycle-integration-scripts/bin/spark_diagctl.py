#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
spark_diagctl.py

Diagnostics and Observability Control Plane for DGX Spark.

Provides comprehensive diagnostic collection covering:
- Health metrics (CPU/GPU/memory/disk/network/thermals/power)
- Structured system event logging (journald/syslog)
- Hardware/FW event logs (boot, ACPI, PCIe errors, ESRT, fwupd, rasdaemon)
- Crash dump capture (kernel kdump + userspace core dumps)
- GPU/accelerator telemetry and error reporting

Design:
- JSON-first output (--human for readable format)
- Read-only by default; state-changing operations require root + explicit flags
- Configurable truncation to prevent runaway output
- Stdlib-only (no external Python dependencies)

Author: DGX Spark Management Team
License: MIT
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
from typing import Any, Dict, List, Optional, Tuple

# Add common module to path
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
    create_subparser_tool_parser,
    setup_logging as cli_setup_logging,
    ExitCode,
)

# ============================================================================
# Constants
# ============================================================================

VERSION = "1.1.0"  # Bumped for CLI standardization
TOOL_NAME = "spark_diagctl"

DEFAULT_CONFIG = {
    "runtime_output_dir": "/var/lib/dgx_spark_management/remote_ops_remediation/diagnostic_collector",
    "log_path": "/var/log/dgx_spark/remote_ops_remediation/diagnostic_collector/spark_diagctl.log",
    "truncate": {
        "max_lines": 500,
        "max_bytes": 500000
    },
    "health": {
        "fast_mode": True,
        "poll_interval_sec": 1
    },
    "crash": {
        "kdump_config": "/etc/default/kdump-tools",
        "core_pattern": "/proc/sys/kernel/core_pattern",
        "core_dump_dirs": ["/var/crash", "/var/lib/systemd/coredump"]
    }
}

logger = logging.getLogger(__name__)

# ============================================================================
# Utility Functions
# ============================================================================

# setup_logging() now imported from cli_base
# Use: cli_setup_logging(log_path, verbose, tool_name="spark_diagctl")


def run_command(
    cmd: List[str],
    timeout: int = 30
) -> Tuple[bool, str, str, Optional[int]]:
    """Run command and return results."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return True, result.stdout, result.stderr, result.returncode
    
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s", None
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}", None
    except Exception as e:
        return False, "", str(e), None


def truncate_text(text: str, max_lines: int, max_bytes: int) -> Tuple[str, bool]:
    """Truncate text by lines or bytes."""
    truncated = False
    
    lines = text.split("\n")
    if len(lines) > max_lines:
        text = "\n".join(lines[:max_lines])
        truncated = True
    
    if len(text.encode("utf-8")) > max_bytes:
        text = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        truncated = True
    
    return text, truncated


# format_envelope() replaced by format_envelope() from cli_base
# Tool and version info added to meta in main() function


def require_root() -> Tuple[bool, Optional[str]]:
    """Check if running as root."""
    if os.geteuid() != 0:
        return False, "This operation requires root permissions (run with sudo)"
    return True, None


# ============================================================================
# Health Metrics Collection
# ============================================================================

def collect_cpu_metrics(config: Dict) -> Dict:
    """Collect CPU health metrics."""
    metrics = {
        "load_average": None,
        "cpu_count": None,
        "cpu_usage_percent": None,
        "top_processes": []
    }
    
    # Load average
    try:
        with open("/proc/loadavg", "r") as f:
            load_parts = f.read().split()
            metrics["load_average"] = {
                "1min": float(load_parts[0]),
                "5min": float(load_parts[1]),
                "15min": float(load_parts[2])
            }
    except Exception as e:
        logger.debug(f"Failed to read load average: {e}")
    
    # CPU count
    try:
        metrics["cpu_count"] = os.cpu_count()
    except Exception:
        pass
    
    # Top processes by CPU
    success, stdout, _, _ = run_command(["ps", "aux", "--sort=-%cpu"], timeout=5)
    if success:
        lines = stdout.strip().split("\n")[1:6]  # Top 5
        metrics["top_processes"] = [line.split()[10] for line in lines if line]
    
    return metrics


def collect_memory_metrics(config: Dict) -> Dict:
    """Collect memory health metrics."""
    metrics = {
        "mem_total_kb": None,
        "mem_free_kb": None,
        "mem_available_kb": None,
        "mem_used_percent": None
    }
    
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = {}
            for line in f:
                if ":" in line:
                    key, value = line.split(":", 1)
                    meminfo[key.strip()] = int(value.strip().split()[0])
            
            metrics["mem_total_kb"] = meminfo.get("MemTotal")
            metrics["mem_free_kb"] = meminfo.get("MemFree")
            metrics["mem_available_kb"] = meminfo.get("MemAvailable")
            
            if meminfo.get("MemTotal"):
                used = meminfo["MemTotal"] - meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
                metrics["mem_used_percent"] = round(used / meminfo["MemTotal"] * 100, 1)
    
    except Exception as e:
        logger.debug(f"Failed to read meminfo: {e}")
    
    return metrics


def collect_disk_metrics(config: Dict) -> Dict:
    """Collect disk health metrics."""
    metrics = {
        "filesystems": []
    }
    
    # df output
    success, stdout, _, _ = run_command(["df", "-h", "-x", "tmpfs", "-x", "devtmpfs"], timeout=5)
    if success:
        lines = stdout.strip().split("\n")[1:]  # Skip header
        for line in lines:
            parts = line.split()
            if len(parts) >= 6:
                metrics["filesystems"].append({
                    "filesystem": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "avail": parts[3],
                    "use_percent": parts[4],
                    "mounted_on": parts[5]
                })
    
    return metrics


def collect_network_metrics(config: Dict) -> Dict:
    """Collect network health metrics."""
    metrics = {
        "interfaces": []
    }
    
    # ip -s link
    success, stdout, _, _ = run_command(["ip", "-s", "link"], timeout=5)
    if success:
        # Parse interface stats (simplified)
        current_if = None
        for line in stdout.split("\n"):
            if re.match(r'^\d+:', line):
                parts = line.split()
                if_name = parts[1].rstrip(":")
                state = parts[8] if len(parts) > 8 else "UNKNOWN"
                current_if = {"name": if_name, "state": state, "rx_bytes": 0, "tx_bytes": 0}
                metrics["interfaces"].append(current_if)
            elif "RX:" in line and current_if:
                # Next line has RX stats
                continue
            elif current_if and re.match(r'^\s+\d+', line):
                parts = line.split()
                if len(parts) >= 2:
                    current_if["rx_bytes"] = int(parts[0])
    
    return metrics


def collect_thermal_metrics(config: Dict) -> Dict:
    """Collect thermal metrics."""
    metrics = {
        "sensors_available": False,
        "temperatures": []
    }
    
    if not shutil.which("sensors"):
        return metrics
    
    success, stdout, _, _ = run_command(["sensors"], timeout=5)
    if success:
        metrics["sensors_available"] = True
        # Parse sensor output (simplified)
        for line in stdout.split("\n"):
            if "°C" in line and ":" in line:
                metrics["temperatures"].append(line.strip())
    
    return metrics


def collect_gpu_health(config: Dict) -> Dict:
    """Collect GPU health metrics."""
    metrics = {
        "nvidia_smi_available": False,
        "gpus": []
    }
    
    if not shutil.which("nvidia-smi"):
        return metrics
    
    metrics["nvidia_smi_available"] = True
    
    # nvidia-smi query
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit",
        "--format=csv,noheader,nounits"
    ]
    
    success, stdout, _, _ = run_command(cmd, timeout=10)
    if success:
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 9:
                metrics["gpus"].append({
                    "index": parts[0],
                    "name": parts[1],
                    "temp_c": parts[2] if parts[2] != "N/A" else None,
                    "util_gpu_percent": parts[3] if parts[3] != "N/A" else None,
                    "util_mem_percent": parts[4] if parts[4] != "N/A" else None,
                    "mem_used_mib": parts[5] if parts[5] != "N/A" else None,
                    "mem_total_mib": parts[6] if parts[6] != "N/A" else None,
                    "power_draw_w": parts[7] if parts[7] != "N/A" else None,
                    "power_limit_w": parts[8] if parts[8] != "N/A" else None
                })
    
    return metrics


def cmd_health_snapshot(args, config: Dict) -> Dict:
    """Health snapshot command."""
    logger.info("Collecting health snapshot...")
    
    errors = []
    
    data = {
        "cpu": collect_cpu_metrics(config),
        "memory": collect_memory_metrics(config),
        "disk": collect_disk_metrics(config),
        "network": collect_network_metrics(config),
        "thermal": collect_thermal_metrics(config),
        "gpu": collect_gpu_health(config)
    }
    
    return format_envelope(True, data, errors)


# ============================================================================
# System Event Logging
# ============================================================================

def cmd_logs_snapshot(args, config: Dict) -> Dict:
    """Logs snapshot command."""
    logger.info("Collecting system logs snapshot...")
    
    errors = []
    max_lines = args.max_lines or config["truncate"]["max_lines"]
    max_bytes = args.max_bytes or config["truncate"]["max_bytes"]
    
    data = {
        "journald": {},
        "syslog": {},
        "kern_log": {}
    }
    
    # journalctl (last N lines)
    success, stdout, stderr, _ = run_command(
        ["journalctl", "-n", str(max_lines), "--no-pager"],
        timeout=30
    )
    if success:
        truncated_output, truncated = truncate_text(stdout, max_lines, max_bytes)
        data["journald"] = {
            "lines": truncated_output.split("\n"),
            "truncated": truncated
        }
    else:
        errors.append(f"journalctl failed: {stderr}")
    
    # journalctl kernel log
    success, stdout, _, _ = run_command(
        ["journalctl", "-k", "-n", str(max_lines // 2), "--no-pager"],
        timeout=30
    )
    if success:
        truncated_output, truncated = truncate_text(stdout, max_lines // 2, max_bytes // 2)
        data["kern_log"] = {
            "lines": truncated_output.split("\n"),
            "truncated": truncated
        }
    
    # Check if rsyslog is active
    success, stdout, _, _ = run_command(["systemctl", "is-active", "rsyslog"], timeout=5)
    data["syslog"]["rsyslog_active"] = (stdout.strip() == "active")
    
    return format_envelope(True, data, errors)


# ============================================================================
# Hardware/Firmware Event Logs
# ============================================================================

def cmd_hwfw_events_snapshot(args, config: Dict) -> Dict:
    """Hardware/firmware events snapshot."""
    logger.info("Collecting hardware/firmware event logs...")
    
    errors = []
    max_lines = args.max_lines or config["truncate"]["max_lines"]
    
    data = {
        "boot_logs": {},
        "acpi_events": {},
        "pcie_aer": {},
        "fwupd_history": {},
        "rasdaemon": {}
    }
    
    # Boot logs from journalctl
    success, stdout, _, _ = run_command(
        ["journalctl", "-b", "-0", "-n", str(max_lines), "--no-pager"],
        timeout=30
    )
    if success:
        truncated_output, truncated = truncate_text(stdout, max_lines, config["truncate"]["max_bytes"])
        data["boot_logs"] = {
            "lines": truncated_output.split("\n"),
            "truncated": truncated
        }
    
    # ACPI events
    success, stdout, _, _ = run_command(
        ["journalctl", "-u", "acpid", "-n", "100", "--no-pager"],
        timeout=10
    )
    if success:
        data["acpi_events"]["available"] = True
        data["acpi_events"]["recent_count"] = len(stdout.strip().split("\n"))
    else:
        data["acpi_events"]["available"] = False
    
    # PCIe AER errors from dmesg
    success, stdout, _, _ = run_command(["journalctl", "-k", "--grep=AER"], timeout=10)
    if success and stdout.strip():
        truncated_output, truncated = truncate_text(stdout, 50, 50000)
        data["pcie_aer"] = {
            "errors_found": True,
            "lines": truncated_output.split("\n"),
            "truncated": truncated
        }
    else:
        data["pcie_aer"]["errors_found"] = False
    
    # fwupd history
    if shutil.which("fwupdmgr"):
        success, stdout, _, _ = run_command(["fwupdmgr", "get-history"], timeout=10)
        if success:
            data["fwupd_history"]["available"] = True
            truncated_output, truncated = truncate_text(stdout, 100, 100000)
            data["fwupd_history"]["output"] = truncated_output
        else:
            data["fwupd_history"]["available"] = False
    
    # rasdaemon (if present)
    success, stdout, _, _ = run_command(["systemctl", "is-active", "rasdaemon"], timeout=5)
    data["rasdaemon"]["active"] = (stdout.strip() == "active")
    
    return format_envelope(True, data, errors)


# ============================================================================
# Crash Diagnostics
# ============================================================================

def cmd_crash_status(args, config: Dict) -> Dict:
    """Crash dump status."""
    logger.info("Checking crash dump status...")
    
    errors = []
    
    data = {
        "kdump": {
            "enabled": False,
            "config_path": config["crash"]["kdump_config"],
            "config_exists": False,
            "service_active": False
        },
        "userspace_coredumps": {
            "core_pattern": None,
            "systemd_coredump_active": False
        },
        "crash_dumps_found": []
    }
    
    # Check kdump config
    kdump_cfg = Path(config["crash"]["kdump_config"])
    if kdump_cfg.exists():
        data["kdump"]["config_exists"] = True
        try:
            content = kdump_cfg.read_text()
            data["kdump"]["enabled"] = "USE_KDUMP=1" in content
        except Exception as e:
            errors.append(f"Failed to read kdump config: {e}")
    
    # Check kdump service
    success, stdout, _, _ = run_command(["systemctl", "is-active", "kdump"], timeout=5)
    data["kdump"]["service_active"] = (stdout.strip() == "active")
    
    # Check core_pattern
    core_pattern_path = Path(config["crash"]["core_pattern"])
    if core_pattern_path.exists():
        try:
            data["userspace_coredumps"]["core_pattern"] = core_pattern_path.read_text().strip()
        except Exception:
            pass
    
    # Check systemd-coredump
    success, stdout, _, _ = run_command(["systemctl", "is-active", "systemd-coredump.socket"], timeout=5)
    data["userspace_coredumps"]["systemd_coredump_active"] = (stdout.strip() == "active")
    
    # Scan for crash dumps
    for crash_dir in config["crash"]["core_dump_dirs"]:
        crash_path = Path(crash_dir)
        if crash_path.exists():
            try:
                dumps = list(crash_path.glob("*"))[:10]  # Limit to 10
                for dump in dumps:
                    data["crash_dumps_found"].append({
                        "path": str(dump),
                        "size_bytes": dump.stat().st_size if dump.is_file() else None
                    })
            except Exception as e:
                logger.debug(f"Failed to scan {crash_dir}: {e}")
    
    return format_envelope(True, data, errors)


def cmd_crash_configure(args, config: Dict) -> Dict:
    """Configure crash capture settings."""
    logger.info("Configuring crash capture...")
    
    is_root, root_error = require_root()
    if not is_root:
        return format_envelope(False, None, [root_error])
    
    errors = []
    changes = []
    
    # This is a placeholder - actual implementation would modify:
    # - /etc/default/kdump-tools
    # - /etc/sysctl.d/50-coredump.conf
    # - GRUB_CMDLINE_LINUX_DEFAULT (for crashkernel=)
    
    if args.enable_kdump:
        changes.append("Would enable kdump (requires config file modification + reboot)")
    
    if args.core_pattern:
        changes.append(f"Would set core_pattern to: {args.core_pattern}")
    
    data = {
        "dry_run": not args.apply,
        "changes": changes
    }
    
    if args.apply:
        # Actual implementation would apply changes here
        logger.warning("Crash configuration changes not yet implemented")
        errors.append("Configuration changes not implemented (placeholder)")
    
    return format_envelope(len(errors) == 0, data, errors)


# ============================================================================
# GPU Telemetry
# ============================================================================

def cmd_gpu_snapshot(args, config: Dict) -> Dict:
    """GPU telemetry snapshot."""
    logger.info("Collecting GPU telemetry...")
    
    errors = []
    max_lines = args.max_lines or config["truncate"]["max_lines"]
    
    data = {
        "nvidia_smi_available": False,
        "gpus": [],
        "driver_info": {},
        "gpu_processes": []
    }
    
    if not shutil.which("nvidia-smi"):
        errors.append("nvidia-smi not available")
        return format_envelope(False, data, errors)
    
    data["nvidia_smi_available"] = True
    
    # Full GPU query
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,driver_version,vbios_version,temperature.gpu,fan.speed,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,clocks.gr,clocks.sm,clocks.mem",
        "--format=csv,noheader,nounits"
    ]
    
    success, stdout, stderr, _ = run_command(cmd, timeout=10)
    if success:
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 16:
                gpu_data = {
                    "index": parts[0],
                    "uuid": parts[1],
                    "name": parts[2],
                    "driver_version": parts[3],
                    "vbios_version": parts[4] if parts[4] != "N/A" else None,
                    "temp_c": parts[5] if parts[5] != "N/A" else None,
                    "fan_speed_percent": parts[6] if parts[6] != "N/A" else None,
                    "util_gpu_percent": parts[7] if parts[7] != "N/A" else None,
                    "util_mem_percent": parts[8] if parts[8] != "N/A" else None,
                    "mem_used_mib": parts[9] if parts[9] != "N/A" else None,
                    "mem_total_mib": parts[10] if parts[10] != "N/A" else None,
                    "power_draw_w": parts[11] if parts[11] != "N/A" else None,
                    "power_limit_w": parts[12] if parts[12] != "N/A" else None,
                    "clock_graphics_mhz": parts[13] if parts[13] != "N/A" else None,
                    "clock_sm_mhz": parts[14] if parts[14] != "N/A" else None,
                    "clock_mem_mhz": parts[15] if parts[15] != "N/A" else None
                }
                data["gpus"].append(gpu_data)
    else:
        errors.append(f"nvidia-smi query failed: {stderr}")
    
    # Driver info from /proc
    proc_nvidia_version = Path("/proc/driver/nvidia/version")
    if proc_nvidia_version.exists():
        try:
            data["driver_info"]["proc_version"] = proc_nvidia_version.read_text().strip()
        except Exception:
            pass
    
    # GPU processes
    success, stdout, _, _ = run_command(["nvidia-smi", "pmon", "-c", "1"], timeout=5)
    if success:
        lines = stdout.strip().split("\n")[2:]  # Skip header
        for line in lines[:10]:  # Limit to 10
            if line.strip() and not line.startswith("#"):
                data["gpu_processes"].append(line.strip())
    
    # Check for GPU errors in kernel log
    success, stdout, _, _ = run_command(
        ["journalctl", "-k", "--grep=nvidia|NVRM|GPU", "-n", str(max_lines)],
        timeout=10
    )
    if success and stdout.strip():
        truncated_output, truncated = truncate_text(stdout, max_lines, config["truncate"]["max_bytes"])
        data["kernel_gpu_messages"] = {
            "lines": truncated_output.split("\n"),
            "truncated": truncated
        }
    
    return format_envelope(True, data, errors)


# ============================================================================
# Collect All
# ============================================================================

def cmd_collect_all(args, config: Dict) -> Dict:
    """Collect all diagnostics."""
    logger.info("Collecting all diagnostics...")
    
    errors = []
    
    # Collect everything
    health_result = cmd_health_snapshot(args, config)
    logs_result = cmd_logs_snapshot(args, config)
    hwfw_result = cmd_hwfw_events_snapshot(args, config)
    crash_result = cmd_crash_status(args, config)
    gpu_result = cmd_gpu_snapshot(args, config)
    
    data = {
        "health": health_result.get("data"),
        "logs": logs_result.get("data"),
        "hwfw_events": hwfw_result.get("data"),
        "crash": crash_result.get("data"),
        "gpu": gpu_result.get("data")
    }
    
    # Aggregate errors
    for result in [health_result, logs_result, hwfw_result, crash_result, gpu_result]:
        errors.extend(result.get("errors", []))
    
    # Save to tarball if requested
    if args.tarball:
        try:
            runtime_dir = Path(config["runtime_output_dir"])
            runtime_dir.mkdir(parents=True, exist_ok=True)
            
            # Write JSON
            json_path = runtime_dir / "diagnostics_full.json"
            full_output = format_envelope(True, data, errors)
            json_path.write_text(json.dumps(full_output, indent=2))
            
            # Create tarball
            tarball_name = f"spark_diagnostics_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.tar.gz"
            tarball_path = runtime_dir / tarball_name
            
            success, _, stderr, _ = run_command(
                ["tar", "czf", str(tarball_path), "-C", str(runtime_dir), "diagnostics_full.json"],
                timeout=30
            )
            
            if success:
                data["tarball_created"] = str(tarball_path)
            else:
                errors.append(f"Failed to create tarball: {stderr}")
        
        except Exception as e:
            errors.append(f"Failed to create tarball: {e}")
    
    return format_envelope(len(errors) == 0, data, errors)


# ============================================================================
# Status Command
# ============================================================================

def cmd_status(args, config: Dict) -> Dict:
    """Status overview."""
    logger.info("Collecting diagnostic status...")
    
    errors = []
    
    data = {
        "diagnostic_capabilities": {
            "journalctl": shutil.which("journalctl") is not None,
            "nvidia_smi": shutil.which("nvidia-smi") is not None,
            "sensors": shutil.which("sensors") is not None,
            "fwupdmgr": shutil.which("fwupdmgr") is not None
        },
        "crash_capture": {
            "kdump_service_active": False,
            "systemd_coredump_active": False
        },
        "logging": {
            "journald_active": False,
            "rsyslog_active": False
        }
    }
    
    # Check services
    for service, key in [
        ("kdump", "kdump_service_active"),
        ("systemd-coredump.socket", "systemd_coredump_active")
    ]:
        success, stdout, _, _ = run_command(["systemctl", "is-active", service], timeout=5)
        if "crash_capture" in data and key in ["kdump_service_active", "systemd_coredump_active"]:
            data["crash_capture"][key] = (stdout.strip() == "active")
    
    success, stdout, _, _ = run_command(["systemctl", "is-active", "systemd-journald"], timeout=5)
    data["logging"]["journald_active"] = (stdout.strip() == "active")
    
    success, stdout, _, _ = run_command(["systemctl", "is-active", "rsyslog"], timeout=5)
    data["logging"]["rsyslog_active"] = (stdout.strip() == "active")
    
    return format_envelope(True, data, errors)


# ============================================================================
# Human-Readable Output
# ============================================================================

def format_human_output(command: str, result: Dict) -> str:
    """Format JSON result as human-readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"Spark Diagnostics - {command}")
    lines.append("=" * 80)
    lines.append("")
    
    if not result.get("ok"):
        lines.append("❌ FAILED")
        if result.get("errors"):
            lines.append("\nErrors:")
            for error in result["errors"]:
                lines.append(f"  • {error}")
        return "\n".join(lines)
    
    lines.append("✓ SUCCESS")
    lines.append("")
    
    data = result.get("data", {})
    
    if command == "status":
        caps = data.get("diagnostic_capabilities", {})
        lines.append("Diagnostic Capabilities:")
        for tool, available in caps.items():
            status = "✓" if available else "✗"
            lines.append(f"  {status} {tool}")
        lines.append("")
        
        crash = data.get("crash_capture", {})
        lines.append("Crash Capture:")
        lines.append(f"  kdump: {crash.get('kdump_service_active')}")
        lines.append(f"  coredump: {crash.get('systemd_coredump_active')}")
    
    elif command == "health":
        cpu = data.get("cpu", {})
        mem = data.get("memory", {})
        gpu_data = data.get("gpu", {})
        
        lines.append("CPU:")
        if cpu.get("load_average"):
            lines.append(f"  Load: {cpu['load_average']['1min']}, {cpu['load_average']['5min']}, {cpu['load_average']['15min']}")
        
        lines.append("\nMemory:")
        lines.append(f"  Used: {mem.get('mem_used_percent', 'N/A')}%")
        
        if gpu_data.get("gpus"):
            lines.append(f"\nGPUs: {len(gpu_data['gpus'])} found")
            for gpu in gpu_data["gpus"][:3]:
                lines.append(f"  GPU {gpu['index']}: {gpu['name']} - {gpu.get('temp_c', 'N/A')}°C, {gpu.get('util_gpu_percent', 'N/A')}% util")
    
    lines.append("")
    lines.append("=" * 80)
    
    return "\n".join(lines)


# ============================================================================
# Main CLI
# ============================================================================

def load_config(config_path: Optional[str] = None) -> Dict:
    """Load configuration from JSON file."""
    config = DEFAULT_CONFIG.copy()
    
    if not config_path:
        script_dir = Path(__file__).resolve().parent.parent
        config_path = script_dir / "config" / "default.json"
    
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, "r") as f:
                loaded_config = json.load(f)
                for key, value in loaded_config.items():
                    if isinstance(value, dict) and key in config:
                        config[key].update(value)
                    else:
                        config[key] = value
        except Exception as e:
            logger.warning(f"Could not load config: {e}")
    
    return config


def main() -> int:
    """Main entry point."""
    # Create parser with shared CLI infrastructure
    parser, subparsers = create_subparser_tool_parser(
        tool_name=TOOL_NAME,
        description="Spark Diagnostics Control - Health, Logs, Events, Crash, GPU Telemetry",
        version=VERSION,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Add tool-specific flags
    parser.add_argument("--max-lines", type=int, help="Maximum lines for truncation")
    parser.add_argument("--max-bytes", type=int, help="Maximum bytes for truncation")
    
    # status
    subparsers.add_parser("status", help="Show diagnostic capabilities status")
    
    # health snapshot
    subparsers.add_parser("health", help="Collect health metrics snapshot")
    
    # logs snapshot
    subparsers.add_parser("logs", help="Collect system logs snapshot")
    
    # hwfw-events snapshot
    subparsers.add_parser("hwfw-events", help="Collect hardware/firmware event logs")
    
    # crash status
    crash_parser = subparsers.add_parser("crash", help="Crash dump status and configuration")
    crash_subparsers = crash_parser.add_subparsers(dest="crash_command")
    crash_subparsers.add_parser("status", help="Show crash capture status")
    
    crash_config_parser = crash_subparsers.add_parser("configure", help="Configure crash capture")
    crash_config_parser.add_argument("--enable-kdump", action="store_true", help="Enable kdump")
    crash_config_parser.add_argument("--core-pattern", help="Set core pattern")
    crash_config_parser.add_argument("--apply", action="store_true", help="Apply changes (requires root)")
    
    # gpu snapshot
    subparsers.add_parser("gpu", help="Collect GPU telemetry snapshot")
    
    # collect all
    collect_parser = subparsers.add_parser("collect-all", help="Collect all diagnostics")
    collect_parser.add_argument("--tarball", action="store_true", help="Create tarball of results")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return ExitCode.INVALID_ARGS

    # Load config
    config = load_config(args.config)

    # Apply CLI overrides
    if args.max_lines:
        config["truncate"]["max_lines"] = args.max_lines
    if args.max_bytes:
        config["truncate"]["max_bytes"] = args.max_bytes

    # Setup logging using shared infrastructure
    log_path = config.get("log_path")
    global logger
    logger = cli_setup_logging(log_path, args.verbose, tool_name="spark_diagctl")
    
    logger.info(f"Spark Diagnostics {VERSION}")
    logger.info(f"Command: {args.command}")
    
    # Route commands
    try:
        if args.command == "status":
            result = cmd_status(args, config)
        elif args.command == "health":
            result = cmd_health_snapshot(args, config)
        elif args.command == "logs":
            result = cmd_logs_snapshot(args, config)
        elif args.command == "hwfw-events":
            result = cmd_hwfw_events_snapshot(args, config)
        elif args.command == "crash":
            if args.crash_command == "configure":
                result = cmd_crash_configure(args, config)
            else:
                result = cmd_crash_status(args, config)
        elif args.command == "gpu":
            result = cmd_gpu_snapshot(args, config)
        elif args.command == "collect-all":
            result = cmd_collect_all(args, config)
        else:
            result = format_envelope(False, None, ["Unknown command"])
    
    except Exception as e:
        logger.exception("Unhandled exception")
        result = format_envelope(False, None, [f"Unhandled exception: {e}"])

    # Ensure meta has tool and version info
    if "meta" not in result or not isinstance(result.get("meta"), dict):
        result["meta"] = {}
    result["meta"]["tool"] = TOOL_NAME
    result["meta"]["version"] = VERSION

    # Output result
    if args.human:
        output = format_human_output(args.command, result)
    else:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    
    if args.output:
        try:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            temp_path = output_path.with_suffix(".tmp")
            temp_path.write_text(output + "\n")
            temp_path.replace(output_path)
            
            logger.info(f"Output written to {args.output}")
        except Exception as e:
            logger.error(f"Failed to write output: {e}")
            return ExitCode.GENERAL_ERROR
    else:
        print(output)

    return ExitCode.SUCCESS if result.get("ok") else ExitCode.GENERAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
