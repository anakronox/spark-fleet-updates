#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
software_inventory_reporter.py

Enterprise software inventory collector for DGX Spark management.

Enumerates installed software from multiple sources:
- dpkg (Debian packages)
- snap (Ubuntu snaps)
- pip (Python packages, optional)
- docker (Images and containers, optional)

Produces a canonical JSON output with:
- Complete software inventory (per source)
- Deterministic manifest with counts and hashes
- Software fingerprint for drift detection

Designed for:
- Enterprise asset tracking and CMDB integration
- Support baselining and configuration drift detection
- Troubleshooting and compliance auditing

Requirements:
- Python 3.6+
- stdlib only (no external dependencies)
- Runs on Ubuntu Linux (DGX Spark)

Author: DGX Spark Management Team
License: MIT
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
from asset_id import resolve_asset_id, get_platform_dmi

_TOOL = "software_inventory_reporter"
_VERSION = "1.0.0"
_FUNCTIONAL_AREA = "clear_asset_information"

# ============================================================================
# Constants
# ============================================================================

DEFAULT_OUTPUT_PATH = f"/var/lib/dgx_spark_management/{_FUNCTIONAL_AREA}/{_TOOL}/{_TOOL}.json"

# Repo log path (relative to script location)
REPO_LOG_PATH = (
    "logs/clear_asset_information/software_inventory_reporter/"
    "software_inventory_reporter.log"
)

DEFAULT_MAX_ITEMS = 50000

DMI_SYSFS_BASE = Path("/sys/class/dmi/id")

# ============================================================================
# Logging Setup
# ============================================================================

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging to repo logs/ if available, else stderr.
    
    Args:
        verbose: If True, set level to DEBUG; else INFO
    """
    level = logging.DEBUG if verbose else logging.INFO
    
    # Try repo log path first
    script_dir = Path(__file__).resolve().parent.parent.parent.parent
    repo_log_file = script_dir / REPO_LOG_PATH
    
    log_handler = None
    try:
        repo_log_file.parent.mkdir(parents=True, exist_ok=True)
        log_handler = logging.FileHandler(repo_log_file, encoding="utf-8")
        logger.info(f"Logging to {repo_log_file}")
    except (OSError, PermissionError) as e:
        # Fallback to stderr
        log_handler = logging.StreamHandler(sys.stderr)
        logger.debug(f"Could not open log file {repo_log_file}: {e}, using stderr")
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    logger.setLevel(level)


# ============================================================================
# Platform Identity Collection
# ============================================================================

def read_dmi_field(field_name: str) -> Optional[str]:
    """
    Read a single DMI sysfs field.
    
    Args:
        field_name: DMI field name (e.g., 'product_serial')
    
    Returns:
        Field value as string, or None if not readable
    """
    try:
        path = DMI_SYSFS_BASE / field_name
        value = path.read_text(encoding="utf-8", errors="ignore").strip()
        return value if value else None
    except Exception:
        return None


def is_valid_dmi_value(value: Optional[str]) -> bool:
    """
    Check if a DMI value is valid (not placeholder/empty).
    
    Args:
        value: DMI field value
    
    Returns:
        True if valid, False otherwise
    """
    if not value:
        return False
    
    invalid_patterns = [
        "none",
        "not specified",
        "to be filled by o.e.m.",
        "default string",
        "system serial number",
        "system product name",
    ]
    
    normalized = value.lower().strip()
    if normalized in invalid_patterns:
        return False
    
    # Check for all-zero UUID
    if re.match(r"^0+$", normalized.replace("-", "")):
        return False
    
    return True


def collect_platform_identity() -> Tuple[Dict[str, Any], Optional[str], str]:
    """
    Collect platform identity using canonical shared module.

    Returns:
        Tuple of (platform_dict, asset_id, asset_id_source)
    """
    platform = get_platform_dmi()
    asset_id, asset_id_source = resolve_asset_id()

    logger.debug(f"Platform identity: asset_id={asset_id}, source={asset_id_source}")
    return platform, asset_id, asset_id_source


# ============================================================================
# OS Identity Collection
# ============================================================================

def parse_os_release(path: str = "/etc/os-release") -> Dict[str, str]:
    """
    Parse /etc/os-release into a dictionary.
    
    Args:
        path: Path to os-release file
    
    Returns:
        Dictionary of key-value pairs
    """
    result = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip('"').strip("'")
                result[key] = value
    except FileNotFoundError:
        logger.warning(f"{path} not found")
    except Exception as e:
        logger.warning(f"Error parsing {path}: {e}")
    
    return result


def get_kernel_version() -> Optional[str]:
    """
    Get kernel version via uname -r.
    
    Returns:
        Kernel version string or None
    """
    try:
        result = subprocess.run(
            ["uname", "-r"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        logger.warning(f"uname -r failed: {e}")
        return None


# ============================================================================
# dpkg Inventory Collection
# ============================================================================

def collect_dpkg_inventory(
    mode: str,
    curated_regex: str,
    max_items: int
) -> Dict[str, Any]:
    """
    Collect dpkg package inventory.
    
    Args:
        mode: "full" or "curated"
        curated_regex: Regex pattern for curated mode
        max_items: Maximum number of packages to return
    
    Returns:
        Dictionary with packages, holds, errors, etc.
    """
    result = {
        "available": False,
        "mode": mode,
        "packages": [],
        "holds": [],
        "errors": []
    }
    
    dpkg_query = shutil.which("dpkg-query")
    if not dpkg_query:
        logger.info("dpkg-query not found, skipping dpkg inventory")
        result["errors"].append("dpkg-query not found")
        return result
    
    result["available"] = True
    
    try:
        # Query all packages
        cmd = [dpkg_query, "-W", "-f=${Package}\t${Version}\t${Architecture}\n"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=True
        )
        
        packages = []
        pattern = re.compile(curated_regex) if mode == "curated" else None
        
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            
            name, version, arch = parts[0], parts[1], parts[2]
            
            # Filter if curated mode
            if mode == "curated" and pattern:
                if not pattern.search(name):
                    continue
            
            packages.append({
                "name": name,
                "version": version,
                "arch": arch
            })
            
            if len(packages) >= max_items:
                logger.warning(f"dpkg: reached max_items limit ({max_items})")
                result["errors"].append(f"Truncated at {max_items} packages")
                break
        
        # Sort deterministically
        packages.sort(key=lambda p: p["name"])
        result["packages"] = packages
        
        logger.info(f"dpkg: collected {len(packages)} packages (mode={mode})")
    
    except subprocess.TimeoutExpired:
        logger.error("dpkg-query timed out")
        result["errors"].append("dpkg-query timed out")
    except subprocess.CalledProcessError as e:
        logger.error(f"dpkg-query failed: {e}")
        result["errors"].append(f"dpkg-query failed: {e}")
    except Exception as e:
        logger.error(f"dpkg collection error: {e}")
        result["errors"].append(f"Unexpected error: {e}")
    
    # Collect held packages (best-effort)
    try:
        apt_mark = shutil.which("apt-mark")
        if apt_mark:
            proc = subprocess.run(
                [apt_mark, "showhold"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True
            )
            holds = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            holds.sort()
            result["holds"] = holds
            logger.debug(f"dpkg: {len(holds)} held packages")
    except Exception as e:
        logger.debug(f"apt-mark showhold failed: {e}")
    
    return result


# ============================================================================
# snap Inventory Collection
# ============================================================================

def collect_snap_inventory(
    mode: str,
    curated_snaps: List[str],
    max_items: int
) -> Dict[str, Any]:
    """
    Collect snap inventory.
    
    Args:
        mode: "full" or "curated"
        curated_snaps: List of snap names for curated mode
        max_items: Maximum number of snaps to return
    
    Returns:
        Dictionary with snaps, errors, etc.
    """
    result = {
        "available": False,
        "mode": mode,
        "snaps": [],
        "errors": []
    }
    
    snap_cmd = shutil.which("snap")
    if not snap_cmd:
        logger.info("snap not found, skipping snap inventory")
        result["errors"].append("snap not found")
        return result
    
    result["available"] = True
    
    try:
        proc = subprocess.run(
            [snap_cmd, "list"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        
        snaps = []
        lines = proc.stdout.splitlines()
        
        # Skip header line
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts) < 4:
                continue
            
            name = parts[0]
            version = parts[1]
            rev = parts[2]
            tracking = parts[3]
            publisher = parts[4] if len(parts) > 4 else None
            notes = parts[5] if len(parts) > 5 else None
            
            # Filter if curated mode
            if mode == "curated":
                if name not in curated_snaps:
                    continue
            
            snaps.append({
                "name": name,
                "version": version,
                "revision": rev,
                "tracking": tracking,
                "publisher": publisher,
                "notes": notes
            })
            
            if len(snaps) >= max_items:
                logger.warning(f"snap: reached max_items limit ({max_items})")
                result["errors"].append(f"Truncated at {max_items} snaps")
                break
        
        # Sort deterministically
        snaps.sort(key=lambda s: s["name"])
        result["snaps"] = snaps
        
        logger.info(f"snap: collected {len(snaps)} snaps (mode={mode})")
    
    except subprocess.TimeoutExpired:
        logger.error("snap list timed out")
        result["errors"].append("snap list timed out")
    except subprocess.CalledProcessError as e:
        logger.error(f"snap list failed: {e}")
        result["errors"].append(f"snap list failed: {e}")
    except Exception as e:
        logger.error(f"snap collection error: {e}")
        result["errors"].append(f"Unexpected error: {e}")
    
    return result


# ============================================================================
# pip Inventory Collection
# ============================================================================

def collect_pip_inventory(enabled: bool, max_items: int) -> Dict[str, Any]:
    """
    Collect pip package inventory (optional).
    
    Args:
        enabled: Whether pip inventory is enabled
        max_items: Maximum number of packages to return
    
    Returns:
        Dictionary with packages, errors, etc.
    """
    result = {
        "enabled": enabled,
        "available": False,
        "packages": [],
        "errors": []
    }
    
    if not enabled:
        logger.debug("pip inventory disabled")
        return result
    
    try:
        # Try python3 -m pip list --format=json
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        
        result["available"] = True
        
        packages_json = json.loads(proc.stdout)
        packages = []
        
        for item in packages_json:
            packages.append({
                "name": item.get("name", ""),
                "version": item.get("version", "")
            })
            
            if len(packages) >= max_items:
                logger.warning(f"pip: reached max_items limit ({max_items})")
                result["errors"].append(f"Truncated at {max_items} packages")
                break
        
        # Sort deterministically
        packages.sort(key=lambda p: p["name"])
        result["packages"] = packages
        
        logger.info(f"pip: collected {len(packages)} packages")
    
    except subprocess.TimeoutExpired:
        logger.error("pip list timed out")
        result["errors"].append("pip list timed out")
    except subprocess.CalledProcessError as e:
        logger.warning(f"pip list failed: {e}")
        result["errors"].append(f"pip not available or failed: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"pip list JSON parse error: {e}")
        result["errors"].append(f"pip JSON parse error: {e}")
    except Exception as e:
        logger.error(f"pip collection error: {e}")
        result["errors"].append(f"Unexpected error: {e}")
    
    return result


# ============================================================================
# docker Inventory Collection
# ============================================================================

def collect_docker_inventory(
    enabled: bool,
    include_info: bool,
    max_items: int
) -> Dict[str, Any]:
    """
    Collect docker images and containers inventory (optional).
    
    Args:
        enabled: Whether docker inventory is enabled
        include_info: Whether to include docker info
        max_items: Maximum number of items to return
    
    Returns:
        Dictionary with images, containers, errors, etc.
    """
    result = {
        "enabled": enabled,
        "available": False,
        "docker_version": None,
        "images": [],
        "containers": [],
        "errors": []
    }
    
    if not enabled:
        logger.debug("docker inventory disabled")
        return result
    
    docker_cmd = shutil.which("docker")
    if not docker_cmd:
        logger.info("docker not found, skipping docker inventory")
        result["errors"].append("docker not found")
        return result
    
    result["available"] = True
    
    # Get docker version
    try:
        proc = subprocess.run(
            [docker_cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
        result["docker_version"] = proc.stdout.strip()
        logger.debug(f"docker version: {result['docker_version']}")
    except Exception as e:
        logger.warning(f"docker --version failed: {e}")
        result["errors"].append(f"docker --version failed: {e}")
    
    # Get docker images
    try:
        proc = subprocess.run(
            [docker_cmd, "images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        
        images = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            
            images.append({
                "repo": parts[0],
                "tag": parts[1],
                "id": parts[2],
                "created": parts[3],
                "size": parts[4]
            })
            
            if len(images) >= max_items:
                logger.warning(f"docker images: reached max_items limit ({max_items})")
                result["errors"].append(f"Images truncated at {max_items}")
                break
        
        # Sort deterministically
        images.sort(key=lambda i: (i["repo"], i["tag"]))
        result["images"] = images
        
        logger.info(f"docker: collected {len(images)} images")
    
    except subprocess.TimeoutExpired:
        logger.error("docker images timed out")
        result["errors"].append("docker images timed out")
    except subprocess.CalledProcessError as e:
        logger.warning(f"docker images failed: {e}")
        result["errors"].append(f"docker images failed (daemon not running?): {e}")
    except Exception as e:
        logger.error(f"docker images collection error: {e}")
        result["errors"].append(f"docker images error: {e}")
    
    # Get docker containers
    try:
        proc = subprocess.run(
            [docker_cmd, "ps", "-a", "--format", "{{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        
        containers = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            
            containers.append({
                "id": parts[0],
                "image": parts[1],
                "status": parts[2],
                "name": parts[3]
            })
            
            if len(containers) >= max_items:
                logger.warning(f"docker containers: reached max_items limit ({max_items})")
                result["errors"].append(f"Containers truncated at {max_items}")
                break
        
        # Sort deterministically
        containers.sort(key=lambda c: c["name"])
        result["containers"] = containers
        
        logger.info(f"docker: collected {len(containers)} containers")
    
    except subprocess.TimeoutExpired:
        logger.error("docker ps timed out")
        result["errors"].append("docker ps timed out")
    except subprocess.CalledProcessError as e:
        logger.warning(f"docker ps failed: {e}")
        result["errors"].append(f"docker ps failed: {e}")
    except Exception as e:
        logger.error(f"docker ps collection error: {e}")
        result["errors"].append(f"docker ps error: {e}")
    
    return result


# ============================================================================
# Manifest Generation
# ============================================================================

def compute_inventory_hash(items: List[Dict[str, Any]], key_fields: List[str]) -> Optional[str]:
    """
    Compute deterministic SHA256 hash over inventory items.
    
    Args:
        items: List of inventory items
        key_fields: Fields to include in hash (e.g., ["name", "version"])
    
    Returns:
        SHA256 hex digest or None if items empty
    """
    if not items:
        return None
    
    lines = []
    for item in items:
        parts = [str(item.get(field, "")) for field in key_fields]
        lines.append("=".join(parts))
    
    material = "\n".join(lines)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def generate_manifest(
    os_release: Dict[str, str],
    kernel_version: Optional[str],
    dpkg_result: Dict[str, Any],
    snap_result: Dict[str, Any],
    pip_result: Dict[str, Any],
    docker_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate software manifest with counts, hashes, and fingerprint.
    
    Args:
        os_release: OS release info
        kernel_version: Kernel version
        dpkg_result: dpkg inventory result
        snap_result: snap inventory result
        pip_result: pip inventory result
        docker_result: docker inventory result
    
    Returns:
        Manifest dictionary
    """
    counts = {
        "dpkg": len(dpkg_result.get("packages", [])),
        "snaps": len(snap_result.get("snaps", [])),
        "pip": len(pip_result.get("packages", [])),
        "docker_images": len(docker_result.get("images", [])),
        "docker_containers": len(docker_result.get("containers", []))
    }
    
    hashes = {
        "dpkg_sha256": compute_inventory_hash(
            dpkg_result.get("packages", []),
            ["name", "version"]
        ),
        "snaps_sha256": compute_inventory_hash(
            snap_result.get("snaps", []),
            ["name", "version"]
        ),
        "pip_sha256": compute_inventory_hash(
            pip_result.get("packages", []),
            ["name", "version"]
        ) if pip_result.get("enabled") else None,
        "docker_images_sha256": compute_inventory_hash(
            docker_result.get("images", []),
            ["repo", "tag", "id"]
        ) if docker_result.get("enabled") else None
    }
    
    # Compute overall software fingerprint
    fingerprint_material = {
        "os_pretty_name": os_release.get("PRETTY_NAME"),
        "os_version_id": os_release.get("VERSION_ID"),
        "kernel_uname_r": kernel_version,
        "dpkg_sha256": hashes["dpkg_sha256"],
        "snaps_sha256": hashes["snaps_sha256"],
        "pip_sha256": hashes["pip_sha256"],
        "docker_images_sha256": hashes["docker_images_sha256"]
    }
    
    fingerprint_parts = []
    for key in sorted(fingerprint_material.keys()):
        value = fingerprint_material[key]
        if value is not None:
            fingerprint_parts.append(f"{key}={value}")
    
    fingerprint_string = "\n".join(fingerprint_parts)
    software_fingerprint = hashlib.sha256(fingerprint_string.encode("utf-8")).hexdigest()
    
    logger.info(f"Manifest: dpkg={counts['dpkg']}, snaps={counts['snaps']}, "
                f"pip={counts['pip']}, docker_images={counts['docker_images']}, "
                f"fingerprint={software_fingerprint[:16]}...")
    
    return {
        "counts": counts,
        "hashes": hashes,
        "software_fingerprint_sha256": software_fingerprint,
        "fingerprint_material": fingerprint_material
    }


# ============================================================================
# Main Collection Logic
# ============================================================================

def collect_software_inventory(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main collection function - orchestrates all inventory sources.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Complete software inventory dictionary
    """
    logger.info("Starting software inventory collection")
    
    # Platform identity
    platform, asset_id, asset_id_source = collect_platform_identity()
    
    # OS identity
    os_release = parse_os_release()
    kernel_version = get_kernel_version()
    
    # dpkg inventory
    dpkg_result = collect_dpkg_inventory(
        mode=config.get("mode", "full"),
        curated_regex=config.get("curated_dpkg_regex", ""),
        max_items=config.get("max_items", DEFAULT_MAX_ITEMS)
    )
    
    # snap inventory
    snap_result = collect_snap_inventory(
        mode=config.get("mode", "full"),
        curated_snaps=config.get("curated_snaps", []),
        max_items=config.get("max_items", DEFAULT_MAX_ITEMS)
    )
    
    # pip inventory (optional)
    pip_result = collect_pip_inventory(
        enabled=config.get("enable_pip", False),
        max_items=config.get("max_items", DEFAULT_MAX_ITEMS)
    )
    
    # docker inventory (optional)
    docker_result = collect_docker_inventory(
        enabled=config.get("enable_docker", False),
        include_info=config.get("docker_include_info", False),
        max_items=config.get("max_items", DEFAULT_MAX_ITEMS)
    )
    
    # Generate manifest
    manifest = generate_manifest(
        os_release=os_release,
        kernel_version=kernel_version,
        dpkg_result=dpkg_result,
        snap_result=snap_result,
        pip_result=pip_result,
        docker_result=docker_result
    )
    
    # Determine sources
    sources = {
        "dpkg": "dpkg-query" if dpkg_result["available"] else "none",
        "snaps": "snap list" if snap_result["available"] else "none",
        "pip": "python3 -m pip" if pip_result.get("available") else "none",
        "docker": "docker cli" if docker_result.get("available") else "none"
    }
    
    # Assemble final output
    inventory = {
        "collected_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "asset_id": asset_id,
        "asset_id_source": asset_id_source,
        "platform_dmi": platform,
        "os": {
            "os_release": os_release,
            "kernel_uname_r": kernel_version
        },
        "dpkg": dpkg_result,
        "snaps": snap_result,
        "pip": pip_result,
        "docker": docker_result,
        "manifest": manifest,
        "sources": sources
    }
    
    logger.info("Software inventory collection complete")
    
    return inventory


# ============================================================================
# Output Handling
# ============================================================================

def write_json_output(data: Dict[str, Any], output_path: str) -> None:
    """
    Write JSON output atomically.
    
    Args:
        data: Data to write
        output_path: Output file path
    """
    output_file = Path(output_path)
    
    # Ensure directory exists
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    except Exception as e:
        logger.error(f"Could not create output directory: {e}")
        raise
    
    # Write atomically
    temp_file = output_file.parent / f".{output_file.name}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        
        os.replace(temp_file, output_file)
        
        # Set permissions (best-effort)
        try:
            os.chmod(output_file, 0o644)
        except Exception:
            pass
        
        logger.info(f"Output written to {output_path}")
    
    except Exception as e:
        logger.error(f"Failed to write output: {e}")
        if temp_file.exists():
            temp_file.unlink()
        raise


# ============================================================================
# Configuration Loading
# ============================================================================

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from JSON file.
    
    Args:
        config_path: Path to config file (optional)
    
    Returns:
        Configuration dictionary
    """
    default_config = {
        "output_path": DEFAULT_OUTPUT_PATH,
        "mode": "full",
        "enable_pip": False,
        "enable_docker": False,
        "docker_include_info": False,
        "curated_dpkg_regex": r"^(dgx|nvidia|linux-image|linux-headers|snapd|ubuntu-pro-client)\b",
        "curated_snaps": [
            "firmware-updater", "snapd", "core22", "bare",
            "snap-store", "firefox", "thunderbird"
        ],
        "max_items": DEFAULT_MAX_ITEMS
    }
    
    if not config_path:
        # Try default location relative to script
        script_dir = Path(__file__).resolve().parent.parent
        config_path = script_dir / "config" / "default.json"
    
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
                default_config.update(loaded_config)
                logger.debug(f"Loaded config from {config_path}")
        except Exception as e:
            logger.warning(f"Could not load config from {config_path}: {e}")
    
    return default_config


# ============================================================================
# CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Software inventory reporter for DGX Spark management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print inventory to stdout
  %(prog)s --print
  
  # Write to default output (requires sudo for default path)
  sudo %(prog)s
  
  # Enable pip and docker inventories
  sudo %(prog)s --enable-pip --enable-docker
  
  # Curated mode (smaller output)
  %(prog)s --mode curated --print
  
  # Custom output path
  %(prog)s --output /tmp/software_inventory.json
"""
    )
    
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print JSON to stdout only (do not write file)"
    )
    
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Override output file path"
    )
    
    parser.add_argument(
        "--mode",
        choices=["full", "curated"],
        help="Inventory mode (default: full)"
    )
    
    parser.add_argument(
        "--enable-pip",
        action="store_true",
        help="Enable pip package inventory"
    )
    
    parser.add_argument(
        "--enable-docker",
        action="store_true",
        help="Enable docker images/containers inventory"
    )
    
    parser.add_argument(
        "--docker-include-info",
        action="store_true",
        help="Include docker info (verbose)"
    )
    
    parser.add_argument(
        "--max-items",
        type=int,
        metavar="N",
        help="Maximum items per inventory (default: 50000)"
    )
    
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to config JSON file"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    add_standard_output_flags(parser)

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 = success, non-zero = error)
    """
    args = parse_args()
    set_quiet(args.quiet)

    setup_logging(verbose=args.verbose)

    logger.info("Software Inventory Reporter starting")

    try:
        # Load config
        config = load_config(args.config)

        # Apply CLI overrides
        if args.output:
            config["output_path"] = args.output
        if args.mode:
            config["mode"] = args.mode
        if args.enable_pip:
            config["enable_pip"] = True
        if args.enable_docker:
            config["enable_docker"] = True
        if args.docker_include_info:
            config["docker_include_info"] = True
        if args.max_items:
            config["max_items"] = args.max_items

        # Collect inventory
        inventory = collect_software_inventory(config)

        route_output(
            inventory, args, _TOOL, _VERSION, config["output_path"],
            lambda data, path: write_json_output(data, path),
        )

        logger.info("Software Inventory Reporter completed successfully")
        return 0

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return emit_error(
            [make_error(EC_INTERRUPTED, "Interrupted by user", severity="warning")],
            _TOOL, _VERSION, rc=EXIT_INTERRUPTED,
        )
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return emit_error(
            [make_error(EC_GENERAL, str(e), detail=type(e).__name__,
                        hint="Check logs for details")],
            _TOOL, _VERSION, rc=EXIT_GENERAL_ERROR,
        )


if __name__ == "__main__":
    sys.exit(main())
