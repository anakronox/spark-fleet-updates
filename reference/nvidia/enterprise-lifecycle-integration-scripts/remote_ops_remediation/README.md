# Remote Operations & Remediation

This functional area provides tools for remote management, diagnostics, and automated remediation on DGX Spark devices.

## Overview

Remote operations enable IT administrators to:
- Understand why a device rebooted or reset
- Perform remote diagnostics and troubleshooting
- Execute remediation actions remotely
- Automate common fixes

## Implemented Tools

### 1. Reset Reason Reporter ✅ (Complete)

**Purpose:** Analyze and classify why the system last rebooted or reset.

**Location:** `reset_reason_reporter/`

**Status:** ✅ **COMPLETE** - Production ready

**Key Features:**
- **7 Evidence Sources:**
  - Boot history (journalctl, wtmp)
  - Previous boot shutdown/crash markers
  - Kernel crash markers (panic, oops, lockup)
  - pstore (persistent crash logs)
  - systemd reboot hints
  - EFI variables (CapsuleLast, LoaderEntryRebootReason)
- **7 Reason Codes with Confidence Scoring:**
  - PLANNED_REBOOT (80-95%)
  - KERNEL_PANIC_OR_OOPS (90-100%)
  - WATCHDOG_RESET_SUSPECTED (50-75%)
  - POWER_LOSS_OR_HARD_RESET_SUSPECTED (40-70%)
  - FIRMWARE_UPDATE_REBOOT_SUSPECTED (40-70%)
  - PLANNED_SHUTDOWN (60-80%)
  - UNKNOWN (10-40%)
- **JSON-first output** with `--human` option
- **Conservative classification** (prefers UNKNOWN over speculation)
- **Audit trail:** Plan + result JSON + logs

**Commands:**
- Default: print JSON report
- `--human`: readable summary
- `--record`: write to runtime directory
- `--output <path>`: save to file

**DGX Spark Validation:**
- ✓ journalctl --list-boots works
- ✓ pstore enabled (efi_pstore)
- ✓ EFI variables accessible
- ✓ Previous boot journal accessible

**Output:** `/var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter/`

---

### 2. Diagnostic Collector (spark_diagctl) ✅ (Complete)

**Purpose:** Comprehensive diagnostics and observability control plane.

**Location:** `diagnostic_collector/`

**Status:** ✅ **COMPLETE** - Production ready

**Key Features:**
- **5 Diagnostic Domains:**
  1. **Health Metrics:** CPU, GPU, memory, disk, network, thermals, power
  2. **System Event Logging:** journald, syslog, kernel logs
  3. **Hardware/FW Event Logs:** boot, ACPI, PCIe AER, ESRT, fwupd, rasdaemon
  4. **Crash Diagnostics:** kdump status, core dumps, configuration
  5. **GPU Telemetry:** NVIDIA GPU metrics, processes, errors
- **JSON-first output** with `--human` option
- **Read-only by default** (no system changes)
- **Configurable truncation** (prevents runaway output)
- **Stdlib-only** (no external Python dependencies)

**Commands:**
- `status`: Show diagnostic capabilities
- `health`: Health metrics snapshot
- `logs`: System logs snapshot
- `hwfw-events`: Hardware/firmware events
- `crash status`: Crash dump status
- `crash configure`: Configure crash capture (requires root + --apply)
- `gpu`: GPU telemetry snapshot
- `collect-all`: All diagnostics (optionally create tarball)

**DGX Spark Validation:**
- ✓ journalctl available and working
- ✓ nvidia-smi available (GB10 GPU)
- ✓ sensors available (lm-sensors)
- ✓ fwupdmgr available

**Output:** `/var/lib/dgx_spark_management/remote_ops_remediation/diagnostic_collector/`

---

## Runtime Data

All tools in this functional area write to:
```
/var/lib/dgx_spark_management/remote_ops_remediation/{tool_name}/
```

## Logs

Runtime logs are written to:
```
logs/remote_ops_remediation/{tool_name}/
```

---

## Integration

These tools integrate with:
- **Clear Asset Information**: Device identity and hardware config
- **Controlled SW/FW Updates**: Update control plane (spark_updatectl)
- **Security Posture**: Audit logging and compliance

---

## Getting Started

Once implemented, each tool will have:
- Comprehensive README in its subdirectory
- Installation script (`install.sh`)
- Configuration file in `config/`
- Unit tests in `tests/unit/remote_ops_remediation/`

---

**Last Updated:** January 2026  
**Maintainer:** Core Development Team
