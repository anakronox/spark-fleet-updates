#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
spark_updatectl.py

Enterprise update control tool for DGX Spark management.

Provides:
1. Reboot coordination with inhibitor handling
2. Kernel rollback via GRUB next-boot selection
3. Firmware rollback reporting (report-only, no execution)

Design:
- JSON-first output (--human for readable format)
- Read-only commands work without root
- State-changing operations require root and explicit confirmation
- Stdlib only (no external dependencies)

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
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

DEFAULT_CONFIG = {
    "runtime_output_dir": "/var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane",
    "log_path": "logs/controlled_sw_fw_updates/update_control_plane/spark_updatectl.log",
    "reboot": {
        "require_no_blocking_inhibitors": True,
        "allow_delay_inhibitors": True,
        "default_delay_sec": 0
    },
    "grub": {
        "grub_cfg": "/boot/grub/grub.cfg"
    },
    "systemd_schedule": {
        "timer_unit": "spark-updatectl-reboot.timer",
        "service_unit": "spark-updatectl-reboot.service"
    },
    "fwupd": {
        "enable_release_query": False,
        "max_releases_per_device": 20
    }
}

logger = logging.getLogger(__name__)

# ============================================================================
# Utility Functions
# ============================================================================

# setup_logging() now imported from cli_base
# Use: cli_setup_logging(log_path, verbose, tool_name="spark_updatectl")


def run_command(
    cmd: List[str],
    timeout: int = 30,
    check: bool = False
) -> Tuple[bool, str, str, Optional[int]]:
    """
    Run command and return results.
    
    Args:
        cmd: Command and arguments
        timeout: Timeout in seconds
        check: Raise on non-zero exit
    
    Returns:
        Tuple of (success, stdout, stderr, returncode)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check
        )
        return True, result.stdout, result.stderr, result.returncode
    
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s", None
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr, e.returncode
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}", None
    except Exception as e:
        return False, "", str(e), None


def require_root() -> Tuple[bool, Optional[str]]:
    """
    Check if running as root.
    
    Returns:
        Tuple of (is_root, error_message)
    """
    if os.geteuid() != 0:
        return False, "This operation requires root permissions (run with sudo)"
    return True, None


# format_envelope() replaced by format_envelope() from cli_base
# New signature adds meta field: format_envelope(ok, data, errors, meta)


# ============================================================================
# Status Collection
# ============================================================================

def collect_kernel_info() -> Dict:
    """Collect current kernel information."""
    info = {}
    
    # Current kernel
    success, stdout, _, _ = run_command(["uname", "-r"])
    if success:
        info["current_kernel"] = stdout.strip()
    
    # Full uname
    success, stdout, _, _ = run_command(["uname", "-a"])
    if success:
        info["uname_all"] = stdout.strip()
    
    return info


def collect_uptime_info() -> Dict:
    """Collect uptime information."""
    info = {}
    
    try:
        with open("/proc/uptime", "r") as f:
            uptime_sec = float(f.read().split()[0])
            info["uptime_seconds"] = int(uptime_sec)
            info["uptime_human"] = str(datetime.timedelta(seconds=int(uptime_sec)))
    except Exception as e:
        logger.debug(f"Failed to read uptime: {e}")
    
    # Boot ID from journalctl
    success, stdout, _, _ = run_command(["journalctl", "--list-boots", "-n", "1"])
    if success:
        # Parse: "-0 <boot-id> <timestamp>"
        match = re.search(r'([0-9a-f-]{36})', stdout)
        if match:
            info["boot_id"] = match.group(1)
    
    return info


def check_pending_reboot() -> Dict:
    """Check for pending reboot indicators."""
    info = {
        "pending": False,
        "indicators": []
    }
    
    # Check /run/reboot-required*
    reboot_required = Path("/run/reboot-required")
    if reboot_required.exists():
        info["pending"] = True
        info["indicators"].append("/run/reboot-required exists")
        
        # Check reason file
        reason_file = Path("/run/reboot-required.pkgs")
        if reason_file.exists():
            try:
                info["packages"] = reason_file.read_text().strip().split("\n")
            except Exception:
                pass
    
    return info


def collect_inhibitors() -> Dict:
    """Collect systemd inhibitors."""
    info = {
        "inhibitors": [],
        "blocking_count": 0,
        "delay_count": 0
    }
    
    # loginctl list-inhibitors
    success, stdout, _, _ = run_command(["loginctl", "list-inhibitors"])
    if not success:
        return info
    
    lines = stdout.strip().split("\n")
    for line in lines[1:]:  # Skip header
        if not line.strip() or "inhibitors listed" in line.lower():
            continue
        
        parts = line.split()
        if len(parts) >= 4:
            what, who, why, mode = parts[0], parts[1], parts[2], parts[3]
            
            inhibitor = {
                "what": what,
                "who": who,
                "why": why,
                "mode": mode
            }
            
            info["inhibitors"].append(inhibitor)
            
            if mode == "block":
                info["blocking_count"] += 1
            elif mode == "delay":
                info["delay_count"] += 1
    
    return info


def collect_systemd_timeouts() -> Dict:
    """Collect systemd reboot/shutdown timeouts."""
    info = {}
    
    # systemctl show for timeout values
    success, stdout, _, _ = run_command(["systemctl", "show", "-p", "DefaultTimeoutStopUSec", "-p", "DefaultTimeoutStartUSec"])
    if success:
        for line in stdout.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                info[key] = value
    
    return info


def collect_last_reboot_history() -> List[Dict]:
    """Collect last reboot history."""
    history = []
    
    success, stdout, _, _ = run_command(["last", "-x", "reboot", "shutdown", "-n", "10"])
    if success:
        for line in stdout.strip().split("\n"):
            if "reboot" in line.lower() or "shutdown" in line.lower():
                history.append({"line": line.strip()})
    
    return history


def cmd_status(args, config: Dict) -> Dict:
    """
    Status command - gather and output unified status.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Status dictionary
    """
    logger.info("Collecting system status...")
    
    errors = []
    data = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "kernel": collect_kernel_info(),
        "uptime": collect_uptime_info(),
        "pending_reboot": check_pending_reboot(),
        "inhibitors": collect_inhibitors(),
        "systemd_timeouts": collect_systemd_timeouts(),
        "last_reboot_history": collect_last_reboot_history()
    }
    
    # Collect GRUB kernel entries
    grub_cfg = config["grub"]["grub_cfg"]
    kernels, grub_errors = parse_grub_kernels(grub_cfg)
    data["available_kernels"] = kernels
    if grub_errors:
        errors.extend(grub_errors)
    
    # Collect GRUB env (next_entry)
    grub_env, grub_env_errors = get_grub_env()
    data["grub_env"] = grub_env
    if grub_env_errors:
        errors.extend(grub_env_errors)
    
    # Firmware rollback summary (lightweight)
    fw_summary, fw_errors = collect_fw_rollback_summary(config)
    data["firmware_rollback_summary"] = fw_summary
    if fw_errors:
        errors.extend(fw_errors)
    
    logger.info("Status collection complete")
    
    return format_envelope(True, data, errors)


# ============================================================================
# GRUB Kernel Parsing
# ============================================================================

def parse_grub_kernels(grub_cfg_path: str) -> Tuple[List[Dict], List[str]]:
    """
    Parse GRUB config for kernel menuentries.
    
    Args:
        grub_cfg_path: Path to grub.cfg
    
    Returns:
        Tuple of (kernel_list, errors)
    """
    kernels = []
    errors = []
    
    grub_cfg = Path(grub_cfg_path)
    if not grub_cfg.exists():
        errors.append(f"GRUB config not found: {grub_cfg_path}")
        return kernels, errors
    
    try:
        with open(grub_cfg, "r") as f:
            content = f.read()
        
        # Parse menuentries
        # Example: menuentry 'Ubuntu, with Linux 6.14.0-1015-nvidia' --class ubuntu ... {
        pattern = r"menuentry\s+'([^']+)'.*?--id\s+([^\s{]+)"
        
        for match in re.finditer(pattern, content):
            title = match.group(1)
            entry_id = match.group(2)
            
            # Extract kernel version from title
            kernel_match = re.search(r'Linux\s+([\d\.-]+(?:-\w+)?)', title)
            if kernel_match:
                kernel_version = kernel_match.group(1)
                
                kernels.append({
                    "title": title,
                    "menuentry_id": entry_id,
                    "kernel_version": kernel_version
                })
        
        # Also list /boot/vmlinuz-* for corroboration
        boot_kernels = []
        boot_dir = Path("/boot")
        if boot_dir.exists():
            for vmlinuz in boot_dir.glob("vmlinuz-*"):
                boot_kernels.append(vmlinuz.name.replace("vmlinuz-", ""))
        
        logger.debug(f"Found {len(kernels)} GRUB menuentries, {len(boot_kernels)} /boot kernels")
    
    except Exception as e:
        errors.append(f"Error parsing GRUB config: {e}")
    
    return kernels, errors


def get_grub_env() -> Tuple[Dict, List[str]]:
    """
    Get GRUB environment variables (next_entry, saved_entry).
    
    Returns:
        Tuple of (env_dict, errors)
    """
    env = {}
    errors = []
    
    success, stdout, stderr, _ = run_command(["grub-editenv", "list"])
    if not success:
        errors.append(f"grub-editenv failed: {stderr}")
        return env, errors
    
    for line in stdout.strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    
    return env, errors


# ============================================================================
# Reboot Commands
# ============================================================================

def cmd_reboot_plan(args, config: Dict) -> Dict:
    """
    Reboot plan command - assess reboot readiness.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Plan dictionary
    """
    logger.info("Creating reboot plan...")
    
    errors = []
    
    # Collect inhibitors
    inhibitors_info = collect_inhibitors()
    
    # Assess blockage
    require_no_blocking = config["reboot"].get("require_no_blocking_inhibitors", True)
    allow_delay = config["reboot"].get("allow_delay_inhibitors", True)
    
    blocked = False
    block_reasons = []
    
    if require_no_blocking and inhibitors_info["blocking_count"] > 0:
        blocked = True
        block_reasons.append(f"{inhibitors_info['blocking_count']} blocking inhibitors present")
    
    if not allow_delay and inhibitors_info["delay_count"] > 0:
        blocked = True
        block_reasons.append(f"{inhibitors_info['delay_count']} delay inhibitors present (not allowed)")
    
    plan = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "reason": args.reason or "Planned reboot",
        "delay_sec": args.delay_sec or config["reboot"]["default_delay_sec"],
        "blocked": blocked,
        "block_reasons": block_reasons,
        "safe_to_proceed": not blocked,
        "inhibitors": inhibitors_info,
        "recommended_actions": []
    }
    
    if blocked:
        plan["recommended_actions"].append("Review inhibitors and resolve blocking conditions")
        plan["recommended_actions"].append("Or use --force flag to override (not recommended)")
    
    logger.info(f"Reboot plan: blocked={blocked}")
    
    return format_envelope(True, plan, errors)


def cmd_reboot_now(args, config: Dict) -> Dict:
    """
    Reboot now command - execute reboot with guardrails.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Result dictionary
    """
    logger.info("Executing reboot now...")
    
    # Check root
    is_root, error = require_root()
    if not is_root:
        return format_envelope(False, None, [error])
    
    errors = []
    
    # Check inhibitors unless --force
    if not args.force:
        inhibitors_info = collect_inhibitors()
        require_no_blocking = config["reboot"].get("require_no_blocking_inhibitors", True)
        
        if require_no_blocking and inhibitors_info["blocking_count"] > 0:
            return format_envelope(
                False,
                {"inhibitors": inhibitors_info},
                [f"Reboot blocked: {inhibitors_info['blocking_count']} blocking inhibitors present. Use --force to override."]
            )
    
    # Write audit record
    reason = args.reason or "Manual reboot via spark_updatectl"
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    
    # Best-effort: write reboot reason to /run
    try:
        reason_file = Path("/run/spark_updatectl_reboot_reason.json")
        reason_data = {
            "timestamp": timestamp,
            "reason": reason,
            "forced": args.force
        }
        reason_file.write_text(json.dumps(reason_data, indent=2))
        logger.info(f"Wrote reboot reason to {reason_file}")
    except Exception as e:
        logger.warning(f"Could not write reboot reason file: {e}")
    
    # Log to journal (best-effort)
    try:
        subprocess.run(
            ["logger", "-t", "spark_updatectl", f"Reboot initiated: {reason}"],
            timeout=5
        )
    except Exception as e:
        logger.debug(f"Could not log to journal: {e}")
    
    # Delay if requested
    delay_sec = args.delay_sec or 0
    if delay_sec > 0:
        logger.info(f"Delaying {delay_sec} seconds before reboot...")
        time.sleep(delay_sec)
    
    # Execute reboot
    logger.info("Calling systemctl reboot...")
    
    # Try with --message flag first (systemd 247+)
    success, stdout, stderr, _ = run_command(["systemctl", "reboot", "--message", reason], timeout=10)
    
    if not success and "unrecognized option" in stderr.lower():
        # Fallback: systemctl reboot without --message
        success, stdout, stderr, _ = run_command(["systemctl", "reboot"], timeout=10)
    
    if not success:
        return format_envelope(False, None, [f"Reboot failed: {stderr}"])
    
    return format_envelope(
        True,
        {
            "reason": reason,
            "delay_sec": delay_sec,
            "forced": args.force,
            "timestamp": timestamp
        },
        errors
    )


def cmd_reboot_schedule(args, config: Dict) -> Dict:
    """
    Schedule a reboot via systemd timer.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Result dictionary
    """
    logger.info("Scheduling reboot...")
    
    # Check root
    is_root, error = require_root()
    if not is_root:
        return format_envelope(False, None, [error])
    
    errors = []
    
    # Calculate trigger time
    if args.at:
        # Parse YYYY-MM-DD HH:MM:SS
        try:
            trigger_dt = datetime.datetime.strptime(args.at, "%Y-%m-%d %H:%M:%S")
            on_calendar = trigger_dt.strftime("%Y-%m-%d %H:%M:%S")
            on_active_sec = None
        except ValueError as e:
            return format_envelope(False, None, [f"Invalid --at format: {e}"])
    
    elif args.in_minutes:
        on_calendar = None
        on_active_sec = f"{args.in_minutes}min"
        trigger_dt = datetime.datetime.now() + datetime.timedelta(minutes=args.in_minutes)
    
    else:
        return format_envelope(False, None, ["Must specify --at or --in-minutes"])
    
    reason = args.reason or "Scheduled reboot"
    
    # Create systemd units
    service_unit = config["systemd_schedule"]["service_unit"]
    timer_unit = config["systemd_schedule"]["timer_unit"]
    
    unit_dir = Path("/etc/systemd/system")
    service_path = unit_dir / service_unit
    timer_path = unit_dir / timer_unit
    
    # Service unit content
    force_flag = "--force" if args.force else ""
    service_content = f"""[Unit]
Description=Spark UpdateCtl Scheduled Reboot
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {sys.argv[0]} reboot now --reason "{reason}" {force_flag}

[Install]
WantedBy=multi-user.target
"""
    
    # Timer unit content
    timer_content = f"""[Unit]
Description=Spark UpdateCtl Reboot Timer

[Timer]
"""
    
    if on_calendar:
        timer_content += f"OnCalendar={on_calendar}\n"
    else:
        timer_content += f"OnActiveSec={on_active_sec}\n"
    
    timer_content += """Persistent=true

[Install]
WantedBy=timers.target
"""
    
    # Write units
    try:
        service_path.write_text(service_content)
        timer_path.write_text(timer_content)
        logger.info(f"Created units: {service_path}, {timer_path}")
    except Exception as e:
        return format_envelope(False, None, [f"Failed to write systemd units: {e}"])
    
    # Reload systemd
    success, stdout, stderr, _ = run_command(["systemctl", "daemon-reload"], timeout=10)
    if not success:
        errors.append(f"systemctl daemon-reload warning: {stderr}")
    
    # Enable and start timer
    success, stdout, stderr, _ = run_command(["systemctl", "enable", "--now", timer_unit], timeout=10)
    if not success:
        return format_envelope(False, None, [f"Failed to enable timer: {stderr}"])
    
    logger.info(f"Reboot scheduled for {trigger_dt}")
    
    return format_envelope(
        True,
        {
            "reason": reason,
            "trigger_time": trigger_dt.isoformat(),
            "on_calendar": on_calendar,
            "on_active_sec": on_active_sec,
            "timer_unit": timer_unit,
            "service_unit": service_unit
        },
        errors
    )


def cmd_reboot_cancel(args, config: Dict) -> Dict:
    """
    Cancel scheduled reboot.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Result dictionary
    """
    logger.info("Canceling scheduled reboot...")
    
    # Check root
    is_root, error = require_root()
    if not is_root:
        return format_envelope(False, None, [error])
    
    errors = []
    
    service_unit = config["systemd_schedule"]["service_unit"]
    timer_unit = config["systemd_schedule"]["timer_unit"]
    
    # Stop and disable timer
    success, stdout, stderr, _ = run_command(["systemctl", "disable", "--now", timer_unit], timeout=10)
    if not success and "not loaded" not in stderr.lower():
        errors.append(f"Failed to disable timer: {stderr}")
    
    # Optionally remove units
    if args.remove_units:
        unit_dir = Path("/etc/systemd/system")
        service_path = unit_dir / service_unit
        timer_path = unit_dir / timer_unit
        
        try:
            if service_path.exists():
                service_path.unlink()
            if timer_path.exists():
                timer_path.unlink()
            
            # Reload
            run_command(["systemctl", "daemon-reload"], timeout=10)
            logger.info("Removed systemd units")
        except Exception as e:
            errors.append(f"Failed to remove units: {e}")
    
    return format_envelope(True, {"cancelled": True}, errors)


def cmd_reboot_schedule_status(args, config: Dict) -> Dict:
    """
    Get scheduled reboot status.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Status dictionary
    """
    logger.info("Getting reboot schedule status...")
    
    errors = []
    
    timer_unit = config["systemd_schedule"]["timer_unit"]
    
    # Check if timer exists
    success, stdout, stderr, _ = run_command(["systemctl", "status", timer_unit], timeout=10)
    
    if not success and "not loaded" in stderr.lower():
        return format_envelope(True, {"scheduled": False}, errors)
    
    # Get timer details
    success, stdout, stderr, _ = run_command(["systemctl", "show", timer_unit, "-p", "NextElapseUSecRealtime", "-p", "LastTriggerUSec"], timeout=10)
    
    timer_info = {"scheduled": True, "timer_unit": timer_unit}
    
    if success:
        for line in stdout.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                timer_info[key] = value
    
    return format_envelope(True, timer_info, errors)


# ============================================================================
# Rollback Commands
# ============================================================================

def cmd_rollback_kernel_list(args, config: Dict) -> Dict:
    """
    List available kernels from GRUB.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Kernel list dictionary
    """
    logger.info("Listing available kernels...")
    
    grub_cfg = config["grub"]["grub_cfg"]
    kernels, errors = parse_grub_kernels(grub_cfg)
    
    # Get current kernel
    current_kernel = None
    success, stdout, _, _ = run_command(["uname", "-r"])
    if success:
        current_kernel = stdout.strip()
    
    # Mark current kernel
    for kernel in kernels:
        kernel["is_current"] = (kernel["kernel_version"] == current_kernel)
    
    data = {
        "current_kernel": current_kernel,
        "available_kernels": kernels,
        "count": len(kernels)
    }
    
    return format_envelope(True, data, errors)


def cmd_rollback_kernel_set_next(args, config: Dict) -> Dict:
    """
    Set next boot kernel via grub-reboot.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Result dictionary
    """
    logger.info(f"Setting next boot kernel: {args.kernel}")
    
    # Check root
    is_root, error = require_root()
    if not is_root:
        return format_envelope(False, None, [error])
    
    errors = []
    
    # Find matching kernel menuentry
    grub_cfg = config["grub"]["grub_cfg"]
    kernels, parse_errors = parse_grub_kernels(grub_cfg)
    if parse_errors:
        errors.extend(parse_errors)
    
    matching_kernel = None
    for kernel in kernels:
        if kernel["kernel_version"] == args.kernel:
            matching_kernel = kernel
            break
    
    if not matching_kernel:
        available = [k["kernel_version"] for k in kernels]
        return format_envelope(
            False,
            {"available_kernels": available},
            [f"Kernel '{args.kernel}' not found in GRUB config"]
        )
    
    menuentry_id = matching_kernel["menuentry_id"]
    
    # Call grub-reboot
    success, stdout, stderr, _ = run_command(["grub-reboot", menuentry_id], timeout=10)
    if not success:
        return format_envelope(False, None, [f"grub-reboot failed: {stderr}"])
    
    logger.info(f"Set next boot to: {menuentry_id}")
    
    # Verify by reading grub-editenv
    grub_env, env_errors = get_grub_env()
    if env_errors:
        errors.extend(env_errors)
    
    verified = grub_env.get("next_entry") == menuentry_id
    
    return format_envelope(
        True,
        {
            "kernel_version": args.kernel,
            "menuentry_id": menuentry_id,
            "title": matching_kernel["title"],
            "verified": verified,
            "next_entry": grub_env.get("next_entry")
        },
        errors
    )


def cmd_rollback_kernel_clear_next(args, config: Dict) -> Dict:
    """
    Clear next boot kernel setting.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Result dictionary
    """
    logger.info("Clearing next boot kernel setting...")
    
    # Check root
    is_root, error = require_root()
    if not is_root:
        return format_envelope(False, None, [error])
    
    errors = []
    
    # Clear next_entry
    success, stdout, stderr, _ = run_command(["grub-editenv", "-", "unset", "next_entry"], timeout=10)
    if not success:
        return format_envelope(False, None, [f"grub-editenv failed: {stderr}"])
    
    # Verify
    grub_env, env_errors = get_grub_env()
    if env_errors:
        errors.extend(env_errors)
    
    cleared = "next_entry" not in grub_env or not grub_env["next_entry"]
    
    return format_envelope(
        True,
        {
            "cleared": cleared,
            "grub_env": grub_env
        },
        errors
    )


def cmd_rollback_os_backup_status(args, config: Dict) -> Dict:
    """
    Report OS backup/snapshot capability.
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Status dictionary
    """
    logger.info("Checking OS backup/snapshot capability...")
    
    errors = []
    capabilities = []
    
    # Check for snapshot tools
    snapshot_tools = [
        "timeshift",
        "snapper",
        "ostree",
        "rauc",
        "mender",
        "zfs",
        "btrfs"
    ]
    
    installed_tools = []
    for tool in snapshot_tools:
        if shutil.which(tool):
            installed_tools.append(tool)
    
    # Check root filesystem
    success, stdout, _, _ = run_command(["findmnt", "/", "-o", "FSTYPE", "-n"])
    root_fstype = None
    if success:
        root_fstype = stdout.strip()
    
    # Assess capability
    if root_fstype in ["btrfs", "zfs"]:
        capabilities.append(f"Root filesystem is {root_fstype} (supports snapshots)")
    elif root_fstype == "ext4":
        capabilities.append("Root filesystem is ext4 (no native snapshot support)")
    
    if installed_tools:
        capabilities.append(f"Snapshot tools installed: {', '.join(installed_tools)}")
    else:
        capabilities.append("No standard snapshot tools detected")
    
    # Generate recovery manifest (metadata only)
    recovery_manifest = None
    if args.export_manifest:
        manifest, manifest_errors = generate_recovery_manifest(config)
        if manifest_errors:
            errors.extend(manifest_errors)
        recovery_manifest = manifest
    
    data = {
        "root_filesystem": root_fstype,
        "installed_tools": installed_tools,
        "capabilities": capabilities,
        "snapshot_capable": root_fstype in ["btrfs", "zfs"] or len(installed_tools) > 0,
        "recovery_manifest": recovery_manifest
    }
    
    return format_envelope(True, data, errors)


def generate_recovery_manifest(config: Dict) -> Tuple[Optional[Dict], List[str]]:
    """
    Generate recovery manifest (metadata only, not full backup).
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Tuple of (manifest_dict, errors)
    """
    errors = []
    manifest = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "type": "recovery_metadata"
    }
    
    # OS release
    try:
        with open("/etc/os-release", "r") as f:
            manifest["os_release"] = dict(
                line.strip().split("=", 1)
                for line in f
                if "=" in line and not line.startswith("#")
            )
    except Exception as e:
        errors.append(f"Failed to read /etc/os-release: {e}")
    
    # DGX release
    try:
        dgx_release_path = Path("/etc/dgx-release")
        if dgx_release_path.exists():
            manifest["dgx_release"] = dgx_release_path.read_text().strip()
    except Exception:
        pass
    
    # Kernel list
    grub_cfg = config["grub"]["grub_cfg"]
    kernels, _ = parse_grub_kernels(grub_cfg)
    manifest["kernels"] = [k["kernel_version"] for k in kernels]
    
    # Write manifest to runtime output dir
    try:
        output_dir = Path(config["runtime_output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = output_dir / "recovery_manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        manifest["manifest_file"] = str(manifest_file)
        logger.info(f"Wrote recovery manifest to {manifest_file}")
    except Exception as e:
        errors.append(f"Failed to write recovery manifest: {e}")
    
    return manifest, errors


# ============================================================================
# Firmware Commands
# ============================================================================

def collect_fw_rollback_summary(config: Dict) -> Tuple[Dict, List[str]]:
    """
    Collect lightweight firmware rollback summary (for status command).
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Tuple of (summary_dict, errors)
    """
    summary = {
        "fwupd_available": False,
        "device_count": 0
    }
    errors = []
    
    # Check if fwupdmgr exists
    if not shutil.which("fwupdmgr"):
        return summary, errors
    
    summary["fwupd_available"] = True
    
    # Get device count
    success, stdout, _, _ = run_command(["fwupdmgr", "get-devices"], timeout=30)
    if success:
        # Count devices (rough estimate from output)
        device_lines = [line for line in stdout.split("\n") if "Device ID" in line]
        summary["device_count"] = len(device_lines)
    
    return summary, errors


def cmd_fw_rollback_report(args, config: Dict) -> Dict:
    """
    Generate firmware rollback capability report (report-only, no execution).
    
    Args:
        args: Parsed arguments
        config: Configuration dictionary
    
    Returns:
        Report dictionary
    """
    logger.info("Generating firmware rollback report...")
    
    errors = []
    
    # Check if fwupdmgr exists
    if not shutil.which("fwupdmgr"):
        return format_envelope(
            False,
            None,
            ["fwupdmgr not found (install fwupd package)"]
        )
    
    # Get fwupdmgr version
    success, stdout, _, _ = run_command(["fwupdmgr", "--version"], timeout=10)
    fwupd_version = stdout.strip() if success else "unknown"
    
    # Check if downgrade/reinstall flags are supported
    success, stdout, _, _ = run_command(["fwupdmgr", "downgrade", "--help"], timeout=10)
    supports_downgrade = success or "downgrade" in stdout.lower()
    
    success, stdout, _, _ = run_command(["fwupdmgr", "reinstall", "--help"], timeout=10)
    supports_reinstall = success or "reinstall" in stdout.lower()
    
    # Get devices
    devices, device_errors = parse_fwupd_devices()
    if device_errors:
        errors.extend(device_errors)
    
    # Optionally query releases per device
    if config["fwupd"].get("enable_release_query", False) and args.query_releases:
        for device in devices:
            releases, release_errors = query_device_releases(
                device.get("device_id"),
                config["fwupd"].get("max_releases_per_device", 20)
            )
            if release_errors:
                errors.extend(release_errors)
            device["available_releases"] = releases
    
    data = {
        "fwupd_version": fwupd_version,
        "supports_downgrade": supports_downgrade,
        "supports_reinstall": supports_reinstall,
        "device_count": len(devices),
        "devices": devices
    }
    
    return format_envelope(True, data, errors)


def parse_fwupd_devices() -> Tuple[List[Dict], List[str]]:
    """
    Parse fwupdmgr get-devices output.
    
    Returns:
        Tuple of (device_list, errors)
    """
    devices = []
    errors = []
    
    success, stdout, stderr, _ = run_command(["fwupdmgr", "get-devices"], timeout=30)
    if not success:
        errors.append(f"fwupdmgr get-devices failed: {stderr}")
        return devices, errors
    
    # Parse text output (key: value format)
    current_device = None
    for line in stdout.split("\n"):
        line = line.strip()
        
        if not line:
            if current_device:
                devices.append(current_device)
                current_device = None
            continue
        
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            
            if key == "Device ID":
                if current_device:
                    devices.append(current_device)
                current_device = {"device_id": value}
            
            elif current_device:
                # Store relevant fields
                if key == "Summary":
                    current_device["summary"] = value
                elif key == "Current version":
                    current_device["current_version"] = value
                elif key == "Minimum Version":
                    current_device["minimum_version"] = value
                elif key == "Vendor":
                    current_device["vendor"] = value
                elif key == "Flags":
                    current_device["flags"] = value
                    # Check for upgrade-only constraint
                    if "only-version-upgrade" in value.lower() or "only version upgrades" in value.lower():
                        current_device["upgrade_only"] = True
                    else:
                        current_device["upgrade_only"] = False
    
    if current_device:
        devices.append(current_device)
    
    return devices, errors


def query_device_releases(device_id: str, max_releases: int) -> Tuple[List[Dict], List[str]]:
    """
    Query available releases for a device.
    
    Args:
        device_id: Device ID or GUID
        max_releases: Maximum number of releases to return
    
    Returns:
        Tuple of (releases_list, errors)
    """
    releases = []
    errors = []
    
    success, stdout, stderr, _ = run_command(["fwupdmgr", "get-releases", device_id], timeout=30)
    if not success:
        errors.append(f"get-releases failed for {device_id}: {stderr}")
        return releases, errors
    
    # Parse releases (simplified)
    for line in stdout.split("\n"):
        if "Version:" in line:
            version = line.split(":", 1)[1].strip()
            releases.append({"version": version})
            
            if len(releases) >= max_releases:
                break
    
    return releases, errors


# ============================================================================
# Human-Readable Output
# ============================================================================

def format_human_output(command: str, result: Dict) -> str:
    """
    Format JSON result as human-readable text.
    
    Args:
        command: Command name
        result: JSON result dictionary
    
    Returns:
        Human-readable string
    """
    lines = []
    lines.append("=" * 80)
    lines.append(f"Spark UpdateCtl - {command}")
    lines.append("=" * 80)
    lines.append("")
    
    if not result.get("ok"):
        lines.append("❌ FAILED")
        lines.append("")
        if result.get("errors"):
            lines.append("Errors:")
            for error in result["errors"]:
                lines.append(f"  • {error}")
        lines.append("")
        return "\n".join(lines)
    
    lines.append("✓ SUCCESS")
    lines.append("")
    
    data = result.get("data", {})
    errors = result.get("errors", [])
    
    # Command-specific formatting
    if command == "status":
        lines.append(f"Timestamp: {data.get('timestamp', 'N/A')}")
        lines.append("")
        
        lines.append("Kernel:")
        kernel = data.get("kernel", {})
        lines.append(f"  Current: {kernel.get('current_kernel', 'N/A')}")
        lines.append("")
        
        lines.append("Uptime:")
        uptime = data.get("uptime", {})
        lines.append(f"  Duration: {uptime.get('uptime_human', 'N/A')}")
        lines.append(f"  Boot ID: {uptime.get('boot_id', 'N/A')}")
        lines.append("")
        
        lines.append("Pending Reboot:")
        pending = data.get("pending_reboot", {})
        lines.append(f"  Status: {'YES' if pending.get('pending') else 'NO'}")
        if pending.get("indicators"):
            for indicator in pending["indicators"]:
                lines.append(f"    {indicator}")
        lines.append("")
        
        lines.append("Inhibitors:")
        inhibitors = data.get("inhibitors", {})
        lines.append(f"  Blocking: {inhibitors.get('blocking_count', 0)}")
        lines.append(f"  Delay: {inhibitors.get('delay_count', 0)}")
        lines.append("")
        
        lines.append("Available Kernels:")
        kernels = data.get("available_kernels", [])
        for kernel in kernels:
            current_marker = " (CURRENT)" if kernel.get("is_current") else ""
            lines.append(f"  • {kernel.get('kernel_version', 'N/A')}{current_marker}")
        lines.append("")
    
    elif command == "reboot_plan":
        lines.append(f"Reason: {data.get('reason', 'N/A')}")
        lines.append(f"Delay: {data.get('delay_sec', 0)} seconds")
        lines.append(f"Blocked: {'YES' if data.get('blocked') else 'NO'}")
        lines.append(f"Safe to Proceed: {'YES' if data.get('safe_to_proceed') else 'NO'}")
        lines.append("")
        
        if data.get("block_reasons"):
            lines.append("Block Reasons:")
            for reason in data["block_reasons"]:
                lines.append(f"  • {reason}")
            lines.append("")
    
    elif command == "rollback_kernel_list":
        lines.append(f"Current Kernel: {data.get('current_kernel', 'N/A')}")
        lines.append(f"Available Kernels: {data.get('count', 0)}")
        lines.append("")
        
        for kernel in data.get("available_kernels", []):
            current_marker = " ← CURRENT" if kernel.get("is_current") else ""
            lines.append(f"  • {kernel.get('kernel_version', 'N/A')}{current_marker}")
            lines.append(f"    ID: {kernel.get('menuentry_id', 'N/A')}")
        lines.append("")
    
    # Show errors if any
    if errors:
        lines.append("Warnings/Errors:")
        for error in errors:
            lines.append(f"  ⚠ {error}")
        lines.append("")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)


# ============================================================================
# Main CLI
# ============================================================================

def load_config(config_path: Optional[str] = None) -> Dict:
    """
    Load configuration from JSON file.
    
    Args:
        config_path: Path to config file
    
    Returns:
        Configuration dictionary
    """
    config = DEFAULT_CONFIG.copy()
    
    if not config_path:
        # Try default location
        script_dir = Path(__file__).resolve().parent.parent
        config_path = script_dir / "config" / "default.json"
    
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, "r") as f:
                loaded_config = json.load(f)
                # Deep merge
                for key, value in loaded_config.items():
                    if isinstance(value, dict) and key in config:
                        config[key].update(value)
                    else:
                        config[key] = value
                logger.debug(f"Loaded config from {config_path}")
        except Exception as e:
            logger.warning(f"Could not load config: {e}")
    
    return config


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code
    """
    # Create parser with shared CLI infrastructure
    parser, subparsers = create_subparser_tool_parser(
        tool_name="spark_updatectl",
        description="Spark UpdateCtl - Enterprise update control for DGX Spark",
        version=VERSION,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # status command
    subparsers.add_parser("status", help="Gather and output unified system status")
    
    # reboot command
    reboot_parser = subparsers.add_parser("reboot", help="Reboot operations")
    reboot_sub = reboot_parser.add_subparsers(dest="reboot_cmd", help="Reboot subcommand")
    
    # reboot plan
    plan_parser = reboot_sub.add_parser("plan", help="Assess reboot readiness")
    plan_parser.add_argument("--reason", help="Reason for reboot")
    plan_parser.add_argument("--delay-sec", type=int, help="Delay before reboot")
    plan_parser.add_argument("--require-no-blocking-inhibitors", action="store_true", default=True)
    plan_parser.add_argument("--allow-delay-inhibitors", action="store_true", default=True)
    
    # reboot now
    now_parser = reboot_sub.add_parser("now", help="Execute reboot immediately")
    now_parser.add_argument("--reason", help="Reason for reboot")
    now_parser.add_argument("--delay-sec", type=int, help="Delay before reboot")
    now_parser.add_argument("--force", action="store_true", help="Ignore blocking inhibitors")
    
    # reboot schedule
    schedule_parser = reboot_sub.add_parser("schedule", help="Schedule a reboot")
    schedule_parser.add_argument("--at", help="Schedule time (YYYY-MM-DD HH:MM:SS)")
    schedule_parser.add_argument("--in-minutes", type=int, help="Schedule in N minutes")
    schedule_parser.add_argument("--reason", help="Reason for reboot")
    schedule_parser.add_argument("--force", action="store_true", help="Ignore inhibitors at execution time")
    
    # reboot cancel
    cancel_parser = reboot_sub.add_parser("cancel", help="Cancel scheduled reboot")
    cancel_parser.add_argument("--remove-units", action="store_true", help="Remove systemd units")
    
    # reboot schedule-status
    reboot_sub.add_parser("schedule-status", help="Get scheduled reboot status")
    
    # rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback operations")
    rollback_sub = rollback_parser.add_subparsers(dest="rollback_cmd", help="Rollback subcommand")
    
    # rollback kernel list
    rollback_sub.add_parser("kernel-list", help="List available kernels")
    
    # rollback kernel set-next
    set_next_parser = rollback_sub.add_parser("kernel-set-next", help="Set next boot kernel")
    set_next_parser.add_argument("--kernel", required=True, help="Kernel version")
    
    # rollback kernel clear-next
    rollback_sub.add_parser("kernel-clear-next", help="Clear next boot kernel setting")
    
    # rollback os-backup-status
    backup_parser = rollback_sub.add_parser("os-backup-status", help="Report OS backup capability")
    backup_parser.add_argument("--export-manifest", action="store_true", help="Export recovery manifest")
    
    # fw command
    fw_parser = subparsers.add_parser("fw", help="Firmware operations")
    fw_sub = fw_parser.add_subparsers(dest="fw_cmd", help="Firmware subcommand")
    
    # fw rollback-report
    fw_report_parser = fw_sub.add_parser("rollback-report", help="Generate firmware rollback report")
    fw_report_parser.add_argument("--query-releases", action="store_true", help="Query available releases per device")
    
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return ExitCode.INVALID_ARGS
    
    # Load config
    config = load_config(args.config)
    
    # Setup logging using shared infrastructure
    log_path = args.log or config.get("log_path")
    # Re-assign logger from shared setup
    global logger
    logger = cli_setup_logging(log_path, args.verbose, tool_name="spark_updatectl")

    logger.info(f"Spark UpdateCtl {VERSION}")
    logger.info(f"Command: {args.command}")
    
    # Route commands
    result = None
    command_name = args.command
    
    try:
        if args.command == "status":
            result = cmd_status(args, config)
            command_name = "status"
        
        elif args.command == "reboot":
            if args.reboot_cmd == "plan":
                result = cmd_reboot_plan(args, config)
                command_name = "reboot_plan"
            elif args.reboot_cmd == "now":
                result = cmd_reboot_now(args, config)
                command_name = "reboot_now"
            elif args.reboot_cmd == "schedule":
                result = cmd_reboot_schedule(args, config)
                command_name = "reboot_schedule"
            elif args.reboot_cmd == "cancel":
                result = cmd_reboot_cancel(args, config)
                command_name = "reboot_cancel"
            elif args.reboot_cmd == "schedule-status":
                result = cmd_reboot_schedule_status(args, config)
                command_name = "reboot_schedule_status"
            else:
                result = format_envelope(False, None, ["Unknown reboot subcommand"])
        
        elif args.command == "rollback":
            if args.rollback_cmd == "kernel-list":
                result = cmd_rollback_kernel_list(args, config)
                command_name = "rollback_kernel_list"
            elif args.rollback_cmd == "kernel-set-next":
                result = cmd_rollback_kernel_set_next(args, config)
                command_name = "rollback_kernel_set_next"
            elif args.rollback_cmd == "kernel-clear-next":
                result = cmd_rollback_kernel_clear_next(args, config)
                command_name = "rollback_kernel_clear_next"
            elif args.rollback_cmd == "os-backup-status":
                result = cmd_rollback_os_backup_status(args, config)
                command_name = "rollback_os_backup_status"
            else:
                result = format_envelope(False, None, ["Unknown rollback subcommand"])
        
        elif args.command == "fw":
            if args.fw_cmd == "rollback-report":
                result = cmd_fw_rollback_report(args, config)
                command_name = "fw_rollback_report"
            else:
                result = format_envelope(False, None, ["Unknown fw subcommand"])
        
        else:
            result = format_envelope(False, None, ["Unknown command"])
    
    except Exception as e:
        logger.exception("Unhandled exception")
        result = format_envelope(False, None, [f"Unhandled exception: {e}"])

    # Ensure meta has tool and version info
    if "meta" not in result or not isinstance(result.get("meta"), dict):
        result["meta"] = {}
    result["meta"]["tool"] = "spark_updatectl"
    result["meta"]["version"] = VERSION

    # Output result
    if args.human:
        output = format_human_output(command_name, result)
    else:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    
    if args.output:
        try:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output + "\n")
            logger.info(f"Output written to {args.output}")
        except Exception as e:
            logger.error(f"Failed to write output: {e}")
            return ExitCode.GENERAL_ERROR
    else:
        print(output)

    return ExitCode.SUCCESS if result.get("ok") else ExitCode.GENERAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
