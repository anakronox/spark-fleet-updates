# DGX Spark Management - Project Structure

**Last Updated:** January 9, 2026  
**Version:** 1.1.0  
**Status:** Production Ready + Landscape Integration

---

## Implementation Status

### ✅ **PRODUCTION TOOLS: 11 Complete (94.4% of core requirements)**

**Clear Asset Information** (7 tools):
1. ✅ Device Identity (`device_identity.py` + `hardware_config.py`)
2. ✅ Hardware Configuration Enumeration (`hardware_config.py`)
3. ✅ Firmware Version Reporter (`firmware_reporter.py`)
4. ✅ OS Build Identity (`os_build_identity.py`)
5. ✅ Driver Inventory (`driver_inventory_reporter.py`)
6. ✅ Software Inventory (`software_inventory_reporter.py`)
7. ✅ Asset Tag Manager (`NVAIAwrite` + `NVAIAread`)

**Controlled SW/FW Updates** (1 tool):
8. ✅ Update Control Plane (`spark_updatectl.py`)

**Remote Ops & Remediation** (2 tools):
9. ✅ Diagnostic Collector (`spark_diagctl.py`)
10. ✅ Reset Reason Reporter (`reset_reason_reporter.py`)

### 🌐 **LANDSCAPE REFERENCE SCRIPTS: 8 Complete**

**Attestable Conformance & Regulatory** (1 script):
1. 🌐 APT Signing Verification (`signing_verification.sh`)

**Resilience, Recovery & Rollback Safety** (4 scripts):
2. 🌐 Verified Boot Chain Integrity (`verified_boot_integrity.sh`)
3. 🌐 Recovery Partition & Backup Levels (`recovery_backup_levels.sh`)
4. 🌐 Factory Reset with Secure Re-provisioning (`factory_reset_reprovision.sh`)
5. 🌐 Health Watchdogs (`health_watchdogs.sh`)

**Network & Enterprise Connectivity** (2 scripts):
6. 🌐 Collect Package (`collect_package.sh`)
7. 🌐 Retrieve Logs to Stdout (`retrieve_logs_stdout.sh`)

**Security Posture & Vulnerability Response** (1 script):
8. 🌐 Encryption-at-Rest State Reporting (`encryption_at_rest.sh`)

**Total Implementation: 19 tools/scripts covering 25 of 26 requirements (96.2%)**

---

## Directory Tree (Actual Implementation)

```
DGX_spark_management/
│
├── README.md                           # Main project README
├── LICENSE                             # MIT License
├── CHANGELOG.md                        # Version history
├── CONTRIBUTING.md                     # Contribution guidelines
│
├── bin/                                # Installed production scripts
│   ├── device_identity.py              # ✅ Device identity collector
│   ├── hardware_config.py              # ✅ Hardware config collector
│   ├── firmware_reporter.py            # ✅ Firmware version reporter
│   ├── os_build_identity.py            # ✅ OS build identity
│   ├── driver_inventory_reporter.py    # ✅ Driver inventory
│   ├── software_inventory_reporter.py  # ✅ Software inventory
│   ├── NVAIAwrite                      # ✅ Asset tag writer
│   ├── NVAIAread                       # ✅ Asset tag reader
│   ├── spark_updatectl.py              # ✅ Update control plane
│   ├── spark_diagctl.py                # ✅ Diagnostic collector
│   └── reset_reason_reporter.py        # ✅ Reset reason reporter
│
├── logs/                               # Runtime logs (repo-local dev logs)
│
├── tests/                              # Test suites
│   ├── run_unit_tests.sh               # Unit test runner
│   ├── run_integration_tests.sh        # Integration test runner
│   ├── run_all_tests.sh                # Comprehensive test runner
│   ├── unit/                           # Unit tests
│   │   ├── clear_asset_information/    # Asset tests + fixtures
│   │   ├── controlled_sw_fw_updates/   # Update control tests + fixtures
│   │   └── remote_ops_remediation/     # Diagnostics tests + fixtures
│   ├── integration/                    # Integration tests
│   ├── system/                         # System/E2E tests
│   └── fixtures/                       # Shared test fixtures
│
├── docs/                               # Comprehensive documentation
│   ├── PROJECT_STRUCTURE.md            # This file
│   ├── architecture/
│   │   └── system_overview.md
│   ├── user_guides/
│   │   ├── getting_started.md
│   │   └── faq.md
│   ├── development/
│   │   ├── setup.md
│   │   └── contributing.md
│   ├── deployment/
│   │   └── deployment_guide.md
│   └── templates/
│       ├── REQUIREMENT_README_TEMPLATE.md
│       ├── SCRIPT_TEMPLATE.sh
│       └── PYTHON_SCRIPT_TEMPLATE.py
│
├── clear_asset_information/            # ✅ FUNCTIONAL AREA 1 - COMPLETE (7 tools)
│   ├── README.md                       # Area overview
│   │
│   ├── hardware_inventory_collector/   # ✅ Tools 1 & 2: Identity + Hardware Config
│   │   ├── README.md                   # Combined documentation
│   │   ├── device_identity.md          # Device identity details
│   │   ├── hardware_config.md          # Hardware config details
│   │   ├── IMPLEMENTATION_NOTES.md     # Implementation notes
│   │   ├── src/
│   │   │   ├── device_identity.py      # Stable device identifier
│   │   │   └── hardware_config.py      # CPU/GPU/SSD/NIC enumeration
│   │   ├── config/
│   │   │   ├── default.json            # Hardware config defaults
│   │   │   └── hardware_config_default.conf
│   │   ├── install.sh                  # Device identity installer
│   │   └── install_hardware_config.sh  # Hardware config installer
│   │
│   ├── firmware_version_reporter/      # ✅ Tool 3: Firmware Enumeration
│   │   ├── README.md                   # BIOS/UEFI/NIC/SSD/GPU firmware docs
│   │   ├── src/
│   │   │   └── firmware_reporter.py    # Firmware version collector
│   │   ├── config/
│   │   │   └── default.json
│   │   └── install.sh
│   │
│   ├── os_build_identity_reporter/     # ✅ Tool 4: OS Version/Build Identity
│   │   ├── README.md                   # OS/DGX build documentation
│   │   ├── src/
│   │   │   └── os_build_identity.py    # OS version + DGX build identity
│   │   ├── config/
│   │   │   └── default.json
│   │   └── install.sh
│   │
│   ├── driver_inventory_reporter/      # ✅ Tool 5: Driver Enumeration
│   │   ├── README.md                   # GPU/NIC/storage/USB drivers docs
│   │   ├── src/
│   │   │   └── driver_inventory_reporter.py
│   │   ├── config/
│   │   │   └── default.json
│   │   └── install.sh
│   │
│   ├── software_inventory_reporter/    # ✅ Tool 6: Software/Package Enumeration
│   │   ├── README.md                   # dpkg/snap/pip/docker docs
│   │   ├── src/
│   │   │   └── software_inventory_reporter.py
│   │   ├── config/
│   │   │   └── default.json
│   │   └── install.sh
│   │
│   └── asset_tag_manager/              # ✅ Tool 7: Asset Tags (entitlement + CMDB)
│       ├── README.md                   # UEFI variable storage docs
│       ├── src/
│       │   ├── nvaia_schema.py         # Schema definitions
│       │   ├── nvaia_uefi_store.py     # UEFI variable I/O
│       │   ├── platform_dmi.py         # DMI helper
│       │   ├── nvaiawrite.py           # Write tool
│       │   └── nvaiaread.py            # Read tool
│       ├── config/
│       │   └── default.conf
│       └── install.sh
│
├── controlled_sw_fw_updates/           # ✅ FUNCTIONAL AREA 2 - PARTIAL (1 tool)
│   ├── README.md                       # Area overview
│   │
│   └── update_control_plane/           # ✅ Tool 8: Reboot + Rollback
│       ├── README.md                   # Reboot coordination + kernel rollback docs
│       ├── src/
│       │   └── spark_updatectl.py      # Reboot control + kernel rollback
│       ├── config/
│       │   └── default.json
│       └── install.sh
│
├── remote_ops_remediation/             # ✅ FUNCTIONAL AREA 3 - COMPLETE (2 tools)
│   ├── README.md                       # Area overview
│   │
│   ├── diagnostic_collector/           # ✅ Tool 9: Comprehensive Diagnostics
│   │   ├── README.md                   # Health/logs/events/crash/GPU docs
│   │   ├── src/
│   │   │   └── spark_diagctl.py        # Diagnostics collector (5 domains)
│   │   ├── config/
│   │   │   └── default.json
│   │   └── install.sh
│   │
│   └── reset_reason_reporter/          # ✅ Tool 10: Reset Reason Analysis
│       ├── README.md                   # Boot/reboot reason forensics docs
│       ├── src/
│       │   └── reset_reason_reporter.py
│       ├── config/
│       │   └── default.json
│       └── install.sh
│
├── attestable_conformance_regulatory/  # 🌐 FUNCTIONAL AREA 5 - Landscape Scripts (1 script)
│   ├── README.md                       # Area overview
│   │
│   └── landscape_signing_verification/ # 🌐 APT Signing Verification
│       ├── README.md                   # Script documentation
│       ├── signing_verification.sh     # APT repository signing check
│       └── IMPLEMENTATION_NOTES.md     # Implementation details
│
├── resilience_recovery_rollback/       # 🌐 FUNCTIONAL AREA 6 - Landscape Scripts (4 scripts)
│   ├── README.md                       # Area overview
│   │
│   ├── landscape_verified_boot_integrity/    # 🌐 Boot Chain Integrity
│   │   ├── README.md                   # Script documentation
│   │   └── verified_boot_integrity.sh  # UEFI Secure Boot + TPM check
│   │
│   ├── landscape_recovery_backup_levels/     # 🌐 Recovery & Backup
│   │   ├── README.md                   # Script documentation
│   │   └── recovery_backup_levels.sh   # 3-level backup (probe/config/rebuild)
│   │
│   ├── landscape_factory_reset_reprovision/  # 🌐 Factory Reset
│   │   ├── README.md                   # Script documentation
│   │   └── factory_reset_reprovision.sh # 4-level reset with gating
│   │
│   └── landscape_health_watchdogs/     # 🌐 Health Watchdogs
│       ├── README.md                   # Script documentation
│       └── health_watchdogs.sh         # Watchdog probe + self-test
│
├── network_enterprise_connectivity/    # 🌐 FUNCTIONAL AREA 7 - Landscape Scripts (2 scripts)
│   ├── README.md                       # Area overview
│   │
│   ├── landscape_collect_package/      # 🌐 Support Bundle Collection
│   │   ├── README.md                   # Script documentation
│   │   └── collect_package.sh          # Generate tar.gz support bundle
│   │
│   └── landscape_retrieve_logs_stdout/ # 🌐 Log Retrieval
│       ├── README.md                   # Script documentation
│       └── retrieve_logs_stdout.sh     # Retrieve logs to stdout
│
├── security_posture_vuln_response/     # 🌐 FUNCTIONAL AREA 8 - Landscape Scripts (1 script)
│   ├── README.md                       # Area overview
│   │
│   └── landscape_encryption_at_rest/   # 🌐 Encryption State Reporting
│       ├── README.md                   # Script documentation
│       └── encryption_at_rest.sh       # LUKS/dm-crypt state (read-only)
│
├── packaging/                          # Packaging artifacts
│   └── systemd/                        # systemd unit files (if needed)
│
└── tools/                              # Development tools
    └── README.md
```

---

## Runtime Data Organization

All tools and scripts write runtime output to:
```
/var/lib/dgx_spark_management/{functional_area}/{tool_or_script_name}/
```

**Production Tool Examples:**
- `/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json`
- `/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/hardware_config.json`
- `/var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane/status.json`
- `/var/lib/dgx_spark_management/remote_ops_remediation/diagnostic_collector/diagnostics_full.json`
- `/var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter/reset_reason_report.json`

**Landscape Script Examples:**
- `/var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/run_<UTC>/`
- `/var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_verified_boot_integrity/run_<UTC>/`
- `/var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_<UTC>/`
- `/var/lib/dgx_spark_management/security_posture_vuln_response/landscape_encryption_at_rest/run_<UTC>/`

---

## Logging

Production logs:
```
/var/log/dgx_spark/{functional_area}/{tool_name}/
```

**Examples:**
- `/var/log/dgx_spark/clear_asset_information/hardware_inventory_collector/device_identity.log`
- `/var/log/dgx_spark/controlled_sw_fw_updates/update_control_plane/spark_updatectl.log`
- `/var/log/dgx_spark/remote_ops_remediation/diagnostic_collector/spark_diagctl.log`

---

## Production Tools vs. Landscape Reference Scripts

This repository contains two types of implementations:

### Production Tools (11 tools implemented)

Comprehensive, production-ready tools with:
- **Extensive documentation** (500-1000+ lines per tool)
- **Complete error handling** and graceful degradation
- **Unit tests** with fixtures and test runners
- **Installation scripts** for deployment to `bin/`
- **JSON-first output** with `--human` flag for readability
- **Configuration files** with CLI override support
- **Atomic file writes** and permission management
- **Comprehensive logging** with rotation support
- **Safety guardrails** for destructive operations

**Production tools are located in:**
- `clear_asset_information/` (7 tools)
- `controlled_sw_fw_updates/` (1 tool)
- `remote_ops_remediation/` (2 tools)

### Landscape Reference Scripts (8 scripts implemented)

Simpler, focused scripts for **Canonical Landscape Remote Script Execution**:
- **Brief documentation** (50-120 lines per script)
- **Minimal error handling** (reference implementations)
- **No installation scripts** (run in-place via SSH)
- **Single-line JSON to stdout** (respects Landscape output limits)
- **Evidence files stored locally** (detailed data)
- **Simple configuration** (optional config.conf)
- **Exit codes:** 0=PASS, 1=FAIL, 2=UNKNOWN

**Landscape scripts are located in:**
- `attestable_conformance_regulatory/` (1 script: APT signing verification)
- `resilience_recovery_rollback/` (4 scripts: boot integrity, backups, reset, watchdogs)
- `network_enterprise_connectivity/` (2 scripts: support bundle, log retrieval)
- `security_posture_vuln_response/` (1 script: encryption state reporting)

### Landscape Reference Scripts (as implemented)

Simplified integration examples for use with Canonical Landscape:
- **Brief documentation** (50-100 lines)
- **Minimal error handling** (reference implementation focus)
- **No extensive testing** (example/demonstration purpose)
- **No install scripts** (reference/example usage)
- **Simple output** (stdout/files)
- **Basic configuration** (key=value files when needed)
- **Inline comments** for clarity
- **Focused scope** (single capability per script)

**Reference script structure:**
```
{functional_area}/landscape_{script_name}/
├── README.md                    # Brief documentation
├── {script_name}.sh or .py      # Main script
└── config.conf                  # Simple config (if needed)
```

**Naming convention:** `landscape_{descriptive_name}`
- Examples: `landscape_signing_verification/`, `landscape_tpm_attestation/`

**Reference scripts are located in:**
- `attestable_conformance_regulatory/`
- `resilience_recovery_rollback/`
- `network_enterprise_connectivity/`
- `security_posture_vuln_response/`

**Purpose:** Provide integration examples and reference implementations for capabilities that Canonical Landscape cannot directly deliver, enabling organizations to extend Landscape functionality for DGX Spark-specific requirements.

---

## Functional Areas

### ✅ 1. Clear Asset Information (COMPLETE - 7 tools)

**Purpose:** Comprehensive device inventory and asset tracking.

**Implemented Tools:**
1. Device Identity - Stable identifier (serial/UUID)
2. Hardware Configuration - CPU/GPU/SSD/NIC enumeration
3. Firmware Version Reporter - BIOS/UEFI/EC/NIC/SSD/GPU firmware
4. OS Build Identity - Ubuntu + DGX build info
5. Driver Inventory - GPU/NIC/storage/USB drivers
6. Software Inventory - dpkg/snap/pip/docker packages
7. Asset Tag Manager - UEFI-backed metadata (entitlement + CMDB tags)

**Output Format:** JSON (Redfish-ready)

---

### ✅ 2. Controlled SW/FW Updates (PARTIAL - 1 tool)

**Purpose:** Safe update orchestration with rollback capability.

**Implemented Tools:**
1. Update Control Plane (`spark_updatectl`) - Reboot coordination + kernel rollback + firmware rollback reporting

**Commands:**
- `status` - System update/reboot status
- `reboot plan/schedule/now/cancel` - Reboot coordination
- `rollback kernel-list/set-next/clear-next` - Kernel-only rollback
- `rollback os-backup-status` - OS backup detection
- `fw rollback-report` - Firmware rollback status (report-only)

---

### ✅ 3. Remote Ops & Remediation (COMPLETE - 2 tools)

**Purpose:** Remote diagnostics, troubleshooting, and incident analysis.

**Implemented Tools:**
1. Diagnostic Collector (`spark_diagctl`) - Comprehensive diagnostics
   - Health metrics (CPU/GPU/memory/disk/network/thermals/power)
   - System event logging (journald/syslog)
   - Hardware/FW event logs (boot/ACPI/PCIe/ESRT/fwupd/rasdaemon)
   - Crash diagnostics (kdump/core dumps/pstore)
   - GPU telemetry (NVIDIA metrics/processes/errors)

2. Reset Reason Reporter - Boot/reboot reason forensics
   - 7 evidence sources
   - 7 reason codes with confidence scoring
   - Conservative classification

---

### ✅ 4. Data Protection & Privacy (PARTIAL - 1 tool)

**Purpose:** Secure data deletion and privacy compliance.

**Implemented Tools:**
1. Secure Erase Tool - Secure deletion for decommissioning
   - 8 erase methods (NVMe/SATA/LUKS/generic)
   - Safety-first with multiple confirmations
   - NIST SP 800-88 compliance
   - Plan-execute-verify workflow

---

### 📋 5. Attestable Conformance & Regulatory (Landscape Reference Scripts)

**Purpose:** Compliance verification and regulatory policy enforcement.

**Implementation Type:** Landscape Reference Scripts

**Implemented Reference Scripts:**
- `landscape_signing_verification` - APT cryptographic signing verification

---

### 📋 6. Resilience, Recovery & Rollback Safety (Landscape Reference Scripts)

**Purpose:** Update resilience, system recovery, and rollback protection.

**Implementation Type:** Landscape Reference Scripts

**Implemented Reference Scripts:**
- `landscape_verified_boot_integrity` - UEFI Secure Boot + kernel lockdown + TPM evidence
- `landscape_recovery_backup_levels` - 3-level backup (probe/config snapshot/rebuild manifest)
- `landscape_factory_reset_reprovision` - 4-level factory reset with secure re-provisioning
- `landscape_health_watchdogs` - Watchdog probe + self-test with transient units

---

### 📋 7. Network & Enterprise Connectivity (Landscape Reference Scripts)

**Purpose:** Enterprise network management and connectivity.

**Implementation Type:** Landscape Reference Scripts

**Implemented Reference Scripts:**
- `landscape_collect_package` - Generate support bundle (tar.gz with checksums)
- `landscape_retrieve_logs_stdout` - Retrieve logs to stdout (text or gzip+base64)

---

### 📋 8. Security Posture & Vulnerability Response (Landscape Reference Scripts)

**Purpose:** Security configuration management and vulnerability assessment.

**Implementation Type:** Landscape Reference Scripts

**Implemented Reference Scripts:**
- `landscape_encryption_at_rest` - Encryption-at-rest state reporting (LUKS/dm-crypt, read-only)

---

## Naming Conventions

**Folders:** `snake_case`

**Production Tool Folders:**
```
{functional_area}/{tool_name}/
```

**Reference Script Folders:**
```
{functional_area}/landscape_{script_name}/
```

**Files:**
- Python scripts: `snake_case.py`
- Shell scripts: `snake_case.sh` or `kebab-case.sh`
- Config files: `default.json` or `default.conf`
- Documentation: `UPPERCASE.md` or `kebab-case.md`

**Examples:**

Production tool:
```
clear_asset_information/hardware_inventory_collector/src/device_identity.py
```

Reference script:
```
attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh
```

---

## Configuration Pattern

Each tool has:
```
{tool_folder}/
├── src/{tool_name}.py          # Main script
├── config/default.json         # Default configuration
├── install.sh                  # Installation script
└── README.md                   # Tool documentation
```

**Configuration precedence:**
1. CLI arguments (highest priority)
2. Config file (if specified via `--config`)
3. Built-in defaults (lowest priority)

---

## Development Workflow

### 1. Create New Tool

```bash
# Use template
cp docs/templates/PYTHON_SCRIPT_TEMPLATE.py \
   {functional_area}/{tool_name}/src/{tool_name}.py

# Follow structure
{functional_area}/{tool_name}/
├── README.md
├── src/{tool_name}.py
├── config/default.json
└── install.sh
```

### 2. Install Tool

```bash
cd {functional_area}/{tool_name}
bash install.sh
```

### 3. Test Tool

```bash
# Unit tests
bash tests/run_unit_tests.sh

# Manual test
bin/{tool_name}.py --help
```

### 4. Documentation

- Update tool README.md
- Update functional area README.md
- Update PROJECT_STRUCTURE.md (this file)

---

## Testing Strategy

**Unit Tests:**
- Location: `tests/unit/{functional_area}/`
- Pattern: `test_{tool_name}.py`
- Fixtures: `tests/unit/{functional_area}/fixtures/`
- Runner: `tests/run_unit_tests.sh`

**Integration Tests:**
- Location: `tests/integration/`
- Test tool interactions
- Runner: `tests/run_integration_tests.sh`

**System Tests:**
- Location: `tests/system/`
- End-to-end scenarios
- Runner: `tests/run_all_tests.sh`

---

## Dependencies

**Python:**
- Stdlib-only (no pip dependencies)
- Python 3.6+ required

**System Tools:**
- Ubuntu Linux Pro (ARM64 or x86_64)
- systemd (journalctl, systemctl, loginctl)
- Standard tools: lsblk, lscpu, ip, ethtool, lspci, lsusb, lsmod, modinfo
- Optional: nvidia-smi, fwupdmgr, nvme-cli, hdparm, cryptsetup, sensors

---

## Key Design Principles

1. **JSON-first output** - All tools output JSON by default
2. **--human flag** - Readable output available via --human
3. **Stdlib-only** - No external Python dependencies
4. **Read-only by default** - State changes require explicit flags + root
5. **Atomic writes** - All file writes use temp + rename
6. **Graceful degradation** - Handle missing tools/permissions gracefully
7. **Comprehensive logging** - Detailed logs for troubleshooting
8. **Safety guardrails** - Multiple confirmations for destructive operations
9. **DGX Spark validated** - All tools tested on actual hardware

---

## Production Deployment

**Installation:**
```bash
# Clone or extract repository, then from repo root:
bash install.sh

# Verify
ls -la bin/
```

`bash install.sh` installs `common/` first, then all tool `install.sh` scripts (see root `reinstall_all.sh`). Use `bash`, not `./install.sh`, when scripts are not marked executable.

**Runtime directories:**
```bash
# Create runtime directories
sudo mkdir -p /var/lib/dgx_spark_management/{clear_asset_information,controlled_sw_fw_updates,remote_ops_remediation}

# Create log directories
sudo mkdir -p /var/log/dgx_spark/{clear_asset_information,controlled_sw_fw_updates,remote_ops_remediation}
```

**Usage:**
```bash
# Asset inventory
sudo bin/device_identity.py
sudo bin/hardware_config.py
sudo bin/firmware_reporter.py

# Diagnostics
bin/spark_diagctl.py health --human
bin/spark_diagctl.py collect-all --tarball

# Reset reason
bin/reset_reason_reporter.py --human

# Update control
bin/spark_updatectl.py status
sudo bin/spark_updatectl.py reboot plan --reason "maintenance"

```

---

## Maintenance

**Adding a new tool:**
1. Create folder under appropriate functional area
2. Implement following the template pattern
3. Write comprehensive README.md
4. Add unit tests + fixtures
5. Update functional area README.md
6. Update this file (PROJECT_STRUCTURE.md)
7. Update root README.md

**Removing a tool:**
1. Remove tool folder
2. Remove from bin/
3. Update all documentation
4. Remove from tests/

---

## License

MIT License - See LICENSE file in repository root.

---

**End of Document**
