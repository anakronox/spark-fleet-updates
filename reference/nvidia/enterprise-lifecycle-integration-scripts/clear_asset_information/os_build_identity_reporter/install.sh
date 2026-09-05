#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Installation script for os_build_identity.py
#
# Usage:
#   bash install.sh [--system]
#
# Options:
#   --system    Also install to /usr/local/bin (requires sudo)
#
# This script:
# 1. Copies os_build_identity.py to ../../bin/
# 2. Makes it executable
# 3. Optionally installs to /usr/local/bin for system-wide access
# 4. Creates output directory structure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_FILE="${SCRIPT_DIR}/src/os_build_identity.py"
BIN_DIR="${SCRIPT_DIR}/../../bin"
OUTPUT_DIR="/var/lib/dgx_spark_management/clear_asset_information/os_build_identity_reporter"
LOG_DIR="/var/log/dgx_spark/clear_asset_information/os_build_identity_reporter"

INSTALL_SYSTEM=false
if [[ "${1:-}" == "--system" ]]; then
    INSTALL_SYSTEM=true
fi

echo "=== OS Build Identity Reporter - Installation ==="
echo ""

# Check source file exists
if [[ ! -f "${SRC_FILE}" ]]; then
    echo "ERROR: Source file not found: ${SRC_FILE}"
    exit 1
fi

# Install to repo bin/
echo "[1/5] Installing to repository bin/ directory..."
mkdir -p "${BIN_DIR}"
cp "${SRC_FILE}" "${BIN_DIR}/os_build_identity.py"
chmod 0755 "${BIN_DIR}/os_build_identity.py"
echo "  ✓ Installed: ${BIN_DIR}/os_build_identity.py"

# Create output directory (if we have permissions)
echo ""
echo "[2/5] Creating output directory..."
if [[ -w "$(dirname "${OUTPUT_DIR}" 2>/dev/null || echo /tmp)" ]] || [[ "${EUID}" -eq 0 ]]; then
    mkdir -p "${OUTPUT_DIR}"
    chmod 755 "${OUTPUT_DIR}"
    echo "  ✓ Created: ${OUTPUT_DIR}"
else
    echo "  ⚠ Cannot create ${OUTPUT_DIR} (need sudo)"
    echo "    You can create it later with:"
    echo "      sudo mkdir -p ${OUTPUT_DIR}"
    echo "      sudo chmod 755 ${OUTPUT_DIR}"
fi

# Create log directory (if we have permissions)
echo ""
echo "[3/5] Creating log directory..."
if [[ -w "$(dirname "$(dirname "${LOG_DIR}")" 2>/dev/null || echo /tmp)" ]] || [[ "${EUID}" -eq 0 ]]; then
    mkdir -p "${LOG_DIR}"
    chmod 755 "${LOG_DIR}"
    echo "  ✓ Created: ${LOG_DIR}"
else
    echo "  ⚠ Cannot create ${LOG_DIR} (need sudo)"
    echo "    You can create it later with:"
    echo "      sudo mkdir -p ${LOG_DIR}"
    echo "      sudo chmod 755 ${LOG_DIR}"
fi

# Install to system (optional)
echo ""
if [[ "${INSTALL_SYSTEM}" == "true" ]]; then
    echo "[4/5] Installing to /usr/local/bin..."
    if [[ "${EUID}" -ne 0 ]]; then
        echo "  ERROR: --system requires sudo"
        exit 1
    fi
    cp "${SRC_FILE}" /usr/local/bin/os_build_identity.py
    chmod 755 /usr/local/bin/os_build_identity.py
    echo "  ✓ Installed: /usr/local/bin/os_build_identity.py"
else
    echo "[4/5] Skipping system installation (use --system to enable)"
fi

# Verify installation
echo ""
echo "[5/5] Verifying installation..."
"${BIN_DIR}/os_build_identity.py" --help > /dev/null 2>&1 && {
    echo "  ✓ Script is executable and functional"
}

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Usage examples:"
echo "  # Print OS build identity to stdout"
echo "  python3 ${BIN_DIR}/os_build_identity.py --print"
echo ""
echo "  # Write to default location (requires sudo)"
echo "  sudo python3 ${BIN_DIR}/os_build_identity.py"
echo ""
echo "  # Include all packages (large output)"
echo "  python3 ${BIN_DIR}/os_build_identity.py --all-packages --print"
echo ""
echo "  # Verbose logging"
echo "  sudo python3 ${BIN_DIR}/os_build_identity.py --verbose"
echo ""

if [[ "${INSTALL_SYSTEM}" == "true" ]]; then
    echo "System-wide installation:"
    echo "  os_build_identity.py --print"
    echo ""
fi

echo "Configuration file:"
echo "  ${SCRIPT_DIR}/config/default.json"
echo ""
echo "Runtime output:"
echo "  ${OUTPUT_DIR}/os_build_identity.json"
echo ""
echo "Runtime logs:"
echo "  ${LOG_DIR}/os_build_identity.log"
echo ""
echo "Documentation:"
echo "  ${SCRIPT_DIR}/README.md"
echo ""
