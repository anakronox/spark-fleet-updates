# Controlled SW/FW Updates

**Status:** ✅ Partial Implementation (1 tool implemented)

This functional area provides managed and controlled software and firmware update capabilities for DGX Spark devices.

## Overview

Controlled SW/FW Updates ensures that all software and firmware updates are safely coordinated with proper rollback mechanisms.

## Implemented Tools

### ✅ 1. Update Control Plane (`spark_updatectl.py`)

**Status:** Complete  
**Location:** `update_control_plane/`

**Purpose:** Reboot coordination, kernel rollback, and firmware rollback reporting.

**Key Features:**
- **Reboot Coordination:**
  - Status reporting (current kernel, uptime, pending reboot, inhibitors)
  - Reboot planning with safety checks
  - Scheduled reboot (systemd timer-based)
  - Immediate reboot with guardrails
  - Reboot cancellation
  
- **Kernel Rollback:**
  - List available kernel versions
  - Set next-boot kernel (via grub-reboot)
  - Clear next-boot selection
  - OS kernel-only rollback (no package rollback)

- **Firmware Rollback Reporting:**
  - Report firmware versions and downgrade capabilities
  - Query fwupdmgr for device capabilities
  - NO firmware rollback execution (report-only)

- **OS Backup Status:**
  - Detect snapshot tools (timeshift/snapper/etc.)
  - Report filesystem snapshot capabilities

**Commands:**
```bash
# Status
spark_updatectl.py status

# Reboot coordination
spark_updatectl.py reboot plan --reason "maintenance"
sudo spark_updatectl.py reboot schedule --in-minutes 60 --reason "security updates"
sudo spark_updatectl.py reboot now --reason "critical patch"
sudo spark_updatectl.py reboot cancel

# Kernel rollback
spark_updatectl.py rollback kernel-list
sudo spark_updatectl.py rollback kernel-set-next --kernel 6.14.0-1013-nvidia
sudo spark_updatectl.py rollback kernel-clear-next

# Firmware rollback (report only)
spark_updatectl.py fw rollback-report

# OS backup status
spark_updatectl.py rollback os-backup-status
```

**DGX Spark Validation:**
- ✓ systemd PID 1 (systemctl/loginctl/systemd-inhibit available)
- ✓ GRUB bootloader with multiple kernel entries
- ✓ grub-reboot and grub-editenv available
- ✓ fwupdmgr available for firmware reporting
- ✓ Root filesystem is ext4 (no built-in snapshots)

**Output:**
- JSON-first with `--human` option
- Runtime artifacts: `/var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane/`
- Logs: `/var/log/dgx_spark/controlled_sw_fw_updates/update_control_plane/`

---

## Installation

```bash
# Install update control plane
cd update_control_plane
bash install.sh

# Verify installation
bin/spark_updatectl.py --version
```

---

## Usage Examples

### Check System Status

```bash
$ spark_updatectl.py status --human
Current kernel: 6.14.0-1015-nvidia
Uptime: 123456 seconds
Pending reboot: False
Inhibitors: 2 (NetworkManager, UPower)
Available kernels: 2
```

### Plan a Reboot

```bash
$ spark_updatectl.py reboot plan --reason "maintenance window"
{
  "ok": true,
  "data": {
    "plan": {
      "reason": "maintenance window",
      "inhibitors_blocking": false,
      "safe_to_proceed": true
    }
  }
}
```

### Schedule a Reboot

```bash
$ sudo spark_updatectl.py reboot schedule --in-minutes 60 --reason "security updates"
# Creates systemd timer for reboot in 60 minutes

$ spark_updatectl.py reboot schedule-status
# Check scheduled reboot status
```

### Kernel Rollback

```bash
# List available kernels
$ spark_updatectl.py rollback kernel-list
Available kernels:
  - 6.14.0-1015-nvidia (current)
  - 6.14.0-1013-nvidia

# Set next boot to older kernel
$ sudo spark_updatectl.py rollback kernel-set-next --kernel 6.14.0-1013-nvidia
Next boot will use: 6.14.0-1013-nvidia

# Reboot to apply
$ sudo reboot
```

---

## Safety & Guardrails

**Reboot Coordination:**
- Detects blocking inhibitors (prevents reboot if critical services are running)
- Supports systemd inhibitor framework
- Audit logging via journald
- Configurable grace periods

**Kernel Rollback:**
- One-time boot selection (via GRUB)
- Reverts to default kernel if rollback kernel fails
- No permanent GRUB configuration changes

**Limitations:**
- Kernel rollback only (no package rollback)
- Firmware rollback is report-only (no execution)
- No automatic update ring/channel management

---

## Integration

This functional area integrates with:
- **Clear Asset Information:** Version tracking and inventory
- **Remote Ops & Remediation:** Diagnostics before/after updates
- **Data Protection & Privacy:** Secure erase during decommissioning

---

## Documentation

- **Update Control Plane:** `update_control_plane/README.md`
- **Root README:** `../README.md`
- **Project Structure:** `../docs/PROJECT_STRUCTURE.md`

---

**Last Updated:** January 8, 2026  
**Maintainer:** Core Development Team
