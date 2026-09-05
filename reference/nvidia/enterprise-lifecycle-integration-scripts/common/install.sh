#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
################################################################################
# Installation Script for Common Module
#
# This script installs the common module to the project bin/ directory
# so that installed tools can import shared utilities.
################################################################################

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly PROJECT_BIN="${PROJECT_ROOT}/bin"
readonly COMMON_TARGET="${PROJECT_BIN}/common"

echo "Installing common module to bin/common/..."

# Create bin/common/ directory
mkdir -p "$COMMON_TARGET"

# Copy Python files
cp "${SCRIPT_DIR}/cli_base.py"  "$COMMON_TARGET/"
cp "${SCRIPT_DIR}/output.py"    "$COMMON_TARGET/"
cp "${SCRIPT_DIR}/asset_id.py"  "$COMMON_TARGET/"
cp "${SCRIPT_DIR}/__init__.py"  "$COMMON_TARGET/"

# Libraries are not executable: rw-r--r-- (0644)
chmod 0644 \
    "$COMMON_TARGET/cli_base.py" \
    "$COMMON_TARGET/output.py" \
    "$COMMON_TARGET/asset_id.py" \
    "$COMMON_TARGET/__init__.py"

echo "✓ Common module installed to: $COMMON_TARGET"
