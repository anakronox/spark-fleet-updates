#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Shared output helpers for DGX Spark Management tools.

Contract: stdout is always bounded JSON matching the repo schema:
  { "ok": bool, "data": {...}|null, "errors": [...], "meta": {...} }

stderr is reserved for human diagnostics only (log()).

Exit code contract:
  - main() returns 0 on success (ok: true)
  - main() returns non-zero on failure (ok: false)
  - emit_error() returns the exit code; callers must `return emit_error(...)`
  - sys.exit(main()) at module level propagates the code
"""

import argparse
import datetime
import json
import sys
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Integer exit codes
# ---------------------------------------------------------------------------

EXIT_SUCCESS          = 0
EXIT_GENERAL_ERROR    = 1
EXIT_INVALID_ARGS     = 2
EXIT_PERMISSION_DENIED = 3
EXIT_NOT_FOUND        = 4
EXIT_TIMEOUT          = 5
EXIT_INTERRUPTED      = 130


# ---------------------------------------------------------------------------
# Error / warning code strings  (go in errors[].code)
# ---------------------------------------------------------------------------

EC_GENERAL      = "E_GENERAL"
EC_INTERRUPTED  = "E_INTERRUPTED"
EC_PERMISSION   = "E_PERMISSION"
EC_NOT_FOUND    = "E_NOT_FOUND"
EC_INVALID_ARGS = "E_INVALID_ARGS"
EC_TIMEOUT      = "E_TIMEOUT"

WC_NO_ASSET_ID  = "W_NO_ASSET_ID"
WC_PARTIAL_DATA = "W_PARTIAL_DATA"


# ---------------------------------------------------------------------------
# Quiet mode (suppresses log() diagnostic messages on stderr)
# ---------------------------------------------------------------------------

_quiet: bool = False


def set_quiet(quiet: bool) -> None:
    """Enable/disable quiet mode. When True, log() calls are no-ops."""
    global _quiet
    _quiet = quiet


# ---------------------------------------------------------------------------
# Error object constructors
# ---------------------------------------------------------------------------

def make_error(
    code: str,
    message: str,
    detail: str = "",
    hint: str = "",
    severity: str = "error",
) -> Dict[str, str]:
    """Build a structured error object for the errors[] array.

    Args:
        code:     machine-readable code, e.g. EC_GENERAL or WC_NO_ASSET_ID
        message:  human-readable summary
        detail:   technical detail (exception type, field name, etc.)
        hint:     actionable suggestion for the operator
        severity: "error" (fatal, ok:false) or "warning" (non-fatal, ok:true)
    """
    return {
        "code": code,
        "message": message,
        "detail": detail,
        "hint": hint,
        "severity": severity,
    }


def _normalize_errors(errors: Optional[List]) -> List[Dict]:
    """Normalize a mixed List[str | dict] to a List[structured error dict].

    Plain strings are wrapped with code=EC_GENERAL, severity="error".
    Existing dicts are passed through with missing fields defaulted.
    """
    if not errors:
        return []
    result = []
    for e in errors:
        if isinstance(e, str):
            result.append(make_error(EC_GENERAL, e))
        elif isinstance(e, dict):
            result.append({
                "code":     e.get("code", EC_GENERAL),
                "message":  e.get("message", str(e)),
                "detail":   e.get("detail", ""),
                "hint":     e.get("hint", ""),
                "severity": e.get("severity", "error"),
            })
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_meta(tool: str, version: str) -> Dict[str, Any]:
    return {
        "tool": tool,
        "version": version,
        "collected_at_utc": _now_utc(),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def emit_ok(
    data: Dict[str, Any],
    tool: str,
    version: str,
    artifacts: Optional[List[str]] = None,
    truncation: Optional[Dict[str, Any]] = None,
    errors: Optional[List] = None,
) -> None:
    """Serialize data as a success envelope and print to stdout.

    errors[] is for non-fatal warnings (severity="warning").  Plain strings
    are auto-normalized to structured objects.
    """
    meta = _build_meta(tool, version)
    if artifacts is not None:
        meta["artifacts"] = artifacts
    if truncation is not None:
        meta["truncation"] = truncation
    envelope = {
        "ok": True,
        "data": data,
        "errors": _normalize_errors(errors),
        "meta": meta,
    }
    print(json.dumps(envelope, indent=2, ensure_ascii=False))


def emit_error(
    errors: List,
    tool: str,
    version: str,
    rc: int = EXIT_GENERAL_ERROR,
) -> int:
    """Serialize errors as a failure envelope, print to stdout, and return rc.

    Callers MUST propagate the return value::

        return emit_error([make_error(EC_GENERAL, str(e))], _TOOL, _VERSION)

    This keeps main() testable and exit code semantics clear:
    sys.exit(main()) at module level will receive the correct non-zero code.

    errors[] items may be plain strings (auto-normalized) or make_error() dicts.
    """
    meta = _build_meta(tool, version)
    envelope = {
        "ok": False,
        "data": None,
        "errors": _normalize_errors(errors),
        "meta": meta,
    }
    print(json.dumps(envelope, indent=2, ensure_ascii=False))
    return rc


def log(msg: str) -> None:
    """Write a diagnostic message to stderr (suppressed in quiet mode)."""
    if not _quiet:
        print(msg, file=sys.stderr)


def route_output(
    data: Dict[str, Any],
    args: Any,
    tool: str,
    version: str,
    default_path: str,
    write_fn: Callable[[Dict[str, Any], str], None],
    errors: Optional[List] = None,
    truncation: Optional[Dict[str, Any]] = None,
) -> None:
    """Route collected data to stdout and/or file based on CLI flags.

    Honors:
      --stdout-json   print JSON envelope to stdout
      --print         legacy alias for --stdout-json (also suppresses file write)
      --write-file    write JSON to file (default: True)
      --no-write-file disable file write
      --out PATH      override output path (falls back to --output, then default_path)
      --quiet         suppress diagnostic stderr messages

    Args:
        data:         collected payload (the value of "data" in the envelope)
        args:         parsed argparse.Namespace
        tool:         tool name for meta
        version:      tool version for meta
        default_path: fallback output file path
        write_fn:     callable(data, path) that persists data to a file
        errors:       non-fatal warning objects/strings to include in envelope
        truncation:   optional truncation stats for meta
    """
    if errors is None:
        errors = []

    legacy_print = getattr(args, 'print', False)
    stdout_json = getattr(args, 'stdout_json', False) or legacy_print
    # --print suppresses file write for backward compatibility
    write_file = getattr(args, 'write_file', True) and not legacy_print
    out_path = (
        getattr(args, 'out', None)
        or getattr(args, 'output', None)
        or default_path
    )

    if stdout_json:
        emit_ok(data, tool, version, truncation=truncation, errors=errors)

    if write_file and out_path:
        write_fn(data, str(out_path))
        log(f"Output: {out_path}")


def add_standard_output_flags(parser: argparse.ArgumentParser) -> None:
    """Add the four standard output-control flags to any argparse parser.

    Flags added:
      --stdout-json     print JSON envelope to stdout (default: off during transition)
      --write-file      write JSON to output file (default: on)
      --no-write-file   disable file write
      --out PATH        override output file path
      --quiet           suppress diagnostic stderr messages (warnings still shown)
    """
    parser.add_argument(
        '--stdout-json', dest='stdout_json', action='store_true', default=False,
        help='Print JSON envelope to stdout (default: off; becomes default on after alignment)'
    )
    parser.add_argument(
        '--write-file', dest='write_file', action='store_true',
        help='Write JSON to output file (default: on)'
    )
    parser.add_argument(
        '--no-write-file', dest='write_file', action='store_false',
        help='Do not write JSON to file'
    )
    parser.set_defaults(write_file=True)
    parser.add_argument(
        '--out', metavar='PATH',
        help='Override output file path (alias for --output)'
    )
    parser.add_argument(
        '--quiet', action='store_true', default=False,
        help='Suppress diagnostic stderr messages (warnings still shown)'
    )
