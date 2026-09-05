#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Factory Reset with Secure Re-provisioning - Landscape Reference Script
# Purpose: Probe reset readiness + generate plan + gated execution for deprovisioning
# Output: Single-line JSON to stdout + plan file + evidence files
# Exit: 0=PASS, 1=FAIL, 2=UNKNOWN
#
# Reference script for Canonical Landscape Remote Script Execution

set -o pipefail

# --- Default Configuration ---
LEVEL=0
MODE="plan"
CONFIRM=""
PRESERVE_NETWORK=true
PRESERVE_USERS=true
DETACH_PRO=false
REENABLE_CLOUD_INIT=false
OUT_ROOT="/var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_factory_reset_reprovision"

# --- Parse CLI ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --level) LEVEL="$2"; shift 2 ;;
        --plan) MODE="plan"; shift ;;
        --execute) MODE="execute"; shift ;;
        --confirm) CONFIRM="$2"; shift 2 ;;
        --preserve-network) PRESERVE_NETWORK="$2"; shift 2 ;;
        --preserve-users) PRESERVE_USERS="$2"; shift 2 ;;
        --detach-pro) DETACH_PRO="$2"; shift 2 ;;
        --reenable-cloud-init) REENABLE_CLOUD_INIT="$2"; shift 2 ;;
        --out-root) OUT_ROOT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# --- Setup (fallback to /tmp if default not writable) ---
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
EVIDENCE_DIR="${RUN_DIR}/evidence"
PLAN_FILE="${RUN_DIR}/factory_reset_plan.txt"
if ! mkdir -p "${EVIDENCE_DIR}" 2>/dev/null; then
    OUT_ROOT="/tmp/dgx_spark_management_$(id -u 2>/dev/null || echo 'unknown')/resilience_recovery_rollback/landscape_factory_reset_reprovision"
    RUN_DIR="${OUT_ROOT}/run_${RUN_ID}"
    EVIDENCE_DIR="${RUN_DIR}/evidence"
    PLAN_FILE="${RUN_DIR}/factory_reset_plan.txt"
    mkdir -p "${EVIDENCE_DIR}" 2>/dev/null || {
        echo '{"status":"UNKNOWN","error":"Failed to create output directory"}'
        exit 2
    }
fi

# --- JSON Output Fields (initial) ---
STATUS="PASS"
UEFI_MODE=false
BOOTLOADER="UNKNOWN"
GRUB_RECOVERY_LINES=-1
PRO_PRESENT=false
PRO_ATTACHED=false
LANDSCAPE_SERVICE_AVAILABLE="unknown"
LANDSCAPE_SERVICE_STATUS="null"
LANDSCAPE_CONFIG_PRESENT=false
LANDSCAPE_CLIENT_INSTALLED=false
CLOUD_INIT_PRESENT=false
CLOUD_INIT_DISABLED_MARKER=false
MACHINE_ID_PRESENT=false
SSH_HOSTKEY_COUNT=0
NM_CONNECTION_COUNT=0
SECURE_ERASE_TOOL=false
UPDATE_CTL_TOOL=false
DIAG_CTL_TOOL=false
ACTIONS_TAKEN=()
MISSING_OPTIONAL=()
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

# ============================================================
# PROBE (always run)
# ============================================================

# 1) Boot / Recovery Entry Points
if [ -d /sys/firmware/efi ]; then
    UEFI_MODE=true
fi

if [ -f /boot/grub/grub.cfg ]; then
    BOOTLOADER="grub"
    if grep -nEi 'recovery mode|rescue target|emergency target' /boot/grub/grub.cfg > "${EVIDENCE_DIR}/grub_recovery_grep.txt" 2>/dev/null; then
        GRUB_RECOVERY_LINES=$(wc -l < "${EVIDENCE_DIR}/grub_recovery_grep.txt")
    else
        MISSING_OPTIONAL+=("grub_cfg_permission_denied")
        GRUB_RECOVERY_LINES=-1
    fi
elif command -v bootctl >/dev/null 2>&1 && bootctl status >/dev/null 2>&1; then
    BOOTLOADER="systemd-boot"
    bootctl status > "${EVIDENCE_DIR}/bootctl_status.txt" 2>/dev/null || true
fi

# 2) Ubuntu Pro / Landscape Surfaces
if command -v pro >/dev/null 2>&1; then
    PRO_PRESENT=true
    pro status --format json > "${EVIDENCE_DIR}/pro_status.json" 2>/dev/null || true
    
    if [ -f "${EVIDENCE_DIR}/pro_status.json" ]; then
        PRO_ATTACHED=$(python3 -c "import json,sys; d=json.load(open('${EVIDENCE_DIR}/pro_status.json')); print('true' if d.get('attached') else 'false')" 2>/dev/null || echo "false")
        
        LANDSCAPE_SERVICE_AVAILABLE=$(python3 -c "import json,sys; d=json.load(open('${EVIDENCE_DIR}/pro_status.json')); services=d.get('services',[]); ls=[s for s in services if s.get('name')=='landscape']; print('yes' if ls and ls[0].get('available') else 'no')" 2>/dev/null || echo "unknown")
        
        if [ "$LANDSCAPE_SERVICE_AVAILABLE" = "yes" ]; then
            LANDSCAPE_SERVICE_STATUS=$(python3 -c "import json,sys; d=json.load(open('${EVIDENCE_DIR}/pro_status.json')); services=d.get('services',[]); ls=[s for s in services if s.get('name')=='landscape']; print(ls[0].get('status','null') if ls else 'null')" 2>/dev/null || echo "null")
        fi
    fi
    
    pro status 2>/dev/null | head -n60 > "${EVIDENCE_DIR}/pro_status_head.txt" || true
fi

# 3) Landscape Client State
if command -v dpkg >/dev/null 2>&1; then
    dpkg -l 2>/dev/null | grep -E '^ii.*landscape' > "${EVIDENCE_DIR}/landscape_pkgs.txt" 2>/dev/null || true
    [ -s "${EVIDENCE_DIR}/landscape_pkgs.txt" ] && LANDSCAPE_CLIENT_INSTALLED=true
fi

command -v systemctl >/dev/null 2>&1 && systemctl status landscape-client > "${EVIDENCE_DIR}/landscape_client_status.txt" 2>/dev/null || true

[ -f /etc/landscape/client.conf ] && LANDSCAPE_CONFIG_PRESENT=true

# 4) cloud-init Reprovision Surface
if command -v cloud-init >/dev/null 2>&1; then
    CLOUD_INIT_PRESENT=true
    cloud-init --version > "${EVIDENCE_DIR}/cloud_init_version.txt" 2>/dev/null || true
    cloud-init status 2>/dev/null | head -n20 > "${EVIDENCE_DIR}/cloud_init_status.txt" 2>/dev/null || true
fi

[ -f /etc/cloud/cloud-init.disabled ] && CLOUD_INIT_DISABLED_MARKER=true

# 5) Identity Elements Evidence
[ -f /etc/machine-id ] && [ -s /etc/machine-id ] && MACHINE_ID_PRESENT=true

SSH_HOSTKEY_COUNT=$(find /etc/ssh -maxdepth 1 -name 'ssh_host_*' -type f 2>/dev/null | wc -l)

if [ -d /etc/NetworkManager/system-connections ]; then
    NM_CONNECTION_COUNT=$(find /etc/NetworkManager/system-connections -type f 2>/dev/null | wc -l)
fi

# 6) DGX Spark Tool Reuse Detection
(command -v spark_updatectl.py >/dev/null 2>&1 || [ -f "bin/spark_updatectl.py" ]) && UPDATE_CTL_TOOL=true
(command -v spark_diagctl.py >/dev/null 2>&1 || [ -f "bin/spark_diagctl.py" ]) && DIAG_CTL_TOOL=true

# ============================================================
# PLAN FILE GENERATION (always)
# ============================================================

cat > "${PLAN_FILE}" <<'PLANEOF'
================================================================================
  FACTORY RESET WITH SECURE RE-PROVISIONING - EXECUTION PLAN
================================================================================

CRITICAL WARNINGS:
- Factory reset is DESTRUCTIVE and may cause PERMANENT DATA LOSS
- Default behavior PRESERVES network configuration and user data
- Network removal (--preserve-network=false) causes REMOTE LOCKOUT
- User data removal (--preserve-users=false) DELETES /home/*
- Execute mode requires: --execute --confirm=FACTORY_RESET_EXECUTE

================================================================================
RESET LEVELS
================================================================================

LEVEL 0: Probe Only (Safe)
---------------------------
- Collect readiness evidence (boot config, Pro/Landscape state, identity)
- Generate this plan file
- NO system modifications
- Safe for all environments

LEVEL 1: Deprovision Management + Identity Reset (DESTRUCTIVE)
---------------------------------------------------------------
Actions (when --execute --confirm=FACTORY_RESET_EXECUTE):
1. Stop landscape-client service (if present)
2. Remove Landscape client configuration:
   - /etc/landscape/*
   - /var/lib/landscape/*
   - /var/cache/landscape-client/*
3. Reset machine identity:
   - Remove or reset /etc/machine-id (regenerates on boot)
   - Remove /etc/ssh/ssh_host_* keys (regenerate on boot)
4. Network/user data: PRESERVED by default
   - Override: --preserve-network=false (causes remote lockout)
   - Override: --preserve-users=false (deletes user data)
5. Ubuntu Pro detachment (ONLY if --detach-pro=true AND attached):
   - Run: pro detach --assume-yes
6. cloud-init re-enable (ONLY if --reenable-cloud-init=true):
   - Remove: /etc/cloud/cloud-init.disabled
   - WARNING: May change boot behavior

Remote Access Impact: SSH host keys change (fingerprint warning on reconnect)

LEVEL 2: Tenant Cleanup (DESTRUCTIVE)
--------------------------------------
Actions: Level 1 + (when --execute --confirm=FACTORY_RESET_EXECUTE):
1. Optional log cleanup (bounded, non-destructive where possible)
2. Optional user data cleanup (ONLY if --preserve-users=false):
   - WARNING: Deletes /home/* (excludes /home/nvidia by default)
3. Network cleanup (ONLY if --preserve-network=false):
   - WARNING: Removes /etc/NetworkManager/system-connections/*

Remote Access Impact: May lose SSH access if network removed

LEVEL 3: Full Wipe / Reimage Plan (PLAN ONLY - NOT EXECUTED)
-------------------------------------------------------------
This level generates instructions but DOES NOT execute wipe operations.

Detection:
- Identify storage devices and filesystems

Reimage Plan (manual execution required):
1. Create bootable installation media (Ubuntu 24.04 LTS for DGX Spark)
2. Boot from installation media
3. Perform storage sanitization as required (NVMe crypto-erase, ATA SECURITY ERASE, or equivalent)
4. Perform fresh OS installation
5. Apply DGX Spark baseline configuration
6. Execute re-provisioning steps (see below)

Note: Full wipe requires out-of-band access (physical or BMC/IPMI)

================================================================================
SECURE RE-PROVISIONING STEPS
================================================================================

After factory reset, the system must be re-provisioned to restore management.

OPTION A: Ubuntu Pro + Landscape Service
-----------------------------------------
Prerequisites:
- Ubuntu Pro subscription with Landscape entitlement
- Network connectivity to Ubuntu Pro service
- Pro token (keep secret; do NOT commit to scripts)

Steps:
1. Attach to Ubuntu Pro (requires token):
   sudo pro attach <PRO_TOKEN>

2. Enable Landscape service:
   sudo pro enable landscape --assume-yes

3. Configure Landscape client (pass args after --):
   sudo pro enable landscape --assume-yes -- \
     --computer-title "DGX-Spark-hostname" \
     --account-name "your-landscape-account" \
     --url "https://landscape.canonical.com/message-system" \
     --ping-url "https://landscape.canonical.com/ping"

IMPORTANT: pro enable landscape requires machine to be attached first.
If unattached, script will report precondition failure.

OPTION B: Direct Landscape Client Registration
-----------------------------------------------
Prerequisites:
- Landscape server URL (on-premises or SaaS)
- Account credentials or registration key
- landscape-client package installed

Steps:
1. Install Landscape client (if not present):
   sudo apt-get update && sudo apt-get install -y landscape-client

2. Register with Landscape server:
   sudo landscape-config \
     --computer-title "DGX-Spark-hostname" \
     --account-name "your-landscape-account" \
     --url "https://your-landscape-server.example.com/message-system" \
     --ping-url "https://your-landscape-server.example.com/ping" \
     --silent

Note: Credentials and tokens should be provided securely (not in scripts)

OPTION C: cloud-init Provisioning (Advanced)
---------------------------------------------
Prerequisites:
- cloud-init installed and enabled
- Cloud provider metadata service OR NoCloud data source
- User-data with Landscape configuration

IMPORTANT: DGX Spark baseline has cloud-init disabled by /etc/cloud/cloud-init.disabled
Enabling requires removing this marker file (--reenable-cloud-init=true with --execute)

Steps (after re-enabling cloud-init):
1. Provide cloud-init configuration:
   - Cloud provider metadata (automatic)
   - NoCloud data source (/var/lib/cloud/seed/nocloud/)
   - Kernel command line (ds=nocloud-net;...)

2. Clean cloud-init state and re-run:
   sudo cloud-init clean --logs
   sudo cloud-init init --local
   sudo cloud-init init
   sudo cloud-init modules --mode config
   sudo cloud-init modules --mode final

Note: cloud-init re-provisioning is complex; test in non-production first

================================================================================
DGX SPARK SPECIFICS
================================================================================

Bootloader: GRUB
- Recovery mode entries exist in /boot/grub/grub.cfg (root-only access)
- Recovery accessed via GRUB menu at boot (not dedicated partition)
- See: https://help.ubuntu.com/community/RecoveryMode

Ubuntu Pro:
- Client installed but machine NOT attached on baseline
- Landscape service available via Pro but not enabled
- Requires pro attach before pro enable landscape

cloud-init:
- Installed but disabled by /etc/cloud/cloud-init.disabled marker
- Enabling is optional and may change boot behavior
- Use with caution

NetworkManager:
- System connections stored in /etc/NetworkManager/system-connections/
- Removing connections causes remote lockout (requires console access)

================================================================================
SAFEGUARDS AND VERIFICATION
================================================================================

Pre-Execution Checks:
1. Verify backups exist (if any data is important)
2. Confirm out-of-band access if removing network (physical, BMC, serial)
3. Document current configuration (hostnames, IPs, credentials)
4. Test re-provisioning workflow in lab environment first

Post-Execution Verification:
1. Verify machine-id regenerated: cat /etc/machine-id
2. Verify SSH host keys regenerated: ls -l /etc/ssh/ssh_host_*
3. Verify Landscape client removed: dpkg -l | grep landscape
4. Verify Pro detachment (if requested): pro status
5. Test SSH access (expect host key warning)
6. Verify network connectivity (if preserved)

Rollback / Recovery:
- If management removal fails, manually reinstall:
  sudo apt-get install landscape-client
- If network removed accidentally, physical/console access required
- If machine-id issues, manually regenerate:
  sudo rm /etc/machine-id && systemd-machine-id-setup
- If SSH issues, manually regenerate keys:
  sudo ssh-keygen -A

================================================================================
EXECUTION COMMAND EXAMPLES
================================================================================

Probe Only (Safe):
  sudo bash factory_reset_reprovision.sh --level 0

Level 1 (Management Deprovision):
  sudo bash factory_reset_reprovision.sh --level 1 \
    --execute --confirm=FACTORY_RESET_EXECUTE

Level 1 + Pro Detach (if attached):
  sudo bash factory_reset_reprovision.sh --level 1 \
    --execute --confirm=FACTORY_RESET_EXECUTE --detach-pro=true

Level 1 + Re-enable cloud-init:
  sudo bash factory_reset_reprovision.sh --level 1 \
    --execute --confirm=FACTORY_RESET_EXECUTE --reenable-cloud-init=true

Level 2 with User Cleanup (VERY DESTRUCTIVE):
  sudo bash factory_reset_reprovision.sh --level 2 \
    --execute --confirm=FACTORY_RESET_EXECUTE --preserve-users=false

Level 2 with Network Removal (CAUSES LOCKOUT):
  sudo bash factory_reset_reprovision.sh --level 2 \
    --execute --confirm=FACTORY_RESET_EXECUTE --preserve-network=false

Level 3 (Reimage Plan Only):
  sudo bash factory_reset_reprovision.sh --level 3

================================================================================
REFERENCES
================================================================================

- Landscape Remote Script Execution:
  https://documentation.ubuntu.com/landscape/explanation/features/remote-script-execution/

- Configure Landscape Client:
  https://documentation.ubuntu.com/landscape/how-to-guides/landscape-installation-and-set-up/configure-landscape-client/

- Enable Landscape via Ubuntu Pro:
  https://documentation.ubuntu.com/landscape/how-to-guides/ubuntu-pro/enable-landscape/
  https://documentation.ubuntu.com/pro-client/en/latest/howtoguides/enable_landscape/

- cloud-init CLI Reference:
  https://cloudinit.readthedocs.io/en/latest/reference/cli.html

- Ubuntu Recovery Mode:
  https://help.ubuntu.com/community/RecoveryMode

================================================================================
END OF PLAN
================================================================================
PLANEOF

# ============================================================
# EXECUTION (only if MODE=execute and LEVEL >= 1)
# ============================================================

if [ "$MODE" = "execute" ]; then
    if [ "$CONFIRM" != "FACTORY_RESET_EXECUTE" ]; then
        FAIL_REASONS+=("Execute mode requires --confirm=FACTORY_RESET_EXECUTE")
        STATUS="FAIL"
    elif [ $LEVEL -ge 1 ]; then
        # LEVEL 1: Deprovision Management + Identity Reset
        if command -v systemctl >/dev/null 2>&1; then
            systemctl stop landscape-client 2>/dev/null && ACTIONS_TAKEN+=("stopped_landscape_client") || true
        fi
        
        if [ -d /etc/landscape ]; then
            rm -rf /etc/landscape/* 2>/dev/null && ACTIONS_TAKEN+=("removed_etc_landscape") || true
        fi
        
        if [ -d /var/lib/landscape ]; then
            rm -rf /var/lib/landscape/* 2>/dev/null && ACTIONS_TAKEN+=("removed_var_lib_landscape") || true
        fi
        
        if [ -d /var/cache/landscape-client ]; then
            rm -rf /var/cache/landscape-client/* 2>/dev/null && ACTIONS_TAKEN+=("removed_var_cache_landscape") || true
        fi
        
        if [ -f /etc/machine-id ]; then
            echo "uninitialized" > /etc/machine-id 2>/dev/null && ACTIONS_TAKEN+=("reset_machine_id") || \
            rm -f /etc/machine-id 2>/dev/null && ACTIONS_TAKEN+=("removed_machine_id") || true
        fi
        
        if [ $SSH_HOSTKEY_COUNT -gt 0 ]; then
            rm -f /etc/ssh/ssh_host_* 2>/dev/null && ACTIONS_TAKEN+=("removed_ssh_host_keys") || true
        fi
        
        if [ "$DETACH_PRO" = "true" ] && [ "$PRO_ATTACHED" = "true" ]; then
            if command -v pro >/dev/null 2>&1; then
                pro detach --assume-yes >/dev/null 2>&1 && ACTIONS_TAKEN+=("detached_pro") || FAIL_REASONS+=("pro_detach_failed")
            fi
        fi
        
        if [ "$REENABLE_CLOUD_INIT" = "true" ]; then
            if [ -f /etc/cloud/cloud-init.disabled ]; then
                rm -f /etc/cloud/cloud-init.disabled 2>/dev/null && ACTIONS_TAKEN+=("removed_cloud_init_disabled_marker") || FAIL_REASONS+=("failed_to_remove_cloud_init_marker")
            fi
        fi
        
        # LEVEL 2: Tenant Cleanup
        if [ $LEVEL -ge 2 ]; then
            if [ "$PRESERVE_USERS" = "false" ]; then
                for homedir in /home/*; do
                    [ "$(basename "$homedir")" != "nvidia" ] && rm -rf "$homedir" 2>/dev/null && ACTIONS_TAKEN+=("removed_$(basename "$homedir")_home") || true
                done
            fi
            
            if [ "$PRESERVE_NETWORK" = "false" ]; then
                if [ -d /etc/NetworkManager/system-connections ]; then
                    rm -f /etc/NetworkManager/system-connections/* 2>/dev/null && ACTIONS_TAKEN+=("removed_nm_connections") || true
                fi
            fi
        fi
        
        [ ${#FAIL_REASONS[@]} -eq 0 ] && STATUS="PASS" || STATUS="FAIL"
    fi
fi

# ============================================================
# JSON OUTPUT
# ============================================================

cat <<EOF
{"status":"${STATUS}","run_id":"${RUN_ID}","level":${LEVEL},"mode":"${MODE}","uefi_mode":${UEFI_MODE},"bootloader":"${BOOTLOADER}","grub_recovery_entry_lines":${GRUB_RECOVERY_LINES},"pro_present":${PRO_PRESENT},"pro_attached":${PRO_ATTACHED},"landscape_service_available":"${LANDSCAPE_SERVICE_AVAILABLE}","landscape_service_status":"${LANDSCAPE_SERVICE_STATUS}","landscape_config_present":${LANDSCAPE_CONFIG_PRESENT},"landscape_client_installed":${LANDSCAPE_CLIENT_INSTALLED},"cloud_init_present":${CLOUD_INIT_PRESENT},"cloud_init_disabled_marker_present":${CLOUD_INIT_DISABLED_MARKER},"machine_id_present":${MACHINE_ID_PRESENT},"ssh_hostkey_count":${SSH_HOSTKEY_COUNT},"nm_connection_count":${NM_CONNECTION_COUNT},"dgx_tools":{"spark_updatectl":${UPDATE_CTL_TOOL},"spark_diagctl":${DIAG_CTL_TOOL}},"out_dir":"${RUN_DIR}","plan_file":"${PLAN_FILE}","actions_taken":$(array_to_json ACTIONS_TAKEN),"missing_optional":$(array_to_json MISSING_OPTIONAL),"fail_reasons":$(array_to_json FAIL_REASONS),"notes":"Remote Script Execution output is size-limited by script_output_limit; artifacts are stored locally. Snap client confinement may restrict filesystem access vs deb."}
EOF

case "$STATUS" in
    PASS) exit 0 ;;
    FAIL) exit 1 ;;
    *) exit 2 ;;
esac
