#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
###############################################################################
# install.sh - Reset Reason Reporter Installation Script
#
# Installs reset_reason_reporter.py tool into bin/ directory.
#
# Usage:
#   bash install.sh
#
# Requirements:
#   - Run from remote_ops_remediation/reset_reason_reporter/ directory
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
SRC_FILE="$SCRIPT_DIR/src/reset_reason_reporter.py"
DEST_FILE="$BIN_DIR/reset_reason_reporter.py"

# Runtime paths
RUNTIME_DIR="/var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter"
LOG_DIR="/var/log/dgx_spark/remote_ops_remediation/reset_reason_reporter"

echo "========================================================================"
echo "Reset Reason Reporter - Installation"
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
echo "Installing reset_reason_reporter.py to bin/..."
cp "$SRC_FILE" "$DEST_FILE"
chmod +x "$DEST_FILE"
echo -e "${GREEN}✓${NC} Installed: $DEST_FILE"

# Create runtime output directory (best-effort)
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
echo "Basic Report (JSON to stdout):"
echo "  $DEST_FILE"
echo
echo "Human-Readable Report:"
echo "  $DEST_FILE --human"
echo
echo "Save to File:"
echo "  $DEST_FILE --output /tmp/reset_reason.json"
echo
echo "Record to Runtime Directory:"
echo "  sudo $DEST_FILE --record"
echo "  # Creates:"
echo "  #   $RUNTIME_DIR/reset_reason_report.json"
echo "  #   $RUNTIME_DIR/last_reset.json"
echo
echo "Combined (Human + Save):"
echo "  $DEST_FILE --human --output /tmp/reset_reason.json"
echo
echo "With Truncation Controls:"
echo "  $DEST_FILE --max-lines 100 --max-bytes 100000"
echo
echo "========================================================================"
echo "Important Notes:"
echo "========================================================================"
echo
echo "• Tool works without root (read-only analysis)"
echo "• Some journal data may require root for full access"
echo "• Classification is best-effort (may return UNKNOWN)"
echo "• Evidence from multiple sources (journald, wtmp, pstore, EFI vars)"
echo "• Confidence score indicates classification certainty"
echo
echo "For detailed documentation, see:"
echo "  $SCRIPT_DIR/README.md"
echo
echo "========================================================================"

exit 0
