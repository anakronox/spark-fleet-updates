#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
OS Build Identity Reporter for DGX Spark

Collects comprehensive OS version, build identity, and baseline package fingerprint:
- OS version and build (Ubuntu release, kernel)
- DGX base image identity (DGX build version/date/commit)
- Baseline package fingerprint (curated APT/dpkg packages and snaps)
- Deterministic fingerprint for build/configuration tracking

Output: Canonical JSON suitable for CMDB, Redfish mapping, and compliance tracking.

Requirements:
- Python 3 stdlib only (no external dependencies)
- Read-only system queries
- Graceful degradation if optional sources missing
- Atomic file writes
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import re
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
from asset_id import resolve_asset_id, get_platform_dmi, load_identity_file

_TOOL = "os_build_identity_reporter"
_VERSION = "1.0.0"
_FUNCTIONAL_AREA = "clear_asset_information"

# Default paths
DEFAULT_OUTPUT_PATH = f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.json"
DEFAULT_IDENTITY_PATH = f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/device_identity/device_identity.json"
DEFAULT_LOG_PATH = f"/var/log/dgx_spark/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.log"
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"

# Constants
MAX_RELEASE_MARKER_BYTES = 10240  # 10KB per file
PACKAGE_WARNING_THRESHOLD = 1000


def setup_logging(log_path: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """
    Setup logging to file and/or stderr.
    
    Args:
        log_path: Path to log file (if None or fails, log to stderr)
        verbose: Enable DEBUG level logging
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("os_build_identity")
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


def parse_key_value_file(content: str, strip_quotes: bool = True) -> Dict[str, str]:
    """
    Parse KEY=VALUE or KEY="VALUE" format file.
    
    Handles:
    - Comments (lines starting with #)
    - Empty lines
    - Quoted and unquoted values
    - Whitespace around = sign
    
    Args:
        content: File content as string
        strip_quotes: Remove surrounding quotes from values
    
    Returns:
        Dict of key -> value
    """
    result = {}
    
    for line in content.split("\n"):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue
        
        # Look for KEY=VALUE
        if "=" not in line:
            continue
        
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        
        # Strip quotes if requested
        if strip_quotes and len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
        
        result[key] = value
    
    return result


def collect_os_identity(logger: logging.Logger) -> Dict[str, Any]:
    """Collect OS version and build identity."""
    logger.info("Collecting OS identity...")
    
    os_data = {
        "os_release": {},
        "lsb_release_file": None,
        "lsb_release_cmd": None,
        "kernel": {
            "uname_r": None,
            "uname_a": None
        }
    }
    
    sources = []
    
    # Parse /etc/os-release
    os_release_path = Path("/etc/os-release")
    if os_release_path.exists():
        try:
            content = os_release_path.read_text()
            os_data["os_release"] = parse_key_value_file(content)
            sources.append("/etc/os-release")
            logger.debug(f"Parsed /etc/os-release: {len(os_data['os_release'])} fields")
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read /etc/os-release: {e}")
    
    # Parse /etc/lsb-release (optional)
    lsb_release_path = Path("/etc/lsb-release")
    if lsb_release_path.exists():
        try:
            content = lsb_release_path.read_text()
            os_data["lsb_release_file"] = parse_key_value_file(content)
            sources.append("/etc/lsb-release")
            logger.debug(f"Parsed /etc/lsb-release: {len(os_data['lsb_release_file'])} fields")
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read /etc/lsb-release: {e}")
    
    # Run lsb_release command (optional)
    if shutil.which("lsb_release"):
        success, stdout, stderr = run_command(["lsb_release", "-a"], logger, timeout=5)
        if success:
            os_data["lsb_release_cmd"] = stdout.strip()
            sources.append("lsb_release")
            logger.debug("Captured lsb_release -a output")
    
    # Capture kernel info
    success, stdout, stderr = run_command(["uname", "-r"], logger, timeout=5)
    if success:
        os_data["kernel"]["uname_r"] = stdout.strip()
        sources.append("uname")
        logger.info(f"Kernel (uname -r): {os_data['kernel']['uname_r']}")
    
    success, stdout, stderr = run_command(["uname", "-a"], logger, timeout=5)
    if success:
        os_data["kernel"]["uname_a"] = stdout.strip()
        logger.debug("Captured uname -a output")
    
    return os_data, sources


def collect_dgx_identity(logger: logging.Logger) -> Tuple[Dict[str, Any], List[str]]:
    """Collect DGX base image identity from various release markers."""
    logger.info("Collecting DGX identity...")
    
    dgx_data = {
        "dgx_release": None,
        "release_markers": {}
    }
    
    sources = []
    
    # Primary: /etc/dgx-release
    dgx_release_path = Path("/etc/dgx-release")
    if dgx_release_path.exists():
        try:
            content = dgx_release_path.read_text()
            dgx_data["dgx_release"] = parse_key_value_file(content)
            sources.append("/etc/dgx-release")
            
            # Log key fields
            if dgx_data["dgx_release"]:
                version = dgx_data["dgx_release"].get("DGX_SWBUILD_VERSION", "unknown")
                logger.info(f"DGX build version: {version}")
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read /etc/dgx-release: {e}")
    else:
        logger.info("/etc/dgx-release not found (may not be DGX platform)")
    
    # Additional release markers (best-effort)
    release_marker_paths = [
        "/etc/dgx-release",
        "/etc/dgx-os-release",
        "/etc/nvidia-release",
        "/etc/nv_tegra_release",
        "/etc/image-release",
        "/etc/system-image-release",
        "/etc/cloud/build.info",
        "/etc/issue",
        "/etc/issue.net"
    ]
    
    for marker_path_str in release_marker_paths:
        marker_path = Path(marker_path_str)
        if marker_path.exists():
            try:
                content = marker_path.read_text()
                
                # Truncate if too large
                if len(content) > MAX_RELEASE_MARKER_BYTES:
                    content = content[:MAX_RELEASE_MARKER_BYTES] + \
                              f"\n... [truncated, {len(content)} total bytes]"
                    logger.debug(f"Truncated {marker_path_str} to {MAX_RELEASE_MARKER_BYTES} bytes")
                
                dgx_data["release_markers"][marker_path_str] = content
                
                if "release_markers" not in sources:
                    sources.append("release_markers")
                
                logger.debug(f"Collected release marker: {marker_path_str} ({len(content)} bytes)")
            except (OSError, IOError) as e:
                logger.debug(f"Could not read {marker_path_str}: {e}")
    
    return dgx_data, sources


def collect_baseline_packages(
    curated_list: List[str],
    all_packages: bool,
    logger: logging.Logger
) -> Tuple[Dict[str, str], List[str]]:
    """
    Collect baseline package versions from dpkg.
    
    Args:
        curated_list: List of package name patterns to include (if not all_packages)
        all_packages: If True, include all installed packages
        logger: Logger instance
    
    Returns:
        Tuple of (packages dict, sources list)
    """
    logger.info("Collecting baseline packages from dpkg...")
    
    packages = {}
    sources = []
    
    # Run dpkg-query
    success, stdout, stderr = run_command(
        ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
        logger,
        timeout=30
    )
    
    if not success:
        logger.warning("dpkg-query failed or not available")
        return packages, sources
    
    sources.append("dpkg-query")
    
    # Parse output
    all_pkgs = {}
    for line in stdout.split("\n"):
        line = line.strip()
        if not line or "\t" not in line:
            continue
        
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        
        pkg_name, pkg_version = parts
        all_pkgs[pkg_name] = pkg_version
    
    logger.debug(f"dpkg reports {len(all_pkgs)} total packages")
    
    if all_packages:
        packages = all_pkgs
        if len(packages) > PACKAGE_WARNING_THRESHOLD:
            logger.warning(f"Including {len(packages)} packages in output (--all-packages enabled)")
    else:
        # Curated filtering
        for pkg_name, pkg_version in all_pkgs.items():
            # Exact match
            if pkg_name in curated_list:
                packages[pkg_name] = pkg_version
                continue
            
            # Pattern match for versioned packages
            # linux-image-* packages
            if pkg_name.startswith("linux-image-") and \
               any(p.startswith("linux-image-") for p in curated_list):
                packages[pkg_name] = pkg_version
                continue
            
            # linux-headers-* packages
            if pkg_name.startswith("linux-headers-") and \
               any(p.startswith("linux-headers-") for p in curated_list):
                packages[pkg_name] = pkg_version
                continue
            
            # nvidia-driver-* packages
            if pkg_name.startswith("nvidia-driver-"):
                packages[pkg_name] = pkg_version
                continue
            
            # nvidia-utils-* packages
            if pkg_name.startswith("nvidia-utils-"):
                packages[pkg_name] = pkg_version
                continue
            
            # nvidia-firmware-* packages
            if pkg_name.startswith("nvidia-firmware-"):
                packages[pkg_name] = pkg_version
                continue
            
            # dgx-* packages
            if pkg_name.startswith("dgx-"):
                packages[pkg_name] = pkg_version
                continue
        
        logger.info(f"Filtered to {len(packages)} curated packages")
    
    return packages, sources


def collect_baseline_snaps(
    curated_list: List[str],
    all_snaps: bool,
    logger: logging.Logger
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Collect installed snaps.
    
    Args:
        curated_list: List of snap names to include (if not all_snaps)
        all_snaps: If True, include all installed snaps
        logger: Logger instance
    
    Returns:
        Tuple of (snaps list, sources list)
    """
    logger.info("Collecting snaps...")
    
    snaps = []
    sources = []
    
    if not shutil.which("snap"):
        logger.info("snap command not available")
        return snaps, sources
    
    # Run snap list
    success, stdout, stderr = run_command(["snap", "list"], logger, timeout=15)
    
    if not success:
        logger.warning("snap list failed")
        return snaps, sources
    
    sources.append("snap list")
    
    # Parse output
    # Format: Name  Version  Rev   Tracking       Publisher   Notes
    lines = stdout.split("\n")
    
    for i, line in enumerate(lines):
        # Skip header
        if i == 0:
            continue
        
        line = line.strip()
        if not line:
            continue
        
        # Parse columns (whitespace-separated, but values may contain spaces in publisher)
        parts = line.split()
        
        if len(parts) < 4:
            continue
        
        name = parts[0]
        version = parts[1]
        rev = parts[2]
        tracking = parts[3] if len(parts) > 3 else None
        publisher = parts[4] if len(parts) > 4 else None
        notes = " ".join(parts[5:]) if len(parts) > 5 else None
        
        snap_entry = {
            "name": name,
            "version": version,
            "rev": rev,
            "tracking": tracking,
            "publisher": publisher,
            "notes": notes
        }
        
        # Filter if not all_snaps
        if all_snaps or name in curated_list:
            snaps.append(snap_entry)
    
    if all_snaps:
        logger.info(f"Collected {len(snaps)} snaps")
    else:
        logger.info(f"Filtered to {len(snaps)} curated snaps")
    
    return snaps, sources


def compute_fingerprint(
    os_data: Dict[str, Any],
    dgx_data: Dict[str, Any],
    packages: Dict[str, str],
    snaps: List[Dict[str, Any]],
    logger: logging.Logger
) -> Tuple[str, Dict[str, Any]]:
    """
    Compute deterministic fingerprint for the base image/build.
    
    Returns:
        Tuple of (fingerprint_sha256_hex, fingerprint_material_dict)
    """
    logger.info("Computing baseline fingerprint...")
    
    # Collect key components
    material = {
        "os_id": os_data.get("os_release", {}).get("ID"),
        "os_version_id": os_data.get("os_release", {}).get("VERSION_ID"),
        "os_version": os_data.get("os_release", {}).get("VERSION"),
        "os_codename": os_data.get("os_release", {}).get("UBUNTU_CODENAME"),
        "kernel_uname_r": os_data.get("kernel", {}).get("uname_r"),
        "dgx_build_version": None,
        "dgx_build_date": None,
        "dgx_commit_id": None,
        "packages": {},
        "snaps": []
    }
    
    # DGX fields (if present)
    if dgx_data.get("dgx_release"):
        material["dgx_build_version"] = dgx_data["dgx_release"].get("DGX_SWBUILD_VERSION")
        material["dgx_build_date"] = dgx_data["dgx_release"].get("DGX_SWBUILD_DATE")
        material["dgx_commit_id"] = dgx_data["dgx_release"].get("DGX_COMMIT_ID")
    
    # Packages (sorted)
    material["packages"] = dict(sorted(packages.items()))
    
    # Snaps (sorted by name)
    material["snaps"] = sorted(
        [{"name": s["name"], "version": s["version"], "rev": s["rev"]} for s in snaps],
        key=lambda x: x["name"]
    )
    
    # Create deterministic string for hashing
    hash_parts = []
    
    # OS identity
    hash_parts.append(f"os_id={material['os_id']}")
    hash_parts.append(f"os_version_id={material['os_version_id']}")
    hash_parts.append(f"os_version={material['os_version']}")
    hash_parts.append(f"os_codename={material['os_codename']}")
    hash_parts.append(f"kernel={material['kernel_uname_r']}")
    
    # DGX identity
    if material["dgx_build_version"]:
        hash_parts.append(f"dgx_version={material['dgx_build_version']}")
    if material["dgx_build_date"]:
        hash_parts.append(f"dgx_date={material['dgx_build_date']}")
    if material["dgx_commit_id"]:
        hash_parts.append(f"dgx_commit={material['dgx_commit_id']}")
    
    # Packages (sorted)
    for pkg, ver in material["packages"].items():
        hash_parts.append(f"pkg:{pkg}={ver}")
    
    # Snaps (sorted)
    for snap in material["snaps"]:
        hash_parts.append(f"snap:{snap['name']}={snap['version']}:{snap['rev']}")
    
    # Compute hash
    hash_string = "\n".join(hash_parts)
    fingerprint_sha256 = hashlib.sha256(hash_string.encode("utf-8")).hexdigest()
    
    logger.info(f"Fingerprint computed: {fingerprint_sha256[:16]}...")
    logger.debug(f"Fingerprint based on {len(hash_parts)} components")
    
    return fingerprint_sha256, material


def collect_os_build_identity(
    config: Dict[str, Any],
    args: argparse.Namespace,
    logger: logging.Logger
) -> Dict[str, Any]:
    """Main collection orchestrator."""
    
    logger.info("=" * 60)
    logger.info("Starting OS build identity collection")
    logger.info("=" * 60)
    
    # Load identity
    identity_path = args.identity or config.get("identity_path", DEFAULT_IDENTITY_PATH)
    asset_id, asset_id_source = load_identity(identity_path, logger)
    
    # Collect OS identity
    os_data, os_sources = collect_os_identity(logger)
    
    # Collect DGX identity
    dgx_data, dgx_sources = collect_dgx_identity(logger)
    
    # Collect baseline packages
    curated_packages = config.get("curated_packages", [])
    packages, pkg_sources = collect_baseline_packages(curated_packages, args.all_packages, logger)
    
    # Collect snaps
    curated_snaps = config.get("curated_snaps", [])
    snaps, snap_sources = collect_baseline_snaps(curated_snaps, args.all_snaps, logger)
    
    # Compute fingerprint
    fingerprint_sha256, fingerprint_material = compute_fingerprint(
        os_data, dgx_data, packages, snaps, logger
    )
    
    # Build output
    output = {
        "collected_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "asset_id": asset_id,
        "asset_id_source": asset_id_source,
        "platform_dmi": get_platform_dmi(),
        "os": os_data,
        "dgx": dgx_data,
        "baseline": {
            "packages": packages,
            "snaps": snaps,
            "fingerprint_sha256": fingerprint_sha256,
            "fingerprint_material": fingerprint_material
        },
        "sources": {
            "os": os_sources,
            "dgx": dgx_sources,
            "packages": pkg_sources,
            "snaps": snap_sources
        }
    }
    
    logger.info("=" * 60)
    logger.info("OS build identity collection complete")
    logger.info(f"  OS: {os_data.get('os_release', {}).get('PRETTY_NAME', 'unknown')}")
    logger.info(f"  Kernel: {os_data.get('kernel', {}).get('uname_r', 'unknown')}")
    
    if dgx_data.get("dgx_release"):
        logger.info(f"  DGX build: {dgx_data['dgx_release'].get('DGX_SWBUILD_VERSION', 'unknown')}")
    
    logger.info(f"  Packages: {len(packages)}")
    logger.info(f"  Snaps: {len(snaps)}")
    logger.info(f"  Fingerprint: {fingerprint_sha256[:16]}...")
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
        description="OS Build Identity Reporter for DGX Spark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print OS build identity to stdout
  %(prog)s --print
  
  # Write to default location (requires sudo)
  sudo %(prog)s
  
  # Write to custom location
  %(prog)s --output /tmp/os_build_identity.json
  
  # Include all packages (large output)
  %(prog)s --all-packages --print
  
  # Include all snaps
  %(prog)s --all-snaps --print
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
    parser.add_argument("--all-packages", action="store_true",
                        help="Include all installed packages (WARNING: large output)")
    parser.add_argument("--all-snaps", action="store_true",
                        help="Include all installed snaps")
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

    logger.info(f"OS Build Identity Reporter starting...")
    logger.info(f"Config: {config_path} (exists: {config_path.exists()})")

    try:
        # Collect identity
        identity = collect_os_build_identity(config, args, logger)

        default_path = args.output or config.get("output_path", DEFAULT_OUTPUT_PATH)
        route_output(
            identity, args, _TOOL, _VERSION, default_path,
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
