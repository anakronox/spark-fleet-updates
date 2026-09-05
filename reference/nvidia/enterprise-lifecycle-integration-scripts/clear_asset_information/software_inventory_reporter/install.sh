#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
###############################################################################
# install.sh - Software Inventory Reporter Installation Script
#
# Installs the software inventory reporter into the bin/ directory and
# sets up necessary directories.
#
# Usage:
#   bash install.sh
#
# Requirements:
#   - Run from clear_asset_information/software_inventory_reporter/ directory
#   - Python 3.6+ available as python3
#
# Author: DGX Spark Management Team
# License: MIT
###############################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BIN_DIR="$REPO_ROOT/bin"
SRC_FILE="$SCRIPT_DIR/src/software_inventory_reporter.py"
DEST_FILE="$BIN_DIR/software_inventory_reporter.py"

# Runtime paths
OUTPUT_DIR="/var/lib/dgx_spark_management/clear_asset_information/software_inventory_reporter"
LOG_DIR_REPO="$REPO_ROOT/logs/clear_asset_information/software_inventory_reporter"
LOG_DIR_RUNTIME="/var/log/dgx_spark/clear_asset_information/software_inventory_reporter"

echo "========================================================================"
echo "Software Inventory Reporter - Installation"
echo "========================================================================"
echo

# Check source file exists
if [[ ! -f "$SRC_FILE" ]]; then
    echo -e "${RED}ERROR: Source file not found: $SRC_FILE${NC}"
    exit 1
fi

# Create bin directory if it doesn't exist
if [[ ! -d "$BIN_DIR" ]]; then
    echo "Creating bin directory: $BIN_DIR"
    mkdir -p "$BIN_DIR"
fi

# Copy script to bin
echo "Installing software_inventory_reporter.py to bin/..."
cp "$SRC_FILE" "$DEST_FILE"
chmod 0755 "$DEST_FILE"
echo -e "${GREEN}✓${NC} Installed: $DEST_FILE"

# Create repo log directory (for development)
if [[ ! -d "$LOG_DIR_REPO" ]]; then
    echo "Creating repo log directory: $LOG_DIR_REPO"
    mkdir -p "$LOG_DIR_REPO"
    echo -e "${GREEN}✓${NC} Created: $LOG_DIR_REPO"
fi

# Create runtime output directory (best-effort)
echo
echo "Attempting to create runtime output directory (requires sudo)..."
if mkdir -p "$OUTPUT_DIR" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Created: $OUTPUT_DIR"
else
    echo -e "${YELLOW}⚠${NC} Could not create $OUTPUT_DIR (run with sudo if needed)"
fi

# Create runtime log directory (best-effort)
if mkdir -p "$LOG_DIR_RUNTIME" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Created: $LOG_DIR_RUNTIME"
else
    echo -e "${YELLOW}⚠${NC} Could not create $LOG_DIR_RUNTIME (will use repo logs)"
fi

echo
echo "========================================================================"
echo "Installation Complete!"
echo "========================================================================"
echo
echo "Installed script:"
echo "  $DEST_FILE"
echo
echo "Default output path:"
echo "  $OUTPUT_DIR/software_inventory.json"
echo
echo "Repo log path (development):"
echo "  $LOG_DIR_REPO/software_inventory_reporter.log"
echo
echo "Runtime log path (production):"
echo "  $LOG_DIR_RUNTIME/software_inventory_reporter.log"
echo
echo "========================================================================"
echo "Usage Examples:"
echo "========================================================================"
echo
echo "1. Print inventory to stdout (no root required):"
echo "   python3 $DEST_FILE --print"
echo
echo "2. Write to default output path (requires sudo):"
echo "   sudo python3 $DEST_FILE"
echo
echo "3. Enable pip and docker inventories:"
echo "   sudo python3 $DEST_FILE --enable-pip --enable-docker"
echo
echo "4. Curated mode (smaller output for CMDB):"
echo "   python3 $DEST_FILE --mode curated --print"
echo
echo "5. Custom output path:"
echo "   python3 $DEST_FILE --output /tmp/software_inventory.json"
echo
echo "6. Full verbose run:"
echo "   sudo python3 $DEST_FILE --verbose --enable-pip --enable-docker"
echo
echo "========================================================================"
echo "Verification:"
echo "========================================================================"
echo
echo "Run a test collection:"
echo "  python3 $DEST_FILE --print | head -30"
echo
echo "Check manifest counts:"
echo "  python3 $DEST_FILE --print | jq '.manifest.counts'"
echo
echo "========================================================================"

exit 0
