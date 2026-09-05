#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
CLI Base Infrastructure for DGX Spark Management Tools

Provides shared utilities for consistent CLI interfaces and output formatting
across all production tools.

Features:
- Standard JSON envelope format: {ok, data, errors, meta}
- Argument parser factory with consistent flags
- Logging setup with file and stderr handlers
- Configuration loading from JSON files
- Atomic output writing
- Standard exit codes

Author: DGX Spark Management Team
Version: 1.1.0
"""

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import add_standard_output_flags so create_base_parser can wire it in
from output import add_standard_output_flags

__version__ = "1.1.0"


# ============================================================================
# Exit Code Constants
# ============================================================================

class ExitCode:
    """Standard exit codes for all tools."""
    SUCCESS = 0                # Successful execution
    GENERAL_ERROR = 1          # General error (default)
    INVALID_ARGS = 2           # Invalid arguments
    PERMISSION_DENIED = 3      # Insufficient permissions (needs root)
    NOT_FOUND = 4              # Resource not found
    TIMEOUT = 5                # Operation timed out
    INTERRUPTED = 130          # KeyboardInterrupt (Ctrl+C)


# ============================================================================
# Envelope Format
# ============================================================================

def format_envelope(
    ok: bool,
    data: Any,
    errors: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create standard JSON output envelope.

    All tools must output this standard envelope format for consistency
    in automation, error handling, and Landscape integration.

    Args:
        ok: Success flag (True = success, False = failure)
        data: Payload data (tool-specific content, may be None on failure)
        errors: List of error/warning messages (defaults to empty list)
        meta: Metadata dict (auto-populated if not provided)

    Returns:
        Standard envelope dictionary with keys: ok, data, errors, meta

    Example:
        >>> envelope = format_envelope(
        ...     ok=True,
        ...     data={"asset_id": "ABC123"},
        ...     errors=[],
        ...     meta={"tool": "device_identity", "version": "1.1.0"}
        ... )
        >>> envelope["ok"]
        True
        >>> envelope["data"]["asset_id"]
        'ABC123'
    """
    if errors is None:
        errors = []

    if meta is None:
        meta = {}

    # Auto-populate timestamp if not provided
    if "collected_at_utc" not in meta:
        meta["collected_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')

    return {
        "ok": ok,
        "data": data,
        "errors": errors,
        "meta": meta
    }


# ============================================================================
# Argument Parser Factory
# ============================================================================

def create_base_parser(
    tool_name: str,
    description: str,
    version: str,
    add_version: bool = True,
    add_human: bool = True,
    add_json: bool = False,     # Explicit --json flag (rarely needed)
    add_print: bool = False,    # Backward compat for tools 1-6
    add_output: bool = True,
    add_config: bool = True,
    add_log: bool = True,
    add_verbose: bool = True,
    formatter_class: type = argparse.RawDescriptionHelpFormatter,
    epilog: Optional[str] = None
) -> argparse.ArgumentParser:
    """
    Create base argument parser with standard flags.

    Provides consistent CLI interface across all tools with flags for:
    - Version display
    - Output format (JSON vs human-readable)
    - Output destination (file path)
    - Config file override
    - Log file override
    - Verbose logging

    Args:
        tool_name: Tool name (used in --version output)
        description: Parser description
        version: Tool version string
        add_version: Include --version flag
        add_human: Include --human flag for readable output
        add_json: Include explicit --json flag (default is already JSON)
        add_print: Include --print flag for backward compat (tools 1-6)
        add_output: Include --output flag for file path
        add_config: Include --config flag for config file override
        add_log: Include --log flag for log file override
        add_verbose: Include --verbose flag for debug logging
        formatter_class: Argparse formatter class
        epilog: Epilog text for help message

    Returns:
        Configured argparse.ArgumentParser instance

    Example:
        >>> parser = create_base_parser(
        ...     tool_name="device_identity",
        ...     description="Collect device identity from DMI",
        ...     version="1.1.0"
        ... )
        >>> args = parser.parse_args(["--verbose", "--output", "/tmp/out.json"])
        >>> args.verbose
        True
    """
    parser = argparse.ArgumentParser(
        prog=tool_name,
        description=description,
        formatter_class=formatter_class,
        epilog=epilog
    )

    if add_version:
        parser.add_argument(
            '--version',
            action='version',
            version=f'{tool_name} {version}'
        )

    if add_human:
        parser.add_argument(
            '--human',
            action='store_true',
            help='Output human-readable format instead of JSON'
        )

    if add_json:
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output JSON format (default)'
        )

    if add_print:
        parser.add_argument(
            '--print',
            action='store_true',
            help='Print to stdout only (do not write file)'
        )

    if add_output:
        parser.add_argument(
            '--output',
            metavar='PATH',
            type=str,
            help='Write output to specified file path'
        )

    if add_config:
        parser.add_argument(
            '--config',
            metavar='PATH',
            type=str,
            help='Path to config JSON file (overrides default)'
        )

    if add_log:
        parser.add_argument(
            '--log',
            metavar='PATH',
            type=str,
            help='Override log file path'
        )

    if add_verbose:
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose (DEBUG) logging'
        )

    # Add standard output-control flags to every parser
    add_standard_output_flags(parser)

    return parser


def create_subparser_tool_parser(
    tool_name: str,
    description: str,
    version: str,
    **kwargs
) -> Tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """
    Create base parser with subcommand support.

    Used for tools with multiple commands (e.g., spark_updatectl, spark_diagctl).

    Args:
        tool_name: Tool name
        description: Parser description
        version: Tool version
        **kwargs: Additional arguments passed to create_base_parser()

    Returns:
        Tuple of (parser, subparsers) where subparsers can be used to add commands

    Example:
        >>> parser, subparsers = create_subparser_tool_parser(
        ...     "spark_updatectl",
        ...     "Update control tool",
        ...     "1.1.0"
        ... )
        >>> status_parser = subparsers.add_parser("status", help="Show status")
    """
    # Set defaults for subparser tools
    kwargs.setdefault('add_human', True)
    kwargs.setdefault('add_print', False)

    parser = create_base_parser(
        tool_name=tool_name,
        description=description,
        version=version,
        **kwargs
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="Command to execute"
    )

    return parser, subparsers


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(
    log_path: Optional[str],
    verbose: bool = False,
    tool_name: str = "tool"
) -> logging.Logger:
    """
    Setup logging with file handler and stderr handler.

    Configures logging to write to:
    - Log file (if path provided and writable)
    - stderr (for warnings and errors, always)

    Args:
        log_path: Path to log file (None to skip file logging)
        verbose: Enable DEBUG level logging (False = INFO level)
        tool_name: Tool name for logger instance

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logging("/var/log/tool.log", verbose=True, tool_name="my_tool")
        >>> logger.info("Tool started")
        >>> logger.debug("Detailed debug info")  # Only shown if verbose=True
    """
    logger = logging.getLogger(tool_name)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()  # Remove any existing handlers

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Try to setup file handler
    if log_path:
        try:
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
            logger.addHandler(file_handler)
        except (PermissionError, OSError) as e:
            # Fall back to stderr only
            sys.stderr.write(f"Warning: Could not setup log file {log_path}: {e}\n")

    # Always add stderr handler for warnings and errors
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    return logger


# ============================================================================
# Configuration Loading
# ============================================================================

def load_config(
    config_path: Optional[str],
    default_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Load configuration from JSON file with defaults.

    Merges user config with default config. If config file doesn't exist
    or is invalid, returns default config.

    Args:
        config_path: Path to config JSON file (None to use defaults only)
        default_config: Default configuration dictionary

    Returns:
        Merged configuration dictionary

    Example:
        >>> default = {"timeout": 60, "retries": 3}
        >>> config = load_config("/etc/tool/config.json", default)
        >>> config["timeout"]  # From file or default
        60
    """
    config = default_config.copy()

    if config_path:
        config_file = Path(config_path)

        if not config_file.exists():
            sys.stderr.write(f"Warning: Config file not found: {config_path}\n")
            return config

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)

            # Deep merge: update nested dicts
            for key, value in loaded_config.items():
                if isinstance(value, dict) and key in config and isinstance(config[key], dict):
                    config[key].update(value)
                else:
                    config[key] = value

        except json.JSONDecodeError as e:
            sys.stderr.write(f"Warning: Invalid JSON in config file {config_path}: {e}\n")
        except (OSError, IOError) as e:
            sys.stderr.write(f"Warning: Could not read config file {config_path}: {e}\n")

    return config


# ============================================================================
# Output Writing
# ============================================================================

def write_output(
    envelope: Dict[str, Any],
    output_path: str,
    human_format: bool = False,
    human_formatter: Optional[Callable[[Dict], str]] = None
) -> None:
    """
    Write output to file (JSON or human-readable).

    Writes output atomically using temporary file + rename to ensure
    file is never partially written.

    Args:
        envelope: Output envelope dict
        output_path: Path to output file
        human_format: Format as human-readable text (requires human_formatter)
        human_formatter: Optional function to format envelope as human text

    Raises:
        OSError: If cannot write file
        TypeError: If human_format=True but human_formatter not provided

    Example:
        >>> envelope = format_envelope(True, {"test": "data"}, [])
        >>> write_output(envelope, "/tmp/output.json")
        >>> # File now contains JSON envelope
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Format output
    if human_format:
        if human_formatter is None:
            raise TypeError("human_formatter required when human_format=True")
        output = human_formatter(envelope)
    else:
        output = json.dumps(envelope, indent=2, ensure_ascii=False)

    # Ensure output ends with newline
    if not output.endswith('\n'):
        output += '\n'

    # Atomic write using temporary file
    temp_file = output_file.parent / f".{output_file.name}.tmp"

    try:
        temp_file.write_text(output, encoding="utf-8")
        temp_file.replace(output_file)  # Atomic on POSIX systems

        # Best-effort chmod
        try:
            output_file.chmod(0o644)
        except (OSError, PermissionError):
            pass  # Ignore chmod failures

    finally:
        # Clean up temp file if it still exists
        if temp_file.exists():
            try:
                temp_file.unlink()
            except (OSError, FileNotFoundError):
                pass


# ============================================================================
# Main Entry Point (for testing)
# ============================================================================

if __name__ == "__main__":
    # Simple test of envelope format
    envelope = format_envelope(
        ok=True,
        data={"test": "data", "value": 42},
        errors=[],
        meta={"tool": "cli_base_test", "version": __version__}
    )

    print(json.dumps(envelope, indent=2))

    # Test parser creation
    parser = create_base_parser(
        tool_name="test_tool",
        description="Test tool for CLI base",
        version="1.0.0"
    )

    args = parser.parse_args(["--verbose", "--help"] if len(sys.argv) == 1 else sys.argv[1:])
    print(f"\nParsed args: {args}")
