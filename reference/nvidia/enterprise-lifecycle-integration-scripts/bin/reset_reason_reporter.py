#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
reset_reason_reporter.py

Best-effort classification of why the most recent reset/reboot happened.

Analyzes multiple evidence sources:
- systemd boot history
- wtmp reboot/shutdown records
- Previous boot journal (shutdown markers, kernel panics)
- pstore crash records
- systemd reboot hints
- EFI variables

Design:
- JSON-first output (--human for readable format)
- Read-only operations (no root required, graceful degradation)
- Conservative classification (prefers UNKNOWN over speculation)
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
    create_base_parser,
    setup_logging as cli_setup_logging,
    ExitCode,
)

# ============================================================================
# Constants
# ============================================================================

VERSION = "1.1.0"  # Bumped for CLI standardization
TOOL_NAME = "reset_reason_reporter"

# Reason codes
REASON_CODES = {
    "PLANNED_REBOOT": "Planned reboot with clean shutdown sequence",
    "PLANNED_SHUTDOWN": "Planned shutdown",
    "KERNEL_PANIC_OR_OOPS": "Kernel panic or oops detected",
    "WATCHDOG_RESET_SUSPECTED": "Watchdog reset or hard lockup suspected",
    "POWER_LOSS_OR_HARD_RESET_SUSPECTED": "Power loss or hard reset suspected",
    "FIRMWARE_UPDATE_REBOOT_SUSPECTED": "Firmware update reboot suspected",
    "UNKNOWN": "Insufficient evidence to determine reset reason"
}

DEFAULT_CONFIG = {
    "runtime_output_dir": "/var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter",
    "log_path": "/var/log/dgx_spark/remote_ops_remediation/reset_reason_reporter/reset_reason_reporter.log",
    "truncate": {
        "max_lines": 200,
        "max_bytes": 200000
    },
    "timeouts": {
        "subprocess_sec": 10
    }
}

logger = logging.getLogger(__name__)

# ============================================================================
# Utility Functions
# ============================================================================

# setup_logging() now imported from cli_base
# Use: cli_setup_logging(log_path, verbose, tool_name="reset_reason_reporter")


def run_command(
    cmd: List[str],
    timeout: int = 10
) -> Tuple[bool, str, str]:
    """
    Run command and return results.
    
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return True, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return False, "", str(e)


def truncate_text(
    text: str,
    max_lines: Optional[int] = None,
    max_bytes: Optional[int] = None
) -> Tuple[str, bool]:
    """
    Truncate text by lines or bytes.
    
    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    truncated = False
    
    if max_lines:
        lines = text.split("\n")
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines])
            truncated = True
    
    if max_bytes and len(text.encode("utf-8")) > max_bytes:
        text = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        truncated = True
    
    return text, truncated


# format_envelope() replaced by format_envelope() from cli_base
# Tool and version info added to meta in main() function


# ============================================================================
# Data Collection Functions
# ============================================================================

def collect_current_boot(config: Dict) -> Dict:
    """Collect current boot identity."""
    info = {}
    
    # Boot ID
    try:
        with open("/proc/sys/kernel/random/boot_id", "r") as f:
            info["boot_id"] = f.read().strip()
    except Exception as e:
        logger.debug(f"Failed to read boot_id: {e}")
    
    # Kernel
    success, stdout, _ = run_command(["uname", "-r"])
    if success:
        info["kernel"] = stdout.strip()
    
    # Uptime
    try:
        with open("/proc/uptime", "r") as f:
            uptime_sec = float(f.read().split()[0])
            info["uptime_seconds"] = int(uptime_sec)
    except Exception as e:
        logger.debug(f"Failed to read uptime: {e}")
    
    return info


def collect_boot_history(config: Dict) -> Tuple[Dict, List[str]]:
    """Collect boot history from multiple sources."""
    max_lines = config["truncate"]["max_lines"]
    timeout = config["timeouts"]["subprocess_sec"]
    errors = []
    info = {}
    
    # journalctl --list-boots
    success, stdout, stderr = run_command(["journalctl", "--list-boots"], timeout=timeout)
    if success:
        lines = stdout.strip().split("\n")
        # Take last 10 boots
        lines = lines[-10:] if len(lines) > 10 else lines
        info["systemd_boot_list"] = {
            "lines": lines,
            "truncated": False
        }
    else:
        errors.append(f"journalctl --list-boots failed: {stderr}")
    
    # who -b
    success, stdout, _ = run_command(["who", "-b"], timeout=timeout)
    if success:
        info["who_last_boot"] = stdout.strip()
    
    # last -x (last 20 reboot/shutdown lines)
    success, stdout, stderr = run_command(["last", "-x", "-n", "20"], timeout=timeout)
    if success:
        # Filter for reboot/shutdown lines
        reboot_lines = [line for line in stdout.split("\n") if "reboot" in line.lower() or "shutdown" in line.lower()]
        truncated_lines, truncated = truncate_text("\n".join(reboot_lines), max_lines=max_lines)
        info["wtmp_reboot_history"] = {
            "lines": truncated_lines.split("\n"),
            "truncated": truncated
        }
    else:
        errors.append(f"last -x failed: {stderr}")
    
    return info, errors


def collect_prev_boot_shutdown_markers(config: Dict) -> Tuple[Dict, List[str]]:
    """Collect clean shutdown markers from previous boot."""
    max_lines = config["truncate"]["max_lines"]
    timeout = config["timeouts"]["subprocess_sec"]
    errors = []
    info = {}
    
    # journalctl -b -1 for shutdown markers
    success, stdout, stderr = run_command(["journalctl", "-b", "-1", "--no-pager"], timeout=timeout)
    
    if not success:
        errors.append(f"Previous boot journal not accessible: {stderr}")
        return info, errors
    
    # Search for shutdown markers
    shutdown_keywords = [
        "System is rebooting",
        "Reached target reboot.target",
        "systemd-shutdown",
        "Syncing filesystems"
    ]
    
    matching_lines = []
    for line in stdout.split("\n"):
        if any(kw in line for kw in shutdown_keywords):
            matching_lines.append(line)
    
    if matching_lines:
        truncated_text, truncated = truncate_text("\n".join(matching_lines), max_lines=max_lines)
        info["prev_boot_shutdown_markers"] = {
            "lines": truncated_text.split("\n"),
            "truncated": truncated
        }
    else:
        info["prev_boot_shutdown_markers"] = {
            "lines": [],
            "truncated": False
        }
    
    return info, errors


def collect_prev_boot_kernel_markers(config: Dict) -> Tuple[Dict, List[str]]:
    """Collect kernel crash/hang markers from previous boot."""
    max_lines = config["truncate"]["max_lines"]
    timeout = config["timeouts"]["subprocess_sec"]
    errors = []
    info = {}
    
    # journalctl -k -b -1 for kernel markers
    success, stdout, stderr = run_command(["journalctl", "-k", "-b", "-1", "--no-pager"], timeout=timeout)
    
    if not success:
        errors.append(f"Previous boot kernel log not accessible: {stderr}")
        return info, errors
    
    # Search for crash/hang markers
    crash_keywords = [
        "panic", "oops", "hard lockup", "soft lockup",
        "hung", "watchdog", "resetting"
    ]
    
    matching_lines = []
    for line in stdout.split("\n"):
        if any(kw in line.lower() for kw in crash_keywords):
            matching_lines.append(line)
    
    if matching_lines:
        truncated_text, truncated = truncate_text("\n".join(matching_lines), max_lines=max_lines)
        info["prev_boot_kernel_markers"] = {
            "lines": truncated_text.split("\n"),
            "truncated": truncated
        }
    else:
        info["prev_boot_kernel_markers"] = {
            "lines": [],
            "truncated": False
        }
    
    return info, errors


def collect_pstore_evidence(config: Dict) -> Tuple[Dict, List[str]]:
    """Collect pstore crash evidence."""
    max_lines = config["truncate"]["max_lines"]
    errors = []
    info = {
        "mounted": False,
        "backend": "unknown",
        "files": [],
        "samples": [],
        "truncated": False
    }
    
    pstore_path = Path("/sys/fs/pstore")
    
    # Check if mounted
    if not pstore_path.exists():
        return info, errors
    
    info["mounted"] = True
    
    # Check backend
    success, stdout, _ = run_command(["lsmod"])
    if success and "efi_pstore" in stdout:
        info["backend"] = "efi_pstore"
    
    # List files
    try:
        files = list(pstore_path.iterdir())
        info["files"] = [f.name for f in files]
        
        # Sample first few files
        for f in files[:3]:  # Limit to 3 files
            try:
                content = f.read_text(errors="ignore")
                truncated_content, truncated = truncate_text(content, max_lines=max_lines // 3)
                info["samples"].append({
                    "file": f.name,
                    "content": truncated_content,
                    "truncated": truncated
                })
            except Exception as e:
                logger.debug(f"Failed to read pstore file {f.name}: {e}")
        
        if len(files) > 3:
            info["truncated"] = True
    
    except Exception as e:
        errors.append(f"Failed to read pstore: {e}")
    
    return info, errors


def collect_systemd_reboot_hints(config: Dict) -> Tuple[Dict, List[str]]:
    """Collect systemd reboot hints from /run."""
    errors = []
    info = {
        "present": [],
        "hexdumps": {}
    }
    
    hint_files = [
        "/run/systemd/reboot-param",
        "/run/systemd/reboot-to-firmware-setup",
        "/run/systemd/reboot-to-boot-loader-menu"
    ]
    
    for hint_file in hint_files:
        hint_path = Path(hint_file)
        if hint_path.exists():
            info["present"].append(hint_file)
            
            try:
                # Read and hexdump (limited)
                with open(hint_path, "rb") as f:
                    data = f.read(256)  # Cap at 256 bytes
                    hex_str = data.hex()
                    info["hexdumps"][hint_file] = hex_str
            except Exception as e:
                logger.debug(f"Failed to read {hint_file}: {e}")
    
    return info, errors


def decode_efi_var_payload(payload: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Attempt to decode EFI variable payload.
    
    Returns:
        Tuple of (decoded_text, raw_hex)
    """
    decoded_text = None
    raw_hex = payload.hex()
    
    # Try UTF-16LE (common for EFI strings)
    try:
        # Check if it looks like UTF-16LE (NUL bytes every other byte)
        if len(payload) > 2:
            nul_count = sum(1 for i in range(1, len(payload), 2) if payload[i] == 0)
            if nul_count > len(payload) // 4:  # >25% NUL bytes in odd positions
                decoded = payload.decode("utf-16-le").strip("\x00")
                if decoded.isprintable() or all(ord(c) < 128 for c in decoded):
                    decoded_text = decoded
                    return decoded_text, raw_hex
    except Exception:
        pass
    
    # Try UTF-8/ASCII
    try:
        decoded = payload.decode("utf-8").strip("\x00")
        if decoded.isprintable():
            decoded_text = decoded
            return decoded_text, raw_hex
    except Exception:
        pass
    
    # Return hex only
    return None, raw_hex


def collect_efi_vars(config: Dict) -> Tuple[List[Dict], List[str]]:
    """Collect relevant EFI variables."""
    max_bytes = config["truncate"]["max_bytes"]
    errors = []
    efi_vars = []
    
    efivars_path = Path("/sys/firmware/efi/efivars")
    
    if not efivars_path.exists():
        return efi_vars, errors
    
    # Target variable name patterns
    target_patterns = [
        "CapsuleLast-",
        "LastBoot-",
        "LoaderEntryRebootReason-"
    ]
    
    try:
        for var_file in efivars_path.iterdir():
            var_name = var_file.name
            
            # Check if matches target patterns
            if not any(pattern in var_name for pattern in target_patterns):
                continue
            
            try:
                # Read variable
                with open(var_file, "rb") as f:
                    data = f.read(max_bytes)
                
                # Parse: first 4 bytes = attributes (uint32 little-endian)
                if len(data) < 4:
                    continue
                
                attributes = int.from_bytes(data[:4], byteorder='little')
                payload = data[4:]
                
                # Decode payload
                decoded_text, raw_hex = decode_efi_var_payload(payload)
                
                # Extract GUID from name (format: name-GUID)
                parts = var_name.rsplit("-", 5)
                if len(parts) == 6:
                    guid = "-".join(parts[-5:])
                    name = parts[0]
                else:
                    guid = "unknown"
                    name = var_name
                
                var_info = {
                    "name": name,
                    "guid": guid,
                    "attributes": attributes,
                    "decoded_text": decoded_text,
                    "raw_hex": raw_hex if len(raw_hex) <= 512 else raw_hex[:512],  # Cap hex
                    "truncated": len(data) >= max_bytes or len(raw_hex) > 512
                }
                
                efi_vars.append(var_info)
            
            except Exception as e:
                logger.debug(f"Failed to read EFI var {var_name}: {e}")
    
    except Exception as e:
        errors.append(f"Failed to scan EFI vars: {e}")
    
    return efi_vars, errors


# ============================================================================
# Classification Logic
# ============================================================================

def classify_reset_reason(signals: Dict) -> Tuple[str, int, str, List[Dict]]:
    """
    Classify reset reason based on collected signals.
    
    Returns:
        Tuple of (reason_code, confidence, summary, evidence)
    """
    evidence = []
    
    # Check for pstore records
    pstore = signals.get("pstore", {})
    if pstore.get("files"):
        evidence.append({
            "source": "pstore",
            "detail": f"Found {len(pstore['files'])} pstore records",
            "severity": "strong"
        })
    
    # Check for kernel panic/oops markers
    kernel_markers = signals.get("prev_boot_kernel_markers", {})
    panic_lines = kernel_markers.get("lines", [])
    has_panic = any("panic" in line.lower() or "oops" in line.lower() for line in panic_lines)
    
    if has_panic:
        evidence.append({
            "source": "journald_prev_boot_kernel",
            "detail": "Kernel panic or oops detected in previous boot",
            "severity": "strong"
        })
    
    # Check for clean shutdown markers
    shutdown_markers = signals.get("prev_boot_shutdown_markers", {})
    shutdown_lines = shutdown_markers.get("lines", [])
    has_reboot_target = any("reboot.target" in line for line in shutdown_lines)
    has_systemd_shutdown = any("systemd-shutdown" in line for line in shutdown_lines)
    has_sync_fs = any("Syncing filesystems" in line.lower() for line in shutdown_lines)
    
    if has_reboot_target or has_systemd_shutdown:
        evidence.append({
            "source": "journald_prev_boot",
            "detail": "Clean shutdown sequence detected",
            "severity": "info"
        })
    
    # Check for watchdog/lockup
    has_watchdog = any("watchdog" in line.lower() or "lockup" in line.lower() for line in panic_lines)
    
    if has_watchdog and not (has_reboot_target or has_systemd_shutdown):
        evidence.append({
            "source": "journald_prev_boot_kernel",
            "detail": "Watchdog or lockup detected without clean shutdown",
            "severity": "warn"
        })
    
    # Check for firmware update hints
    efi_vars = signals.get("efi_vars", [])
    has_capsule = any("CapsuleLast" in var.get("name", "") for var in efi_vars)
    
    if has_capsule:
        evidence.append({
            "source": "efi_vars",
            "detail": "CapsuleLast EFI variable present (firmware update suspected)",
            "severity": "info"
        })
    
    # Classification logic
    if pstore.get("files") or has_panic:
        return "KERNEL_PANIC_OR_OOPS", 95, "Kernel panic or oops detected in previous boot", evidence
    
    elif has_reboot_target and (has_systemd_shutdown or has_sync_fs):
        return "PLANNED_REBOOT", 85, "Planned reboot with clean shutdown sequence", evidence
    
    elif has_systemd_shutdown and not has_reboot_target:
        # Shutdown without reboot target
        return "PLANNED_SHUTDOWN", 70, "Planned shutdown detected", evidence
    
    elif has_watchdog and not (has_reboot_target or has_systemd_shutdown):
        return "WATCHDOG_RESET_SUSPECTED", 60, "Watchdog reset or hard lockup suspected", evidence
    
    elif not shutdown_lines and not panic_lines:
        # No evidence of clean shutdown or panic
        return "POWER_LOSS_OR_HARD_RESET_SUSPECTED", 50, "No clean shutdown markers found; power loss or hard reset suspected", evidence
    
    elif has_capsule:
        return "FIRMWARE_UPDATE_REBOOT_SUSPECTED", 60, "Firmware update reboot suspected based on EFI capsule", evidence
    
    else:
        return "UNKNOWN", 30, "Insufficient evidence to determine reset reason", evidence


# ============================================================================
# Main Command
# ============================================================================

def cmd_collect(args, config: Dict) -> Dict:
    """
    Collect and classify reset reason.
    """
    logger.info("Collecting reset reason data...")
    
    errors = []
    signals = {}
    
    # Collect data
    signals["current_boot"] = collect_current_boot(config)
    
    boot_history, boot_errors = collect_boot_history(config)
    signals.update(boot_history)
    errors.extend(boot_errors)
    
    shutdown_markers, shutdown_errors = collect_prev_boot_shutdown_markers(config)
    signals.update(shutdown_markers)
    errors.extend(shutdown_errors)
    
    kernel_markers, kernel_errors = collect_prev_boot_kernel_markers(config)
    signals.update(kernel_markers)
    errors.extend(kernel_errors)
    
    pstore_info, pstore_errors = collect_pstore_evidence(config)
    signals["pstore"] = pstore_info
    errors.extend(pstore_errors)
    
    reboot_hints, hints_errors = collect_systemd_reboot_hints(config)
    signals["systemd_reboot_hints"] = reboot_hints
    errors.extend(hints_errors)
    
    efi_vars, efi_errors = collect_efi_vars(config)
    signals["efi_vars"] = efi_vars
    errors.extend(efi_errors)
    
    # Classify
    reason_code, confidence, summary, evidence = classify_reset_reason(signals)
    
    logger.info(f"Reset reason: {reason_code} (confidence: {confidence}%)")
    
    # Build output
    data = {
        "current_boot": signals["current_boot"],
        "last_reset": {
            "reason_code": reason_code,
            "confidence": confidence,
            "summary": summary,
            "evidence": evidence
        },
        "signals": {
            k: v for k, v in signals.items() if k != "current_boot"
        }
    }
    
    meta = {
        "truncation": config["truncate"]
    }
    
    return format_envelope(True, data, errors, meta)


# ============================================================================
# Human-Readable Output
# ============================================================================

def format_human_output(result: Dict) -> str:
    """Format JSON result as human-readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append("Reset Reason Report")
    lines.append("=" * 80)
    lines.append("")
    
    if not result.get("ok"):
        lines.append("❌ FAILED")
        lines.append("")
        if result.get("errors"):
            lines.append("Errors:")
            for error in result["errors"]:
                lines.append(f"  • {error}")
        return "\n".join(lines)
    
    lines.append("✓ SUCCESS")
    lines.append("")
    
    data = result.get("data", {})
    
    # Current boot
    current_boot = data.get("current_boot", {})
    lines.append("Current Boot:")
    lines.append(f"  Boot ID: {current_boot.get('boot_id', 'N/A')}")
    lines.append(f"  Kernel: {current_boot.get('kernel', 'N/A')}")
    lines.append(f"  Uptime: {current_boot.get('uptime_seconds', 0)} seconds")
    lines.append("")
    
    # Last reset
    last_reset = data.get("last_reset", {})
    lines.append("Last Reset Reason:")
    lines.append(f"  Code: {last_reset.get('reason_code', 'UNKNOWN')}")
    lines.append(f"  Confidence: {last_reset.get('confidence', 0)}%")
    lines.append(f"  Summary: {last_reset.get('summary', 'N/A')}")
    lines.append("")
    
    # Evidence
    evidence = last_reset.get("evidence", [])
    if evidence:
        lines.append("Evidence:")
        for ev in evidence:
            severity_symbol = {"strong": "⚠️", "warn": "⚠", "info": "ℹ"}.get(ev.get("severity", "info"), "•")
            lines.append(f"  {severity_symbol} [{ev.get('source', 'unknown')}] {ev.get('detail', '')}")
        lines.append("")
    
    # Signals summary
    signals = data.get("signals", {})
    
    # pstore
    pstore = signals.get("pstore", {})
    if pstore.get("files"):
        lines.append(f"pstore: {len(pstore['files'])} file(s) found")
    
    # Previous boot markers
    shutdown_markers = signals.get("prev_boot_shutdown_markers", {})
    if shutdown_markers.get("lines"):
        lines.append(f"Shutdown markers: {len(shutdown_markers['lines'])} line(s)")
    
    kernel_markers = signals.get("prev_boot_kernel_markers", {})
    if kernel_markers.get("lines"):
        lines.append(f"Kernel markers: {len(kernel_markers['lines'])} line(s)")
    
    # EFI vars
    efi_vars = signals.get("efi_vars", [])
    if efi_vars:
        lines.append(f"EFI variables: {len(efi_vars)} relevant var(s)")
    
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
    """Main entry point."""
    # Create parser with shared CLI infrastructure
    parser = create_base_parser(
        tool_name=TOOL_NAME,
        description="Reset Reason Reporter - Analyze why the system rebooted",
        version=VERSION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_print=True,
    )

    # Add tool-specific flags
    parser.add_argument("--record", action="store_true", help="Write to runtime directory (reset_reason_report.json + last_reset.json)")
    parser.add_argument("--max-lines", type=int, help="Maximum lines for truncation")
    parser.add_argument("--max-bytes", type=int, help="Maximum bytes for truncation")
    parser.add_argument("--timeout-sec", type=int, help="Subprocess timeout in seconds")
    
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    # Apply CLI overrides
    if args.max_lines:
        config["truncate"]["max_lines"] = args.max_lines
    if args.max_bytes:
        config["truncate"]["max_bytes"] = args.max_bytes
    if args.timeout_sec:
        config["timeouts"]["subprocess_sec"] = args.timeout_sec
    
    # Setup logging using shared infrastructure
    log_path = config.get("log_path")
    global logger
    logger = cli_setup_logging(log_path, args.verbose, tool_name="reset_reason_reporter")

    logger.info(f"Reset Reason Reporter {VERSION}")
    
    # Collect and classify
    try:
        result = cmd_collect(args, config)
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
        output = format_human_output(result)
    else:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    
    # Write to file if requested
    if args.output:
        try:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write
            temp_path = output_path.with_suffix(".tmp")
            temp_path.write_text(output + "\n")
            temp_path.replace(output_path)
            
            logger.info(f"Output written to {args.output}")
        except Exception as e:
            logger.error(f"Failed to write output: {e}")
            return ExitCode.GENERAL_ERROR

    # Record to runtime directory if requested
    if args.record:
        try:
            runtime_dir = Path(config["runtime_output_dir"])
            runtime_dir.mkdir(parents=True, exist_ok=True)
            
            # Write reset_reason_report.json
            report_path = runtime_dir / "reset_reason_report.json"
            temp_path = report_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(result, indent=2) + "\n")
            temp_path.replace(report_path)
            
            # Write last_reset.json (simplified)
            last_reset_data = {
                "collected_at_utc": result["meta"]["collected_at_utc"],
                "reason_code": result["data"]["last_reset"]["reason_code"],
                "confidence": result["data"]["last_reset"]["confidence"],
                "summary": result["data"]["last_reset"]["summary"]
            }
            last_reset_path = runtime_dir / "last_reset.json"
            temp_path = last_reset_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(last_reset_data, indent=2) + "\n")
            temp_path.replace(last_reset_path)
            
            logger.info(f"Recorded to {runtime_dir}")
        except Exception as e:
            logger.error(f"Failed to record: {e}")
            return ExitCode.GENERAL_ERROR

    # Print to stdout if not --output and not --record
    if not args.output and not args.record:
        print(output)

    return ExitCode.SUCCESS if result.get("ok") else ExitCode.GENERAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
