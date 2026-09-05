#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Health Watchdogs - Landscape Reference Script
# Purpose: Probe watchdog configuration + optional self-test with transient units
# Output: Single-line JSON to stdout + evidence files
# Exit: 0=PASS, 1=FAIL, 2=UNKNOWN

set -o pipefail

# --- Default Configuration ---
MODE="probe"
SELF_TEST=false
EXECUTE=false
CONFIRM=""
OUT_ROOT="/var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_health_watchdogs"

# --- Parse CLI ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --self-test) SELF_TEST=true; MODE="self_test"; shift ;;
        --execute) EXECUTE=true; shift ;;
        --confirm) CONFIRM="$2"; shift 2 ;;
        --out-root) OUT_ROOT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# --- Setup (fallback to /tmp if default not writable) ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
EVIDENCE_DIR="${RUN_DIR}/evidence"
if ! mkdir -p "${EVIDENCE_DIR}" 2>/dev/null; then
    OUT_ROOT="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/resilience_recovery_rollback/landscape_health_watchdogs"
    RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
    EVIDENCE_DIR="${RUN_DIR}/evidence"
    mkdir -p "${EVIDENCE_DIR}" 2>/dev/null || {
        echo '{"status":"UNKNOWN","error":"Failed to create output directory"}'
        exit 2
    }
fi

# --- JSON Output Fields ---
STATUS="UNKNOWN"
WATCHDOG_DEVICE_PRESENT=false
WATCHDOG_DEVICE_PATH="null"
WDCTL_PRESENT=false
WDCTL_TIMEOUT_SECONDS="null"
WDCTL_SETTIMEOUT_SUPPORTED="null"
SYSFS_IDENTITY="null"
SYSFS_TIMEOUT="null"
SYSFS_NOWAYOUT="null"
SYSFS_STATE="null"
SYSFS_STATUS="null"
SYSFS_TIMELEFT="null"
SYSTEMD_RUNTIME_WATCHDOG="null"
SYSTEMD_SHUTDOWN_WATCHDOG="null"
SYSTEMD_WATCHDOG_DEVICE="null"
SERVICES=()
RESTART_TEST_RAN=false
RESTART_TEST_NRESTARTS="null"
RESTART_TEST_RESULT="null"
WATCHDOG_TEST_RAN=false
WATCHDOG_TEST_NRESTARTS="null"
WATCHDOG_TEST_RESULT="null"
WATCHDOG_TIMEOUT_SEEN=false
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
if ! command -v systemctl >/dev/null 2>&1; then
    FAIL_REASONS+=("systemctl not found")
    STATUS="UNKNOWN"
    echo "{\"status\":\"${STATUS}\",\"fail_reasons\":$(array_to_json FAIL_REASONS)}"
    exit 2
fi

if ! command -v journalctl >/dev/null 2>&1; then
    FAIL_REASONS+=("journalctl not found")
    STATUS="UNKNOWN"
    echo "{\"status\":\"${STATUS}\",\"fail_reasons\":$(array_to_json FAIL_REASONS)}"
    exit 2
fi

# ============================================================
# PROBE MODE (always run)
# ============================================================

# 1) systemd manager watchdog settings
systemctl show -p RuntimeWatchdogUSec -p ShutdownWatchdogUSec -p WatchdogDevice > "${EVIDENCE_DIR}/systemd_manager_watchdog.txt" 2>/dev/null && EVIDENCE_FILES+=("systemd_manager_watchdog.txt")

if [ -f "${EVIDENCE_DIR}/systemd_manager_watchdog.txt" ]; then
    SYSTEMD_RUNTIME_WATCHDOG=$(grep '^RuntimeWatchdogUSec=' "${EVIDENCE_DIR}/systemd_manager_watchdog.txt" | cut -d= -f2)
    SYSTEMD_SHUTDOWN_WATCHDOG=$(grep '^ShutdownWatchdogUSec=' "${EVIDENCE_DIR}/systemd_manager_watchdog.txt" | cut -d= -f2)
    SYSTEMD_WATCHDOG_DEVICE=$(grep '^WatchdogDevice=' "${EVIDENCE_DIR}/systemd_manager_watchdog.txt" | cut -d= -f2)
fi

# 2) Hardware watchdog presence
ls -l /dev/watchdog* > "${EVIDENCE_DIR}/dev_watchdog_list.txt" 2>/dev/null && EVIDENCE_FILES+=("dev_watchdog_list.txt")
ls -al /sys/class/watchdog > "${EVIDENCE_DIR}/sysfs_watchdog_class.txt" 2>/dev/null && EVIDENCE_FILES+=("sysfs_watchdog_class.txt")

if [ -e /dev/watchdog0 ]; then
    WATCHDOG_DEVICE_PRESENT=true
    WATCHDOG_DEVICE_PATH="/dev/watchdog0"
fi

# 3) sysfs watchdog0 fields
if [ -d /sys/class/watchdog/watchdog0 ]; then
    WATCHDOG_DEVICE_PRESENT=true
    [ "$WATCHDOG_DEVICE_PATH" = "null" ] && WATCHDOG_DEVICE_PATH="/sys/class/watchdog/watchdog0"
    
    SYSFS_IDENTITY=$(cat /sys/class/watchdog/watchdog0/identity 2>/dev/null || echo "null")
    SYSFS_TIMEOUT=$(cat /sys/class/watchdog/watchdog0/timeout 2>/dev/null || echo "null")
    SYSFS_NOWAYOUT=$(cat /sys/class/watchdog/watchdog0/nowayout 2>/dev/null || echo "null")
    SYSFS_STATE=$(cat /sys/class/watchdog/watchdog0/state 2>/dev/null || echo "null")
    SYSFS_STATUS=$(cat /sys/class/watchdog/watchdog0/status 2>/dev/null || echo "null")
    SYSFS_TIMELEFT=$(cat /sys/class/watchdog/watchdog0/timeleft 2>/dev/null || echo "null")
    
    {
        echo "identity: $SYSFS_IDENTITY"
        echo "timeout: $SYSFS_TIMEOUT"
        echo "nowayout: $SYSFS_NOWAYOUT"
        echo "state: $SYSFS_STATE"
        echo "status: $SYSFS_STATUS"
        echo "timeleft: $SYSFS_TIMELEFT"
    } > "${EVIDENCE_DIR}/sysfs_watchdog0_fields.txt" && EVIDENCE_FILES+=("sysfs_watchdog0_fields.txt")
fi

# 4) wdctl output
if command -v wdctl >/dev/null 2>&1; then
    WDCTL_PRESENT=true
    wdctl /dev/watchdog0 > "${EVIDENCE_DIR}/wdctl_watchdog0.txt" 2>/dev/null && EVIDENCE_FILES+=("wdctl_watchdog0.txt")
    
    if [ -f "${EVIDENCE_DIR}/wdctl_watchdog0.txt" ]; then
        WDCTL_TIMEOUT_SECONDS=$(grep -i 'timeout' "${EVIDENCE_DIR}/wdctl_watchdog0.txt" | grep -oE '[0-9]+' | head -n1)
        grep -qi 'SETTIMEOUT' "${EVIDENCE_DIR}/wdctl_watchdog0.txt" && WDCTL_SETTIMEOUT_SUPPORTED=true || WDCTL_SETTIMEOUT_SUPPORTED=false
    fi
fi

# 5) fuser check
if command -v fuser >/dev/null 2>&1 && [ -e /dev/watchdog0 ]; then
    fuser -v /dev/watchdog0 > "${EVIDENCE_DIR}/fuser_watchdog0.txt" 2>&1 && EVIDENCE_FILES+=("fuser_watchdog0.txt")
fi

# 6) kernel journal watchdog lines
journalctl -k -b 2>/dev/null | grep -i watchdog | tail -n120 > "${EVIDENCE_DIR}/journal_kernel_watchdog.txt" 2>/dev/null && EVIDENCE_FILES+=("journal_kernel_watchdog.txt")

# 7) Service policy snapshot
PROBE_SERVICES=("ssh.service" "NetworkManager.service" "systemd-journald.service")
for unit in "${PROBE_SERVICES[@]}"; do
    if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
        systemctl show "$unit" -p Restart -p RestartUSec -p WatchdogUSec -p WatchdogTimestamp -p NRestarts -p ActiveState -p StartLimitIntervalUSec -p StartLimitBurst > "${EVIDENCE_DIR}/service_${unit}.txt" 2>/dev/null && EVIDENCE_FILES+=("service_${unit}.txt")
        
        if [ -f "${EVIDENCE_DIR}/service_${unit}.txt" ]; then
            SERVICES+=("{\"unit\":\"$unit\",\"file\":\"service_${unit}.txt\"}")
        fi
    fi
done

# ============================================================
# SELF-TEST MODE (gated)
# ============================================================

if [ "$SELF_TEST" = true ]; then
    if [ "$EXECUTE" != true ] || [ "$CONFIRM" != "FACTORY_TEST_EXECUTE" ]; then
        FAIL_REASONS+=("Self-test requires --execute --confirm=FACTORY_TEST_EXECUTE")
        STATUS="FAIL"
    else
        # TEST 1: Auto-restart test
        RESTART_UNIT="dgx-restart-test-${RUN_ID}.service"
        
        systemd-run --unit="$RESTART_UNIT" \
            --property=Restart=always \
            --property=RestartSec=1 \
            /bin/sh -c 'exit 1' >/dev/null 2>&1
        
        if [ $? -eq 0 ]; then
            RESTART_TEST_RAN=true
            sleep 5
            
            systemctl show "$RESTART_UNIT" -p ActiveState -p Result -p ExecMainStatus -p NRestarts > "${EVIDENCE_DIR}/restart_test_status.txt" 2>/dev/null && EVIDENCE_FILES+=("restart_test_status.txt")
            journalctl -u "$RESTART_UNIT" -n80 > "${EVIDENCE_DIR}/restart_test_journal.txt" 2>/dev/null && EVIDENCE_FILES+=("restart_test_journal.txt")
            
            if [ -f "${EVIDENCE_DIR}/restart_test_status.txt" ]; then
                RESTART_TEST_NRESTARTS=$(grep '^NRestarts=' "${EVIDENCE_DIR}/restart_test_status.txt" | cut -d= -f2)
                RESTART_TEST_RESULT=$(grep '^Result=' "${EVIDENCE_DIR}/restart_test_status.txt" | cut -d= -f2)
            fi
            
            systemctl stop "$RESTART_UNIT" 2>/dev/null
        else
            FAIL_REASONS+=("Failed to create restart test unit")
        fi
        
        # TEST 2: Watchdog timeout test
        if command -v systemd-notify >/dev/null 2>&1; then
            WATCHDOG_UNIT="dgx-watchdog-test-${RUN_ID}.service"
            
            systemd-run --unit="$WATCHDOG_UNIT" \
                --property=Type=notify \
                --property=WatchdogSec=5s \
                --property=Restart=always \
                --property=RestartSec=1 \
                /bin/sh -c 'systemd-notify --ready; echo "READY:$(date -u +%Y%m%dT%H%M%SZ)"; sleep 1000' >/dev/null 2>&1
            
            if [ $? -eq 0 ]; then
                WATCHDOG_TEST_RAN=true
                sleep 12
                
                systemctl show "$WATCHDOG_UNIT" -p ActiveState -p Result -p ExecMainStatus -p NRestarts -p WatchdogUSec > "${EVIDENCE_DIR}/watchdog_test_status.txt" 2>/dev/null && EVIDENCE_FILES+=("watchdog_test_status.txt")
                journalctl -u "$WATCHDOG_UNIT" -n200 > "${EVIDENCE_DIR}/watchdog_test_journal.txt" 2>/dev/null && EVIDENCE_FILES+=("watchdog_test_journal.txt")
                
                if [ -f "${EVIDENCE_DIR}/watchdog_test_status.txt" ]; then
                    WATCHDOG_TEST_NRESTARTS=$(grep '^NRestarts=' "${EVIDENCE_DIR}/watchdog_test_status.txt" | cut -d= -f2)
                    WATCHDOG_TEST_RESULT=$(grep '^Result=' "${EVIDENCE_DIR}/watchdog_test_status.txt" | cut -d= -f2)
                fi
                
                if [ -f "${EVIDENCE_DIR}/watchdog_test_journal.txt" ]; then
                    if grep -qEi 'watchdog|timeout|killed|READY|start' "${EVIDENCE_DIR}/watchdog_test_journal.txt"; then
                        grep -qEi 'watchdog.*timeout|watchdog.*failed' "${EVIDENCE_DIR}/watchdog_test_journal.txt" && WATCHDOG_TIMEOUT_SEEN=true
                        [ "$WATCHDOG_TEST_RESULT" = "watchdog" ] && WATCHDOG_TIMEOUT_SEEN=true
                    fi
                fi
                
                systemctl stop "$WATCHDOG_UNIT" 2>/dev/null
            else
                FAIL_REASONS+=("Failed to create watchdog test unit")
            fi
        fi
        
        # Status logic for self-test
        if [ "$RESTART_TEST_RAN" = true ] && [ "$RESTART_TEST_NRESTARTS" != "null" ] && [ "$RESTART_TEST_NRESTARTS" -ge 1 ]; then
            if [ "$WATCHDOG_TEST_RAN" = true ]; then
                if [ "$WATCHDOG_TIMEOUT_SEEN" = true ] || ([ "$WATCHDOG_TEST_RESULT" = "watchdog" ] && [ "$WATCHDOG_TEST_NRESTARTS" -ge 1 ]); then
                    STATUS="PASS"
                else
                    FAIL_REASONS+=("Watchdog test did not detect timeout/restart")
                    STATUS="FAIL"
                fi
            else
                STATUS="PASS"  # Restart test passed, watchdog test skipped
            fi
        else
            FAIL_REASONS+=("Restart test failed to show restarts")
            STATUS="FAIL"
        fi
    fi
else
    # Probe mode status logic
    if [ "$WATCHDOG_DEVICE_PRESENT" = true ] && [ ${#EVIDENCE_FILES[@]} -gt 0 ]; then
        STATUS="PASS"
    else
        FAIL_REASONS+=("No watchdog device found or no evidence collected")
        STATUS="UNKNOWN"
    fi
fi

# ============================================================
# JSON OUTPUT
# ============================================================

# Build services array
SERVICES_JSON="["
if [ ${#SERVICES[@]} -gt 0 ]; then
    first=true
    for svc in "${SERVICES[@]}"; do
        [ "$first" = false ] && SERVICES_JSON+=","
        first=false
        SERVICES_JSON+="$svc"
    done
fi
SERVICES_JSON+="]"

cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","mode":"${MODE}","watchdog_device_present":${WATCHDOG_DEVICE_PRESENT},"watchdog_device_path":"${WATCHDOG_DEVICE_PATH}","wdctl_present":${WDCTL_PRESENT},"wdctl_timeout_seconds":${WDCTL_TIMEOUT_SECONDS},"wdctl_settimeout_supported":${WDCTL_SETTIMEOUT_SUPPORTED},"sysfs":{"identity":"${SYSFS_IDENTITY}","timeout":"${SYSFS_TIMEOUT}","nowayout":"${SYSFS_NOWAYOUT}","state":"${SYSFS_STATE}","status":"${SYSFS_STATUS}","timeleft":"${SYSFS_TIMELEFT}"},"systemd_manager":{"RuntimeWatchdogUSec":"${SYSTEMD_RUNTIME_WATCHDOG}","ShutdownWatchdogUSec":"${SYSTEMD_SHUTDOWN_WATCHDOG}","WatchdogDevice":"${SYSTEMD_WATCHDOG_DEVICE}"},"services":${SERVICES_JSON},"self_test":{"restart_test":{"ran":${RESTART_TEST_RAN},"nrestarts":"${RESTART_TEST_NRESTARTS}","result":"${RESTART_TEST_RESULT}"},"watchdog_test":{"ran":${WATCHDOG_TEST_RAN},"nrestarts":"${WATCHDOG_TEST_NRESTARTS}","result":"${WATCHDOG_TEST_RESULT}","watchdog_timeout_seen":${WATCHDOG_TIMEOUT_SEEN}}},"out_dir":"${RUN_DIR}","evidence_files":$(array_to_json EVIDENCE_FILES),"fail_reasons":$(array_to_json FAIL_REASONS),"notes":"Hardware watchdog exists on DGX Spark but systemd RuntimeWatchdog is disabled by default; self-test uses transient units and must be explicitly executed."}
EOF

case "$STATUS" in
    PASS) exit 0 ;;
    FAIL) exit 1 ;;
    *) exit 2 ;;
esac
