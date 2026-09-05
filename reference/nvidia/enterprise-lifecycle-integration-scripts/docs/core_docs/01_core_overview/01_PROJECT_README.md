# DGX Spark Enterprise Manageability

**Version:** 1.1.0  
**Status:** Production Ready + Landscape Integration  
**Last Updated:** January 9, 2026

A comprehensive repository of Linux tools and Landscape reference scripts for enterprise manageability on NVIDIA DGX Spark devices (ARM64 Ubuntu Linux Pro).

---

## 🎯 Overview

This repository provides **11 production-ready tools** and **8 Landscape reference scripts** across **9 functional areas**, enabling robust device management, diagnostics, updates, data protection, and Canonical Landscape integration for DGX Spark devices.

**Key Achievements:**
- ✅ 11 production tools implemented and tested on DGX Spark hardware
- ✅ 8 Landscape reference scripts for Canonical Landscape integration
- ✅ 25 of 26 enterprise requirements covered (96.2%)
- ✅ Stdlib-only Python (no external dependencies for production tools)
- ✅ JSON-first output (machine-parseable + human-readable)
- ✅ Comprehensive documentation (~800KB)
- ✅ Enterprise-grade safety guardrails

---

## 📊 Implementation Status

### ✅ **Production Tools: 11 Complete**

| Functional Area | Tools | Status |
|-----------------|-------|--------|
| **Clear Asset Information** | 7 tools | ✅ Complete |
| **Controlled SW/FW Updates** | 1 tool | ✅ Complete |
| **Remote Ops & Remediation** | 2 tools | ✅ Complete |
| **Data Protection & Privacy** | 1 tool | ✅ Complete |

### 🌐 **Landscape Reference Scripts: 8 Complete**

| Functional Area | Scripts | Status |
|-----------------|---------|--------|
| **Attestable Conformance & Regulatory** | 1 script | ✅ Complete |
| **Resilience, Recovery & Rollback** | 4 scripts | ✅ Complete |
| **Network & Enterprise Connectivity** | 2 scripts | ✅ Complete |
| **Security Posture & Vuln Response** | 1 script | ✅ Complete |

---

## 🚀 Quick Start

### Installation

```bash
# Clone repository (folder name matches your Git remote, e.g. cookbook)
git clone <repository-url>
cd cookbook   # or the directory created by clone

# Install common/ + all tools (preferred). Use bash so +x is not required.
bash install.sh

# Verify installation
ls -la bin/
```

`bash install.sh` runs `reinstall_all.sh`, which installs **`common/` first** (required for Python imports), then each functional area’s `install.sh`, and restores execute bits on `*.sh`.

**Do not** use only the historical `for tool in … install.sh` loop without installing `common/` first, and avoid `./install.sh` on fresh clones without `chmod +x` (use `bash …` instead).

**CRLF / “required file not found” on Linux:** If scripts were checked out or copied with Windows line endings, run `git config core.autocrlf false`, then `git add --renormalize .` and `git checkout -- .`. See `common/README.md`.

### Basic Usage

```bash
# Collect device identity
sudo bin/device_identity.py

# Collect hardware configuration
sudo bin/hardware_config.py

# Health check
bin/spark_diagctl.py health --human

# Reset reason analysis
bin/reset_reason_reporter.py --human

# Update status
bin/spark_updatectl.py status
```

---

## 🛠️ Implemented Tools

### 1. Clear Asset Information (7 tools)

#### 🔹 Device Identity
**Path:** `clear_asset_information/hardware_inventory_collector/`  
**Command:** `bin/device_identity.py`  
**Purpose:** Stable device identifier via SMBIOS/DMI  
**Output:** `device_identity.json` with asset_id (serial → UUID → machine-id fallback)

#### 🔹 Hardware Configuration
**Path:** `clear_asset_information/hardware_inventory_collector/`  
**Command:** `bin/hardware_config.py`  
**Purpose:** Enumerate CPU, GPU, SSD, NIC, memory  
**Output:** `hardware_config.json` (Redfish-ready)

#### 🔹 Firmware Version Reporter
**Path:** `clear_asset_information/firmware_version_reporter/`  
**Command:** `bin/firmware_reporter.py`  
**Purpose:** Report BIOS/UEFI, EC, NIC, SSD, GPU firmware  
**Output:** `firmware_versions.json`

#### 🔹 OS Build Identity
**Path:** `clear_asset_information/os_build_identity_reporter/`  
**Command:** `bin/os_build_identity.py`  
**Purpose:** Ubuntu version + DGX build identity + fingerprint  
**Output:** `os_build_identity.json`

#### 🔹 Driver Inventory
**Path:** `clear_asset_information/driver_inventory_reporter/`  
**Command:** `bin/driver_inventory_reporter.py`  
**Purpose:** Enumerate GPU/NIC/storage/USB drivers  
**Output:** `driver_inventory.json` with driver manifest

#### 🔹 Software Inventory
**Path:** `clear_asset_information/software_inventory_reporter/`  
**Command:** `bin/software_inventory_reporter.py`  
**Purpose:** dpkg/snap/pip/docker package enumeration  
**Output:** `software_inventory.json` with deterministic hashes

#### 🔹 Asset Tag Manager
**Path:** `clear_asset_information/asset_tag_manager/`  
**Commands:** `bin/NVAIAwrite`, `bin/NVAIAread`  
**Purpose:** UEFI-backed metadata (warranty, owner, location, cost center)  
**Output:** Custom UEFI variable storage

---

### 2. Controlled SW/FW Updates (1 tool)

#### 🔹 Update Control Plane
**Path:** `controlled_sw_fw_updates/update_control_plane/`  
**Command:** `bin/spark_updatectl.py`  
**Purpose:** Reboot coordination, kernel rollback, firmware rollback reporting  
**Commands:**
- `status` - Update/reboot status
- `reboot plan/schedule/now/cancel` - Safe reboot coordination
- `rollback kernel-list/set-next` - Kernel-only rollback via GRUB
- `fw rollback-report` - Firmware rollback status (report-only)

---

### 3. Remote Ops & Remediation (2 tools)

#### 🔹 Diagnostic Collector
**Path:** `remote_ops_remediation/diagnostic_collector/`  
**Command:** `bin/spark_diagctl.py`  
**Purpose:** Comprehensive diagnostics across 5 domains  
**Domains:**
1. Health Metrics (CPU/GPU/memory/disk/network/thermals/power)
2. System Event Logging (journald/syslog/kernel logs)
3. Hardware/FW Events (boot/ACPI/PCIe/ESRT/fwupd/rasdaemon)
4. Crash Diagnostics (kdump/core dumps/pstore)
5. GPU Telemetry (NVIDIA metrics/processes/errors)

**Commands:**
- `status`, `health`, `logs`, `hwfw-events`, `crash status`, `gpu`, `collect-all --tarball`

#### 🔹 Reset Reason Reporter
**Path:** `remote_ops_remediation/reset_reason_reporter/`  
**Command:** `bin/reset_reason_reporter.py`  
**Purpose:** Analyze why system rebooted  
**Features:**
- 7 evidence sources (journald, pstore, EFI vars, etc.)
- 7 reason codes with confidence scoring
- Conservative classification (prefers UNKNOWN over speculation)

---

---

## 🌐 Landscape Reference Scripts

Reference scripts designed for **Canonical Landscape Remote Script Execution**. These are simpler implementations focused on specific integration capabilities.

### 5. Attestable Conformance & Regulatory (1 script)

#### 🔹 APT Signing Verification
**Path:** `attestable_conformance_regulatory/landscape_signing_verification/`  
**Script:** `signing_verification.sh`  
**Purpose:** Cryptographic signing verification for APT repositories  
**Checks:** APT config, sources.list flags, `apt-get update` signature validation

### 6. Resilience, Recovery & Rollback Safety (4 scripts)

#### 🔹 Verified Boot Chain Integrity
**Path:** `resilience_recovery_rollback/landscape_verified_boot_integrity/`  
**Script:** `verified_boot_integrity.sh`  
**Purpose:** UEFI Secure Boot + kernel lockdown + signature evidence + TPM

#### 🔹 Recovery Partition & Backup Levels
**Path:** `resilience_recovery_rollback/landscape_recovery_backup_levels/`  
**Script:** `recovery_backup_levels.sh`  
**Purpose:** 3-level backup (probe, config snapshot, rebuild manifest)

#### 🔹 Factory Reset with Secure Re-provisioning
**Path:** `resilience_recovery_rollback/landscape_factory_reset_reprovision/`  
**Script:** `factory_reset_reprovision.sh`  
**Purpose:** 4-level reset (probe, deprovision, cleanup, wipe plan) with gated execution

#### 🔹 Health Watchdogs
**Path:** `resilience_recovery_rollback/landscape_health_watchdogs/`  
**Script:** `health_watchdogs.sh`  
**Purpose:** Watchdog configuration probe + optional self-test with transient units

### 7. Network & Enterprise Connectivity (2 scripts)

#### 🔹 Collect Package
**Path:** `network_enterprise_connectivity/landscape_collect_package/`  
**Script:** `collect_package.sh`  
**Purpose:** Generate standardized support bundle (tar.gz) with checksums

#### 🔹 Retrieve Logs to Stdout
**Path:** `network_enterprise_connectivity/landscape_retrieve_logs_stdout/`  
**Script:** `retrieve_logs_stdout.sh`  
**Purpose:** Retrieve logs to stdout with size enforcement and encoding options

### 8. Security Posture & Vulnerability Response (1 script)

#### 🔹 Encryption-at-Rest State Reporting
**Path:** `security_posture_vuln_response/landscape_encryption_at_rest/`  
**Script:** `encryption_at_rest.sh`  
**Purpose:** LUKS/dm-crypt state reporting (READ-ONLY) with enablement plan

**Note:** All Landscape scripts output single-line JSON to stdout and store detailed evidence files locally.

---

## 📁 Repository Structure

```
DGX_spark_management/
├── bin/                                      # Installed production tools (12 scripts)
├── docs/                                     # Documentation (~800KB)
│   ├── PROJECT_STRUCTURE.md                  # Detailed structure guide
│   ├── architecture/
│   ├── development/
│   └── user_guides/
├── tests/                                    # Test suites
│   ├── unit/                                 # Unit tests + fixtures
│   ├── integration/
│   └── system/
├── clear_asset_information/                  # ✅ 7 production tools
├── controlled_sw_fw_updates/                 # ✅ 1 production tool
├── remote_ops_remediation/                   # ✅ 2 production tools
├── attestable_conformance_regulatory/        # 🌐 1 Landscape script
├── resilience_recovery_rollback/             # 🌐 4 Landscape scripts
├── network_enterprise_connectivity/          # 🌐 2 Landscape scripts
└── security_posture_vuln_response/           # 🌐 1 Landscape script
```

---

## 🎯 Use Cases

### Asset Inventory

```bash
# Full inventory collection
sudo bin/device_identity.py
sudo bin/hardware_config.py
sudo bin/firmware_reporter.py
sudo bin/os_build_identity.py
sudo bin/driver_inventory_reporter.py
sudo bin/software_inventory_reporter.py

# Set asset tags
sudo bin/NVAIAwrite OWNERDATA OWNERNAME="IT Dept" LOCATION="Building A"
bin/NVAIAread OWNERDATA
```

### Health Monitoring

```bash
# Quick health check
bin/spark_diagctl.py health --human

# Comprehensive diagnostics
bin/spark_diagctl.py collect-all --tarball

# GPU monitoring
bin/spark_diagctl.py gpu --human
```

### Update Management

```bash
# Check reboot status
bin/spark_updatectl.py status

# Plan reboot
bin/spark_updatectl.py reboot plan --reason "security updates"

# Schedule reboot
sudo bin/spark_updatectl.py reboot schedule --in-minutes 60 --reason "maintenance"

# Kernel rollback
sudo bin/spark_updatectl.py rollback kernel-set-next --kernel 6.14.0-1013-nvidia
```

### Troubleshooting

```bash
# Why did system reboot?
bin/reset_reason_reporter.py --human

# Collect crash diagnostics
bin/spark_diagctl.py crash status

# Collect system logs
bin/spark_diagctl.py logs --output /tmp/system_logs.json
```


---

## 🔧 Technical Details

### Python Requirements

**Version:** Python 3.6+  
**Dependencies:** Stdlib only (no pip dependencies)

### System Requirements

**OS:** Ubuntu Linux Pro (ARM64 or x86_64)  
**Tools Required:**
- systemd (journalctl, systemctl, loginctl)
- Standard utilities (lsblk, lscpu, ip, ethtool, lspci, etc.)

**Optional Tools:**
- nvidia-smi (for GPU telemetry)
- fwupdmgr (for firmware inventory)
- sensors (for thermal monitoring)
### Output Format

**All tools output JSON by default:**
```json
{
  "ok": true,
  "data": { ... },
  "errors": [],
  "meta": {
    "tool": "tool_name",
    "version": "0.1.0",
    "collected_at_utc": "2025-01-08T20:00:00.000000Z"
  }
}
```

**Human-readable output via `--human` flag.**

### Runtime Data

**Output:** `/var/lib/dgx_spark_management/{functional_area}/{tool_name}/`  
**Logs:** `/var/log/dgx_spark/{functional_area}/{tool_name}/`

---

## 📖 Documentation

### Tool Documentation

Each tool has comprehensive README.md with:
- Purpose and scope
- Usage examples (JSON + human-readable)
- JSON schemas
- Troubleshooting guide
- Integration notes

### Repository Documentation

- **PROJECT_STRUCTURE.md** - Complete structure guide
- **architecture/system_overview.md** - Architecture overview
- **development/** - Setup and contributing guides
- **user_guides/** - Getting started and FAQ

---

## 🧪 Testing

```bash
# Run unit tests
bash tests/run_unit_tests.sh

# Run integration tests
bash tests/run_integration_tests.sh

# Run all tests
bash tests/run_all_tests.sh
```

**Test Coverage:**
- Unit tests with fixtures for all tools
- Integration tests for tool interactions
- System tests for end-to-end scenarios

---

## 🔒 Security

### Safety Features

**All tools:**
- Read-only by default
- JSON-first (no eval/exec of untrusted data)
- Atomic file writes (temp + rename)
- Comprehensive logging

### Data Privacy

**Tools collect system information only:**
- No network calls
- No PII collection (except when explicitly configured in asset tags)
- Logs may contain usernames/paths (sanitize before sharing)

---

## 🌐 Canonical Landscape Integration

### Remote Script Execution

All Landscape reference scripts are designed for **Landscape Remote Script Execution**:

```bash
# Example: Run encryption state check via Landscape
ssh root@dgx-spark 'bash -s' < security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh
```

**Features:**
- Single-line JSON output to stdout (respects Landscape output limits)
- Detailed evidence files stored locally
- Exit codes: 0=PASS, 1=FAIL, 2=UNKNOWN
- Safe defaults (read-only where possible)

### Script Categories

**Compliance & Attestation:**
- APT signing verification
- Verified boot chain integrity

**Recovery & Resilience:**
- Recovery backup levels (probe, config snapshot, rebuild manifest)
- Factory reset with gated execution
- Health watchdog probe + self-test

**Remote Support:**
- Support bundle collection (tar.gz)
- Log retrieval to stdout (text or gzip+base64)

**Security Posture:**
- Encryption-at-rest state (LUKS/dm-crypt reporting)

### Documentation

Each Landscape script includes:
- Purpose and Landscape integration notes
- SSH usage examples
- Exit codes and JSON schema
- Limitations and references

See `LANDSCAPE_REFERENCE_SCRIPTS_SETUP.md` for framework details.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Coding standards
- Pull request process
- Testing requirements

---

## 📋 Requirements Coverage

### Production Tools (18 requirements)

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Unique, stable device identifier | ✅ |
| 2 | Hardware configuration enumeration | ✅ |
| 3 | Installed firmware enumeration | ✅ |
| 4 | OS version/build and base image identity | ✅ |
| 5 | Driver enumeration | ✅ |
| 6 | Installed software/package enumeration | ✅ |
| 7-8 | Support entitlement + CMDB tags | ✅ |
| 9 | Cryptographic signing verification | 🌐 Landscape Script |
| 10-11 | Reboot coordination + Rollback | ✅ |
| 12 | Standard health metrics | ✅ |
| 13 | Structured system event logging | ✅ |
| 14 | Hardware/FW event logs | ✅ |
| 15 | Crash dump capture | ✅ |
| 16 | GPU/accelerator telemetry | ✅ |
| 17 | Reset reason reporting | ✅ |
| 18 | Secure deletion / crypto-erase | ✅ |

**Production Tools: 17 of 18 (94.4%)**

### Landscape Integration (8 additional capabilities)

| # | Capability | Status |
|---|------------|--------|
| 19 | APT signing verification | 🌐 ✅ |
| 20 | Verified boot chain integrity | 🌐 ✅ |
| 21 | Recovery partition & backup levels | 🌐 ✅ |
| 22 | Factory reset with re-provisioning | 🌐 ✅ |
| 23 | Health watchdog configuration | 🌐 ✅ |
| 24 | Support bundle collection | 🌐 ✅ |
| 25 | Log retrieval to stdout | 🌐 ✅ |
| 26 | Encryption-at-rest state reporting | 🌐 ✅ |

**Landscape Scripts: 8 of 8 (100%)**

**Total Coverage: 25 of 26 requirements (96.2%)**

---

## 📜 License

MIT License

Copyright (c) 2026 NVIDIA Corporation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 📧 Contact

**Project Maintainer:** DGX Spark Management Team  
**Documentation:** See `docs/` directory for comprehensive guides  
**Support:** Contact your organization's IT support team

---

## 🎉 Acknowledgments

Built for NVIDIA DGX Spark devices with enterprise manageability in mind.

Special thanks to the testing team for comprehensive DGX Spark hardware validation.

---

**Version 1.1.0 - Production Ready + Landscape Integration** 🚀
