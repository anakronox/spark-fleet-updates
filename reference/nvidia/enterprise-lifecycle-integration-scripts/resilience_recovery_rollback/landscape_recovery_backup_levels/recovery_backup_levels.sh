#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Recovery Partition & Backup Levels - Landscape Reference Script
# Purpose: Probe recovery environment + create backup artifacts at different levels
# Output: Single-line JSON + local artifacts
# Exit: 0=PASS, 1=FAIL, 2=UNKNOWN
#
# Reference script for Canonical Landscape Remote Script Execution
# Read-only probe - does not modify partitions, boot entries, or bootloader

set -o pipefail

# --- Default Configuration ---
LEVEL=0
OUT_ROOT="/var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_recovery_backup_levels"
JSON_OUTPUT=true

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --level)
            LEVEL="$2"
            shift 2
            ;;
        --out-root)
            OUT_ROOT="$2"
            shift 2
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            shift
            ;;
    esac
done

# --- Setup (fallback to /tmp if default not writable) ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
PAYLOAD_DIR="${RUN_DIR}/payload"
if ! mkdir -p "${PAYLOAD_DIR}" 2>/dev/null; then
    OUT_ROOT="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/resilience_recovery_rollback/landscape_recovery_backup_levels"
    RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
    PAYLOAD_DIR="${RUN_DIR}/payload"
    mkdir -p "${PAYLOAD_DIR}" 2>/dev/null || {
        echo '{"status":"UNKNOWN","error":"Failed to create output directory"}'
        exit 2
    }
fi

# --- JSON output fields ---
STATUS="UNKNOWN"
UEFI_MODE="NO"
EFI_MOUNT="UNKNOWN"
BOOTLOADER="UNKNOWN"
RECOVERY_PARTITION_LINES=0
GRUB_RECOVERY_LINES=0
SYSTEMD_BOOT_ENTRY_LINES=0
LEVEL0_JSON="${RUN_DIR}/level0_recovery_probe.json"
LEVEL1_TARBALL=""
LEVEL2_TARBALL=""
LEVEL1_SHA256=""
LEVEL2_SHA256=""
MISSING_OPTIONAL=()
NOTES="Artifacts are local; Landscape stdout is size-limited. Snap Landscape client may constrain filesystem access vs deb."

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

# --- Check core prerequisites ---
if ! command -v tar >/dev/null 2>&1; then
    echo '{"status":"UNKNOWN","error":"tar command not found"}'
    exit 2
fi

if ! command -v sha256sum >/dev/null 2>&1; then
    echo '{"status":"UNKNOWN","error":"sha256sum command not found"}'
    exit 2
fi

if ! command -v lsblk >/dev/null 2>&1; then
    echo '{"status":"UNKNOWN","error":"lsblk command not found"}'
    exit 2
fi

# ============================================================
# A) PROBE: Baseline + Partition Evidence
# ============================================================

# Baseline
{
    echo "=== OS Release ==="
    cat /etc/os-release 2>/dev/null || echo "MISSING"
    echo ""
    echo "=== Kernel ==="
    uname -a 2>/dev/null || echo "MISSING"
    echo ""
    echo "=== Kernel Command Line ==="
    cat /proc/cmdline 2>/dev/null || echo "MISSING"
} > "${PAYLOAD_DIR}/baseline.txt"

# Partition evidence
lsblk -o NAME,TYPE,SIZE,FSTYPE,LABEL,PARTLABEL,PARTUUID,UUID,MOUNTPOINT > "${PAYLOAD_DIR}/lsblk.txt" 2>/dev/null || MISSING_OPTIONAL+=("lsblk")

if command -v blkid >/dev/null 2>&1; then
    blkid > "${PAYLOAD_DIR}/blkid.txt" 2>/dev/null || MISSING_OPTIONAL+=("blkid")
else
    MISSING_OPTIONAL+=("blkid")
fi

if command -v findmnt >/dev/null 2>&1; then
    findmnt -r > "${PAYLOAD_DIR}/findmnt.txt" 2>/dev/null || MISSING_OPTIONAL+=("findmnt")
else
    MISSING_OPTIONAL+=("findmnt")
fi

# GPT partition tables (best effort)
if command -v sgdisk >/dev/null 2>&1; then
    for disk in /dev/sda /dev/nvme0n1; do
        if [ -b "$disk" ]; then
            sgdisk -p "$disk" > "${PAYLOAD_DIR}/sgdisk_$(basename $disk).txt" 2>/dev/null
        fi
    done
fi

# Detect recovery partition candidates
if [ -f "${PAYLOAD_DIR}/lsblk.txt" ]; then
    grep -Ei 'recovery|rescue|restore|oem' "${PAYLOAD_DIR}/lsblk.txt" > "${PAYLOAD_DIR}/recovery_partition_matches.txt" 2>/dev/null || true
    RECOVERY_PARTITION_LINES=$(wc -l < "${PAYLOAD_DIR}/recovery_partition_matches.txt" 2>/dev/null || echo 0)
fi

# ============================================================
# B) BOOT ENTRY POINTS EVIDENCE
# ============================================================

# UEFI mode
if [ -d /sys/firmware/efi ]; then
    UEFI_MODE="YES"
else
    UEFI_MODE="NO"
fi

# EFI mount detection
EFI_DIR=""
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
else
    EFI_MOUNT="NO"
fi

# efibootmgr
if command -v efibootmgr >/dev/null 2>&1; then
    efibootmgr -v > "${PAYLOAD_DIR}/efibootmgr_v.txt" 2>/dev/null || MISSING_OPTIONAL+=("efibootmgr_output")
else
    MISSING_OPTIONAL+=("efibootmgr")
fi

# EFI binaries
if [ -n "$EFI_DIR" ] && [ -d "$EFI_DIR/EFI" ]; then
    find "$EFI_DIR/EFI" -maxdepth 3 -name '*.efi' -type f 2>/dev/null > "${PAYLOAD_DIR}/efi_binaries.txt" || MISSING_OPTIONAL+=("efi_binaries")
fi

# ============================================================
# C) BOOTLOADER DETECTION + RECOVERY ENVIRONMENT ENTRY POINTS
# ============================================================

# systemd-boot detection
if command -v bootctl >/dev/null 2>&1 && bootctl status >/dev/null 2>&1; then
    BOOTLOADER="systemd-boot"
    bootctl status > "${PAYLOAD_DIR}/bootctl_status.txt" 2>/dev/null || MISSING_OPTIONAL+=("bootctl_status")
    
    if [ -d /boot/loader/entries ]; then
        ls -al /boot/loader/entries > "${PAYLOAD_DIR}/systemd_boot_entries_ls.txt" 2>/dev/null
        SYSTEMD_BOOT_ENTRY_LINES=$(ls /boot/loader/entries 2>/dev/null | wc -l)
    fi
# GRUB detection
elif [ -f /boot/grub/grub.cfg ]; then
    BOOTLOADER="grub"
    
    # Recovery entries grep (best effort; may fail if not root)
    grep -nEi 'recovery mode|rescue target|emergency target' /boot/grub/grub.cfg > "${PAYLOAD_DIR}/grub_recovery_grep.txt" 2>/dev/null || MISSING_OPTIONAL+=("grub_recovery_grep")
    
    if [ -f "${PAYLOAD_DIR}/grub_recovery_grep.txt" ]; then
        GRUB_RECOVERY_LINES=$(wc -l < "${PAYLOAD_DIR}/grub_recovery_grep.txt")
    fi
    
    # Menuentry list
    grep -nEi '^menuentry ' /boot/grub/grub.cfg 2>/dev/null | head -n80 > "${PAYLOAD_DIR}/grub_menuentry_head.txt" || MISSING_OPTIONAL+=("grub_menuentry")
fi

# ============================================================
# LEVEL 0: Probe JSON
# ============================================================

# Create level0 JSON
cat > "${LEVEL0_JSON}" <<EOF
{
  "run_id": "${RUN_ID}",
  "uefi_mode": "${UEFI_MODE}",
  "efi_mount": "${EFI_MOUNT}",
  "bootloader": "${BOOTLOADER}",
  "recovery_partition_candidate_lines": ${RECOVERY_PARTITION_LINES},
  "grub_recovery_entry_lines": ${GRUB_RECOVERY_LINES},
  "systemd_boot_entry_lines": ${SYSTEMD_BOOT_ENTRY_LINES},
  "notes": "Ubuntu often uses GRUB recovery mode entries instead of a dedicated recovery partition."
}
EOF

# ============================================================
# LEVEL 1: Config Snapshot Tarball
# ============================================================

if [ "$LEVEL" -ge 1 ]; then
    LEVEL1_DIR="${RUN_DIR}/level1_config"
    mkdir -p "${LEVEL1_DIR}/apt" "${LEVEL1_DIR}/probe" 2>/dev/null
    
    # Copy probe evidence
    cp "${PAYLOAD_DIR}"/*.txt "${LEVEL1_DIR}/probe/" 2>/dev/null || true
    cp "${LEVEL0_JSON}" "${LEVEL1_DIR}/" 2>/dev/null || true
    
    # APT repo config
    [ -f /etc/apt/sources.list ] && cp /etc/apt/sources.list "${LEVEL1_DIR}/apt/" 2>/dev/null
    
    if [ -d /etc/apt/sources.list.d ]; then
        find /etc/apt/sources.list.d -maxdepth 1 -type f -exec cp {} "${LEVEL1_DIR}/apt/" \; 2>/dev/null || true
    fi
    
    [ -f /etc/apt/preferences ] && cp /etc/apt/preferences "${LEVEL1_DIR}/apt/" 2>/dev/null
    
    if [ -d /etc/apt/preferences.d ]; then
        find /etc/apt/preferences.d -maxdepth 1 -type f -exec cp {} "${LEVEL1_DIR}/apt/" \; 2>/dev/null || true
    fi
    
    # Extract Signed-By lines
    {
        [ -f /etc/apt/sources.list ] && grep -i 'signed-by' /etc/apt/sources.list 2>/dev/null
        find /etc/apt/sources.list.d -type f -exec grep -i 'signed-by' {} + 2>/dev/null
    } > "${LEVEL1_DIR}/apt/signed_by_lines.txt" 2>/dev/null || true
    
    # Keyring SHA256s (do not copy full keyrings)
    find /usr/share/keyrings /etc/apt/keyrings -name '*.gpg' -o -name '*.asc' 2>/dev/null | \
        xargs sha256sum 2>/dev/null > "${LEVEL1_DIR}/apt/keyrings_sha256.txt" || true
    
    # Copy existing DGX Spark tool outputs (best effort)
    DIAG_JSON="/var/lib/dgx_spark_management/remote_ops_remediation/diagnostic_collector/diagnostics_full.json"
    [ -f "$DIAG_JSON" ] && cp "$DIAG_JSON" "${LEVEL1_DIR}/" 2>/dev/null
    
    RESET_JSON="/var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter/reset_reason_report.json"
    [ -f "$RESET_JSON" ] && cp "$RESET_JSON" "${LEVEL1_DIR}/" 2>/dev/null
    
    UPDATE_JSON="/var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane/status.json"
    [ -f "$UPDATE_JSON" ] && cp "$UPDATE_JSON" "${LEVEL1_DIR}/" 2>/dev/null
    
    # Create tarball
    LEVEL1_TARBALL="${RUN_DIR}/level1_config_backup_${RUN_ID}.tar.gz"
    (cd "${RUN_DIR}" && tar -czf "$(basename $LEVEL1_TARBALL)" level1_config 2>/dev/null) || {
        STATUS="FAIL"
        echo '{"status":"FAIL","error":"Failed to create level1 tarball"}'
        exit 1
    }
    
    LEVEL1_SHA256=$(sha256sum "$LEVEL1_TARBALL" 2>/dev/null | awk '{print $1}')
fi

# ============================================================
# LEVEL 2: Rebuild Manifest Tarball
# ============================================================

if [ "$LEVEL" -ge 2 ]; then
    LEVEL2_DIR="${RUN_DIR}/level2_manifest"
    mkdir -p "${LEVEL2_DIR}" 2>/dev/null
    
    # dpkg package list
    if command -v dpkg-query >/dev/null 2>&1; then
        dpkg-query -W -f='${Package}\t${Version}\n' > "${LEVEL2_DIR}/dpkg_packages.tsv" 2>/dev/null || MISSING_OPTIONAL+=("dpkg_query")
        
        # Kernel/NVIDIA subset
        dpkg -l 2>/dev/null | grep -E '^ii' | grep -E 'linux-image|linux-modules|linux-headers|nvidia|cuda|firmware' > "${LEVEL2_DIR}/kernel_nvidia_pkg_subset.txt" 2>/dev/null || true
    else
        MISSING_OPTIONAL+=("dpkg")
    fi
    
    # Snap list
    if command -v snap >/dev/null 2>&1; then
        snap list > "${LEVEL2_DIR}/snap_list.txt" 2>/dev/null || MISSING_OPTIONAL+=("snap_list")
        snap version > "${LEVEL2_DIR}/snap_version.txt" 2>/dev/null || true
    else
        MISSING_OPTIONAL+=("snap")
    fi
    
    # Boot evidence pointers
    [ -f "${PAYLOAD_DIR}/efibootmgr_v.txt" ] && cp "${PAYLOAD_DIR}/efibootmgr_v.txt" "${LEVEL2_DIR}/" 2>/dev/null
    [ -f "${PAYLOAD_DIR}/grub_menuentry_head.txt" ] && cp "${PAYLOAD_DIR}/grub_menuentry_head.txt" "${LEVEL2_DIR}/" 2>/dev/null
    [ -f "${PAYLOAD_DIR}/efi_binaries.txt" ] && cp "${PAYLOAD_DIR}/efi_binaries.txt" "${LEVEL2_DIR}/" 2>/dev/null
    
    # Copy level0 JSON
    cp "${LEVEL0_JSON}" "${LEVEL2_DIR}/" 2>/dev/null || true
    
    # Create tarball
    LEVEL2_TARBALL="${RUN_DIR}/level2_rebuild_manifest_${RUN_ID}.tar.gz"
    (cd "${RUN_DIR}" && tar -czf "$(basename $LEVEL2_TARBALL)" level2_manifest 2>/dev/null) || {
        STATUS="FAIL"
        echo '{"status":"FAIL","error":"Failed to create level2 tarball"}'
        exit 1
    }
    
    LEVEL2_SHA256=$(sha256sum "$LEVEL2_TARBALL" 2>/dev/null | awk '{print $1}')
    
    # Create backup_tarballs_sha256.txt
    {
        [ -n "$LEVEL1_SHA256" ] && echo "$LEVEL1_SHA256  $(basename $LEVEL1_TARBALL)"
        [ -n "$LEVEL2_SHA256" ] && echo "$LEVEL2_SHA256  $(basename $LEVEL2_TARBALL)"
    } > "${RUN_DIR}/backup_tarballs_sha256.txt" 2>/dev/null || true
fi

# ============================================================
# FINAL STATUS
# ============================================================

# Determine status
if [ "$LEVEL" -eq 0 ]; then
    [ -f "$LEVEL0_JSON" ] && STATUS="PASS" || STATUS="FAIL"
elif [ "$LEVEL" -eq 1 ]; then
    [ -f "$LEVEL1_TARBALL" ] && STATUS="PASS" || STATUS="FAIL"
elif [ "$LEVEL" -eq 2 ]; then
    [ -f "$LEVEL2_TARBALL" ] && STATUS="PASS" || STATUS="FAIL"
else
    STATUS="UNKNOWN"
fi

# ============================================================
# JSON OUTPUT
# ============================================================

cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","level":${LEVEL},"uefi_mode":"${UEFI_MODE}","efi_mount":"${EFI_MOUNT}","bootloader":"${BOOTLOADER}","recovery_partition_candidate_lines":${RECOVERY_PARTITION_LINES},"grub_recovery_entry_lines":${GRUB_RECOVERY_LINES},"systemd_boot_entry_lines":${SYSTEMD_BOOT_ENTRY_LINES},"out_dir":"${RUN_DIR}","level0_json":"${LEVEL0_JSON}","level1_tarball":$(if [ -n "$LEVEL1_TARBALL" ]; then echo "\"$LEVEL1_TARBALL\""; else echo "null"; fi),"level2_tarball":$(if [ -n "$LEVEL2_TARBALL" ]; then echo "\"$LEVEL2_TARBALL\""; else echo "null"; fi),"sha256":{"level1":$(if [ -n "$LEVEL1_SHA256" ]; then echo "\"$LEVEL1_SHA256\""; else echo "null"; fi),"level2":$(if [ -n "$LEVEL2_SHA256" ]; then echo "\"$LEVEL2_SHA256\""; else echo "null"; fi)},"missing_optional":$(array_to_json MISSING_OPTIONAL),"notes":"$(escape_json "$NOTES")"}
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
