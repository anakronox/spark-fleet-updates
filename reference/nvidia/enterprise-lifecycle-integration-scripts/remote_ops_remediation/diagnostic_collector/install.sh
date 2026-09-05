#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
###############################################################################
# install.sh - Spark Diagnostics Collector Installation Script
#
# Installs spark_diagctl.py diagnostic and observability tool.
#
# Usage:
#   bash install.sh
#
# Requirements:
#   - Run from remote_ops_remediation/diagnostic_collector/ directory
#   - Python 3.6+ available as python3
#
# Author: DGX Spark Management Team
# License: MIT
###############################################################################

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BIN_DIR="$REPO_ROOT/bin"
SRC_FILE="$SCRIPT_DIR/src/spark_diagctl.py"
DEST_FILE="$BIN_DIR/spark_diagctl.py"

# Runtime paths
RUNTIME_DIR="/var/lib/dgx_spark_management/remote_ops_remediation/diagnostic_collector"
LOG_DIR="/var/log/dgx_spark/remote_ops_remediation/diagnostic_collector"

echo "========================================================================"
echo "Spark Diagnostics Collector - Installation"
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
echo "Installing spark_diagctl.py to bin/..."
cp "$SRC_FILE" "$DEST_FILE"
chmod +x "$DEST_FILE"
echo -e "${GREEN}✓${NC} Installed: $DEST_FILE"

# Create runtime directories (best-effort)
echo
echo "Attempting to create runtime directories (may require sudo)..."
if mkdir -p "$RUNTIME_DIR" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Created: $RUNTIME_DIR"
else
    echo -e "${YELLOW}⚠${NC} Could not create $RUNTIME_DIR (run with sudo if needed)"
fi

if mkdir -p "$LOG_DIR" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Created: $LOG_DIR"
else
    echo -e "${YELLOW}⚠${NC} Could not create $LOG_DIR (run with sudo if needed)"
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
echo "Log Directory:"
echo "  $LOG_DIR"
echo
echo "========================================================================"
echo "Usage Examples:"
echo "========================================================================"
echo
echo "Check diagnostic capabilities:"
echo "  $DEST_FILE status"
echo
echo "Collect health metrics snapshot:"
echo "  $DEST_FILE health"
echo
echo "Collect system logs:"
echo "  $DEST_FILE logs"
echo
echo "Collect hardware/firmware events:"
echo "  $DEST_FILE hwfw-events"
echo
echo "Check crash dump status:"
echo "  $DEST_FILE crash status"
echo
echo "Collect GPU telemetry:"
echo "  $DEST_FILE gpu"
echo
echo "Collect ALL diagnostics:"
echo "  $DEST_FILE collect-all"
echo
echo "Create diagnostic tarball:"
echo "  $DEST_FILE collect-all --tarball"
echo
echo "Human-readable output:"
echo "  $DEST_FILE health --human"
echo
echo "Save to file:"
echo "  $DEST_FILE health --output /tmp/health.json"
echo
echo "========================================================================"
echo "Important Notes:"
echo "========================================================================"
echo
echo "• Most commands work without root (read-only)"
echo "• Some log data may require root for full access"
echo "• Crash configuration changes require root + --apply"
echo "• Output is JSON-first (use --human for readable format)"
echo "• Use --max-lines and --max-bytes to control truncation"
echo
echo "For detailed documentation, see:"
echo "  $SCRIPT_DIR/README.md"
echo
echo "========================================================================"

exit 0
