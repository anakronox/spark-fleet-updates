#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# APT Signing Verification Reference Script
# Purpose: Verify cryptographic signing enforcement for all APT update artifacts
# Usage: sudo bash signing_verification.sh
# Output: Single-line JSON to stdout + persistent log file
# Exit: 0=PASS, 1=FAIL, 2=UNKNOWN
#
# Reference script for Canonical Landscape integration (Remote Script Execution)
# Minimal error handling - demonstration/reference purpose only

set -o pipefail

# --- Configuration (fallback to /tmp if default not writable) ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
LOG_DIR="${DGX_SPARK_MGMT_BASE_DIR:-/var/lib/dgx_spark_management}/attestable_conformance_regulatory/landscape_signing_verification"
if ! mkdir -p "${LOG_DIR}" 2>/dev/null; then
    LOG_DIR="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/attestable_conformance_regulatory/landscape_signing_verification"
    mkdir -p "${LOG_DIR}" 2>/dev/null || true
fi
LOG_FILE="${LOG_DIR}/apt-signature-verify-${RUN_ID}.log"

# --- JSON output fields (accumulated) ---
STATUS="UNKNOWN"
OS_PRETTY_NAME=""
APT_VERSION=""
GPGV_PRESENT=false
ALLOW_INSECURE_REPOS=false
INSECURE_SOURCE_FLAGS_FOUND=false
INSECURE_SOURCE_MATCHES=()
SIGNED_BY_LINES=()
APT_UPDATE_EXIT_CODE=-1
SIGNATURE_ERROR_MATCHES=()
GPGV_EVIDENCE_SAMPLE=()
NOTES="snap client confinement may limit access to /var/lib and /etc/apt"

# --- Helper: Escape JSON strings ---
escape_json() {
    local str="$1"
    # Basic escaping: quotes, backslashes, newlines
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//$'\n'/\\n}"
    str="${str//$'\r'/\\r}"
    str="${str//$'\t'/\\t}"
    echo "$str"
}

# --- Helper: Convert bash array to JSON array ---
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

# --- Baseline checks ---
echo "[$(date -u +"%Y-%m-%d %H:%M:%S UTC")] APT Signing Verification - START" >> "${LOG_FILE}" 2>&1

# OS info
if [ -f /etc/os-release ]; then
    OS_PRETTY_NAME=$(grep '^PRETTY_NAME=' /etc/os-release | cut -d= -f2- | tr -d '"')
fi

# APT version
if command -v apt-get >/dev/null 2>&1; then
    APT_VERSION=$(apt-get --version 2>/dev/null | head -n1 || echo "unknown")
else
    echo "ERROR: apt-get not found" >> "${LOG_FILE}"
    STATUS="UNKNOWN"
    # Print JSON and exit
    cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","os":"$(escape_json "$OS_PRETTY_NAME")","apt_version":"not found","gpgv_present":false,"allow_insecure_repos":false,"insecure_source_flags_found":false,"insecure_source_matches":[],"signed_by_lines":[],"apt_update_exit_code":-1,"signature_error_matches":[],"gpgv_evidence_sample":[],"log_path":"${LOG_FILE}","notes":"$(escape_json "$NOTES")"}
EOF
    exit 2
fi

# gpgv presence
if command -v gpgv >/dev/null 2>&1; then
    GPGV_PRESENT=true
fi

echo "OS: ${OS_PRETTY_NAME}" >> "${LOG_FILE}"
echo "APT Version: ${APT_VERSION}" >> "${LOG_FILE}"
echo "gpgv present: ${GPGV_PRESENT}" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"

# --- Fail-fast APT config check ---
echo "=== APT Config Check ===" >> "${LOG_FILE}"
if command -v apt-config >/dev/null 2>&1; then
    apt-config dump >> "${LOG_FILE}" 2>&1
    
    # Check for insecure settings
    APT_CONFIG_DUMP=$(apt-config dump 2>/dev/null || echo "")
    
    # Check AllowUnauthenticated
    if echo "$APT_CONFIG_DUMP" | grep -iq 'APT::Get::AllowUnauthenticated.*"true"'; then
        ALLOW_INSECURE_REPOS=true
    fi
    
    # Check AllowInsecureRepositories
    if echo "$APT_CONFIG_DUMP" | grep -iq 'Acquire::AllowInsecureRepositories.*"true"'; then
        ALLOW_INSECURE_REPOS=true
    fi
    
    # Check AllowDowngradeToInsecureRepositories
    if echo "$APT_CONFIG_DUMP" | grep -iq 'Acquire::AllowDowngradeToInsecureRepositories.*"true"'; then
        ALLOW_INSECURE_REPOS=true
    fi
    
    echo "Allow insecure repos config: ${ALLOW_INSECURE_REPOS}" >> "${LOG_FILE}"
    
    if [ "$ALLOW_INSECURE_REPOS" = true ]; then
        echo "FAIL: Insecure APT configuration detected" >> "${LOG_FILE}"
        STATUS="FAIL"
    fi
else
    echo "WARNING: apt-config not available" >> "${LOG_FILE}"
fi
echo "" >> "${LOG_FILE}"

# --- Sources scan ---
echo "=== Sources Scan ===" >> "${LOG_FILE}"

# Check sources.list
if [ -f /etc/apt/sources.list ]; then
    echo "Scanning /etc/apt/sources.list..." >> "${LOG_FILE}"
    
    # Check for insecure flags
    while IFS= read -r line; do
        line_num=$(echo "$line" | cut -d: -f1)
        line_content=$(echo "$line" | cut -d: -f2-)
        
        if echo "$line_content" | grep -Eq '(trusted=yes|allow-insecure=yes|Trusted:[ ]*yes|Allow-Insecure:[ ]*yes)'; then
            INSECURE_SOURCE_FLAGS_FOUND=true
            INSECURE_SOURCE_MATCHES+=("/etc/apt/sources.list:${line_num}:${line_content}")
        fi
        
        # Capture Signed-By usage (observation only)
        if echo "$line_content" | grep -Eq '(signed-by=|Signed-By:)'; then
            SIGNED_BY_LINES+=("/etc/apt/sources.list:${line_num}:${line_content}")
        fi
    done < <(grep -n . /etc/apt/sources.list 2>/dev/null)
fi

# Check sources.list.d
if [ -d /etc/apt/sources.list.d ]; then
    echo "Scanning /etc/apt/sources.list.d/..." >> "${LOG_FILE}"

    # Use nullglob to avoid errors if no files match
    shopt -s nullglob
    for source_file in /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
        if [ -f "$source_file" ]; then
            while IFS= read -r line; do
                line_num=$(echo "$line" | cut -d: -f1)
                line_content=$(echo "$line" | cut -d: -f2-)
                
                if echo "$line_content" | grep -Eq '(trusted=yes|allow-insecure=yes|Trusted:[ ]*yes|Allow-Insecure:[ ]*yes)'; then
                    INSECURE_SOURCE_FLAGS_FOUND=true
                    INSECURE_SOURCE_MATCHES+=("${source_file}:${line_num}:${line_content}")
                fi
                
                if echo "$line_content" | grep -Eq '(signed-by=|Signed-By:)'; then
                    SIGNED_BY_LINES+=("${source_file}:${line_num}:${line_content}")
                fi
            done < <(grep -n . "$source_file" 2>/dev/null)
        fi
    done
    shopt -u nullglob
fi

echo "Insecure source flags found: ${INSECURE_SOURCE_FLAGS_FOUND}" >> "${LOG_FILE}"
echo "Insecure matches count: ${#INSECURE_SOURCE_MATCHES[@]}" >> "${LOG_FILE}"
echo "Signed-By lines count: ${#SIGNED_BY_LINES[@]}" >> "${LOG_FILE}"

if [ "$INSECURE_SOURCE_FLAGS_FOUND" = true ]; then
    echo "FAIL: Insecure source flags detected" >> "${LOG_FILE}"
    for match in "${INSECURE_SOURCE_MATCHES[@]}"; do
        echo "  $match" >> "${LOG_FILE}"
    done
    STATUS="FAIL"
fi
echo "" >> "${LOG_FILE}"

# --- Signature verification via apt-get update ---
echo "=== APT Update with GPG Debug ===" >> "${LOG_FILE}"

# Run apt-get update with GPG debug and no-allow-insecure-repositories
APT_UPDATE_OUTPUT=$(apt-get --no-allow-insecure-repositories -o Debug::Acquire::gpgv=true update 2>&1)
APT_UPDATE_EXIT_CODE=$?

# Save full output to log
echo "$APT_UPDATE_OUTPUT" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"
echo "apt-get update exit code: ${APT_UPDATE_EXIT_CODE}" >> "${LOG_FILE}"

# Check for signature errors
while IFS= read -r line; do
    if echo "$line" | grep -Eq '(NO_PUBKEY|BADSIG|EXPKEYSIG|signatures couldn'"'"'t be verified|is not signed|GPG error:)'; then
        SIGNATURE_ERROR_MATCHES+=("$(escape_json "$line")")
    fi
done <<< "$APT_UPDATE_OUTPUT"

# Check for gpgv evidence
mapfile -t GPGV_EVIDENCE_TEMP < <(echo "$APT_UPDATE_OUTPUT" | grep -E '(GOODSIG|VALIDSIG|gpgv exited with status 0)' | head -n 10)
GPGV_EVIDENCE_SAMPLE=("${GPGV_EVIDENCE_TEMP[@]}")

echo "Signature errors found: ${#SIGNATURE_ERROR_MATCHES[@]}" >> "${LOG_FILE}"
echo "GPG evidence samples found: ${#GPGV_EVIDENCE_SAMPLE[@]}" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"

# --- Determine final status ---
if [ "$STATUS" != "FAIL" ]; then
    # Not already failed by config/sources checks
    
    if [ ${#SIGNATURE_ERROR_MATCHES[@]} -gt 0 ]; then
        STATUS="FAIL"
        echo "FAIL: Signature verification errors detected" >> "${LOG_FILE}"
    elif [ ${#GPGV_EVIDENCE_SAMPLE[@]} -eq 0 ] && [ $APT_UPDATE_EXIT_CODE -ne 0 ]; then
        STATUS="UNKNOWN"
        echo "UNKNOWN: No GPG verification evidence and apt update failed" >> "${LOG_FILE}"
    elif [ $APT_UPDATE_EXIT_CODE -eq 0 ]; then
        STATUS="PASS"
        echo "PASS: Signature verification enforced, no insecure settings" >> "${LOG_FILE}"
    else
        STATUS="UNKNOWN"
        echo "UNKNOWN: Unable to confirm signature verification" >> "${LOG_FILE}"
    fi
fi

echo "[$(date -u +"%Y-%m-%d %H:%M:%S UTC")] APT Signing Verification - END (${STATUS})" >> "${LOG_FILE}"

# --- Build and print JSON output ---
JSON_OUTPUT=$(cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","os":"$(escape_json "$OS_PRETTY_NAME")","apt_version":"$(escape_json "$APT_VERSION")","gpgv_present":${GPGV_PRESENT},"allow_insecure_repos":${ALLOW_INSECURE_REPOS},"insecure_source_flags_found":${INSECURE_SOURCE_FLAGS_FOUND},"insecure_source_matches":$(array_to_json INSECURE_SOURCE_MATCHES),"signed_by_lines":$(array_to_json SIGNED_BY_LINES),"apt_update_exit_code":${APT_UPDATE_EXIT_CODE},"signature_error_matches":$(array_to_json SIGNATURE_ERROR_MATCHES),"gpgv_evidence_sample":$(array_to_json GPGV_EVIDENCE_SAMPLE),"log_path":"${LOG_FILE}","notes":"$(escape_json "$NOTES")"}
EOF
)

echo "$JSON_OUTPUT"

# Exit 0 when we successfully produced JSON (PASS or UNKNOWN); exit 1 only for hard FAIL
case "$STATUS" in
    PASS)
        exit 0
        ;;
    FAIL)
        exit 1
        ;;
    *)
        exit 0
        ;;
esac
