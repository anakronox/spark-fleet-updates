#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Collect Package - Landscape Reference Script
# Purpose: Generate standardized support bundle locally (tar.gz + checksums)
# Output: Single-line JSON summary to stdout
# Exit: 0=PASS (bundle created), 1=FAIL (creation failed), 2=UNKNOWN (missing prereqs)
#
# Reference script for Canonical Landscape Remote Script Execution
# Minimal error handling - demonstration purpose

set -o pipefail

# --- Configuration ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
BASE_DIR="${DGX_SPARK_MGMT_BASE_DIR:-/var/lib/dgx_spark_management}/network_enterprise_connectivity/landscape_collect_package"
if ! mkdir -p "${BASE_DIR}/run_${RUN_ID}/payload" 2>/dev/null; then
    BASE_DIR="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/network_enterprise_connectivity/landscape_collect_package"
    mkdir -p "${BASE_DIR}/run_${RUN_ID}/payload" 2>/dev/null || true
fi
RUN_DIR="${BASE_DIR}/run_${RUN_ID}"
PAYLOAD_DIR="${RUN_DIR}/payload"
BUNDLE_NAME="dgx_collect_package_${RUN_ID}.tar.gz"
BUNDLE_PATH="${RUN_DIR}/${BUNDLE_NAME}"
CHECKSUMS_FILE="${RUN_DIR}/payload_sha256sums.txt"

# --- JSON output fields ---
STATUS="UNKNOWN"
BUNDLE_SHA256=""
BUNDLE_SIZE=0
PAYLOAD_FILES=0
COLLECTED_ITEMS=()
MISSING_OPTIONAL=()
NOTES="Landscape stdout is size-limited by script_output_limit; bundle is local only"

# --- Helper: Escape JSON strings ---
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

# --- Check prerequisites ---
if ! command -v tar >/dev/null 2>&1; then
    echo '{"status":"UNKNOWN","run_id":"'"${RUN_ID}"'","bundle_path":"","bundle_sha256":"","bundle_size_bytes":0,"payload_files":0,"collected_items":[],"missing_optional":[],"notes":"tar command not found"}'
    exit 2
fi

if ! command -v sha256sum >/dev/null 2>&1; then
    echo '{"status":"UNKNOWN","run_id":"'"${RUN_ID}"'","bundle_path":"","bundle_sha256":"","bundle_size_bytes":0,"payload_files":0,"collected_items":[],"missing_optional":[],"notes":"sha256sum command not found"}'
    exit 2
fi

# --- Ensure payload dir exists (already created above with fallback) ---
if [ ! -d "${PAYLOAD_DIR}" ]; then
    echo '{"status":"FAIL","run_id":"'"${RUN_ID}"'","bundle_path":"","bundle_sha256":"","bundle_size_bytes":0,"payload_files":0,"collected_items":[],"missing_optional":[],"notes":"Failed to create payload directory"}'
    exit 1
fi

# --- Collect: /etc/os-release ---
if [ -f /etc/os-release ]; then
    cp /etc/os-release "${PAYLOAD_DIR}/os-release" 2>/dev/null && COLLECTED_ITEMS+=("os-release")
else
    MISSING_OPTIONAL+=("os-release")
fi

# --- Collect: uname -a ---
if command -v uname >/dev/null 2>&1; then
    uname -a > "${PAYLOAD_DIR}/uname.txt" 2>/dev/null && COLLECTED_ITEMS+=("uname.txt")
else
    MISSING_OPTIONAL+=("uname")
fi

# --- Collect: journalctl boot tail ---
if command -v journalctl >/dev/null 2>&1; then
    journalctl -b -o short-iso -n 2000 > "${PAYLOAD_DIR}/journal_boot_tail.txt" 2>/dev/null && COLLECTED_ITEMS+=("journal_boot_tail.txt")
else
    MISSING_OPTIONAL+=("journalctl_boot")
fi

# --- Collect: journalctl kernel tail ---
if command -v journalctl >/dev/null 2>&1; then
    journalctl -k -b -o short-iso -n 2000 > "${PAYLOAD_DIR}/journal_kernel_tail.txt" 2>/dev/null && COLLECTED_ITEMS+=("journal_kernel_tail.txt")
else
    MISSING_OPTIONAL+=("journalctl_kernel")
fi

# --- Collect: dmesg -T ---
if command -v dmesg >/dev/null 2>&1; then
    dmesg -T > "${PAYLOAD_DIR}/dmesg_T.txt" 2>/dev/null && COLLECTED_ITEMS+=("dmesg_T.txt")
else
    MISSING_OPTIONAL+=("dmesg")
fi

# --- Collect: systemctl --failed ---
if command -v systemctl >/dev/null 2>&1; then
    systemctl --failed > "${PAYLOAD_DIR}/systemd_failed.txt" 2>/dev/null && COLLECTED_ITEMS+=("systemd_failed.txt")
else
    MISSING_OPTIONAL+=("systemctl_failed")
fi

# --- Collect: APT logs (optional) ---
if [ -f /var/log/apt/history.log ]; then
    cp /var/log/apt/history.log "${PAYLOAD_DIR}/apt_history.log" 2>/dev/null && COLLECTED_ITEMS+=("apt_history.log")
else
    MISSING_OPTIONAL+=("apt_history.log")
fi

if [ -f /var/log/apt/term.log ]; then
    cp /var/log/apt/term.log "${PAYLOAD_DIR}/apt_term.log" 2>/dev/null && COLLECTED_ITEMS+=("apt_term.log")
else
    MISSING_OPTIONAL+=("apt_term.log")
fi

if [ -f /var/log/dpkg.log ]; then
    cp /var/log/dpkg.log "${PAYLOAD_DIR}/dpkg.log" 2>/dev/null && COLLECTED_ITEMS+=("dpkg.log")
else
    MISSING_OPTIONAL+=("dpkg.log")
fi

# --- Collect: Dump indicators (listings only) ---
if [ -d /var/lib/systemd/coredump ]; then
    ls -al /var/lib/systemd/coredump > "${PAYLOAD_DIR}/_var_lib_systemd_coredump_ls.txt" 2>/dev/null && COLLECTED_ITEMS+=("coredump_ls")
else
    MISSING_OPTIONAL+=("coredump_ls")
fi

if [ -d /sys/fs/pstore ]; then
    ls -al /sys/fs/pstore > "${PAYLOAD_DIR}/_sys_fs_pstore_ls.txt" 2>/dev/null && COLLECTED_ITEMS+=("pstore_ls")
else
    MISSING_OPTIONAL+=("pstore_ls")
fi

if [ -d /var/crash ]; then
    ls -al /var/crash > "${PAYLOAD_DIR}/_var_crash_ls.txt" 2>/dev/null && COLLECTED_ITEMS+=("crash_ls")
else
    MISSING_OPTIONAL+=("crash_ls")
fi

# --- Collect: Existing DGX Spark tool outputs (copy only) ---
DIAG_JSON="/var/lib/dgx_spark_management/remote_ops_remediation/diagnostic_collector/diagnostics_full.json"
if [ -f "$DIAG_JSON" ]; then
    cp "$DIAG_JSON" "${PAYLOAD_DIR}/diagnostics_full.json" 2>/dev/null && COLLECTED_ITEMS+=("diagnostics_full.json")
else
    MISSING_OPTIONAL+=("diagnostics_full.json")
fi

RESET_JSON="/var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter/reset_reason_report.json"
if [ -f "$RESET_JSON" ]; then
    cp "$RESET_JSON" "${PAYLOAD_DIR}/reset_reason_report.json" 2>/dev/null && COLLECTED_ITEMS+=("reset_reason_report.json")
else
    MISSING_OPTIONAL+=("reset_reason_report.json")
fi

UPDATE_JSON="/var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane/status.json"
if [ -f "$UPDATE_JSON" ]; then
    cp "$UPDATE_JSON" "${PAYLOAD_DIR}/update_control_status.json" 2>/dev/null && COLLECTED_ITEMS+=("update_control_status.json")
else
    MISSING_OPTIONAL+=("update_control_status.json")
fi

# --- Generate checksums ---
(cd "${PAYLOAD_DIR}" && find . -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum > "${CHECKSUMS_FILE}" 2>/dev/null)

if [ -f "${CHECKSUMS_FILE}" ]; then
    COLLECTED_ITEMS+=("payload_sha256sums.txt")
fi

# --- Count payload files ---
PAYLOAD_FILES=$(find "${PAYLOAD_DIR}" -maxdepth 1 -type f | wc -l)

# --- Create bundle ---
(cd "${RUN_DIR}" && tar -czf "${BUNDLE_NAME}" payload payload_sha256sums.txt 2>/dev/null)

if [ -f "${BUNDLE_PATH}" ]; then
    STATUS="PASS"
    BUNDLE_SHA256=$(sha256sum "${BUNDLE_PATH}" | awk '{print $1}')
    BUNDLE_SIZE=$(stat -c%s "${BUNDLE_PATH}" 2>/dev/null || echo 0)
else
    STATUS="FAIL"
    echo '{"status":"FAIL","run_id":"'"${RUN_ID}"'","bundle_path":"","bundle_sha256":"","bundle_size_bytes":0,"payload_files":'"${PAYLOAD_FILES}"',"collected_items":'"$(array_to_json COLLECTED_ITEMS)"',"missing_optional":'"$(array_to_json MISSING_OPTIONAL)"',"notes":"Bundle creation failed"}'
    exit 1
fi

# --- Output JSON ---
cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","bundle_path":"${BUNDLE_PATH}","bundle_sha256":"${BUNDLE_SHA256}","bundle_size_bytes":${BUNDLE_SIZE},"payload_files":${PAYLOAD_FILES},"collected_items":$(array_to_json COLLECTED_ITEMS),"missing_optional":$(array_to_json MISSING_OPTIONAL),"notes":"$(escape_json "$NOTES")"}
EOF

exit 0
