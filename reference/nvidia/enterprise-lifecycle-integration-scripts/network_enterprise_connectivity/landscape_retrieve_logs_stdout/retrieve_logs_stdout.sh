#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Retrieve Logs to Stdout - Landscape Reference Script
# Purpose: Remote retrieval without interactive access via stdout (text or gzip+base64)
# Output: JSON header + payload between BEGIN/END markers
# Exit: 0=PASS (payload emitted), 1=FAIL (generation failed), 2=UNKNOWN (preset unavailable)
#
# Reference script for Canonical Landscape Remote Script Execution
# Minimal error handling - demonstration purpose

set -o pipefail

# --- Configuration ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
PRESET=""
ENCODING="b64gz"
MAX_BYTES=200000
OUT_DIR=""
BASE_DIR="/var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_retrieve_logs_stdout"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --preset)
            PRESET="$2"
            shift 2
            ;;
        --encoding)
            ENCODING="$2"
            shift 2
            ;;
        --max-bytes)
            MAX_BYTES="$2"
            shift 2
            ;;
        --out-dir)
            OUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

# --- Validate required arguments ---
if [ -z "$PRESET" ]; then
    echo '{"status":"FAIL","error":"--preset is required"}' >&2
    exit 2
fi

# --- Set output directory (fallback to /tmp if default not writable) ---
if [ -z "$OUT_DIR" ]; then
    OUT_DIR="${BASE_DIR}/run_${RUN_ID}"
fi
if ! mkdir -p "$OUT_DIR" 2>/dev/null; then
    BASE_DIR="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/network_enterprise_connectivity/landscape_retrieve_logs_stdout"
    OUT_DIR="${BASE_DIR}/run_${RUN_ID}"
    mkdir -p "$OUT_DIR" 2>/dev/null || {
        echo '{"status":"FAIL","error":"Failed to create output directory"}' >&2
        exit 1
    }
fi

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

# --- Generate or select source content based on preset ---
TEMP_SOURCE="${OUT_DIR}/_temp_source.txt"
TRUNCATED=false
SOURCE_BYTES=0

case "$PRESET" in
    journal_boot_tail)
        if ! command -v journalctl >/dev/null 2>&1; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"journalctl not available"}' >&2
            exit 2
        fi
        journalctl -b -o short-iso -n 2000 2>/dev/null | head -c "$MAX_BYTES" > "$TEMP_SOURCE"
        ;;
    
    journal_kernel_tail)
        if ! command -v journalctl >/dev/null 2>&1; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"journalctl not available"}' >&2
            exit 2
        fi
        journalctl -k -b -o short-iso -n 2000 2>/dev/null | head -c "$MAX_BYTES" > "$TEMP_SOURCE"
        ;;
    
    dmesg_T)
        if ! command -v dmesg >/dev/null 2>&1; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"dmesg not available"}' >&2
            exit 2
        fi
        dmesg -T 2>/dev/null | head -c "$MAX_BYTES" > "$TEMP_SOURCE"
        ;;
    
    systemd_failed)
        if ! command -v systemctl >/dev/null 2>&1; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"systemctl not available"}' >&2
            exit 2
        fi
        systemctl --failed 2>/dev/null | head -c "$MAX_BYTES" > "$TEMP_SOURCE"
        ;;
    
    apt_history)
        if [ ! -f /var/log/apt/history.log ]; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"apt history.log not found"}' >&2
            exit 2
        fi
        head -c "$MAX_BYTES" /var/log/apt/history.log > "$TEMP_SOURCE"
        ;;
    
    dpkg_log)
        if [ ! -f /var/log/dpkg.log ]; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"dpkg.log not found"}' >&2
            exit 2
        fi
        head -c "$MAX_BYTES" /var/log/dpkg.log > "$TEMP_SOURCE"
        ;;
    
    pstore_ls)
        if [ ! -d /sys/fs/pstore ]; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"pstore directory not found"}' >&2
            exit 2
        fi
        ls -al /sys/fs/pstore 2>/dev/null | head -c "$MAX_BYTES" > "$TEMP_SOURCE"
        ;;
    
    coredump_ls)
        if [ ! -d /var/lib/systemd/coredump ]; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"coredump directory not found"}' >&2
            exit 2
        fi
        ls -al /var/lib/systemd/coredump 2>/dev/null | head -c "$MAX_BYTES" > "$TEMP_SOURCE"
        ;;
    
    crash_ls)
        if [ ! -d /var/crash ]; then
            echo '{"status":"UNKNOWN","preset":"'"$PRESET"'","error":"crash directory not found"}' >&2
            exit 2
        fi
        ls -al /var/crash 2>/dev/null | head -c "$MAX_BYTES" > "$TEMP_SOURCE"
        ;;
    
    *)
        echo '{"status":"FAIL","preset":"'"$PRESET"'","error":"Unknown preset"}' >&2
        exit 2
        ;;
esac

# --- Check if source was generated ---
if [ ! -f "$TEMP_SOURCE" ]; then
    echo '{"status":"FAIL","preset":"'"$PRESET"'","error":"Source generation failed"}' >&2
    exit 1
fi

# --- Calculate source bytes and check truncation ---
SOURCE_BYTES=$(stat -c%s "$TEMP_SOURCE" 2>/dev/null || echo 0)

# Check if content was likely truncated (rough heuristic)
if [ "$SOURCE_BYTES" -ge "$MAX_BYTES" ]; then
    TRUNCATED=true
fi

# --- Compute SHA256 of original content ---
SOURCE_SHA256=$(sha256sum "$TEMP_SOURCE" | awk '{print $1}')

# --- Encode and save based on encoding ---
OUT_PATH=""
DECODE_HINT=""

if [ "$ENCODING" = "text" ]; then
    OUT_PATH="${OUT_DIR}/${PRESET}.txt"
    cp "$TEMP_SOURCE" "$OUT_PATH"
    PAYLOAD_CONTENT=$(cat "$TEMP_SOURCE")
    DECODE_HINT="none (plaintext)"
    
elif [ "$ENCODING" = "b64gz" ]; then
    OUT_PATH="${OUT_DIR}/${PRESET}.txt.gz"
    
    # Gzip the source
    gzip -c "$TEMP_SOURCE" > "$OUT_PATH" 2>/dev/null || {
        echo '{"status":"FAIL","preset":"'"$PRESET"'","error":"gzip failed"}' >&2
        exit 1
    }
    
    # Base64 encode for stdout
    PAYLOAD_CONTENT=$(base64 -w 0 < "$OUT_PATH" 2>/dev/null)
    DECODE_HINT="base64 -d | gunzip"
    
    # Also save base64 version for convenience
    echo "$PAYLOAD_CONTENT" > "${OUT_PATH}.b64"
    
else
    echo '{"status":"FAIL","preset":"'"$PRESET"'","error":"Unknown encoding"}' >&2
    exit 2
fi

# --- Build JSON header ---
JSON_HEADER=$(cat <<EOF
{"status":"PASS","run_id":"${RUN_ID}","preset":"${PRESET}","encoding":"${ENCODING}","max_bytes":${MAX_BYTES},"truncated":${TRUNCATED},"source_bytes":${SOURCE_BYTES},"sha256":"${SOURCE_SHA256}","out_path":"${OUT_PATH}","decode_hint":"${DECODE_HINT}","markers":{"begin":"BEGIN_DGX_PAYLOAD","end":"END_DGX_PAYLOAD"},"notes":"Landscape output limited by script_output_limit; keep payload small"}
EOF
)

# --- Output: JSON header + payload with markers ---
echo "$JSON_HEADER"
echo "BEGIN_DGX_PAYLOAD"
echo "$PAYLOAD_CONTENT"
echo "END_DGX_PAYLOAD"

# --- Cleanup temp ---
rm -f "$TEMP_SOURCE"

exit 0
