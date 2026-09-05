#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Installation script for driver_inventory_reporter.py
#
# Usage:
#   bash install.sh [--system]
#
# Options:
#   --system    Also install to /usr/local/bin (requires sudo)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_FILE="${SCRIPT_DIR}/src/driver_inventory_reporter.py"
BIN_DIR="${SCRIPT_DIR}/../../bin"
OUTPUT_DIR="/var/lib/dgx_spark_management/clear_asset_information/driver_inventory_reporter"
LOG_DIR="/var/log/dgx_spark/clear_asset_information/driver_inventory_reporter"

INSTALL_SYSTEM=false
if [[ "${1:-}" == "--system" ]]; then
    INSTALL_SYSTEM=true
fi

echo "=== Driver Inventory Reporter - Installation ==="
echo ""

# Check source file exists
if [[ ! -f "${SRC_FILE}" ]]; then
    echo "ERROR: Source file not found: ${SRC_FILE}"
    exit 1
fi

# Install to repo bin/
echo "[1/5] Installing to repository bin/ directory..."
mkdir -p "${BIN_DIR}"
cp "${SRC_FILE}" "${BIN_DIR}/driver_inventory_reporter.py"
chmod 0755 "${BIN_DIR}/driver_inventory_reporter.py"
echo "  ✓ Installed: ${BIN_DIR}/driver_inventory_reporter.py"

# Create output directory
echo ""
echo "[2/5] Creating output directory..."
if [[ -w "$(dirname "${OUTPUT_DIR}" 2>/dev/null || echo /tmp)" ]] || [[ "${EUID}" -eq 0 ]]; then
    mkdir -p "${OUTPUT_DIR}"
    chmod 755 "${OUTPUT_DIR}"
    echo "  ✓ Created: ${OUTPUT_DIR}"
else
    echo "  ⚠ Cannot create ${OUTPUT_DIR} (need sudo)"
fi

# Create log directory
echo ""
echo "[3/5] Creating log directory..."
if [[ -w "$(dirname "$(dirname "${LOG_DIR}")" 2>/dev/null || echo /tmp)" ]] || [[ "${EUID}" -eq 0 ]]; then
    mkdir -p "${LOG_DIR}"
    chmod 755 "${LOG_DIR}"
    echo "  ✓ Created: ${LOG_DIR}"
else
    echo "  ⚠ Cannot create ${LOG_DIR} (need sudo)"
fi

# Install to system (optional)
echo ""
if [[ "${INSTALL_SYSTEM}" == "true" ]]; then
    echo "[4/5] Installing to /usr/local/bin..."
    if [[ "${EUID}" -ne 0 ]]; then
        echo "  ERROR: --system requires sudo"
        exit 1
    fi
    cp "${SRC_FILE}" /usr/local/bin/driver_inventory_reporter.py
    chmod 755 /usr/local/bin/driver_inventory_reporter.py
    echo "  ✓ Installed: /usr/local/bin/driver_inventory_reporter.py"
else
    echo "[4/5] Skipping system installation (use --system to enable)"
fi

# Verify installation
echo ""
echo "[5/5] Verifying installation..."
"${BIN_DIR}/driver_inventory_reporter.py" --help > /dev/null 2>&1 && {
    echo "  ✓ Script is executable and functional"
}

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Usage examples:"
echo "  # Print driver inventory to stdout"
echo "  python3 ${BIN_DIR}/driver_inventory_reporter.py --print"
echo ""
echo "  # Write to default location (requires sudo)"
echo "  sudo python3 ${BIN_DIR}/driver_inventory_reporter.py"
echo ""
echo "  # Skip USB collection"
echo "  python3 ${BIN_DIR}/driver_inventory_reporter.py --no_usb --print"
echo ""
echo "  # Skip modinfo enrichment (faster)"
echo "  python3 ${BIN_DIR}/driver_inventory_reporter.py --no_modinfo --print"
echo ""

if [[ "${INSTALL_SYSTEM}" == "true" ]]; then
    echo "System-wide installation:"
    echo "  driver_inventory_reporter.py --print"
    echo ""
fi

echo "Configuration file:"
echo "  ${SCRIPT_DIR}/config/default.json"
echo ""
echo "Runtime output:"
echo "  ${OUTPUT_DIR}/driver_inventory.json"
echo ""
echo "Runtime logs:"
echo "  ${LOG_DIR}/driver_inventory.log"
echo ""
echo "Documentation:"
echo "  ${SCRIPT_DIR}/README.md"
echo ""
