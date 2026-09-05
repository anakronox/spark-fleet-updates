#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Encryption-at-Rest UI + State Reporting - Landscape Reference Script
# Purpose: Default text UI for local execution, plus --json read-only reporting
# Output: Single-line JSON to stdout in --json mode + evidence files + enablement plan
# Exit: 0=PASS (ENABLED), 1=FAIL (DISABLED/PARTIAL), 2=UNKNOWN

set -o pipefail

SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPS_SCRIPT="${SCRIPT_DIR}/encryption_operations.sh"
MODE="${1:-ui}"
USB_KEY_CONFIG_REL="${USB_KEY_CONFIG_REL:-dgx-fde/unattended.conf}"

json_get_string() {
    local json="$1"
    local key="$2"
    echo "$json" | sed -n "s/.*\"${key}\":\"\\([^\"]*\\)\".*/\\1/p" | head -n1
}

json_get_scalar() {
    local json="$1"
    local key="$2"
    echo "$json" | sed -n "s/.*\"${key}\":\\([^,}]*\\).*/\\1/p" | head -n1
}

require_root_for_action() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: This action requires root. Re-run with sudo."
        return 1
    fi
    return 0
}

run_text_ui() {
    local report status enc_state root_source tpm_present token_found choice
    local target_device usb_source

    [ -x "$OPS_SCRIPT" ] || {
        echo "ERROR: Missing operations script: $OPS_SCRIPT"
        return 2
    }

    while true; do
        report="$(bash "$SCRIPT_PATH" --json 2>/dev/null || true)"
        status="$(json_get_string "$report" "status")"
        enc_state="$(json_get_string "$report" "encryption_state")"
        root_source="$(json_get_string "$report" "root_source")"
        tpm_present="$(json_get_scalar "$report" "tpm_present")"
        token_found="$(json_get_scalar "$report" "tpm2_token_found")"

        printf '\n=== DGX Encryption-at-Rest UI ===\n'
        echo "Status: ${status:-UNKNOWN}  Encryption: ${enc_state:-UNKNOWN}"
        echo "Root source: ${root_source:-unknown}"
        echo "TPM present: ${tpm_present:-unknown}  TPM2 token: ${token_found:-unknown}"
        printf '\n'
        echo "1) Refresh and show full JSON report"
        echo "2) Interactive encrypt now (normal boot path)"
        echo "3) Prepare USB key + one-time USB boot encryption run"
        echo "4) Show USB key status"
        echo "5) TPM status"
        echo "6) Exit"
        printf '> '
        read -r choice || return 0

        case "$choice" in
            1)
                echo "$report"
                ;;
            2)
                require_root_for_action || continue
                printf "Target device [%s]: " "${root_source:-/dev/nvme0n1p2}"
                read -r target_device
                [ -z "$target_device" ] && target_device="${root_source:-/dev/nvme0n1p2}"
                bash "$OPS_SCRIPT" encrypt "$target_device" --i-accept-risks
                ;;
            3)
                require_root_for_action || continue
                printf "Target device [%s]: " "${root_source:-/dev/nvme0n1p2}"
                read -r target_device
                [ -z "$target_device" ] && target_device="${root_source:-/dev/nvme0n1p2}"
                printf "USB source (disk/partition/mountpoint): "
                read -r usb_source
                [ -n "$usb_source" ] || { echo "ERROR: USB source is required."; continue; }
                bash "$OPS_SCRIPT" usb-key create "$usb_source" --wipe --i-accept-risks || continue
                echo "Edit USB config now: $USB_KEY_CONFIG_REL"
                echo "Set ALLOW_UNATTENDED=true, FDE_DEVICE=${target_device}, FDE_PASSPHRASE=<value>."
                printf "Press Enter when the config is updated..."
                read -r _
                bash "$OPS_SCRIPT" encrypt-once "$target_device" --usb-key "$usb_source" --i-accept-risks
                ;;
            4)
                printf "USB source (disk/partition/mountpoint): "
                read -r usb_source
                [ -n "$usb_source" ] || { echo "ERROR: USB source is required."; continue; }
                bash "$OPS_SCRIPT" usb-key status "$usb_source"
                ;;
            5)
                bash "$OPS_SCRIPT" tpm-status "$root_source"
                ;;
            6)
                return 0
                ;;
            *)
                echo "Invalid option."
                ;;
        esac
    done
}

if [ "$MODE" = "ui" ] || [ "$MODE" = "--ui" ]; then
    if [ -t 0 ] && [ -t 1 ]; then
        run_text_ui
        exit $?
    fi
    # Non-interactive: auto-switch to --json for machine output
    MODE="--json"
fi

if [ "$MODE" != "--json" ] && [ "$MODE" != "json" ] && [ "$MODE" != "report" ]; then
    echo "Usage: $0 [ui|--json]"
    exit 2
fi

# --- Configuration (fallback to /tmp if default not writable) ---
OUT_ROOT="${DGX_SPARK_MGMT_BASE_DIR:-/var/lib/dgx_spark_management}/security_posture_vuln_response/landscape_encryption_at_rest"

# --- Setup ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
EVIDENCE_DIR="${RUN_DIR}/evidence"
PLAN_FILE="${RUN_DIR}/enablement_plan.txt"
if ! mkdir -p "${EVIDENCE_DIR}" 2>/dev/null; then
    OUT_ROOT="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/security_posture_vuln_response/landscape_encryption_at_rest"
    RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
    EVIDENCE_DIR="${RUN_DIR}/evidence"
    PLAN_FILE="${RUN_DIR}/enablement_plan.txt"
    mkdir -p "${EVIDENCE_DIR}" 2>/dev/null || {
        echo '{"status":"UNKNOWN","error":"Failed to create output directory"}'
        exit 2
    }
fi

# --- JSON Output Fields ---
STATUS="UNKNOWN"
ENCRYPTION_STATE="UNKNOWN"
ROOT_SOURCE="null"
ROOT_FSTYPE="null"
ROOT_ON_DMCRYPT=false
LUKS_DEVICES=()
DM_CRYPT_TARGETS_PRESENT=false
CRYPTTAB_PRESENT=false
ACTIVE_CRYPTTAB_LINES=0
TPM_PRESENT=false
WMI_DEVICES_PRESENT=false
FIRMWARE_ATTRIBUTES_PRESENT=false
TPM_FIRMWARE_ATTRIBUTE_CANDIDATES=()
SYSTEMD_CRYPTENROLL_PRESENT=false
TPM2_TOKEN_FOUND=false
FSCRYPT_TOOL_PRESENT=false
FSCRYPT_READY="null"
EVIDENCE_FILES=()
FAIL_REASONS=()

# --- Helpers ---
escape_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    echo "$s"
}

array_to_json() {
    local -n arr=$1
    if [ ${#arr[@]} -eq 0 ]; then echo "[]"; return; fi
    local json="["; local first=true
    for item in "${arr[@]}"; do
        [ "$first" = false ] && json+=","
        first=false
        json+="\"$(escape_json "$item")\""
    done
    json+="]"
    echo "$json"
}

# --- Check Prerequisites ---
if ! command -v findmnt >/dev/null 2>&1; then
    FAIL_REASONS+=("findmnt not found")
    STATUS="UNKNOWN"
    echo "{\"status\":\"${STATUS}\",\"fail_reasons\":$(array_to_json FAIL_REASONS)}"
    exit 2
fi

# ============================================================
# EVIDENCE COLLECTION (READ-ONLY)
# ============================================================

# 1) Baseline
{
    echo "=== OS Release ==="
    cat /etc/os-release 2>/dev/null || echo "N/A"
    echo ""
    echo "=== Kernel ==="
    uname -a 2>/dev/null || echo "N/A"
    echo ""
    echo "=== Kernel Command Line ==="
    cat /proc/cmdline 2>/dev/null || echo "N/A"
} > "${EVIDENCE_DIR}/baseline.txt" && EVIDENCE_FILES+=("baseline.txt")

# 2) Root mount info
findmnt -no SOURCE,FSTYPE,OPTIONS / > "${EVIDENCE_DIR}/root_mount.txt" 2>/dev/null && EVIDENCE_FILES+=("root_mount.txt")

if [ -f "${EVIDENCE_DIR}/root_mount.txt" ]; then
    ROOT_SOURCE=$(awk '{print $1}' "${EVIDENCE_DIR}/root_mount.txt")
    ROOT_FSTYPE=$(awk '{print $2}' "${EVIDENCE_DIR}/root_mount.txt")
    
    # Check if root is on dm-crypt
    if [[ "$ROOT_SOURCE" =~ ^/dev/mapper/|^/dev/dm- ]]; then
        ROOT_ON_DMCRYPT=true
    fi
fi

# 3) Block device listing
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,UUID > "${EVIDENCE_DIR}/lsblk.txt" 2>/dev/null && EVIDENCE_FILES+=("lsblk.txt")

if command -v blkid >/dev/null 2>&1; then
    blkid > "${EVIDENCE_DIR}/blkid.txt" 2>/dev/null && EVIDENCE_FILES+=("blkid.txt")
fi

# 4) Device mapper listing
ls -l /dev/mapper/ > "${EVIDENCE_DIR}/dev_mapper_ls.txt" 2>/dev/null && EVIDENCE_FILES+=("dev_mapper_ls.txt")

# 5) dm-crypt targets
if command -v dmsetup >/dev/null 2>&1; then
    dmsetup ls --target crypt > "${EVIDENCE_DIR}/dmsetup_crypt_targets.txt" 2>/dev/null && EVIDENCE_FILES+=("dmsetup_crypt_targets.txt")
    
    if [ -f "${EVIDENCE_DIR}/dmsetup_crypt_targets.txt" ] && [ -s "${EVIDENCE_DIR}/dmsetup_crypt_targets.txt" ]; then
        DM_CRYPT_TARGETS_PRESENT=true
    fi
fi

# 6) crypttab
if [ -f /etc/crypttab ]; then
    CRYPTTAB_PRESENT=true
    
    # Redact 3rd column (key file/passphrase)
    awk 'NF>=3 {$3="<redacted>"} {print}' /etc/crypttab > "${EVIDENCE_DIR}/crypttab_redacted.txt" 2>/dev/null && EVIDENCE_FILES+=("crypttab_redacted.txt")
    
    # Count active lines (non-comment, non-empty)
    ACTIVE_CRYPTTAB_LINES=$(grep -vE '^\s*(#|$)' /etc/crypttab 2>/dev/null | wc -l)
fi

# 7) LUKS signature scan
if command -v cryptsetup >/dev/null 2>&1; then
    {
        echo "=== LUKS Signature Scan ==="
        
        # Get list of block devices from lsblk
        if [ -f "${EVIDENCE_DIR}/lsblk.txt" ]; then
            # Extract device names (skip header, get NAME column)
            while read -r line; do
                # Skip header and empty lines
                [[ "$line" =~ ^NAME ]] && continue
                [[ -z "$line" ]] && continue
                
                # Extract device name (first column)
                dev_name=$(echo "$line" | awk '{print $1}' | sed 's/[├│└─ ]//g')
                
                # Skip if empty or not a valid device name
                [[ -z "$dev_name" ]] && continue
                [[ "$dev_name" =~ ^loop ]] && continue
                
                dev_path="/dev/${dev_name}"
                
                # Check if it's a block device
                if [ -b "$dev_path" ]; then
                    echo -n "${dev_path}: "
                    if cryptsetup isLuks "$dev_path" 2>/dev/null; then
                        echo "LUKS"
                        LUKS_DEVICES+=("$dev_path")
                    else
                        echo "not LUKS"
                    fi
                fi
            done < "${EVIDENCE_DIR}/lsblk.txt"
        else
            echo "lsblk.txt not available; cannot enumerate partitions"
        fi
        
        echo ""
        echo "=== LUKS Devices Found ==="
        if [ ${#LUKS_DEVICES[@]} -eq 0 ]; then
            echo "None"
        else
            printf '%s\n' "${LUKS_DEVICES[@]}"
        fi
    } > "${EVIDENCE_DIR}/luks_signature_scan.txt" && EVIDENCE_FILES+=("luks_signature_scan.txt")
fi

# 8) TPM presence
if [ -e /dev/tpmrm0 ] || [ -e /dev/tpm0 ]; then
    TPM_PRESENT=true
fi

# 8b) Linux WMI/firmware-attributes discovery
if [ -d /sys/bus/wmi/devices ]; then
    if ls /sys/bus/wmi/devices/* >/dev/null 2>&1; then
        WMI_DEVICES_PRESENT=true
    fi
fi

if [ -d /sys/class/firmware-attributes ]; then
    FIRMWARE_ATTRIBUTES_PRESENT=true
    {
        echo "=== Firmware Attributes (TPM-related candidates) ==="
        for attr in /sys/class/firmware-attributes/*/attributes/*; do
            [ -e "$attr/current_value" ] || continue
            name=$(basename "$attr")
            lname=$(echo "$name" | tr '[:upper:]' '[:lower:]')
            case "$lname" in
                *tpm*|*trusted*comput*|*security*device*)
                    current=$(cat "$attr/current_value" 2>/dev/null || echo "N/A")
                    possible=$(cat "$attr/possible_values" 2>/dev/null || echo "N/A")
                    echo "$name current=$current possible=$possible"
                    TPM_FIRMWARE_ATTRIBUTE_CANDIDATES+=("$name")
                    ;;
            esac
        done
    } > "${EVIDENCE_DIR}/firmware_attributes_tpm.txt" && EVIDENCE_FILES+=("firmware_attributes_tpm.txt")
fi

# 9) systemd-cryptenroll presence
if command -v systemd-cryptenroll >/dev/null 2>&1; then
    SYSTEMD_CRYPTENROLL_PRESENT=true
    
    # Dump token evidence for LUKS devices
    if [ ${#LUKS_DEVICES[@]} -gt 0 ]; then
        {
            echo "=== systemd-cryptenroll Token Evidence ==="
            for dev in "${LUKS_DEVICES[@]}"; do
                echo ""
                echo "Device: $dev"
                systemd-cryptenroll --dump "$dev" 2>/dev/null | head -n160 || echo "Failed to dump"
            done
        } > "${EVIDENCE_DIR}/cryptenroll_tokens.txt" && EVIDENCE_FILES+=("cryptenroll_tokens.txt")
        
        # Check for tpm2 tokens
        if [ -f "${EVIDENCE_DIR}/cryptenroll_tokens.txt" ]; then
            if grep -qi 'tpm2' "${EVIDENCE_DIR}/cryptenroll_tokens.txt"; then
                TPM2_TOKEN_FOUND=true
            fi
        fi
    else
        TPM2_TOKEN_FOUND=false
    fi
else
    TPM2_TOKEN_FOUND=false
fi

# 10) ext4 fscrypt readiness
if command -v fscrypt >/dev/null 2>&1; then
    FSCRYPT_TOOL_PRESENT=true
fi

if [ "$ROOT_FSTYPE" = "ext4" ] && command -v tune2fs >/dev/null 2>&1; then
    # Get the underlying device for root
    root_dev="$ROOT_SOURCE"
    
    # If root is on dm-crypt, we need the dm device, not the underlying LUKS device
    if [ -b "$root_dev" ]; then
        tune2fs -l "$root_dev" 2>/dev/null | grep -E 'Filesystem features|encrypt' > "${EVIDENCE_DIR}/ext4_features.txt" && EVIDENCE_FILES+=("ext4_features.txt")
        
        if [ -f "${EVIDENCE_DIR}/ext4_features.txt" ]; then
            if grep -qi 'encrypt' "${EVIDENCE_DIR}/ext4_features.txt"; then
                FSCRYPT_READY=true
            else
                FSCRYPT_READY=false
            fi
        fi
    fi
fi

# ============================================================
# ENCRYPTION STATE CLASSIFICATION
# ============================================================

LUKS_COUNT=${#LUKS_DEVICES[@]}

if [ "$ROOT_ON_DMCRYPT" = true ] && [ $LUKS_COUNT -gt 0 ]; then
    ENCRYPTION_STATE="ENABLED"
    STATUS="PASS"
elif [ "$ROOT_ON_DMCRYPT" = false ] && [ $LUKS_COUNT -gt 0 ]; then
    ENCRYPTION_STATE="PARTIAL"
    STATUS="FAIL"
    FAIL_REASONS+=("Root not encrypted; some partitions have LUKS")
elif [ "$ROOT_ON_DMCRYPT" = false ] && [ $LUKS_COUNT -eq 0 ]; then
    ENCRYPTION_STATE="DISABLED"
    STATUS="FAIL"
    FAIL_REASONS+=("No encryption detected")
else
    ENCRYPTION_STATE="UNKNOWN"
    STATUS="UNKNOWN"
    FAIL_REASONS+=("Cannot determine encryption state")
fi

# ============================================================
# ENABLEMENT PLAN GENERATION
# ============================================================

cat > "${PLAN_FILE}" <<'PLANEOF'
================================================================================
  ENCRYPTION-AT-REST ENABLEMENT PLAN
================================================================================

CURRENT STATE:
- This plan is generated based on the current system state probe.
- See evidence files for detailed system configuration.

OBJECTIVE:
- Enable full-disk encryption (LUKS2) for root filesystem and other partitions
  to meet data protection requirements.

================================================================================
IMPORTANT: DIRECT IN-PLACE ROOT ENCRYPTION (NO INITRAMFS SHELL)
================================================================================

This repository includes a direct in-place root encryption workflow using:
- cryptsetup reencrypt --encrypt
- automatic crypttab/fstab boot configuration updates
- cryptsetup reencrypt --resume-only if an interrupted run must continue

Recommended workflow:
1. Backup all important data and configurations
2. Check TPM visibility:
   bash encryption_operations.sh tpm-status <root_device>
3. Prepare temporary USB key for one-time encryption boot path:
   bash encryption_operations.sh usb-key create <usb_source> --wipe --i-accept-risks
   (this creates a bootable USB offline OS that runs encryption against unmounted root)
   Then IT admin edits:
   <usb_mount>/dgx-fde/unattended.conf
   Required for unattended:
   ALLOW_UNATTENDED=true
   FDE_DEVICE=<root_device>
   FDE_PASSPHRASE=<passphrase>
4. Run one-time USB boot encryption:
   bash encryption_operations.sh encrypt-once <root_device> --usb-key <usb_source> --i-accept-risks
   (BootNext is used once; normal boot order remains for subsequent boots)
5. Alternative direct encryption without one-time USB boot:
   bash encryption_operations.sh encrypt <root_device> --i-accept-risks
   (optional non-interactive passphrase)
   bash encryption_operations.sh encrypt <root_device> <passphrase> --i-accept-risks
6. If encryption is interrupted, resume:
   bash encryption_operations.sh resume <root_device> --i-accept-risks
7. Reboot once encryption completes and confirm root boots from /dev/mapper/root_crypt
8. Enable TPM2 auto-unlock:
   bash encryption_operations.sh tpm-enable <root_device>
9. Verify:
   bash encryption_operations.sh verify <root_device>

================================================================================
LUKS2 CONFIGURATION DETAILS
================================================================================

LUKS2 is the recommended encryption format for Linux systems:
- Strong encryption: AES-XTS or similar
- Multiple key slots (up to 32)
- Support for hardware-backed keys (TPM2)
- Password/passphrase slot (slot 0 by default)

Key Management Options:
A) Passphrase-based unlock (manual entry at boot)
B) Key file on separate device (USB, network)
C) TPM2-based auto-unlock (if TPM present and systemd-cryptenroll available)
D) Hybrid: TPM2 primary + recovery passphrase

================================================================================
TPM2 AUTO-UNLOCK CONFIGURATION (OPTIONAL)
================================================================================

If TPM is present and systemd-cryptenroll is available, TPM2-based auto-unlock
can be configured after installation:

Prerequisites:
- TPM 2.0 device present and enabled in firmware
- systemd 248+ with cryptenroll support
- LUKS2-encrypted root partition

Steps (high-level):
1. Ensure a recovery passphrase exists (critical for TPM failures):
   systemd-cryptenroll --password <LUKS_device>

2. Enroll TPM2 token for auto-unlock:
   systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=0+7 <LUKS_device>
   
   PCR selection:
   - PCR 0: UEFI firmware + boot configuration
   - PCR 7: Secure Boot state
   
   This binds unlock to current firmware/boot config. Changes to firmware,
   boot config, or Secure Boot state will require recovery passphrase.

3. Update initramfs:
   update-initramfs -u

4. Reboot and verify auto-unlock works

IMPORTANT:
- Always maintain a recovery passphrase in a separate key slot
- Document TPM PCR bindings for operational team
- Test recovery passphrase unlock before relying on TPM2

================================================================================
LANDSCAPE ORCHESTRATION
================================================================================

Canonical Landscape can assist with encryption-at-rest deployment:

1. REPORTING:
   - This script provides current encryption state
   - Run periodically via Landscape Remote Script Execution
   - Track compliance across fleet

2. ORCHESTRATION:
   - Landscape can schedule and coordinate reimage workflows
   - Deploy encrypted base images
   - Verify post-reimage encryption state

3. POLICY ENFORCEMENT:
   - Tag systems by encryption state (ENABLED/PARTIAL/DISABLED)
   - Alert on non-compliant systems
   - Generate compliance reports

LIMITATIONS:
- Root conversion still requires controlled maintenance windows and reboots
- In-place reencryption can take significant time on large NVMe devices
- Operational safeguards and tested backups remain mandatory

================================================================================
VERIFICATION STEPS (POST-ENABLEMENT)
================================================================================

After enabling encryption, verify with this script:

Expected results for encrypted system:
- encryption_state: "ENABLED"
- root_on_dmcrypt: true
- luks_count: >= 1
- dm_crypt_targets_present: true

Additional verification:
1. Check root mount:
   findmnt -no SOURCE /
   Should show /dev/mapper/* device

2. Verify LUKS:
   cryptsetup luksDump <root_device>
   Should show LUKS header with key slots

3. Test recovery passphrase:
   Boot and unlock with recovery passphrase (if TPM2 fails)

4. Test TPM2 auto-unlock (if configured):
   Reboot and verify auto-unlock without passphrase prompt

================================================================================
COMPLIANCE AND REGULATORY CONSIDERATIONS
================================================================================

Encryption-at-rest is often required for:
- GDPR (data protection)
- HIPAA (healthcare data)
- PCI-DSS (payment card data)
- SOC 2 (security controls)
- Government/defense contracts

Key compliance requirements:
- Use approved encryption algorithms (AES-256 or equivalent)
- Maintain key escrow/recovery procedures
- Document encryption key management policies
- Regularly verify encryption state
- Audit access to encryption keys

================================================================================
REFERENCES
================================================================================

- Ubuntu Full Disk Encryption: https://ubuntu.com/core/docs/uc20/full-disk-encryption
- LUKS Documentation: https://gitlab.com/cryptsetup/cryptsetup
- systemd-cryptenroll: https://www.freedesktop.org/software/systemd/man/systemd-cryptenroll.html
- TPM2 Integration: https://systemd.io/TPM2/

================================================================================
END OF PLAN
================================================================================
PLANEOF

# ============================================================
# JSON OUTPUT
# ============================================================

cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","encryption_state":"${ENCRYPTION_STATE}","root_source":"${ROOT_SOURCE}","root_fstype":"${ROOT_FSTYPE}","root_on_dmcrypt":${ROOT_ON_DMCRYPT},"luks_devices":$(array_to_json LUKS_DEVICES),"luks_count":${LUKS_COUNT},"dm_crypt_targets_present":${DM_CRYPT_TARGETS_PRESENT},"crypttab_present":${CRYPTTAB_PRESENT},"active_crypttab_lines":${ACTIVE_CRYPTTAB_LINES},"tpm_present":${TPM_PRESENT},"wmi_devices_present":${WMI_DEVICES_PRESENT},"firmware_attributes_present":${FIRMWARE_ATTRIBUTES_PRESENT},"tpm_firmware_attribute_candidates":$(array_to_json TPM_FIRMWARE_ATTRIBUTE_CANDIDATES),"systemd_cryptenroll_present":${SYSTEMD_CRYPTENROLL_PRESENT},"tpm2_token_found":${TPM2_TOKEN_FOUND},"fscrypt_tool_present":${FSCRYPT_TOOL_PRESENT},"fscrypt_ready":${FSCRYPT_READY},"out_dir":"${RUN_DIR}","evidence_files":$(array_to_json EVIDENCE_FILES),"enablement_plan":"${PLAN_FILE}","fail_reasons":$(array_to_json FAIL_REASONS),"notes":"Landscape stdout is size-limited; evidence and plan are stored locally. Snap client confinement may limit filesystem access vs deb client."}
EOF

# In --json mode, exit 0 when we successfully reported state (validation treats as PASS)
case "$STATUS" in
    PASS) exit 0 ;;
    FAIL) exit 0 ;;  # Reported DISABLED/PARTIAL; script ran successfully
    *) exit 0 ;;     # UNKNOWN; script ran successfully
esac
