# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Common utilities for DGX Spark Management tools.

Provides shared CLI infrastructure for consistent interfaces and output
formatting across all production tools.
"""

from .cli_base import (
    # Envelope format
    format_envelope,

    # Argument parsing
    create_base_parser,
    create_subparser_tool_parser,

    # Utilities
    setup_logging,
    load_config,
    write_output,

    # Exit codes
    ExitCode,
)

__all__ = [
    "format_envelope",
    "create_base_parser",
    "create_subparser_tool_parser",
    "setup_logging",
    "load_config",
    "write_output",
    "ExitCode",
]

__version__ = "1.1.0"
