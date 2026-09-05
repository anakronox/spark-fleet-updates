#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Installation script for hardware_config.py
#
# Usage:
#   bash install_hardware_config.sh [--system]
#
# Options:
#   --system    Also install to /usr/local/bin (requires sudo)
#
# This script:
# 1. Copies hardware_config.py to ../../bin/
# 2. Makes it executable
# 3. Optionally installs to /usr/local/bin for system-wide access
# 4. Creates output directory structure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_FILE="${SCRIPT_DIR}/src/hardware_config.py"
BIN_DIR="${SCRIPT_DIR}/../../bin"
OUTPUT_DIR="/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector"

INSTALL_SYSTEM=false
if [[ "${1:-}" == "--system" ]]; then
    INSTALL_SYSTEM=true
fi

echo "=== Hardware Config Collector - Installation ==="
echo ""

# Check source file exists
if [[ ! -f "${SRC_FILE}" ]]; then
    echo "ERROR: Source file not found: ${SRC_FILE}"
    exit 1
fi

# Install to repo bin/
echo "[1/4] Installing to repository bin/ directory..."
mkdir -p "${BIN_DIR}"
cp "${SRC_FILE}" "${BIN_DIR}/hardware_config.py"
chmod +x "${BIN_DIR}/hardware_config.py"
echo "  ✓ Installed: ${BIN_DIR}/hardware_config.py"

# Create output directory (if we have permissions)
echo ""
echo "[2/4] Creating output directory..."
if [[ -w "$(dirname "${OUTPUT_DIR}")" ]] || [[ "${EUID}" -eq 0 ]]; then
    mkdir -p "${OUTPUT_DIR}"
    chmod 755 "${OUTPUT_DIR}"
    echo "  ✓ Created: ${OUTPUT_DIR}"
else
    echo "  ⚠ Cannot create ${OUTPUT_DIR} (need sudo)"
    echo "    You can create it later with:"
    echo "      sudo mkdir -p ${OUTPUT_DIR}"
    echo "      sudo chmod 755 ${OUTPUT_DIR}"
fi

# Install to system (optional)
echo ""
if [[ "${INSTALL_SYSTEM}" == "true" ]]; then
    echo "[3/4] Installing to /usr/local/bin..."
    if [[ "${EUID}" -ne 0 ]]; then
        echo "  ERROR: --system requires sudo"
        exit 1
    fi
    cp "${SRC_FILE}" /usr/local/bin/hardware_config.py
    chmod 755 /usr/local/bin/hardware_config.py
    echo "  ✓ Installed: /usr/local/bin/hardware_config.py"
else
    echo "[3/4] Skipping system installation (use --system to enable)"
fi

# Verify installation
echo ""
echo "[4/4] Verifying installation..."
"${BIN_DIR}/hardware_config.py" --help > /dev/null 2>&1 || {
    echo "  ✓ Script is executable"
}

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Usage examples:"
echo "  # Print hardware configuration to stdout"
echo "  python3 ${BIN_DIR}/hardware_config.py --print"
echo ""
echo "  # Write to default location (requires sudo)"
echo "  sudo python3 ${BIN_DIR}/hardware_config.py"
echo ""
echo "  # Custom output path"
echo "  python3 ${BIN_DIR}/hardware_config.py --output /tmp/hardware_config.json"
echo ""

if [[ "${INSTALL_SYSTEM}" == "true" ]]; then
    echo "System-wide installation:"
    echo "  hardware_config.py --print"
    echo ""
fi

echo "Configuration file:"
echo "  ${SCRIPT_DIR}/config/hardware_config.conf"
echo ""
echo "Documentation:"
echo "  ${SCRIPT_DIR}/hardware_config.md"
echo ""
