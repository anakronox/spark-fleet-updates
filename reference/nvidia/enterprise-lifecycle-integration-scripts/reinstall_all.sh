#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# Reinstall all tools with common module
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/bin"

# Fix execute bits on all shell scripts (lost when transferred from Windows).
# Users can always bootstrap via: bash install.sh
find "${SCRIPT_DIR}" -name "*.sh" -type f -exec chmod +x {} \;

echo "Installing common module first..."
bash common/install.sh

echo ""
echo "Installing production tools..."
for tool in clear_asset_information/*/install.sh \
            controlled_sw_fw_updates/*/install.sh \
            remote_ops_remediation/*/install.sh; do
    if [ -f "$tool" ]; then
        echo "  Installing: $tool"
        bash "$tool"
    fi
done

# ── Security: enforce enterprise file permissions ────────────────────────────
# Prevent world-writable files regardless of the umask in effect at install time.
echo ""
echo "Enforcing file permissions (enterprise policy)..."

# Executable entry-point scripts: rwxr-xr-x (0755)
find "${BIN_DIR}" -maxdepth 1 -name "*.py" -type f -exec chmod 0755 {} \;

# Shared library modules: rw-r--r-- (0644)
find "${BIN_DIR}/common" -name "*.py" -type f -exec chmod 0644 {} \;

# Directories: rwxr-xr-x (0755)
find "${BIN_DIR}" -type d -exec chmod 0755 {} \;

# Ownership: root:root (best-effort; skipped if not running as root)
if [[ "${EUID}" -eq 0 ]]; then
    chown -R root:root "${BIN_DIR}"
    echo "  ✓ Ownership: root:root"
else
    echo "  ⚠ Skipping chown (not root) – re-run with sudo to set root:root ownership"
fi

echo "  ✓ Executables (bin/*.py):    0755"
echo "  ✓ Libraries   (bin/common/): 0644"
echo "  ✓ Directories:               0755"

echo ""
echo "✓ All tools installed!"
echo ""
echo "Verifying bin/ directory:"
ls -la bin/ | head -20
