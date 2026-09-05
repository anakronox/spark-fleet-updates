# Spark UpdateCtl

Enterprise update control tool for DGX Spark management - Reboot coordination, kernel rollback, and firmware rollback reporting.

## Table of Contents

- [Overview](#overview)
- [Scope](#scope)
- [DGX Spark Validation](#dgx-spark-validation)
- [Design Principles](#design-principles)
- [Commands Reference](#commands-reference)
- [Usage Examples](#usage-examples)
- [Safety and Audit](#safety-and-audit)
- [Troubleshooting](#troubleshooting)
- [JSON Schemas](#json-schemas)

---

## Overview

**Spark UpdateCtl** provides enterprise-friendly orchestration for:

1. **Reboot Coordination**: Safe reboots with inhibitor handling, scheduling, and audit logging
2. **Kernel Rollback**: OS kernel-only rollback via GRUB next-boot selection
3. **Firmware Rollback Reporting**: Capability assessment and constraint reporting (report-only, no execution)

**Key Features:**
- JSON-first output (machine-parseable by default)
- `--human` flag for readable summaries
- Read-only commands work without root
- State-changing operations require explicit root permissions
- Stdlib-only (no external Python dependencies)
- Comprehensive logging and audit trails

---

## Scope

### ✅ In Scope

1. **Reboot Operations:**
   - Status gathering (kernel, uptime, inhibitors, pending reboot)
   - Reboot planning (readiness assessment)
   - Immediate reboot with guardrails
   - Scheduled reboot via systemd timers
   - Schedule management (cancel, status check)

2. **Kernel Rollback:**
   - List available GRUB kernel menuentries
   - Set next-boot kernel (one-time boot selection)
   - Clear next-boot setting
   - OS backup/snapshot capability detection

3. **Firmware Rollback Reporting:**
   - fwupd capability detection
   - Device inventory with version constraints
   - Minimum version enforcement detection
   - Upgrade-only flag detection
   - Optional: query available releases per device

### ❌ Out of Scope

1. **Policy-Controlled Update Channels/Rings:**
   - No ring management (stable/beta/canary)
   - No channel switching logic
   - Use separate policy management tools

2. **Firmware Rollback Execution:**
   - Tool REPORTS firmware rollback capability only
   - Does NOT execute `fwupdmgr downgrade` or `reinstall`
   - Use fwupdmgr directly for actual firmware downgrades

3. **Package Rollback:**
   - Kernel rollback is KERNEL-ONLY
   - Does NOT roll back dpkg/snap packages
   - Does NOT implement APT/dpkg downgrades
   - Use package manager history for package rollback

4. **Full OS Image Recovery:**
   - No disk imaging or OS reinstallation
   - Provides capability detection only
   - Recovery manifest export (metadata only)

---

## DGX Spark Validation

### Validated System Components

**Evidence from DGX Spark SSH session:**

#### systemd (PID 1)
```bash
$ ps -p 1
  PID TTY      STAT   TIME COMMAND
    1 ?        Ss     0:02 /sbin/init
```

**Present Tools:**
- `systemctl` - systemd service manager
- `loginctl` - login manager
- `systemd-inhibit` - inhibitor management
- `journalctl` - journal query
- `last` - login history

**Default Timeouts:**
```bash
$ systemctl show -p DefaultTimeoutStopUSec -p DefaultTimeoutStartUSec
DefaultTimeoutStopUSec=1min 30s
DefaultTimeoutStartUSec=1min 30s
```

#### Inhibitors

**Example inhibitors on DGX Spark:**
```bash
$ loginctl list-inhibitors
     WHO              UID USER  PID WHAT             WHY                 MODE 
     NetworkManager     0 root 1234 sleep            NetworkManager      delay
     UPower             0 root 2345 sleep            UPower              delay
     gdm               42 gdm  3456 sleep            Display Manager     delay

3 inhibitors listed.
```

**Types:**
- `block` inhibitors: Prevent action until removed
- `delay` inhibitors: Delay action briefly (default: allow)

#### Pre-Reboot Hooks

```bash
$ ls /usr/lib/systemd/system-shutdown/
fwupd.shutdown
mdadm.shutdown
```

Pre-reboot hooks exist for firmware updates and RAID management.

#### GRUB Configuration

**Multiple kernel entries present:**
```bash
$ grep "menuentry.*Linux" /boot/grub/grub.cfg
menuentry 'Ubuntu, with Linux 6.14.0-1015-nvidia' ... --id gnulinux-6.14.0-1015-nvidia-advanced-...
menuentry 'Ubuntu, with Linux 6.14.0-1013-nvidia' ... --id gnulinux-6.14.0-1013-nvidia-advanced-...
```

**GRUB tools available:**
- `grub-reboot <menuentry-id>` - Set one-time next boot
- `grub-editenv list` - View environment variables
- `grub-editenv - unset next_entry` - Clear next boot

**Example:**
```bash
$ grub-editenv list
saved_entry=0
next_entry=gnulinux-6.14.0-1013-nvidia-advanced-...
```

#### Firmware Update (fwupd)

**fwupdmgr capabilities:**
```bash
$ fwupdmgr --version
client version: 1.9.31
compile-time dependency versions
```

**Downgrade/Reinstall support:**
```bash
$ fwupdmgr downgrade --help
# (supported)

$ fwupdmgr reinstall --help
# (supported)
```

**Device constraints example:**
```
Device Flags:             internal|updatable|require-ac|only-version-upgrade
```

Some devices have `only-version-upgrade` flag (e.g., UEFI dbx).

---

## Design Principles

### 1. JSON-First Output

**Default:** All commands output JSON to stdout.

```bash
$ spark_updatectl.py status
{
  "ok": true,
  "data": {
    "timestamp": "2025-01-08T15:30:00.000000Z",
    "kernel": {
      "current_kernel": "6.14.0-1015-nvidia"
    },
    ...
  },
  "errors": []
}
```

**Human-Readable:** Use `--human` flag for formatted output.

```bash
$ spark_updatectl.py --human status
================================================================================
Spark UpdateCtl - status
================================================================================

✓ SUCCESS

Timestamp: 2025-01-08T15:30:00.000000Z

Kernel:
  Current: 6.14.0-1015-nvidia

...
```

### 2. Explicit Permissions

**Read-Only Operations (no root required):**
- `status`
- `reboot plan`
- `reboot schedule-status`
- `rollback kernel-list`
- `rollback os-backup-status`
- `fw rollback-report`

**State-Changing Operations (require root):**
- `reboot now`
- `reboot schedule`
- `reboot cancel`
- `rollback kernel-set-next`
- `rollback kernel-clear-next`

**Root Check:**
```json
{
  "ok": false,
  "data": null,
  "errors": ["This operation requires root permissions (run with sudo)"]
}
```

### 3. Safety Guardrails

**Inhibitor Handling:**
- `reboot plan` assesses blocking inhibitors
- `reboot now` fails if blockers present (unless `--force`)
- `reboot schedule` creates systemd timer (blockers checked at execution time)

**Audit Logging:**
- Reboot reason logged to journald (`logger -t spark_updatectl`)
- Reboot reason written to `/run/spark_updatectl_reboot_reason.json`
- All operations logged to `spark_updatectl.log`

**Verification:**
- Kernel rollback: verifies `next_entry` after `grub-reboot`
- Reboot schedule: creates persistent systemd units
- Scheduled reboot: survives systemd daemon-reload

---

## Commands Reference

### status

**Description:** Gather and output unified system status.

**Syntax:**
```bash
spark_updatectl.py [--human] [--output <path>] status
```

**Collects:**
- Current kernel (`uname -r`), boot ID, uptime
- Pending reboot indicators (`/run/reboot-required*`)
- systemd inhibitors (loginctl)
- systemd timeouts
- Last reboot history (`last -x`)
- Available GRUB kernels (parsed from `/boot/grub/grub.cfg`)
- GRUB environment (`grub-editenv list`)
- Firmware rollback summary (device count)

**No root required.**

---

### reboot plan

**Description:** Assess reboot readiness without executing reboot.

**Syntax:**
```bash
spark_updatectl.py [--human] reboot plan \
  [--reason "<text>"] \
  [--delay-sec <int>] \
  [--require-no-blocking-inhibitors] \
  [--allow-delay-inhibitors]
```

**Options:**
- `--reason` - Reason for reboot (stored in plan)
- `--delay-sec` - Proposed delay before reboot
- `--require-no-blocking-inhibitors` - Fail plan if blocking inhibitors present (default: true)
- `--allow-delay-inhibitors` - Allow delay inhibitors (default: true)

**Returns:**
- `blocked`: true/false
- `block_reasons`: List of reasons if blocked
- `safe_to_proceed`: true/false
- `inhibitors`: Full inhibitor list
- `recommended_actions`: Suggested next steps

**No root required.**

---

### reboot now

**Description:** Execute reboot immediately with guardrails.

**Syntax:**
```bash
sudo spark_updatectl.py reboot now \
  [--reason "<text>"] \
  [--delay-sec <int>] \
  [--force]
```

**Options:**
- `--reason` - Reason for reboot (logged to journal)
- `--delay-sec` - Delay before calling `systemctl reboot` (default: 0)
- `--force` - Ignore blocking inhibitors (advanced override)

**Behavior:**
1. Check root permissions
2. Gather inhibitors (fail if blockers present unless `--force`)
3. Write audit record to journald
4. Write reboot reason to `/run/spark_updatectl_reboot_reason.json`
5. Sleep for `--delay-sec` seconds (if specified)
6. Call `systemctl reboot --message "<reason>"`

**Requires root.**

---

### reboot schedule

**Description:** Schedule a reboot via systemd timer.

**Syntax:**
```bash
sudo spark_updatectl.py reboot schedule \
  {--at "YYYY-MM-DD HH:MM:SS" | --in-minutes <int>} \
  [--reason "<text>"] \
  [--force]
```

**Options:**
- `--at` - Absolute time (local time zone)
- `--in-minutes` - Relative time (from now)
- `--reason` - Reason for reboot
- `--force` - Ignore inhibitors at execution time

**Behavior:**
1. Check root permissions
2. Calculate trigger time
3. Create systemd service unit: `spark-updatectl-reboot.service`
   - Executes: `spark_updatectl.py reboot now --reason "<reason>" [--force]`
4. Create systemd timer unit: `spark-updatectl-reboot.timer`
   - OnCalendar= (absolute) or OnActiveSec= (relative)
5. `systemctl daemon-reload`
6. `systemctl enable --now spark-updatectl-reboot.timer`

**Units persist across reboots.**

**Requires root.**

---

### reboot cancel

**Description:** Cancel scheduled reboot.

**Syntax:**
```bash
sudo spark_updatectl.py reboot cancel [--remove-units]
```

**Options:**
- `--remove-units` - Delete systemd units from `/etc/systemd/system`

**Behavior:**
1. `systemctl disable --now spark-updatectl-reboot.timer`
2. If `--remove-units`: delete service and timer files, call `daemon-reload`

**Requires root.**

---

### reboot schedule-status

**Description:** Get status of scheduled reboot.

**Syntax:**
```bash
spark_updatectl.py reboot schedule-status
```

**Returns:**
- `scheduled`: true/false
- `timer_unit`: Unit name
- `NextElapseUSecRealtime`: Next trigger time
- `LastTriggerUSec`: Last trigger time

**No root required.**

---

### rollback kernel-list

**Description:** List available kernels from GRUB config.

**Syntax:**
```bash
spark_updatectl.py [--human] rollback kernel-list
```

**Returns:**
- `current_kernel`: Kernel from `uname -r`
- `available_kernels`: List of kernels with:
  - `title`: GRUB menuentry title
  - `menuentry_id`: GRUB menuentry ID (for `grub-reboot`)
  - `kernel_version`: Extracted kernel version
  - `is_current`: true if matches `uname -r`
- `count`: Number of available kernels

**No root required.**

---

### rollback kernel-set-next

**Description:** Set next boot kernel via GRUB.

**Syntax:**
```bash
sudo spark_updatectl.py rollback kernel-set-next --kernel <version>
```

**Options:**
- `--kernel` - Kernel version (e.g., `6.14.0-1013-nvidia`)

**Behavior:**
1. Check root permissions
2. Parse GRUB config for matching kernel
3. Extract `menuentry_id`
4. Call `grub-reboot <menuentry_id>`
5. Verify with `grub-editenv list` (check `next_entry`)

**Returns:**
- `kernel_version`: Requested kernel
- `menuentry_id`: GRUB menuentry ID set
- `title`: Full menuentry title
- `verified`: true if `next_entry` matches
- `next_entry`: Current value from grub-editenv

**Next boot ONLY:** After one boot, reverts to default kernel.

**Requires root.**

---

### rollback kernel-clear-next

**Description:** Clear next boot kernel setting.

**Syntax:**
```bash
sudo spark_updatectl.py rollback kernel-clear-next
```

**Behavior:**
1. Call `grub-editenv - unset next_entry`
2. Verify with `grub-editenv list`

**Returns:**
- `cleared`: true if `next_entry` is empty/unset
- `grub_env`: Current GRUB environment

**Requires root.**

---

### rollback os-backup-status

**Description:** Report OS backup/snapshot capability.

**Syntax:**
```bash
spark_updatectl.py rollback os-backup-status [--export-manifest]
```

**Options:**
- `--export-manifest` - Export recovery manifest (metadata only)

**Checks:**
- Installed snapshot tools: `timeshift`, `snapper`, `ostree`, `rauc`, `mender`, `zfs`, `btrfs`
- Root filesystem type (via `findmnt /`)
- Snapshot capability assessment

**Returns:**
- `root_filesystem`: Filesystem type (e.g., `ext4`, `btrfs`, `zfs`)
- `installed_tools`: List of detected tools
- `capabilities`: Human-readable capability statements
- `snapshot_capable`: true if snapshots supported
- `recovery_manifest`: (if `--export-manifest`) Metadata export

**Recovery Manifest (metadata only):**
- `/etc/os-release`
- `/etc/dgx-release` (if present)
- List of kernel versions from GRUB
- Written to: `/var/lib/dgx_spark_management/.../recovery_manifest.json`

**No root required.**

---

### fw rollback-report

**Description:** Generate firmware rollback capability report (report-only).

**Syntax:**
```bash
spark_updatectl.py [--human] fw rollback-report [--query-releases]
```

**Options:**
- `--query-releases` - Query available releases per device (slower)

**Checks:**
- fwupdmgr version
- fwupdmgr support for `downgrade` and `reinstall` flags
- Device list with current/minimum versions
- Device flags (e.g., `only-version-upgrade`)
- Optionally: available releases per device (if `--query-releases`)

**Returns:**
- `fwupd_version`: fwupdmgr version string
- `supports_downgrade`: true/false
- `supports_reinstall`: true/false
- `device_count`: Number of devices
- `devices`: List of devices with:
  - `device_id`: Device ID
  - `summary`: Device name
  - `current_version`: Current firmware version
  - `minimum_version`: Minimum allowed version
  - `vendor`: Vendor name
  - `flags`: Device flags
  - `upgrade_only`: true if only upgrades allowed
  - `available_releases`: (if `--query-releases`) List of available versions

**Assessment:**
- Devices with `upgrade_only=true` cannot be downgraded below current version
- Minimum version enforcement prevents downgrade below that version
- Tool DOES NOT execute downgrades (use `fwupdmgr downgrade` manually)

**No root required.**

---

## Usage Examples

### Example 1: Check System Status

```bash
$ spark_updatectl.py status
```

**Output (JSON):**
```json
{
  "ok": true,
  "data": {
    "timestamp": "2025-01-08T15:30:00.000000Z",
    "kernel": {
      "current_kernel": "6.14.0-1015-nvidia",
      "uname_all": "Linux dgx-spark 6.14.0-1015-nvidia #15-Ubuntu SMP..."
    },
    "uptime": {
      "uptime_seconds": 432000,
      "uptime_human": "5 days, 0:00:00",
      "boot_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    },
    "pending_reboot": {
      "pending": true,
      "indicators": ["/run/reboot-required exists"],
      "packages": ["linux-image-6.14.0-1015-nvidia"]
    },
    "inhibitors": {
      "inhibitors": [
        {"what": "sleep", "who": "NetworkManager", "why": "NetworkManager", "mode": "delay"}
      ],
      "blocking_count": 0,
      "delay_count": 1
    },
    "available_kernels": [
      {
        "title": "Ubuntu, with Linux 6.14.0-1015-nvidia",
        "menuentry_id": "gnulinux-6.14.0-1015-nvidia-advanced-...",
        "kernel_version": "6.14.0-1015-nvidia"
      },
      {
        "title": "Ubuntu, with Linux 6.14.0-1013-nvidia",
        "menuentry_id": "gnulinux-6.14.0-1013-nvidia-advanced-...",
        "kernel_version": "6.14.0-1013-nvidia"
      }
    ]
  },
  "errors": []
}
```

**Human-readable:**
```bash
$ spark_updatectl.py --human status
================================================================================
Spark UpdateCtl - status
================================================================================

✓ SUCCESS

Timestamp: 2025-01-08T15:30:00.000000Z

Kernel:
  Current: 6.14.0-1015-nvidia

Uptime:
  Duration: 5 days, 0:00:00
  Boot ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890

Pending Reboot:
  Status: YES
    /run/reboot-required exists

Inhibitors:
  Blocking: 0
  Delay: 1

Available Kernels:
  • 6.14.0-1015-nvidia (CURRENT)
  • 6.14.0-1013-nvidia

================================================================================
```

---

### Example 2: Plan a Reboot

```bash
$ spark_updatectl.py reboot plan --reason "Monthly maintenance window"
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "timestamp": "2025-01-08T15:35:00.000000Z",
    "reason": "Monthly maintenance window",
    "delay_sec": 0,
    "blocked": false,
    "block_reasons": [],
    "safe_to_proceed": true,
    "inhibitors": {
      "blocking_count": 0,
      "delay_count": 1
    },
    "recommended_actions": []
  },
  "errors": []
}
```

**Human-readable:**
```bash
$ spark_updatectl.py --human reboot plan --reason "Monthly maintenance"
================================================================================
Spark UpdateCtl - reboot_plan
================================================================================

✓ SUCCESS

Reason: Monthly maintenance
Delay: 0 seconds
Blocked: NO
Safe to Proceed: YES

================================================================================
```

---

### Example 3: Schedule a Reboot

```bash
$ sudo spark_updatectl.py reboot schedule --in-minutes 30 --reason "Kernel update"
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "reason": "Kernel update",
    "trigger_time": "2025-01-08T16:05:00",
    "on_calendar": null,
    "on_active_sec": "30min",
    "timer_unit": "spark-updatectl-reboot.timer",
    "service_unit": "spark-updatectl-reboot.service"
  },
  "errors": []
}
```

**Check schedule status:**
```bash
$ spark_updatectl.py reboot schedule-status
{
  "ok": true,
  "data": {
    "scheduled": true,
    "timer_unit": "spark-updatectl-reboot.timer",
    "NextElapseUSecRealtime": "Wed 2025-01-08 16:05:00 EST"
  },
  "errors": []
}
```

**Cancel schedule:**
```bash
$ sudo spark_updatectl.py reboot cancel --remove-units
{
  "ok": true,
  "data": {"cancelled": true},
  "errors": []
}
```

---

### Example 4: Kernel Rollback

**List available kernels:**
```bash
$ spark_updatectl.py rollback kernel-list
{
  "ok": true,
  "data": {
    "current_kernel": "6.14.0-1015-nvidia",
    "available_kernels": [
      {
        "title": "Ubuntu, with Linux 6.14.0-1015-nvidia",
        "menuentry_id": "gnulinux-6.14.0-1015-nvidia-advanced-...",
        "kernel_version": "6.14.0-1015-nvidia",
        "is_current": true
      },
      {
        "title": "Ubuntu, with Linux 6.14.0-1013-nvidia",
        "menuentry_id": "gnulinux-6.14.0-1013-nvidia-advanced-...",
        "kernel_version": "6.14.0-1013-nvidia",
        "is_current": false
      }
    ],
    "count": 2
  },
  "errors": []
}
```

**Set next boot to older kernel:**
```bash
$ sudo spark_updatectl.py rollback kernel-set-next --kernel 6.14.0-1013-nvidia
{
  "ok": true,
  "data": {
    "kernel_version": "6.14.0-1013-nvidia",
    "menuentry_id": "gnulinux-6.14.0-1013-nvidia-advanced-...",
    "title": "Ubuntu, with Linux 6.14.0-1013-nvidia",
    "verified": true,
    "next_entry": "gnulinux-6.14.0-1013-nvidia-advanced-..."
  },
  "errors": []
}
```

**Verify:**
```bash
$ grub-editenv list
next_entry=gnulinux-6.14.0-1013-nvidia-advanced-...
```

**Reboot to apply:**
```bash
$ sudo spark_updatectl.py reboot now --reason "Kernel rollback test"
```

**After reboot, check kernel:**
```bash
$ uname -r
6.14.0-1013-nvidia
```

**Next boot will return to default kernel (unless you set next again).**

---

### Example 5: Firmware Rollback Report

```bash
$ spark_updatectl.py fw rollback-report
{
  "ok": true,
  "data": {
    "fwupd_version": "client version: 1.9.31",
    "supports_downgrade": true,
    "supports_reinstall": true,
    "device_count": 8,
    "devices": [
      {
        "device_id": "a1b2c3d4...",
        "summary": "UEFI dbx",
        "current_version": "413",
        "minimum_version": "0",
        "vendor": "UEFI Forum",
        "flags": "internal|updatable|require-ac|only-version-upgrade",
        "upgrade_only": true
      },
      {
        "device_id": "e5f6g7h8...",
        "summary": "Samsung SSD 980 PRO",
        "current_version": "NXHB202Q",
        "minimum_version": "NXHB200Q",
        "vendor": "Samsung",
        "flags": "internal|updatable|require-ac",
        "upgrade_only": false
      }
    ]
  },
  "errors": []
}
```

**Interpretation:**
- **UEFI dbx**: `upgrade_only=true` → Cannot downgrade (security policy)
- **Samsung SSD**: `upgrade_only=false` → Can downgrade to >= `NXHB200Q` (minimum version)

**To actually downgrade (manual):**
```bash
# Only for devices where upgrade_only=false
$ sudo fwupdmgr downgrade <device-id>
```

---

## Safety and Audit

### Inhibitor Handling

**Blocking Inhibitors:**
- Created by applications to PREVENT reboot/shutdown
- Example: Critical service running, unsaved work
- `reboot now` fails unless `--force` used (advanced override)

**Delay Inhibitors:**
- Request brief delay to clean up gracefully
- Typically allowed (default: `allow_delay_inhibitors=true`)
- Example: NetworkManager saving state

**Viewing Inhibitors:**
```bash
$ loginctl list-inhibitors
     WHO              UID USER  PID WHAT             WHY                 MODE 
     NetworkManager     0 root 1234 sleep            NetworkManager      delay
```

**Handling:**
1. `reboot plan` reports inhibitor status
2. `reboot now` checks blockers before proceeding
3. `reboot schedule` creates timer; blockers checked at trigger time

---

### Audit Logging

**Journal Logging:**
```bash
$ sudo spark_updatectl.py reboot now --reason "Security patch"
# Logs to journald:
$ journalctl -t spark_updatectl
Jan 08 15:45:00 dgx-spark spark_updatectl[12345]: Reboot initiated: Security patch
```

**Reboot Reason File:**
- Written to: `/run/spark_updatectl_reboot_reason.json`
- Contains: timestamp, reason, forced flag
- Survives until next boot (tmpfs)

**Log File:**
- Default: `logs/controlled_sw_fw_updates/update_control_plane/spark_updatectl.log`
- Repo-local for development
- All operations logged

---

### Kernel Rollback Safety

**What it does:**
- Sets GRUB `next_entry` for ONE boot
- Boots to older kernel version
- System uses older kernel but SAME packages

**What it does NOT do:**
- Does NOT roll back installed packages
- Does NOT roll back dpkg/snap/pip packages
- Does NOT roll back firmware
- Does NOT roll back configuration files

**When to use:**
- New kernel causes boot failure
- New kernel has driver issues
- Testing kernel compatibility

**When NOT to use:**
- Package-level issues (use APT history)
- Firmware issues (use fwupdmgr)
- Configuration issues (restore from backup)

**After rollback:**
- Verify system stability
- If stable: keep old kernel, remove new kernel
- If unstable: reboot again (reverts to default kernel)

---

### Scheduled Reboot Management

**Created Units:**
```
/etc/systemd/system/spark-updatectl-reboot.service
/etc/systemd/system/spark-updatectl-reboot.timer
```

**Timer Persistence:**
- Units persist across reboots
- Timer survives systemd daemon-reload
- If system reboots before timer triggers, timer is lost (use `Persistent=true`)

**Cancellation:**
```bash
$ sudo spark_updatectl.py reboot cancel
# Disables timer, leaves units

$ sudo spark_updatectl.py reboot cancel --remove-units
# Disables timer AND deletes units
```

**Verification:**
```bash
$ systemctl status spark-updatectl-reboot.timer
$ systemctl list-timers spark-updatectl-reboot.timer
```

---

## Troubleshooting

### Issue: GRUB config not found

**Symptom:**
```json
{
  "ok": true,
  "data": {...},
  "errors": ["GRUB config not found: /boot/grub/grub.cfg"]
}
```

**Cause:** GRUB config path incorrect or not present

**Solutions:**
1. Check GRUB config location:
   ```bash
   $ ls -l /boot/grub/grub.cfg
   $ ls -l /boot/grub2/grub.cfg  # Alternative
   ```

2. Update config path:
   ```json
   {
     "grub": {
       "grub_cfg": "/boot/grub2/grub.cfg"
     }
   }
   ```

3. Regenerate GRUB config:
   ```bash
   $ sudo update-grub
   ```

---

### Issue: fwupdmgr not found

**Symptom:**
```json
{
  "ok": false,
  "data": null,
  "errors": ["fwupdmgr not found (install fwupd package)"]
}
```

**Cause:** fwupd not installed

**Solution:**
```bash
$ sudo apt install fwupd
$ fwupdmgr --version
```

---

### Issue: Permission denied

**Symptom:**
```json
{
  "ok": false,
  "data": null,
  "errors": ["This operation requires root permissions (run with sudo)"]
}
```

**Cause:** State-changing operation without sudo

**Solution:**
```bash
# Wrong
$ spark_updatectl.py rollback kernel-set-next --kernel 6.14.0-1013-nvidia

# Correct
$ sudo spark_updatectl.py rollback kernel-set-next --kernel 6.14.0-1013-nvidia
```

---

### Issue: systemd daemon-reload warning

**Symptom:**
```json
{
  "ok": true,
  "data": {...},
  "errors": ["systemctl daemon-reload warning: ..."]
}
```

**Cause:** systemd detected unit changes but reload had warnings

**Solution:**
- Usually non-fatal (units still loaded)
- Check systemd logs:
  ```bash
  $ journalctl -u system.slice -n 50
  ```

---

### Issue: Kernel not found in GRUB config

**Symptom:**
```json
{
  "ok": false,
  "data": {"available_kernels": ["6.14.0-1015-nvidia", "6.14.0-1013-nvidia"]},
  "errors": ["Kernel '6.14.0-1012-nvidia' not found in GRUB config"]
}
```

**Cause:** Requested kernel not in GRUB menu

**Solution:**
1. List available kernels:
   ```bash
   $ spark_updatectl.py rollback kernel-list
   ```

2. Check `/boot`:
   ```bash
   $ ls /boot/vmlinuz-*
   ```

3. Update GRUB config:
   ```bash
   $ sudo update-grub
   ```

---

## JSON Schemas

### Standard Response Format

**All commands return:**
```json
{
  "ok": true|false,
  "data": { ... },
  "errors": [ "error1", "error2", ... ]
}
```

**Fields:**
- `ok`: Boolean success flag
- `data`: Command-specific data (null on failure)
- `errors`: List of error/warning messages (empty on success)

---

### status Command

```json
{
  "ok": true,
  "data": {
    "timestamp": "2025-01-08T15:30:00.000000Z",
    "kernel": {
      "current_kernel": "6.14.0-1015-nvidia",
      "uname_all": "Linux dgx-spark ..."
    },
    "uptime": {
      "uptime_seconds": 432000,
      "uptime_human": "5 days, 0:00:00",
      "boot_id": "a1b2c3d4-..."
    },
    "pending_reboot": {
      "pending": true|false,
      "indicators": ["...", ...],
      "packages": ["...", ...]
    },
    "inhibitors": {
      "inhibitors": [
        {"what": "...", "who": "...", "why": "...", "mode": "block|delay"}
      ],
      "blocking_count": 0,
      "delay_count": 1
    },
    "systemd_timeouts": {
      "DefaultTimeoutStopUSec": "1min 30s",
      ...
    },
    "last_reboot_history": [
      {"line": "reboot   system boot ..."}
    ],
    "available_kernels": [
      {
        "title": "Ubuntu, with Linux 6.14.0-1015-nvidia",
        "menuentry_id": "gnulinux-...",
        "kernel_version": "6.14.0-1015-nvidia"
      }
    ],
    "grub_env": {
      "saved_entry": "0",
      "next_entry": "gnulinux-..."
    },
    "firmware_rollback_summary": {
      "fwupd_available": true|false,
      "device_count": 8
    }
  },
  "errors": []
}
```

---

### reboot plan Command

```json
{
  "ok": true,
  "data": {
    "timestamp": "2025-01-08T15:35:00.000000Z",
    "reason": "Monthly maintenance window",
    "delay_sec": 0,
    "blocked": false,
    "block_reasons": [],
    "safe_to_proceed": true,
    "inhibitors": { ... },
    "recommended_actions": []
  },
  "errors": []
}
```

---

### rollback kernel-list Command

```json
{
  "ok": true,
  "data": {
    "current_kernel": "6.14.0-1015-nvidia",
    "available_kernels": [
      {
        "title": "Ubuntu, with Linux 6.14.0-1015-nvidia",
        "menuentry_id": "gnulinux-6.14.0-1015-nvidia-advanced-...",
        "kernel_version": "6.14.0-1015-nvidia",
        "is_current": true
      },
      {
        "title": "Ubuntu, with Linux 6.14.0-1013-nvidia",
        "menuentry_id": "gnulinux-6.14.0-1013-nvidia-advanced-...",
        "kernel_version": "6.14.0-1013-nvidia",
        "is_current": false
      }
    ],
    "count": 2
  },
  "errors": []
}
```

---

### fw rollback-report Command

```json
{
  "ok": true,
  "data": {
    "fwupd_version": "client version: 1.9.31",
    "supports_downgrade": true,
    "supports_reinstall": true,
    "device_count": 8,
    "devices": [
      {
        "device_id": "a1b2c3d4...",
        "summary": "UEFI dbx",
        "current_version": "413",
        "minimum_version": "0",
        "vendor": "UEFI Forum",
        "flags": "internal|updatable|require-ac|only-version-upgrade",
        "upgrade_only": true
      }
    ]
  },
  "errors": []
}
```

---

## Related Tools

This tool integrates with the broader DGX Spark management ecosystem:

1. **Clear Asset Information Tools**
   - Device identity and hardware inventory
   - Firmware version reporting
   - OS build identity
   - Driver and software inventory

2. **Update Management** (future)
   - Package update orchestration
   - Firmware update orchestration
   - Policy-controlled channels

3. **Remote Operations** (future)
   - Remote reboot coordination
   - Remote rollback execution
   - Status aggregation across fleet

---

## Known Limitations

1. **Kernel Rollback Scope:**
   - KERNEL-ONLY (does not roll back packages)
   - Use APT history for package rollback

2. **Firmware Rollback:**
   - REPORT-ONLY (does not execute downgrades)
   - Use `fwupdmgr downgrade` manually

3. **OS Snapshot/Recovery:**
   - Capability detection only
   - No full disk imaging
   - Recovery manifest is metadata only

4. **Reboot Scheduling:**
   - Single scheduled reboot at a time
   - Timer does not persist if system reboots before trigger (unless `Persistent=true`)

5. **GRUB Parsing:**
   - Text-based parsing (fragile to GRUB config format changes)
   - May miss some menuentry formats

---

## License

MIT License - See repository root LICENSE file.

---

## Changelog

### v1.0.0 (2025-01-08)
- Initial implementation
- Status collection
- Reboot coordination (plan, now, schedule)
- Kernel rollback via GRUB
- Firmware rollback reporting
- JSON-first design with --human option
- Comprehensive documentation

---

**End of Documentation**
