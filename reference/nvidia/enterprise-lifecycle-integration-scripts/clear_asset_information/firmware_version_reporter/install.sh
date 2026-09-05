#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Installation script for firmware_reporter.py
#
# Usage:
#   bash install.sh [--system]
#
# Options:
#   --system    Also install to /usr/local/bin (requires sudo)
#
# This script:
# 1. Copies firmware_reporter.py to ../../bin/
# 2. Makes it executable
# 3. Optionally installs to /usr/local/bin for system-wide access
# 4. Creates output directory structure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_FILE="${SCRIPT_DIR}/src/firmware_reporter.py"
BIN_DIR="${SCRIPT_DIR}/../../bin"
OUTPUT_DIR="/var/lib/dgx_spark_management/clear_asset_information/firmware_version_reporter"
LOG_DIR="/var/log/dgx_spark/clear_asset_information/firmware_version_reporter"

INSTALL_SYSTEM=false
if [[ "${1:-}" == "--system" ]]; then
    INSTALL_SYSTEM=true
fi

echo "=== Firmware Version Reporter - Installation ==="
echo ""

# Check source file exists
if [[ ! -f "${SRC_FILE}" ]]; then
    echo "ERROR: Source file not found: ${SRC_FILE}"
    exit 1
fi

# Install to repo bin/
echo "[1/5] Installing to repository bin/ directory..."
mkdir -p "${BIN_DIR}"
cp "${SRC_FILE}" "${BIN_DIR}/firmware_reporter.py"
chmod 0755 "${BIN_DIR}/firmware_reporter.py"
echo "  ✓ Installed: ${BIN_DIR}/firmware_reporter.py"

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
    cp "${SRC_FILE}" /usr/local/bin/firmware_reporter.py
    chmod 755 /usr/local/bin/firmware_reporter.py
    echo "  ✓ Installed: /usr/local/bin/firmware_reporter.py"
else
    echo "[4/5] Skipping system installation (use --system to enable)"
fi

# Verify installation
echo ""
echo "[5/5] Verifying installation..."
"${BIN_DIR}/firmware_reporter.py" --help > /dev/null 2>&1 && {
    echo "  ✓ Script is executable and functional"
}

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Usage examples:"
echo "  # Print firmware inventory to stdout"
echo "  python3 ${BIN_DIR}/firmware_reporter.py --print"
echo ""
echo "  # Write to default location (requires sudo)"
echo "  sudo python3 ${BIN_DIR}/firmware_reporter.py"
echo ""
echo "  # Custom output path"
echo "  python3 ${BIN_DIR}/firmware_reporter.py --output /tmp/firmware.json"
echo ""
echo "  # Disable fwupd collection"
echo "  python3 ${BIN_DIR}/firmware_reporter.py --no_fwupd"
echo ""
echo "  # Verbose logging"
echo "  sudo python3 ${BIN_DIR}/firmware_reporter.py --verbose"
echo ""

if [[ "${INSTALL_SYSTEM}" == "true" ]]; then
    echo "System-wide installation:"
    echo "  firmware_reporter.py --print"
    echo ""
fi

echo "Configuration file:"
echo "  ${SCRIPT_DIR}/config/default.json"
echo ""
echo "Runtime output:"
echo "  ${OUTPUT_DIR}/firmware_versions.json"
echo ""
echo "Runtime logs:"
echo "  ${LOG_DIR}/firmware_reporter.log"
echo ""
echo "Documentation:"
echo "  ${SCRIPT_DIR}/README.md"
echo ""
