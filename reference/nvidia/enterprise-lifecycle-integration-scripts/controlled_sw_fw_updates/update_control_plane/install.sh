#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
###############################################################################
# install.sh - Spark UpdateCtl Installation Script
#
# Installs spark_updatectl.py tool into bin/ directory.
#
# Usage:
#   bash install.sh
#
# Requirements:
#   - Run from controlled_sw_fw_updates/update_control_plane/ directory
#   - Python 3.6+ available as python3
#   - systemd present (for reboot scheduling features)
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
SRC_DIR="$SCRIPT_DIR/src"
SRC_FILE="$SRC_DIR/spark_updatectl.py"
DEST_FILE="$BIN_DIR/spark_updatectl.py"

# Policy sub-modules that must live alongside spark_updatectl.py in bin/
POLICY_MODULES=(
    "apt_policy.py"
    "fwupd_policy.py"
    "internet_policy.py"
    "repo_manager.py"
)

# Runtime paths
RUNTIME_DIR="/var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane"
LOG_DIR_REPO="$REPO_ROOT/logs/controlled_sw_fw_updates/update_control_plane"

echo "========================================================================"
echo "Spark UpdateCtl - Installation"
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

# Copy main script to bin
echo "Installing spark_updatectl.py to bin/..."
cp "$SRC_FILE" "$DEST_FILE"
chmod 0755 "$DEST_FILE"
echo -e "${GREEN}✓${NC} Installed: $DEST_FILE"

# Copy policy sub-modules (library files, not executable entry-points)
echo "Installing policy sub-modules to bin/..."
for module in "${POLICY_MODULES[@]}"; do
    src_mod="$SRC_DIR/$module"
    if [[ ! -f "$src_mod" ]]; then
        echo -e "${RED}ERROR: Policy module not found: $src_mod${NC}"
        exit 1
    fi
    cp "$src_mod" "$BIN_DIR/$module"
    chmod 0644 "$BIN_DIR/$module"
    echo -e "${GREEN}✓${NC} Installed: $BIN_DIR/$module"
done

# Create repo log directory (for development)
if [[ ! -d "$LOG_DIR_REPO" ]]; then
    echo "Creating repo log directory: $LOG_DIR_REPO"
    mkdir -p "$LOG_DIR_REPO"
    echo -e "${GREEN}✓${NC} Created: $LOG_DIR_REPO"
fi

# Create runtime output directory (best-effort)
echo
echo "Attempting to create runtime output directory (requires sudo)..."
if mkdir -p "$RUNTIME_DIR" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Created: $RUNTIME_DIR"
else
    echo -e "${YELLOW}⚠${NC} Could not create $RUNTIME_DIR (run with sudo if needed)"
fi

echo
echo "========================================================================"
echo "Installation Complete!"
echo "========================================================================"
echo
echo "Installed Tool:"
echo "  $DEST_FILE"
echo
echo "Runtime Output Directory:"
echo "  $RUNTIME_DIR"
echo
echo "Repo Log Path (development):"
echo "  $LOG_DIR_REPO/spark_updatectl.log"
echo
echo "========================================================================"
echo "Usage Examples:"
echo "========================================================================"
echo
echo "Status Command (no root required):"
echo "  # Get system status as JSON"
echo "  $DEST_FILE status"
echo
echo "  # Get human-readable status"
echo "  $DEST_FILE --human status"
echo
echo "Reboot Commands:"
echo "  # Plan a reboot (check inhibitors)"
echo "  $DEST_FILE reboot plan --reason \"Maintenance window\""
echo
echo "  # Schedule a reboot in 30 minutes (requires sudo)"
echo "  sudo $DEST_FILE reboot schedule --in-minutes 30 --reason \"Patch application\""
echo
echo "  # Check scheduled reboot status"
echo "  $DEST_FILE reboot schedule-status"
echo
echo "  # Cancel scheduled reboot (requires sudo)"
echo "  sudo $DEST_FILE reboot cancel"
echo
echo "  # Execute reboot immediately (requires sudo)"
echo "  sudo $DEST_FILE reboot now --reason \"Emergency patch\""
echo
echo "Kernel Rollback Commands:"
echo "  # List available kernels"
echo "  $DEST_FILE rollback kernel-list"
echo
echo "  # Set next boot kernel (requires sudo)"
echo "  sudo $DEST_FILE rollback kernel-set-next --kernel 6.14.0-1013-nvidia"
echo
echo "  # Clear next boot kernel setting (requires sudo)"
echo "  sudo $DEST_FILE rollback kernel-clear-next"
echo
echo "  # Check OS backup/snapshot capability"
echo "  $DEST_FILE rollback os-backup-status"
echo
echo "Firmware Rollback Report:"
echo "  # Generate firmware rollback capability report"
echo "  $DEST_FILE fw rollback-report"
echo
echo "  # Query available releases (slower)"
echo "  $DEST_FILE fw rollback-report --query-releases"
echo
echo "========================================================================"
echo "Important Notes:"
echo "========================================================================"
echo
echo "• Read-only commands (status, list, report) do NOT require root"
echo "• State-changing operations (schedule, set-next, reboot now) require sudo"
echo "• JSON output is default; use --human for readable format"
echo "• Use --output <path> to save output to file"
echo "• Kernel rollback is KERNEL-ONLY (does not roll back packages)"
echo "• Firmware rollback report is REPORT-ONLY (does not execute downgrades)"
echo
echo "For detailed documentation, see:"
echo "  $SCRIPT_DIR/README.md"
echo
echo "========================================================================"

exit 0
