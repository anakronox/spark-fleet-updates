# Landscape Integration Manual for DGX Spark Management Scripts

**Version:** 1.0.0
**Date:** January 30, 2026
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Authentication Setup](#authentication-setup)
5. [Script Upload Process](#script-upload-process)
6. [Script Execution](#script-execution)
7. [Result Retrieval](#result-retrieval)
8. [Integration by Functional Area](#integration-by-functional-area)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)
11. [Reference](#reference)

---

## Overview

This manual provides complete technical instructions for integrating all DGX Spark Management scripts into Canonical Landscape for remote execution and management across your DGX Spark fleet.

### What You'll Accomplish

By following this guide, you will:
- Upload 11 production tools and 8 Landscape reference scripts to Landscape
- Configure script execution permissions and parameters
- Execute scripts across DGX Spark devices using computer queries
- Retrieve script results and outputs for analysis
- Automate device management workflows

### Script Inventory

**Production Tools (10):**
- 7 Clear Asset Information tools (device identity, hardware config, firmware, OS, drivers, software, asset tags)
- 1 Controlled SW/FW Updates tool (update control plane)
- 2 Remote Ops & Remediation tools (diagnostics collector, reset reason reporter)

**Landscape Reference Scripts (8):**
- 1 Attestable Conformance script (APT signing verification)
- 4 Resilience & Recovery scripts (verified boot, backup levels, factory reset, health watchdogs)
- 2 Network & Connectivity scripts (collect package, retrieve logs)
- 1 Security Posture script (encryption at rest)

---

## Architecture

### Integration Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    Landscape Server                              │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Script Library │  │ Activity Log │  │ Computer Registry  │  │
│  └────────┬───────┘  └──────┬───────┘  └─────────┬──────────┘  │
│           │                  │                     │              │
└───────────┼──────────────────┼─────────────────────┼──────────────┘
            │ (Upload)         │ (Execute)           │ (Query)
            │                  │                     │
     ┌──────▼──────────────────▼─────────────────────▼──────┐
     │         Landscape API (REST v2 + Legacy)             │
     │  • CreateScript (Legacy)                             │
     │  • ExecuteScript (Legacy)                            │
     │  • GetActivities (Legacy)                            │
     │  • GET /scripts (REST v2)                            │
     └──────────────────┬───────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
    ┌────▼───┐    ┌────▼───┐    ┌────▼───┐
    │ DGX #1 │    │ DGX #2 │    │ DGX #N │
    │        │    │        │    │        │
    │ Client │    │ Client │    │ Client │
    └────┬───┘    └────┬───┘    └────┬───┘
         │             │             │
         │    Script Execution      │
         │    Result Storage        │
         │    Output to Landscape   │
         └─────────────┬─────────────┘
                       │
              ┌────────▼────────┐
              │  Runtime Data   │
              │  /var/lib/dgx_  │
              │  spark_mgmt/    │
              └─────────────────┘
```

### Data Flow

1. **Upload Phase**: Scripts uploaded to Landscape Script Library via Legacy API
2. **Execution Phase**: Scripts executed on target computers via computer queries
3. **Collection Phase**: Results stored locally on DGX devices and sent to Landscape
4. **Retrieval Phase**: Results retrieved via Activities API or file transfer scripts

### Output Storage

All scripts store detailed outputs on the target DGX devices:
```
/var/lib/dgx_spark_management/{functional_area}/{tool_name}/
/var/log/dgx_spark/{functional_area}/{tool_name}/
```

---

## Prerequisites

### Landscape Server Requirements

- Canonical Landscape Server (SaaS or Self-Hosted)
- API access enabled with administrator privileges
- Script execution plugin enabled on Landscape server
- Network connectivity between Landscape and DGX Spark devices

### Landscape Client Requirements

**On each DGX Spark device:**
```bash
# Verify Landscape client is installed
landscape-client --version

# Enable script execution plugin
sudo landscape-config \
  --include-manager-plugins=ScriptExecution \
  --script-users=root,landscape,nobody

# Restart client
sudo systemctl restart landscape-client
```

### API Credentials

Obtain from Landscape web interface:
1. Navigate to **Settings** → **API Credentials**
2. Generate API Key and Secret (for HMAC authentication)
   - Or generate JWT token (for JWT authentication)
3. Note your Landscape Server URL (e.g., `https://landscape.example.com`)

### Repository Setup

```bash
# Clone DGX Spark Management repository
git clone <repository-url>
cd <clone-directory>

# Install production tools (optional, for local testing) — installs common/ first
bash install.sh
```

---

## Authentication Setup

Landscape Legacy API supports two authentication methods: **JWT** (recommended) or **API Key & Secret (HMAC)**.

### Method 1: JWT Authentication (Recommended)

#### Obtain JWT Token

```bash
# Request JWT token
curl -X POST https://landscape.example.com/api/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin@example.com",
    "password": "your-password"
  }'

# Response contains token
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600
}
```

#### Use JWT in API Calls

```bash
export LANDSCAPE_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X GET "https://landscape.example.com/api/v2/scripts?version=2011-08-01" \
  -H "Authorization: Bearer $LANDSCAPE_TOKEN"
```

**Note:** JWT tokens expire (typically 1 hour). Refresh periodically.

### Method 2: API Key & Secret (HMAC)

#### Configure Credentials

```bash
# Create ~/.landscape-api.rc
cat > ~/.landscape-api.rc << 'EOF'
LANDSCAPE_API_KEY="your-api-key-here"
LANDSCAPE_API_SECRET="your-api-secret-here"
LANDSCAPE_API_URI="https://landscape.example.com/api/"
EOF

chmod 600 ~/.landscape-api.rc
```

#### Generate HMAC Signature

HMAC authentication requires signing each request. See [HMAC Signature Generation](#hmac-signature-generation) for details.

**Recommendation:** Use the Landscape API command-line client (snap) for HMAC:

```bash
# Install Landscape API CLI
sudo snap install landscape-api

# Configure
landscape-api configure \
  --uri https://landscape.example.com/api/ \
  --key your-api-key \
  --secret your-api-secret

# Test connection
landscape-api GetScripts
```

---

## Script Upload Process

### Overview

Scripts must be uploaded to the Landscape Script Library before execution. This requires the **Legacy API** (script creation via REST API v2 is not yet supported).

### Upload Methods

1. **Landscape Web UI** (manual, good for testing)
2. **Legacy API via curl** (scriptable)
3. **Landscape API CLI snap** (recommended for automation)
4. **Python landscape_api module** (for custom automation)

### Script Preparation

#### Production Tools (Python)

Production tools require preparation before upload:

```bash
# Example: Upload device_identity.py
cd clear_asset_information/hardware_inventory_collector

# Encode script as base64
base64 -w 0 src/device_identity.py > device_identity_b64.txt

# Create script metadata
cat > device_identity_meta.json << 'EOF'
{
  "title": "DGX - Device Identity Collector",
  "code": "<BASE64_CONTENT_HERE>",
  "time_limit": 300,
  "username": "root",
  "access_group": "DGX-Spark-Fleet"
}
EOF
```

#### Landscape Reference Scripts (Bash)

Reference scripts are simpler and ready to upload:

```bash
# Example: signing_verification.sh
cd attestable_conformance_regulatory/landscape_signing_verification

# Encode script
base64 -w 0 signing_verification.sh > signing_verification_b64.txt
```

### Upload via Web UI

1. Navigate to **Scripts** → **Script Library** → **Add Script**
2. Fill in details:
   - **Title**: Descriptive name (e.g., "DGX - Device Identity Collector")
   - **Code**: Paste script content (or use upload button)
   - **Interpreter**: Auto-detected from shebang (#!/usr/bin/env python3 or #!/bin/bash)
   - **Time Limit**: Execution timeout (seconds)
   - **Default User**: root or landscape
   - **Access Group**: Restrict to specific computer groups
3. Click **Save**

### Upload via Legacy API (curl)

#### Step 1: Prepare Script

```bash
# Encode script to base64
SCRIPT_B64=$(base64 -w 0 < src/device_identity.py)

# Prepare JSON payload (using JWT auth)
cat > payload.json << EOF
{
  "action": "CreateScript",
  "version": "2011-08-01",
  "title": "DGX - Device Identity Collector",
  "code": "$SCRIPT_B64",
  "time_limit": 300,
  "username": "root"
}
EOF
```

#### Step 2: Upload Script

```bash
# Using JWT authentication
curl -X POST "https://landscape.example.com/api/" \
  -H "Authorization: Bearer $LANDSCAPE_TOKEN" \
  -H "Content-Type: application/json" \
  -d @payload.json
```

#### Step 3: Verify Upload

```bash
# List all scripts
curl -X GET "https://landscape.example.com/api/v2/scripts?version=2011-08-01" \
  -H "Authorization: Bearer $LANDSCAPE_TOKEN"
```

### Upload via Landscape API CLI

```bash
# Create script
landscape-api CreateScript \
  title="DGX - Device Identity Collector" \
  code="$(base64 -w 0 < src/device_identity.py)" \
  time_limit=300 \
  username=root

# Verify
landscape-api GetScripts
```

### Batch Upload Script

Create an automation script to upload all tools:

```bash
#!/bin/bash
# upload_all_scripts.sh

set -e

LANDSCAPE_TOKEN="your-jwt-token"
API_URL="https://landscape.example.com/api/"

# Production Tools
upload_tool() {
    local path=$1
    local title=$2
    local time_limit=${3:-300}

    echo "Uploading $title..."
    SCRIPT_B64=$(base64 -w 0 < "$path")

    curl -X POST "$API_URL" \
      -H "Authorization: Bearer $LANDSCAPE_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{
        \"action\": \"CreateScript\",
        \"version\": \"2011-08-01\",
        \"title\": \"$title\",
        \"code\": \"$SCRIPT_B64\",
        \"time_limit\": $time_limit,
        \"username\": \"root\"
      }"
}

# Upload Clear Asset Information tools
upload_tool "clear_asset_information/hardware_inventory_collector/src/device_identity.py" \
            "DGX - Device Identity" 300

upload_tool "clear_asset_information/hardware_inventory_collector/src/hardware_config.py" \
            "DGX - Hardware Config" 300

upload_tool "clear_asset_information/firmware_version_reporter/src/firmware_reporter.py" \
            "DGX - Firmware Reporter" 300

upload_tool "clear_asset_information/os_build_identity_reporter/src/os_build_identity.py" \
            "DGX - OS Build Identity" 120

upload_tool "clear_asset_information/driver_inventory_reporter/src/driver_inventory_reporter.py" \
            "DGX - Driver Inventory" 300

upload_tool "clear_asset_information/software_inventory_reporter/src/software_inventory_reporter.py" \
            "DGX - Software Inventory" 600

upload_tool "clear_asset_information/asset_tag_manager/src/nvaiaread.py" \
            "DGX - Asset Tag Reader" 60

# Upload Controlled SW/FW Updates tools
upload_tool "controlled_sw_fw_updates/update_control_plane/src/spark_updatectl.py" \
            "DGX - Update Control" 120

# Upload Remote Ops & Remediation tools
upload_tool "remote_ops_remediation/diagnostic_collector/src/spark_diagctl.py" \
            "DGX - Diagnostic Collector" 600

upload_tool "remote_ops_remediation/reset_reason_reporter/src/reset_reason_reporter.py" \
            "DGX - Reset Reason Reporter" 120

# Upload Landscape Reference Scripts
upload_tool "attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh" \
            "DGX - APT Signing Verification" 120

upload_tool "resilience_recovery_rollback/landscape_verified_boot_integrity/verified_boot_integrity.sh" \
            "DGX - Verified Boot Integrity" 120

upload_tool "resilience_recovery_rollback/landscape_recovery_backup_levels/recovery_backup_levels.sh" \
            "DGX - Recovery Backup Levels" 180

upload_tool "resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh" \
            "DGX - Factory Reset (Probe)" 120

upload_tool "resilience_recovery_rollback/landscape_health_watchdogs/health_watchdogs.sh" \
            "DGX - Health Watchdogs" 120

upload_tool "network_enterprise_connectivity/landscape_collect_package/collect_package.sh" \
            "DGX - Collect Support Package" 300

upload_tool "network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh" \
            "DGX - Retrieve Logs" 180

upload_tool "security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh" \
            "DGX - Encryption At Rest" 120

echo "All scripts uploaded successfully!"
```

### Script Attachments

Some scripts may require configuration files or attachments:

```bash
# Create attachment (format: filename$$base64content)
ATTACHMENT="default.json\$\$$(base64 -w 0 < config/default.json)"

# Upload script with attachment
landscape-api CreateScript \
  title="DGX - Hardware Config" \
  code="$(base64 -w 0 < src/hardware_config.py)" \
  time_limit=300 \
  username=root

# Get script_id from response, then add attachment
landscape-api CreateScriptAttachment \
  script_id=12345 \
  filename="default.json" \
  content="$(base64 -w 0 < config/default.json)"
```

---

## Script Execution

### Execution Methods

1. **Web UI** - Manual execution via Landscape interface
2. **Legacy API** - Programmatic execution via ExecuteScript
3. **Scheduled Execution** - Recurring script runs

### Target Selection (Computer Queries)

Landscape uses query syntax to select target computers:

**Query Examples:**
- `tag:dgx-spark` - All computers with "dgx-spark" tag
- `tag:datacenter-1 AND tag:production` - Intersection of tags
- `hostname:dgx-prod-*` - Wildcard hostname matching
- `access_group:Fleet-A` - All computers in access group
- `id:123 OR id:456` - Specific computer IDs

### Execute via Web UI

1. Navigate to **Scripts** → **Script Library**
2. Select script (e.g., "DGX - Device Identity")
3. Click **Run Script**
4. Configure execution:
   - **Target Computers**: Enter query (e.g., `tag:dgx-spark`)
   - **Username**: root or landscape (override script default)
   - **Schedule**: Run now or schedule for later
5. Click **Execute**

### Execute via Legacy API

```bash
# Get script ID
SCRIPT_ID=$(landscape-api GetScripts | jq '.[] | select(.title=="DGX - Device Identity") | .id')

# Execute on all DGX Spark devices
curl -X POST "https://landscape.example.com/api/" \
  -H "Authorization: Bearer $LANDSCAPE_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"action\": \"ExecuteScript\",
    \"version\": \"2011-08-01\",
    \"script_id\": $SCRIPT_ID,
    \"query\": \"tag:dgx-spark\",
    \"username\": \"root\"
  }"

# Response includes activity_id for tracking
{
  "id": 54321,
  "type": "ExecuteScript",
  "status": "delivered",
  "creation_time": "2026-01-30T15:30:00Z"
}
```

### Schedule Execution

```bash
# Schedule for specific time (UTC)
curl -X POST "https://landscape.example.com/api/" \
  -H "Authorization: Bearer $LANDSCAPE_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"action\": \"ExecuteScript\",
    \"version\": \"2011-08-01\",
    \"script_id\": $SCRIPT_ID,
    \"query\": \"tag:dgx-spark\",
    \"username\": \"root\",
    \"deliver_after\": \"2026-01-31T02:00:00Z\"
  }"
```

### Execution Parameters

Production tools accept command-line arguments:

```bash
# Execute with custom arguments (using script parameter passing)
# Note: Landscape executes scripts as-is; to pass arguments, create wrapper scripts

# Example wrapper for hardware_config.py with --human flag
cat > wrapper.sh << 'EOF'
#!/bin/bash
python3 /path/to/hardware_config.py --human
EOF

# Upload wrapper, then execute
```

**Better Approach:** Upload separate versions of scripts with different arguments pre-configured.

---

## Result Retrieval

### Output Locations

Scripts produce outputs in three places:

1. **Landscape Activity Log** (stdout/stderr, limited to ~1MB)
2. **Local DGX Storage** (full JSON outputs)
3. **Log Files** (detailed execution logs)

### Retrieve via Web UI

1. Navigate to **Activities** → **Recent Activities**
2. Filter by:
   - Activity type: "Script Execution"
   - Status: succeeded, failed, etc.
   - Computer: specific DGX device
   - Date range
3. Click activity to view:
   - Script output (stdout/stderr)
   - Exit code
   - Execution time
   - Computer details

### Retrieve via Legacy API (GetActivities)

```bash
# Get recent script execution activities
curl -X GET "https://landscape.example.com/api/?action=GetActivities&version=2011-08-01&query=type:ExecuteScript status:succeeded" \
  -H "Authorization: Bearer $LANDSCAPE_TOKEN"

# Response example
{
  "activities": [
    {
      "id": 54321,
      "type": "ExecuteScript",
      "status": "succeeded",
      "creation_time": "2026-01-30T15:30:00Z",
      "completion_time": "2026-01-30T15:32:15Z",
      "computer_id": 123,
      "creator": {"email": "admin@example.com"},
      "summary": "Executed 'DGX - Device Identity' on dgx-prod-01"
    }
  ]
}
```

### Get Specific Activity Details

```bash
# Query specific activity by ID
curl -X GET "https://landscape.example.com/api/?action=GetActivities&version=2011-08-01&query=id:54321" \
  -H "Authorization: Bearer $LANDSCAPE_TOKEN"
```

### Retrieve Full Output from DGX Devices

Activity logs in Landscape have size limits (~1MB). For full outputs, use file retrieval:

#### Method 1: Use "Retrieve Logs" Script

```bash
# Execute retrieve_logs_stdout.sh to fetch output files
landscape-api ExecuteScript \
  script_id=$(landscape-api GetScripts | jq '.[] | select(.title=="DGX - Retrieve Logs") | .id') \
  query="tag:dgx-spark" \
  username=root

# Script outputs base64-encoded gzip payload to stdout
# Copy from Landscape activity log and decode locally:
base64 -d < payload.b64 | gunzip > output.json
```

#### Method 2: Direct SSH Access

```bash
# SSH to DGX device
ssh root@dgx-prod-01

# Navigate to output directory
cd /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/

# View device identity output
cat device_identity.json

# View hardware config output
cat hardware_config.json
```

#### Method 3: Use "Collect Package" Script

```bash
# Execute collect_package.sh to create tarball
landscape-api ExecuteScript \
  script_id=$(landscape-api GetScripts | jq '.[] | select(.title=="DGX - Collect Support Package") | .id') \
  query="computer:dgx-prod-01" \
  username=root

# Package saved to /var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/
# Transfer via scp:
scp root@dgx-prod-01:/var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_*/dgx_support_bundle_*.tar.gz .
```

### Automated Result Collection

Create a result collection script:

```bash
#!/bin/bash
# collect_results.sh - Retrieve outputs from all DGX devices

DGX_HOSTS=$(landscape-api GetComputers query="tag:dgx-spark" | jq -r '.[].hostname')

for host in $DGX_HOSTS; do
    echo "Collecting from $host..."

    # Create output directory
    mkdir -p results/$host

    # Collect asset information
    scp -r root@$host:/var/lib/dgx_spark_management/clear_asset_information results/$host/ 2>/dev/null

    # Collect diagnostics
    scp -r root@$host:/var/lib/dgx_spark_management/remote_ops_remediation results/$host/ 2>/dev/null

    # Collect logs
    scp -r root@$host:/var/log/dgx_spark results/$host/ 2>/dev/null
done

echo "Results collected in ./results/"
```

---

## Integration by Functional Area

### 1. Clear Asset Information

**Purpose:** Comprehensive device inventory and asset tracking

#### Scripts to Upload

1. **Device Identity** (`device_identity.py`)
2. **Hardware Configuration** (`hardware_config.py`)
3. **Firmware Reporter** (`firmware_reporter.py`)
4. **OS Build Identity** (`os_build_identity.py`)
5. **Driver Inventory** (`driver_inventory_reporter.py`)
6. **Software Inventory** (`software_inventory_reporter.py`)
7. **Asset Tag Reader** (`nvaiaread.py`)

#### Recommended Execution Schedule

```bash
# Daily inventory collection
for script_id in $ASSET_SCRIPT_IDS; do
    landscape-api ExecuteScript \
      script_id=$script_id \
      query="tag:dgx-spark" \
      username=root \
      deliver_after="$(date -u -d 'tomorrow 02:00' +%Y-%m-%dT%H:%M:%SZ)"
done
```

#### Expected Outputs

All scripts output JSON to `/var/lib/dgx_spark_management/clear_asset_information/{tool}/`

**device_identity.json:**
```json
{
  "ok": true,
  "data": {
    "asset_id": "1983925017704",
    "asset_id_source": "smbios_serial",
    "product_serial": "1983925017704",
    "sys_vendor": "NVIDIA",
    "product_name": "NVIDIA_DGX_Spark",
    "product_uuid": "12345678-1234-1234-1234-123456789012"
  },
  "errors": [],
  "meta": {
    "tool": "device_identity",
    "version": "0.1.0",
    "collected_at_utc": "2026-01-30T15:30:00Z"
  }
}
```

#### Integration Workflow

1. **Upload all 7 scripts** to Landscape Script Library
2. **Execute daily** across all DGX Spark devices
3. **Collect results** via SSH or retrieve_logs script
4. **Import to CMDB/ITSM** - Parse JSON and integrate with ServiceNow, JIRA, etc.

### 2. Controlled SW/FW Updates

**Purpose:** Safe update orchestration with rollback capability

#### Scripts to Upload

1. **Update Control** (`spark_updatectl.py`)

#### Usage Examples

**Check Update Status:**
```bash
# Create status check version
cat > updatectl_status.sh << 'EOF'
#!/bin/bash
python3 /usr/local/bin/spark_updatectl.py status
EOF

# Upload and execute
landscape-api CreateScript title="DGX - Update Status" code="$(base64 -w 0 < updatectl_status.sh)" time_limit=60 username=root
landscape-api ExecuteScript script_id=$SCRIPT_ID query="tag:dgx-spark" username=root
```

**Plan Reboot:**
```bash
# Create reboot plan version
cat > updatectl_reboot_plan.sh << 'EOF'
#!/bin/bash
python3 /usr/local/bin/spark_updatectl.py reboot plan --reason "Security updates"
EOF

# Upload and execute
```

**Schedule Reboot:**
```bash
# Note: Requires --apply flag for actual execution (safety feature)
# Create scheduled reboot wrapper
cat > updatectl_reboot_schedule.sh << 'EOF'
#!/bin/bash
# Schedule reboot for 60 minutes from now
python3 /usr/local/bin/spark_updatectl.py reboot schedule --in-minutes 60 --reason "Maintenance window" --apply
EOF
```

#### Expected Outputs

**status.json:**
```json
{
  "ok": true,
  "data": {
    "reboot_required": true,
    "reboot_required_pkgs": ["nvidia-driver-550", "linux-image-generic"],
    "pending_updates": 12,
    "kernel_rollback_available": true
  }
}
```

### 3. Remote Ops & Remediation

**Purpose:** Remote diagnostics and troubleshooting

#### Scripts to Upload

1. **Diagnostic Collector** (`spark_diagctl.py`)
2. **Reset Reason Reporter** (`reset_reason_reporter.py`)

#### Usage Examples

**Health Check:**
```bash
cat > diagctl_health.sh << 'EOF'
#!/bin/bash
python3 /usr/local/bin/spark_diagctl.py health --human
EOF
```

**Full Diagnostics Collection:**
```bash
cat > diagctl_collect_all.sh << 'EOF'
#!/bin/bash
python3 /usr/local/bin/spark_diagctl.py collect-all --tarball
EOF
```

**Reset Reason Analysis:**
```bash
cat > reset_reason.sh << 'EOF'
#!/bin/bash
python3 /usr/local/bin/reset_reason_reporter.py --human
EOF
```

#### Expected Outputs

**health.json:**
```json
{
  "ok": true,
  "data": {
    "cpu_usage_percent": 15.2,
    "memory_available_gb": 120.5,
    "disk_usage_percent": 45.0,
    "gpu_count": 2,
    "gpu_utilization_avg": 80.0,
    "temperature_c": 42,
    "issues": []
  }
}
```

### 4. Attestable Conformance & Regulatory

**Purpose:** Compliance verification

#### Scripts to Upload

1. **APT Signing Verification** (`signing_verification.sh`)

```bash
landscape-api CreateScript \
  title="DGX - APT Signing Verification" \
  code="$(base64 -w 0 < attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh)" \
  time_limit=120 \
  username=root
```

#### Expected Outputs

Single-line JSON to stdout:
```json
{"status":"PASS","run_id":"20260130_153000Z","apt_signed_by_present":true,"signature_validation_passed":true}
```

Evidence stored in `/var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/`

### 6. Resilience, Recovery & Rollback

**Purpose:** System recovery and resilience verification

#### Scripts to Upload

1. **Verified Boot Integrity** (`verified_boot_integrity.sh`)
2. **Recovery Backup Levels** (`recovery_backup_levels.sh`)
3. **Factory Reset Probe** (`factory_reset_reprovision.sh`)
4. **Health Watchdogs** (`health_watchdogs.sh`)

All scripts output single-line JSON to stdout with detailed evidence files stored locally.

### 7. Network & Enterprise Connectivity

**Purpose:** Remote support and log collection

#### Scripts to Upload

1. **Collect Support Package** (`collect_package.sh`)
2. **Retrieve Logs** (`retrieve_logs_stdout.sh`)

#### Usage: Collect Support Package

```bash
# Execute collect_package.sh
landscape-api ExecuteScript \
  script_id=$(landscape-api GetScripts | jq '.[] | select(.title=="DGX - Collect Support Package") | .id') \
  query="computer:dgx-prod-01" \
  username=root

# Package created at:
# /var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_<UTC>/dgx_support_bundle_<timestamp>.tar.gz

# Transfer via scp
scp root@dgx-prod-01:/var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_*/dgx_support_bundle_*.tar.gz .
```

#### Usage: Retrieve Logs

```bash
# Execute with preset
landscape-api ExecuteScript \
  script_id=$(landscape-api GetScripts | jq '.[] | select(.title=="DGX - Retrieve Logs") | .id') \
  query="computer:dgx-prod-01" \
  username=root

# View output in Landscape activity log
# Copy payload between BEGIN_DGX_PAYLOAD and END_DGX_PAYLOAD markers
# Decode:
base64 -d < payload.b64 | gunzip > recovered.log
```

### 8. Security Posture & Vulnerability Response

**Purpose:** Security configuration verification

#### Scripts to Upload

1. **Encryption At Rest** (`encryption_at_rest.sh`)

---

## Best Practices

### Script Management

1. **Naming Convention:**
   - Prefix all scripts with "DGX -" for easy identification
   - Use descriptive names (e.g., "DGX - Device Identity" not "script1")

2. **Version Control:**
   - Track script_id mappings in a configuration file
   - Document script versions in Landscape script titles (e.g., "DGX - Health Check v1.2")

3. **Access Control:**
   - Use access_group parameter to restrict scripts to specific computer groups
   - Limit destructive scripts to admin-only access groups

4. **Time Limits:**
   - Set appropriate time_limit values (see table below)
   - Monitor for timeout failures and adjust as needed

**Recommended Time Limits:**

| Script Category | Time Limit (seconds) |
|-----------------|---------------------|
| Asset Information | 300 |
| Quick Status Checks | 60-120 |
| Diagnostics Collection | 600 |
| Software Inventory | 600 |
| Compliance Checks | 120 |
| Support Package Collection | 300 |

### Execution Patterns

1. **Daily Inventory:**
   ```bash
   # Schedule asset collection daily at 2 AM UTC
   for script in device_identity hardware_config firmware os_identity; do
       landscape-api ExecuteScript script_id=$script query="tag:dgx-spark" username=root \
         deliver_after="$(date -u -d 'tomorrow 02:00' +%Y-%m-%dT%H:%M:%SZ)"
   done
   ```

2. **Health Monitoring:**
   ```bash
   # Execute health checks every 6 hours
   # Use cron to trigger via API
   0 */6 * * * /usr/local/bin/landscape-execute-health-check.sh
   ```

3. **On-Demand Diagnostics:**
   ```bash
   # Keep diagnostic scripts ready for incident response
   # Execute manually when issues are reported
   ```

### Result Management

1. **Automated Collection:**
   - Set up cron jobs to retrieve results from DGX devices
   - Store results in centralized repository (Git, S3, etc.)

2. **Parsing and Analysis:**
   - Use jq for JSON parsing
   - Import to monitoring/CMDB systems

3. **Alerting:**
   - Monitor activity status via GetActivities
   - Alert on failed executions

### Security Considerations

1. **Script Review:**
   - Review all scripts before uploading to Landscape
   - Test scripts on non-production systems first

2. **Credential Management:**
   - Rotate API tokens regularly
   - Use JWT with short expiry times
   - Store credentials securely (vault, encrypted files)

3. **Destructive Operations:**
   - Require manual intervention for destructive operations
   - Use plan-execute-verify workflows

4. **Output Sanitization:**
   - Review script outputs for sensitive information
   - Sanitize logs before sharing with support

---

## Troubleshooting

### Script Upload Issues

**Problem:** Script creation fails with "Invalid code" error

**Solution:**
- Verify script has valid shebang line (#!/usr/bin/env python3 or #!/bin/bash)
- Ensure base64 encoding is correct (no line wraps with -w 0)
- Check that code is not empty

```bash
# Test base64 encoding
base64 -w 0 < script.py | base64 -d | head -n 1
# Should show shebang line
```

**Problem:** Authentication fails

**Solution:**
- Verify JWT token hasn't expired (refresh if needed)
- Check API key/secret are correct
- Ensure API URL is correct (https://landscape.example.com/api/)

### Script Execution Issues

**Problem:** ExecuteScript fails with "ScriptExecution plugin not enabled"

**Solution:**
```bash
# On each DGX device:
sudo landscape-config \
  --include-manager-plugins=ScriptExecution \
  --script-users=root,landscape,nobody

sudo systemctl restart landscape-client
```

**Problem:** Script times out

**Solution:**
- Increase time_limit parameter
- Optimize script performance
- Check for network issues on target device

**Problem:** No computers match query

**Solution:**
- Verify computer tags in Landscape
- Test query syntax in Web UI first
- Check computer registration status

### Result Retrieval Issues

**Problem:** Activity log truncated (output > 1MB)

**Solution:**
- Use retrieve_logs_stdout.sh with --max-bytes parameter
- Use collect_package.sh to create tarball
- Retrieve full outputs via SSH

**Problem:** Can't find activity results

**Solution:**
```bash
# Query by script execution type
landscape-api GetActivities query="type:ExecuteScript status:succeeded created-after:2026-01-30"

# Query by computer
landscape-api GetActivities query="computer:dgx-prod-01"
```

### Common Script Errors

**Device Identity - No serial found:**
```json
{
  "ok": true,
  "data": {
    "asset_id": "12345678-1234-1234-1234-123456789012",
    "asset_id_source": "smbios_uuid"
  },
  "errors": ["Serial number contains placeholder value"]
}
```

**Solution:** This is expected behavior. Script falls back to UUID.

**Hardware Config - nvidia-smi not found:**
```json
{
  "ok": true,
  "data": { ... },
  "errors": ["nvidia-smi not available, GPU enumeration limited"]
}
```

**Solution:** Install nvidia-driver package or ignore if GPUs are not present.

**Firmware Reporter - fwupdmgr not found:**
```json
{
  "errors": ["fwupdmgr not found, install fwupd package"]
}
```

**Solution:** Install fwupd package or accept partial firmware reporting.

---

## Reference

### API Endpoints Summary

**REST API v2 (Read-Only):**
- `GET /api/v2/scripts` - List scripts
- `GET /api/v2/scripts/<id>` - Get script details
- `GET /api/v2/scripts/<id>/versions` - Get script versions

**Legacy API (Full Access):**
- `CreateScript` - Upload new script
- `EditScript` - Modify existing script
- `ExecuteScript` - Run script on computers
- `GetScripts` - List all scripts
- `GetScriptCode` - Retrieve script code
- `GetActivities` - Retrieve execution results
- `CreateScriptAttachment` - Add file attachments
- `RemoveScript` - Delete script

### Query Syntax

**Computer Selection:**
- `tag:name` - Computers with tag
- `hostname:pattern` - Hostname matching (supports wildcards)
- `access_group:name` - Computers in access group
- `id:N` - Specific computer ID
- `AND`, `OR`, `NOT` - Boolean operators

**Activity Filtering:**
- `id:N` - Activity ID
- `status:STATUS` - undelivered, delivered, succeeded, failed, canceled
- `type:TYPE` - ExecuteScript, PackageUpdate, etc.
- `created-after:DATE` - ISO-8601 format
- `created-before:DATE` - ISO-8601 format
- `creator:EMAIL` - Activity creator
- `computer:CRITERIA` - Associated computer

### Exit Codes

**Production Tools:**
- 0: Success
- 1: Error occurred (check JSON errors field)

**Landscape Reference Scripts:**
- 0 (PASS): Check passed
- 1 (FAIL): Check failed
- 2 (UNKNOWN): Unable to determine status

### File Locations on DGX Devices

**Runtime Data:**
```
/var/lib/dgx_spark_management/
├── clear_asset_information/
│   ├── hardware_inventory_collector/
│   │   ├── device_identity.json
│   │   └── hardware_config.json
│   ├── firmware_version_reporter/
│   │   └── firmware_versions.json
│   ├── os_build_identity_reporter/
│   │   └── os_build_identity.json
│   ├── driver_inventory_reporter/
│   │   └── driver_inventory.json
│   └── software_inventory_reporter/
│       └── software_inventory.json
├── controlled_sw_fw_updates/
│   └── update_control_plane/
│       └── status.json
├── remote_ops_remediation/
│   ├── diagnostic_collector/
│   │   └── diagnostics_full.json
│   └── reset_reason_reporter/
│       └── reset_reason_report.json
└── (landscape reference scripts store evidence in run_<UTC>/ directories)
```

**Logs:**
```
/var/log/dgx_spark/
├── clear_asset_information/
├── controlled_sw_fw_updates/
└── remote_ops_remediation/
```

### HMAC Signature Generation

For API Key/Secret authentication:

```python
#!/usr/bin/env python3
import hmac
import hashlib
import base64
from urllib.parse import quote

def sign_request(method, host, path, query_string, secret):
    """Generate HMAC-SHA256 signature for Landscape API request"""
    # Canonical string: METHOD\nHOST\nPATH\nQUERY
    canonical = f"{method}\n{host}\n{path}\n{query_string}"

    # HMAC-SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()

    # Base64 encode
    return base64.b64encode(signature).decode('utf-8')

# Example usage
method = "POST"
host = "landscape.example.com"
path = "/api/"
params = {
    "action": "CreateScript",
    "version": "2011-08-01",
    "access_key_id": "YOUR_KEY",
    "signature_method": "HmacSHA256",
    "signature_version": "2",
    "timestamp": "2026-01-30T15:30:00Z",
    "title": "Test Script",
    "code": "...",
    "time_limit": "300",
    "username": "root"
}

# Sort and encode
query_string = "&".join(f"{quote(k, safe='')}={quote(str(v), safe='')}"
                        for k, v in sorted(params.items()))

# Generate signature
signature = sign_request(method, host, path, query_string, "YOUR_SECRET")

# Add signature to params
params["signature"] = signature
```

### Resources

**Official Documentation:**
- [Landscape API Reference](https://documentation.ubuntu.com/landscape/reference/api/)
- [Legacy API Scripts Endpoints](https://documentation.ubuntu.com/landscape/reference/api/legacy-api-endpoints/scripts/)
- [REST API Scripts Endpoints](https://documentation.ubuntu.com/landscape/reference/api/rest-api-endpoints/scripts/)
- [Remote Script Execution](https://documentation.ubuntu.com/landscape/explanation/features/remote-script-execution/)
- [Legacy API HTTPS Usage](https://documentation.ubuntu.com/landscape/how-to-guides/api/use-the-legacy-api-via-http-requests/)
- [Legacy API Activities](https://documentation.ubuntu.com/landscape/reference/api/legacy-api-endpoints/activities/)

**DGX Spark Management Documentation:**
- [README.md](../README.md) - Project overview
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Repository structure
- [LANDSCAPE_REFERENCE_SCRIPTS_SETUP.md](../LANDSCAPE_REFERENCE_SCRIPTS_SETUP.md) - Reference scripts framework

**Tools:**
- [Landscape API CLI (snap)](https://snapcraft.io/landscape-api)
- [landscape-api Python package](https://landscape-api-py3.readthedocs.io/)

---

## Appendix: Complete Upload Script

```bash
#!/bin/bash
# complete_upload.sh - Upload all DGX Spark Management scripts to Landscape

set -e

# Configuration
LANDSCAPE_API_URL="https://landscape.example.com/api/"
LANDSCAPE_TOKEN="${LANDSCAPE_TOKEN:-}"  # Set via environment variable

if [ -z "$LANDSCAPE_TOKEN" ]; then
    echo "Error: LANDSCAPE_TOKEN environment variable not set"
    echo "Usage: LANDSCAPE_TOKEN='your-jwt-token' bash complete_upload.sh"
    exit 1
fi

# Function to upload script
upload_script() {
    local script_path=$1
    local title=$2
    local time_limit=${3:-300}
    local username=${4:-root}

    if [ ! -f "$script_path" ]; then
        echo "ERROR: Script not found: $script_path"
        return 1
    fi

    echo "Uploading: $title"

    # Encode script
    SCRIPT_B64=$(base64 -w 0 < "$script_path")

    # Create payload
    PAYLOAD=$(cat <<EOF
{
  "action": "CreateScript",
  "version": "2011-08-01",
  "title": "$title",
  "code": "$SCRIPT_B64",
  "time_limit": $time_limit,
  "username": "$username"
}
EOF
)

    # Upload
    RESPONSE=$(curl -s -X POST "$LANDSCAPE_API_URL" \
        -H "Authorization: Bearer $LANDSCAPE_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD")

    # Check response
    if echo "$RESPONSE" | jq -e '.id' > /dev/null 2>&1; then
        SCRIPT_ID=$(echo "$RESPONSE" | jq -r '.id')
        echo "  ✓ Uploaded successfully (ID: $SCRIPT_ID)"
        return 0
    else
        echo "  ✗ Upload failed: $RESPONSE"
        return 1
    fi
}

echo "========================================"
echo "DGX Spark Management - Landscape Upload"
echo "========================================"
echo ""

# Navigate to repository root
cd "$(dirname "$0")/.."

# Upload Clear Asset Information tools
echo "[1/8] Clear Asset Information Tools"
upload_script "clear_asset_information/hardware_inventory_collector/src/device_identity.py" \
              "DGX - Device Identity" 300 root

upload_script "clear_asset_information/hardware_inventory_collector/src/hardware_config.py" \
              "DGX - Hardware Configuration" 300 root

upload_script "clear_asset_information/firmware_version_reporter/src/firmware_reporter.py" \
              "DGX - Firmware Reporter" 300 root

upload_script "clear_asset_information/os_build_identity_reporter/src/os_build_identity.py" \
              "DGX - OS Build Identity" 120 root

upload_script "clear_asset_information/driver_inventory_reporter/src/driver_inventory_reporter.py" \
              "DGX - Driver Inventory" 300 root

upload_script "clear_asset_information/software_inventory_reporter/src/software_inventory_reporter.py" \
              "DGX - Software Inventory" 600 root

upload_script "clear_asset_information/asset_tag_manager/src/nvaiaread.py" \
              "DGX - Asset Tag Reader" 60 root

echo ""

# Upload Controlled SW/FW Updates tools
echo "[2/8] Controlled SW/FW Updates Tools"
upload_script "controlled_sw_fw_updates/update_control_plane/src/spark_updatectl.py" \
              "DGX - Update Control Status" 120 root

echo ""

# Upload Remote Ops & Remediation tools
echo "[3/8] Remote Ops & Remediation Tools"
upload_script "remote_ops_remediation/diagnostic_collector/src/spark_diagctl.py" \
              "DGX - Diagnostic Collector" 600 root

upload_script "remote_ops_remediation/reset_reason_reporter/src/reset_reason_reporter.py" \
              "DGX - Reset Reason Reporter" 120 root

echo ""

# Upload Attestable Conformance & Regulatory scripts
echo "[4/8] Attestable Conformance & Regulatory Scripts"
upload_script "attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh" \
              "DGX - APT Signing Verification" 120 root

echo ""

# Upload Resilience, Recovery & Rollback scripts
echo "[6/8] Resilience, Recovery & Rollback Scripts"
upload_script "resilience_recovery_rollback/landscape_verified_boot_integrity/verified_boot_integrity.sh" \
              "DGX - Verified Boot Integrity" 120 root

upload_script "resilience_recovery_rollback/landscape_recovery_backup_levels/recovery_backup_levels.sh" \
              "DGX - Recovery Backup Levels" 180 root

upload_script "resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh" \
              "DGX - Factory Reset Probe" 120 root

upload_script "resilience_recovery_rollback/landscape_health_watchdogs/health_watchdogs.sh" \
              "DGX - Health Watchdogs" 120 root

echo ""

# Upload Network & Enterprise Connectivity scripts
echo "[7/8] Network & Enterprise Connectivity Scripts"
upload_script "network_enterprise_connectivity/landscape_collect_package/collect_package.sh" \
              "DGX - Collect Support Package" 300 root

upload_script "network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh" \
              "DGX - Retrieve Logs to Stdout" 180 root

echo ""

# Upload Security Posture & Vulnerability Response scripts
echo "[8/8] Security Posture & Vulnerability Response Scripts"
upload_script "security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh" \
              "DGX - Encryption At Rest Status" 120 root

echo ""
echo "========================================"
echo "Upload Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Verify scripts in Landscape Web UI: Scripts → Script Library"
echo "2. Tag your DGX Spark devices with 'dgx-spark' tag"
echo "3. Test execution on a single device first"
echo "4. Roll out to fleet after validation"
echo ""
