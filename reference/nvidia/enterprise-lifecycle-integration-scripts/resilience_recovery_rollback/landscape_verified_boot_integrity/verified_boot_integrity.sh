#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Verified Boot Chain Integrity - Landscape Reference Script
# Purpose: End-to-end boot chain integrity validation (UEFI Secure Boot + kernel lockdown + signatures + TPM evidence)
# Output: Single-line JSON summary + evidence files saved locally
# Exit: 0=PASS, 1=FAIL, 2=UNKNOWN
#
# Reference script for Canonical Landscape Remote Script Execution
# Read-only validation - does not modify boot config, UEFI vars, TPM state, or keys

set -o pipefail

# --- Configuration (fallback to /tmp if default not writable) ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
BASE_DIR="${DGX_SPARK_MGMT_BASE_DIR:-/var/lib/dgx_spark_management}/resilience_recovery_rollback/landscape_verified_boot_integrity"
EVIDENCE_DIR="${BASE_DIR}/run_${RUN_ID}"
if ! mkdir -p "${EVIDENCE_DIR}" 2>/dev/null; then
    BASE_DIR="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/resilience_recovery_rollback/landscape_verified_boot_integrity"
    EVIDENCE_DIR="${BASE_DIR}/run_${RUN_ID}"
    mkdir -p "${EVIDENCE_DIR}" 2>/dev/null || true
fi

# --- JSON output fields ---
STATUS="UNKNOWN"
UEFI_MODE=false
EFI_MOUNT="UNKNOWN"
SECUREBOOT_VAR="missing"
SETUPMODE_VAR="missing"
MOKUTIL_SB_STATE="MISSING"
LOCKDOWN_RAW=""
LOCKDOWN_ACTIVE="UNKNOWN"
MODULE_SIG_ENFORCE="UNKNOWN"
SBVERIFY_PRESENT=false
KERNEL_IMAGE=""
TPM_PRESENT=false
TPM_EVENTLOG_PRESENT=false
TPM2_PCRREAD_PRESENT=false
FAIL_REASONS=()
EVIDENCE_FILES=()
NOTES="Landscape stdout is size-limited; review evidence files locally. Snap client confinement may limit access vs deb client."

# --- Helper: Escape JSON ---
escape_json() {
    local str="$1"
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//$'\n'/\\n}"
    str="${str//$'\r'/\\r}"
    str="${str//$'\t'/\\t}"
    echo "$str"
}

# --- Helper: Array to JSON ---
array_to_json() {
    local -n arr=$1
    if [ ${#arr[@]} -eq 0 ]; then
        echo "[]"
        return
    fi
    local json="["
    local first=true
    for item in "${arr[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            json+=","
        fi
        json+="\"$(escape_json "$item")\""
    done
    json+="]"
    echo "$json"
}

# --- Create evidence directory ---
# EVIDENCE_DIR already created above with fallback
[ -d "${EVIDENCE_DIR}" ] || {
    echo '{"status":"UNKNOWN","error":"Failed to create evidence directory"}'
    exit 2
}

# --- 1) Baseline ---
{
    echo "=== OS Release ==="
    cat /etc/os-release 2>/dev/null || echo "MISSING"
    echo ""
    echo "=== Kernel ==="
    uname -a 2>/dev/null || echo "MISSING"
    echo ""
    echo "=== Kernel Command Line ==="
    cat /proc/cmdline 2>/dev/null || echo "MISSING"
} > "${EVIDENCE_DIR}/baseline.txt"
EVIDENCE_FILES+=("baseline.txt")

# --- 2) UEFI presence ---
if [ -d /sys/firmware/efi ]; then
    UEFI_MODE=true
else
    UEFI_MODE=false
    FAIL_REASONS+=("Not in UEFI mode")
fi

# --- 3) Secure Boot state ---
# Read SecureBoot variable (byte at offset 4)
SECUREBOOT_FILE=$(find /sys/firmware/efi/efivars/ -name 'SecureBoot-*' 2>/dev/null | head -n1)
if [ -n "$SECUREBOOT_FILE" ] && [ -r "$SECUREBOOT_FILE" ]; then
    # Read byte at offset 4 (after 4-byte attributes)
    SECUREBOOT_BYTE=$(od -An -t u1 -j 4 -N 1 "$SECUREBOOT_FILE" 2>/dev/null | tr -d ' ')
    SECUREBOOT_VAR="${SECUREBOOT_BYTE:-missing}"
else
    SECUREBOOT_VAR="missing"
fi

# Read SetupMode variable
SETUPMODE_FILE=$(find /sys/firmware/efi/efivars/ -name 'SetupMode-*' 2>/dev/null | head -n1)
if [ -n "$SETUPMODE_FILE" ] && [ -r "$SETUPMODE_FILE" ]; then
    SETUPMODE_BYTE=$(od -An -t u1 -j 4 -N 1 "$SETUPMODE_FILE" 2>/dev/null | tr -d ' ')
    SETUPMODE_VAR="${SETUPMODE_BYTE:-missing}"
else
    SETUPMODE_VAR="missing"
fi

# mokutil if available
if command -v mokutil >/dev/null 2>&1; then
    MOKUTIL_SB_STATE=$(mokutil --sb-state 2>/dev/null | head -n1 || echo "ERROR")
    mokutil --list-enrolled 2>/dev/null | head -n40 > "${EVIDENCE_DIR}/mokutil_list_enrolled_head.txt"
    EVIDENCE_FILES+=("mokutil_list_enrolled_head.txt")
fi

# --- 4) Kernel lockdown + module signature enforcement ---
if [ -f /sys/kernel/security/lockdown ]; then
    LOCKDOWN_RAW=$(cat /sys/kernel/security/lockdown 2>/dev/null || echo "MISSING")
    # Extract bracketed active mode, e.g., "none [integrity] confidentiality"
    LOCKDOWN_ACTIVE=$(echo "$LOCKDOWN_RAW" | grep -oP '\[\K[^\]]+' || echo "UNKNOWN")
else
    LOCKDOWN_RAW="MISSING"
    LOCKDOWN_ACTIVE="UNKNOWN"
fi

if [ -f /proc/sys/kernel/module_sig_enforce ]; then
    MODULE_SIG_ENFORCE=$(cat /proc/sys/kernel/module_sig_enforce 2>/dev/null || echo "UNKNOWN")
else
    MODULE_SIG_ENFORCE="UNKNOWN"
fi

# dmesg evidence
dmesg 2>/dev/null | grep -Ei 'secure boot|secureboot|lockdown|EFI:.*Secure' > "${EVIDENCE_DIR}/dmesg_secureboot_lockdown.txt" 2>/dev/null
EVIDENCE_FILES+=("dmesg_secureboot_lockdown.txt")

# --- 5) EFI boot entries and binaries ---
if command -v efibootmgr >/dev/null 2>&1; then
    efibootmgr -v > "${EVIDENCE_DIR}/efibootmgr_v.txt" 2>&1
    EVIDENCE_FILES+=("efibootmgr_v.txt")
fi

# Determine EFI mount
EFI_MOUNT="NO"
if mount | grep -q '/boot/efi'; then
    EFI_DIR="/boot/efi"
    EFI_MOUNT="YES"
elif mount | grep -q ' /efi '; then
    EFI_DIR="/efi"
    EFI_MOUNT="YES"
elif [ -d /boot/efi/EFI ]; then
    EFI_DIR="/boot/efi"
    EFI_MOUNT="LIKELY"
elif [ -d /efi/EFI ]; then
    EFI_DIR="/efi"
    EFI_MOUNT="LIKELY"
fi

if [ "$EFI_MOUNT" != "NO" ] && [ -n "$EFI_DIR" ]; then
    find "$EFI_DIR/EFI" -maxdepth 3 -name '*.efi' -type f 2>/dev/null > "${EVIDENCE_DIR}/efi_binaries.txt"
    EVIDENCE_FILES+=("efi_binaries.txt")
fi

# --- 6) Signature evidence ---
if command -v sbverify >/dev/null 2>&1; then
    SBVERIFY_PRESENT=true
    
    # Kernel image
    KERNEL_IMAGE="/boot/vmlinuz-$(uname -r)"
    if [ ! -f "$KERNEL_IMAGE" ]; then
        KERNEL_IMAGE="/boot/vmlinuz"
    fi
    
    if [ -f "$KERNEL_IMAGE" ]; then
        sbverify --list "$KERNEL_IMAGE" > "${EVIDENCE_DIR}/sbverify_kernel.txt" 2>&1
        EVIDENCE_FILES+=("sbverify_kernel.txt")
        
        file "$KERNEL_IMAGE" > "${EVIDENCE_DIR}/kernel_filetype.txt" 2>&1
        EVIDENCE_FILES+=("kernel_filetype.txt")
    fi
    
    # Shim/GRUB/BOOTAA64 - find candidates
    if [ -f "${EVIDENCE_DIR}/efi_binaries.txt" ]; then
        SHIM_EFI=$(grep -i 'shim.*\.efi' "${EVIDENCE_DIR}/efi_binaries.txt" | head -n1)
        GRUB_EFI=$(grep -i 'grub.*\.efi' "${EVIDENCE_DIR}/efi_binaries.txt" | head -n1)
        BOOTAA64_EFI=$(grep -i 'BOOTAA64\.EFI' "${EVIDENCE_DIR}/efi_binaries.txt" | head -n1)
        
        if [ -n "$SHIM_EFI" ] && [ -f "$SHIM_EFI" ]; then
            sbverify --list "$SHIM_EFI" > "${EVIDENCE_DIR}/sbverify_shim.txt" 2>&1
            EVIDENCE_FILES+=("sbverify_shim.txt")
        fi
        
        if [ -n "$GRUB_EFI" ] && [ -f "$GRUB_EFI" ]; then
            sbverify --list "$GRUB_EFI" > "${EVIDENCE_DIR}/sbverify_grub.txt" 2>&1
            EVIDENCE_FILES+=("sbverify_grub.txt")
        fi
        
        if [ -n "$BOOTAA64_EFI" ] && [ -f "$BOOTAA64_EFI" ]; then
            sbverify --list "$BOOTAA64_EFI" > "${EVIDENCE_DIR}/sbverify_bootaa64.txt" 2>&1
            EVIDENCE_FILES+=("sbverify_bootaa64.txt")
        fi
    fi
fi

# --- 7) TPM / measured boot evidence ---
if [ -e /dev/tpmrm0 ] || [ -e /dev/tpm0 ]; then
    TPM_PRESENT=true
fi

TPM_EVENTLOG="/sys/kernel/security/tpm0/binary_bios_measurements"
if [ -r "$TPM_EVENTLOG" ]; then
    TPM_EVENTLOG_PRESENT=true
    sha256sum "$TPM_EVENTLOG" 2>/dev/null | awk '{print $1}' > "${EVIDENCE_DIR}/tpm_eventlog_sha256.txt"
    stat -c%s "$TPM_EVENTLOG" >> "${EVIDENCE_DIR}/tpm_eventlog_sha256.txt" 2>/dev/null
    EVIDENCE_FILES+=("tpm_eventlog_sha256.txt")
    
    if command -v tpm2_eventlog >/dev/null 2>&1; then
        tpm2_eventlog "$TPM_EVENTLOG" 2>/dev/null | head -n80 > "${EVIDENCE_DIR}/tpm_eventlog_head.txt"
        EVIDENCE_FILES+=("tpm_eventlog_head.txt")
    fi
fi

if command -v tpm2_pcrread >/dev/null 2>&1; then
    TPM2_PCRREAD_PRESENT=true
    tpm2_pcrread sha256:0,2,7 > "${EVIDENCE_DIR}/tpm_pcrread_sha256_0_2_7.txt" 2>&1
    EVIDENCE_FILES+=("tpm_pcrread_sha256_0_2_7.txt")
    
    tpm2_pcrread 2>/dev/null | head -n120 > "${EVIDENCE_DIR}/tpm_pcrread_head.txt"
    EVIDENCE_FILES+=("tpm_pcrread_head.txt")
fi

# --- PASS/FAIL logic ---
if [ "$UEFI_MODE" = false ]; then
    STATUS="FAIL"
    # Already added to FAIL_REASONS
elif [ "$SETUPMODE_VAR" = "1" ]; then
    STATUS="FAIL"
    FAIL_REASONS+=("SetupMode is enabled (value=1)")
elif [ "$SECUREBOOT_VAR" != "1" ]; then
    # Check mokutil as corroboration
    if [[ "$MOKUTIL_SB_STATE" =~ disabled|Disabled ]]; then
        STATUS="FAIL"
        FAIL_REASONS+=("SecureBoot disabled (var=$SECUREBOOT_VAR, mokutil=$MOKUTIL_SB_STATE)")
    elif [ "$SECUREBOOT_VAR" = "missing" ]; then
        # If var is missing but mokutil says enabled, be lenient
        if [[ "$MOKUTIL_SB_STATE" =~ enabled|Enabled ]]; then
            STATUS="PASS"
        else
            STATUS="FAIL"
            FAIL_REASONS+=("SecureBoot variable missing and not confirmed enabled")
        fi
    else
        # SECUREBOOT_VAR is 0 or other value
        STATUS="FAIL"
        FAIL_REASONS+=("SecureBoot not enabled (var=$SECUREBOOT_VAR)")
    fi
else
    # SECUREBOOT_VAR == 1, SETUPMODE != 1, UEFI_MODE = true
    STATUS="PASS"
fi

# If still UNKNOWN, default to FAIL with explanation
if [ "$STATUS" = "UNKNOWN" ]; then
    STATUS="FAIL"
    FAIL_REASONS+=("Unable to determine Secure Boot state definitively")
fi

# --- Output JSON ---
cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","uefi_mode":${UEFI_MODE},"efi_mount":"${EFI_MOUNT}","secureboot_var":"${SECUREBOOT_VAR}","setupmode_var":"${SETUPMODE_VAR}","mokutil_sb_state":"$(escape_json "$MOKUTIL_SB_STATE")","lockdown_state_raw":"$(escape_json "$LOCKDOWN_RAW")","lockdown_active_mode":"${LOCKDOWN_ACTIVE}","module_sig_enforce":"${MODULE_SIG_ENFORCE}","sbverify_present":${SBVERIFY_PRESENT},"kernel_image":"$(escape_json "$KERNEL_IMAGE")","tpm_present":${TPM_PRESENT},"tpm_eventlog_present":${TPM_EVENTLOG_PRESENT},"tpm2_pcrread_present":${TPM2_PCRREAD_PRESENT},"fail_reasons":$(array_to_json FAIL_REASONS),"evidence_dir":"${EVIDENCE_DIR}","evidence_files":$(array_to_json EVIDENCE_FILES),"notes":"$(escape_json "$NOTES")"}
EOF

# Exit with appropriate code
case "$STATUS" in
    PASS)
        exit 0
        ;;
    FAIL)
        exit 1
        ;;
    *)
        exit 2
        ;;
esac
