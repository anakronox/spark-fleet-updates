#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
###############################################################################
# install.sh - NVAIA Asset Tag Manager Installation Script
#
# Installs NVAIAwrite and NVAIAread tools into bin/ directory.
#
# Usage:
#   bash install.sh
#
# Requirements:
#   - Run from clear_asset_information/asset_tag_manager/ directory
#   - Python 3.6+ available as python3
#   - efivarfs mounted (for runtime use)
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

# Source files
WRITE_SRC="$SRC_DIR/nvaiawrite.py"
READ_SRC="$SRC_DIR/nvaiaread.py"

# Destination files
WRITE_DEST="$BIN_DIR/NVAIAwrite"
READ_DEST="$BIN_DIR/NVAIAread"

# Configuration
CONFIG_FILE="$SCRIPT_DIR/config/default.conf"

echo "========================================================================"
echo "NVAIA Asset Tag Manager - Installation"
echo "========================================================================"
echo

# Check source files exist
if [[ ! -f "$WRITE_SRC" ]]; then
    echo -e "${RED}ERROR: Source file not found: $WRITE_SRC${NC}"
    exit 1
fi

if [[ ! -f "$READ_SRC" ]]; then
    echo -e "${RED}ERROR: Source file not found: $READ_SRC${NC}"
    exit 1
fi

# Create bin directory if it doesn't exist
if [[ ! -d "$BIN_DIR" ]]; then
    echo "Creating bin directory: $BIN_DIR"
    mkdir -p "$BIN_DIR"
fi

# Copy and install NVAIAwrite
echo "Installing NVAIAwrite..."
cp "$WRITE_SRC" "$WRITE_DEST"
chmod 0755 "$WRITE_DEST"
echo -e "${GREEN}✓${NC} Installed: $WRITE_DEST"

# Copy and install NVAIAread
echo "Installing NVAIAread..."
cp "$READ_SRC" "$READ_DEST"
chmod 0755 "$READ_DEST"
echo -e "${GREEN}✓${NC} Installed: $READ_DEST"

# Copy module dependencies to bin directory
echo "Installing module dependencies..."
cp "$SRC_DIR/nvaia_schema.py" "$BIN_DIR/"
cp "$SRC_DIR/nvaia_uefi_store.py" "$BIN_DIR/"
cp "$SRC_DIR/platform_dmi.py" "$BIN_DIR/"
echo -e "${GREEN}✓${NC} Installed module dependencies"

# Load configuration
VAR_NAME="NVAIAAssetMeta"
VAR_GUID="3b8e3c2a-2f4a-4a4b-8d2d-9f4d0c8b7b2a"
MAX_PAYLOAD="8192"

if [[ -f "$CONFIG_FILE" ]]; then
    source <(grep -E '^uefi_var_name=' "$CONFIG_FILE")
    source <(grep -E '^uefi_var_guid=' "$CONFIG_FILE")
    source <(grep -E '^max_payload_bytes=' "$CONFIG_FILE")
    VAR_NAME="${uefi_var_name:-$VAR_NAME}"
    VAR_GUID="${uefi_var_guid:-$VAR_GUID}"
    MAX_PAYLOAD="${max_payload_bytes:-$MAX_PAYLOAD}"
fi

echo
echo "========================================================================"
echo "Installation Complete!"
echo "========================================================================"
echo
echo "Installed Tools:"
echo "  NVAIAwrite: $WRITE_DEST"
echo "  NVAIAread:  $READ_DEST"
echo
echo "Configuration:"
echo "  Variable Name: $VAR_NAME"
echo "  Variable GUID: $VAR_GUID"
echo "  Max Payload:   $MAX_PAYLOAD bytes"
echo "  efivarfs path: /sys/firmware/efi/efivars/${VAR_NAME}-${VAR_GUID}"
echo
echo "========================================================================"
echo "Usage Examples:"
echo "========================================================================"
echo
echo "NVAIAwrite (requires root for write operations):"
echo "  # Set owner location and department"
echo "  sudo $WRITE_DEST OWNERDATA LOCATION=RDU1 DEPARTMENT=Engineering"
echo
echo "  # Set asset number and warranty info"
echo "  sudo $WRITE_DEST USERASSETDATA ASSET_NUMBER=DGX12345 WARRANTY_END=2026-12-31"
echo
echo "  # Set lease data"
echo "  sudo $WRITE_DEST LEASEDATA LEASE_START_DATE=2025-01-01 LEASE_TERM=36 LESSOR=Acme"
echo
echo "  # Load from file"
echo "  sudo $WRITE_DEST OWNERDATA --file /tmp/owner_data.txt"
echo
echo "  # Dry run (preview changes without writing)"
echo "  $WRITE_DEST OWNERDATA LOCATION=RDU1 --dry-run"
echo
echo "  # Emit compact tag"
echo "  sudo $WRITE_DEST USERASSETDATA ASSET_NUMBER=DGX12345 --emit-compact"
echo
echo "NVAIAread (no root required for read operations):"
echo "  # Read all data as JSON"
echo "  $READ_DEST ALL --format json"
echo
echo "  # Read specific group"
echo "  $READ_DEST OWNERDATA"
echo
echo "  # Read specific fields"
echo "  $READ_DEST OWNERDATA LOCATION DEPARTMENT"
echo
echo "  # Exclude empty fields"
echo "  $READ_DEST USERASSETDATA --exclude-empty"
echo
echo "  # Output as SET commands"
echo "  $READ_DEST LEASEDATA --format set --prefix ASSET_"
echo
echo "  # Save to file"
echo "  $READ_DEST ALL --format json --output /tmp/asset_metadata.json"
echo
echo "========================================================================"
echo "Verification:"
echo "========================================================================"
echo
echo "Check if efivarfs is mounted:"
echo "  mount | grep efivarfs"
echo
echo "Test read (will fail if variable not written yet):"
echo "  $READ_DEST ALL --format json"
echo
echo "Write test data (requires root):"
echo "  sudo $WRITE_DEST OWNERDATA LOCATION=Test --dry-run"
echo
echo "========================================================================"
echo "Important Notes:"
echo "========================================================================"
echo
echo "• Write operations require root permissions (use sudo)"
echo "• Read operations do not require root"
echo "• efivarfs must be mounted read-write at /sys/firmware/efi/efivars"
echo "• The variable persists across reboots"
echo "• Maximum payload size is $MAX_PAYLOAD bytes (configurable, hard limit 32768)"
echo "• Do NOT store secrets or sensitive PII in asset metadata"
echo "• Variable may have immutable flag; tools handle this automatically"
echo
echo "For detailed documentation, see:"
echo "  $SCRIPT_DIR/README.md"
echo
echo "========================================================================"

exit 0
