#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
################################################################################
# Installation Script for Hardware Inventory Collector - Device Identity
#
# This script installs the device_identity.py collector to:
# 1. Project bin/ directory
# 2. Optionally to system-wide /usr/local/bin/
#
# Usage:
#   bash install.sh              # Install to project bin/ only
#   sudo bash install.sh --system # Install to both project and system
################################################################################

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
readonly SRC_FILE="${SCRIPT_DIR}/src/device_identity.py"
readonly PROJECT_BIN="${PROJECT_ROOT}/bin"
readonly PROJECT_BIN_TARGET="${PROJECT_BIN}/device_identity.py"
readonly SYSTEM_BIN="/usr/local/bin/device_identity.py"

# Colors
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Check if source file exists
check_source() {
    if [[ ! -f "$SRC_FILE" ]]; then
        log_error "Source file not found: $SRC_FILE"
        exit 1
    fi
}

# Install to project bin/
install_to_project_bin() {
    log_info "Installing to project bin/ directory..."
    
    # Create bin/ if it doesn't exist
    mkdir -p "$PROJECT_BIN"
    
    # Copy file
    cp "$SRC_FILE" "$PROJECT_BIN_TARGET"
    chmod 0755 "$PROJECT_BIN_TARGET"
    
    log_info "✓ Installed to: $PROJECT_BIN_TARGET"
}

# Install to system /usr/local/bin/
install_to_system() {
    if [[ $EUID -ne 0 ]]; then
        log_warn "System-wide install requires root. Skipping /usr/local/bin/ installation."
        log_warn "Run with sudo for system-wide install: sudo bash install.sh --system"
        return 1
    fi
    
    log_info "Installing to system /usr/local/bin/..."
    
    cp "$SRC_FILE" "$SYSTEM_BIN"
    chmod 0755 "$SYSTEM_BIN"
    
    log_info "✓ Installed to: $SYSTEM_BIN"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    
    # Test Python syntax
    if python3 -m py_compile "$PROJECT_BIN_TARGET" 2>/dev/null; then
        log_info "✓ Python syntax valid"
    else
        log_error "Python syntax check failed"
        return 1
    fi
    
    # Test --help
    if python3 "$PROJECT_BIN_TARGET" --help &>/dev/null; then
        log_info "✓ Script --help works"
    else
        log_warn "Script --help returned non-zero"
    fi
    
    # Test --print (requires DMI sysfs)
    log_info "Testing --print mode..."
    if python3 "$PROJECT_BIN_TARGET" --print &>/dev/null; then
        log_info "✓ Script --print works"
    else
        log_warn "Script --print test had issues (may be normal if DMI unavailable)"
    fi
}

# Print usage instructions
print_usage() {
    echo ""
    echo "=========================================="
    log_info "Installation complete!"
    echo "=========================================="
    echo ""
    echo "Usage examples:"
    echo ""
    echo "  # Print identity to stdout"
    echo "  python3 bin/device_identity.py --print"
    echo ""
    echo "  # Write to default location (requires sudo)"
    echo "  sudo python3 bin/device_identity.py"
    echo ""
    echo "  # Write to custom location"
    echo "  python3 bin/device_identity.py --output /tmp/identity.json"
    echo ""
    
    if [[ -f "$SYSTEM_BIN" ]]; then
        echo "  # System-wide command (no path needed)"
        echo "  device_identity.py --print"
        echo ""
    fi
    
    echo "Documentation:"
    echo "  clear_asset_information/hardware_inventory_collector/README.md"
    echo ""
}

# Main installation
main() {
    local install_system=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --system)
                install_system=true
                shift
                ;;
            --help|-h)
                echo "Usage: bash install.sh [--system]"
                echo ""
                echo "Options:"
                echo "  --system    Also install to /usr/local/bin/ (requires sudo)"
                echo ""
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    echo "=========================================="
    echo "Hardware Inventory Collector - Device Identity"
    echo "Installation Script"
    echo "=========================================="
    echo ""
    
    # Check source
    check_source
    
    # Install to project bin
    install_to_project_bin
    
    # Optionally install to system
    if [[ "$install_system" == true ]]; then
        install_to_system || true  # Don't fail if no sudo
    fi
    
    # Verify
    verify_installation
    
    # Print usage
    print_usage
}

main "$@"
