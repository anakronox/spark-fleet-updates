# Reset Reason Reporter

Best-effort classification of why the most recent system reset/reboot happened.

## Table of Contents

- [Overview](#overview)
- [Evidence Sources](#evidence-sources)
- [Reason Codes](#reason-codes)
- [DGX Spark Validation](#dgx-spark-validation)
- [Usage Examples](#usage-examples)
- [Interpretation Guide](#interpretation-guide)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)
- [JSON Schema](#json-schema)

---

## Overview

**Reset Reason Reporter** analyzes multiple evidence sources to determine why the system last rebooted or reset.

**Key Features:**
- JSON-first output (machine-parseable by default)
- `--human` flag for readable summaries
- Conservative classification (prefers UNKNOWN over speculation)
- Confidence scoring (0-100%)
- Multi-source evidence correlation
- Works without root (graceful degradation)
- Stdlib-only (no external dependencies)

**What is "Reset Reason"?**

A best-effort classification of the cause of the most recent system reboot, based on available evidence from:
- systemd journal logs
- wtmp login records
- Kernel crash logs (pstore)
- EFI variables
- systemd shutdown markers

**Important:** This is forensic analysis with inherent uncertainty. The tool provides a **reason code** + **confidence score** + **evidence list**.

---

## Evidence Sources

### 1. Current Boot Identity

- **boot_id**: `/proc/sys/kernel/random/boot_id`
- **kernel**: `uname -r`
- **uptime**: `/proc/uptime`

**Purpose:** Identify the current boot for correlation.

### 2. Boot History

- **systemd**: `journalctl --list-boots` (last 10 boots)
- **wtmp**: `last -x` (last 20 reboot/shutdown records)
- **who**: `who -b` (last boot time)

**Purpose:** Establish boot sequence and timing.

### 3. Previous Boot Shutdown Markers

**Source:** `journalctl -b -1` (previous boot journal)

**Search for:**
- "System is rebooting"
- "Reached target reboot.target"
- "systemd-shutdown"
- "Syncing filesystems"

**Purpose:** Detect clean, planned shutdown sequences.

### 4. Previous Boot Kernel Crash Markers

**Source:** `journalctl -k -b -1` (previous boot kernel log)

**Search for:**
- panic, oops
- hard lockup, soft lockup
- hung, watchdog
- resetting

**Purpose:** Detect kernel crashes, hangs, or watchdog resets.

### 5. pstore (Persistent Storage)

**Location:** `/sys/fs/pstore`

**Contents:**
- dmesg-* (kernel panic logs)
- console-* (console output)
- ftrace-* (function traces)

**Backend:** `efi_pstore` (EFI-based persistent RAM)

**Purpose:** Strong evidence of kernel crashes that survived reboot.

### 6. systemd Reboot Hints

**Location:** `/run/systemd/`

**Files:**
- `reboot-param`
- `reboot-to-firmware-setup`
- `reboot-to-boot-loader-menu`

**Purpose:** Indicate systemd-initiated reboots with specific targets.

### 7. EFI Variables

**Location:** `/sys/firmware/efi/efivars`

**Target Variables:**
- `CapsuleLast-*` (firmware update capsule)
- `LastBoot-*` (boot information)
- `LoaderEntryRebootReason-*` (bootloader reboot reason)

**Purpose:** Platform-specific reset reasons (firmware updates, boot parameters).

---

## Reason Codes

### KERNEL_PANIC_OR_OOPS

**Description:** Kernel panic or oops detected in previous boot.

**Confidence:** 90-100%

**Evidence:**
- pstore records present, OR
- Panic/oops lines in `journalctl -k -b -1`

**Interpretation:** System crashed due to kernel error. Review kernel logs and pstore contents for root cause.

---

### PLANNED_REBOOT

**Description:** Planned reboot with clean shutdown sequence.

**Confidence:** 80-95%

**Evidence:**
- "System is rebooting" in previous boot journal
- "Reached target reboot.target"
- "systemd-shutdown" sequence
- "Syncing filesystems"

**Interpretation:** Normal, intentional reboot (e.g., `reboot` command, systemctl reboot, update-triggered reboot).

---

### PLANNED_SHUTDOWN

**Description:** Planned shutdown (not reboot).

**Confidence:** 60-80%

**Evidence:**
- "systemd-shutdown" in previous boot
- No "reboot.target" markers
- Clean filesystem sync

**Interpretation:** System was powered off intentionally. Current boot may be after manual power-on or scheduled wake.

---

### WATCHDOG_RESET_SUSPECTED

**Description:** Watchdog reset or hard lockup suspected.

**Confidence:** 50-75%

**Evidence:**
- "watchdog" or "hard lockup" / "soft lockup" in kernel log
- No clean shutdown markers

**Interpretation:** System hung and was reset by hardware/software watchdog. Investigate processes/drivers that may have caused hang.

---

### POWER_LOSS_OR_HARD_RESET_SUSPECTED

**Description:** Power loss or hard reset suspected.

**Confidence:** 40-70%

**Evidence:**
- No clean shutdown markers
- No kernel panic evidence
- Abrupt boot (wtmp shows reboot without preceding shutdown)

**Interpretation:** System lost power or was hard-reset (power button, IPMI reset). Check power logs, physical environment, remote management logs.

---

### FIRMWARE_UPDATE_REBOOT_SUSPECTED

**Description:** Firmware update reboot suspected.

**Confidence:** 40-70%

**Evidence:**
- `CapsuleLast-*` EFI variable present
- fwupd offline update markers (optional)

**Interpretation:** System rebooted to apply firmware update. Check fwupd logs for update details.

---

### UNKNOWN

**Description:** Insufficient evidence to determine reset reason.

**Confidence:** 10-40%

**Evidence:**
- Partial or missing journal data
- Conflicting signals
- First boot after installation

**Interpretation:** Unable to classify confidently. Manual log review recommended.

---

## DGX Spark Validation

### Verified Evidence Sources

**systemd boot history:**
```bash
$ journalctl --list-boots
-2 a1b2c3d4... Mon 2025-01-06 10:00:00 EST—Mon 2025-01-06 18:00:00 EST
-1 e5f6g7h8... Mon 2025-01-06 18:01:00 EST—Tue 2025-01-07 10:00:00 EST
 0 i9j0k1l2... Tue 2025-01-07 10:01:00 EST—Tue 2025-01-07 20:00:00 EST
```

**wtmp history:**
```bash
$ last -x | grep reboot
reboot   system boot  6.14.0-1015-nv Tue Jan  7 10:01
reboot   system boot  6.14.0-1015-nv Mon Jan  6 18:01
```

**Previous boot clean shutdown:**
```bash
$ journalctl -b -1 | grep -i "system is rebooting\|reboot.target"
Jan 06 17:59:55 dgx-spark systemd-logind[1234]: System is rebooting.
Jan 06 17:59:56 dgx-spark systemd[1]: Reached target reboot.target.
Jan 06 17:59:58 dgx-spark systemd-shutdown[5678]: Syncing filesystems and block devices.
```

**pstore (empty on sample system):**
```bash
$ ls /sys/fs/pstore
(empty)

$ lsmod | grep efi_pstore
efi_pstore             16384  0

$ systemctl status systemd-pstore
● systemd-pstore.service - Platform Persistent Storage Archival
     Loaded: loaded (/lib/systemd/system/systemd-pstore.service; enabled)
     Active: inactive (dead)
       Docs: man:systemd-pstore(8)
```

**EFI variables present:**
```bash
$ ls /sys/firmware/efi/efivars/ | grep -E 'CapsuleLast|LastBoot|LoaderEntry'
CapsuleLast-8be4df61-93ca-11d2-aa0d-00e098032b8c
LoaderEntryRebootReason-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f
```

---

## Usage Examples

### Example 1: Basic Report (JSON)

```bash
$ reset_reason_reporter.py
{
  "ok": true,
  "data": {
    "current_boot": {
      "boot_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "kernel": "6.14.0-1015-nvidia",
      "uptime_seconds": 3600
    },
    "last_reset": {
      "reason_code": "PLANNED_REBOOT",
      "confidence": 85,
      "summary": "Planned reboot with clean shutdown sequence",
      "evidence": [
        {
          "source": "journald_prev_boot",
          "detail": "Clean shutdown sequence detected",
          "severity": "info"
        }
      ]
    },
    "signals": {
      ...
    }
  },
  "errors": [],
  "meta": {
    "tool": "reset_reason_reporter",
    "version": "0.1.0",
    "collected_at_utc": "2025-01-08T20:00:00.000000Z"
  }
}
```

### Example 2: Human-Readable Report

```bash
$ reset_reason_reporter.py --human
================================================================================
Reset Reason Report
================================================================================

✓ SUCCESS

Current Boot:
  Boot ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Kernel: 6.14.0-1015-nvidia
  Uptime: 3600 seconds

Last Reset Reason:
  Code: PLANNED_REBOOT
  Confidence: 85%
  Summary: Planned reboot with clean shutdown sequence

Evidence:
  ℹ [journald_prev_boot] Clean shutdown sequence detected

Shutdown markers: 4 line(s)

================================================================================
```

### Example 3: Save to File

```bash
$ reset_reason_reporter.py --output /tmp/reset_reason.json
# Output written to /tmp/reset_reason.json
```

### Example 4: Record to Runtime Directory

```bash
$ sudo reset_reason_reporter.py --record
# Recorded to /var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter/

$ ls -l /var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter/
reset_reason_report.json    # Full report
last_reset.json             # Simplified last reset record
```

**last_reset.json format:**
```json
{
  "collected_at_utc": "2025-01-08T20:00:00.000000Z",
  "reason_code": "PLANNED_REBOOT",
  "confidence": 85,
  "summary": "Planned reboot with clean shutdown sequence"
}
```

### Example 5: Kernel Panic Detected

```bash
$ reset_reason_reporter.py --human
================================================================================
Reset Reason Report
================================================================================

✓ SUCCESS

Last Reset Reason:
  Code: KERNEL_PANIC_OR_OOPS
  Confidence: 95%
  Summary: Kernel panic or oops detected in previous boot

Evidence:
  ⚠️ [pstore] Found 2 pstore records
  ⚠️ [journald_prev_boot_kernel] Kernel panic or oops detected in previous boot

pstore: 2 file(s) found
Kernel markers: 5 line(s)

================================================================================
```

---

## Interpretation Guide

### High Confidence (80-100%)

**Action:** Trust the classification.

**Examples:**
- KERNEL_PANIC_OR_OOPS with pstore records
- PLANNED_REBOOT with full shutdown sequence

**What to do:**
- KERNEL_PANIC: Analyze kernel logs, pstore contents, stack traces
- PLANNED_REBOOT: Normal operation, no action needed

### Medium Confidence (50-79%)

**Action:** Consider classification likely but verify.

**Examples:**
- WATCHDOG_RESET_SUSPECTED (watchdog lines but partial journal)
- PLANNED_SHUTDOWN (shutdown markers but no reboot.target)

**What to do:**
- Review evidence in signals section
- Check physical environment (for watchdog/power loss)
- Correlate with external monitoring

### Low Confidence (10-49%)

**Action:** Manual investigation required.

**Examples:**
- UNKNOWN (first boot, missing journals)
- POWER_LOSS_OR_HARD_RESET_SUSPECTED (limited evidence)

**What to do:**
- Review full journal: `journalctl -b -1`
- Check IPMI/BMC logs
- Check power management logs
- Review physical environment

### UNKNOWN Classification

**Common Causes:**
1. First boot after OS installation
2. Journal rotation/cleanup removed previous boot
3. Insufficient permissions to read journals
4. System without pstore support

**Recommendations:**
- Run with `sudo` for full journal access
- Configure persistent journald storage
- Enable pstore if not active
- Accept uncertainty for first boots

---

## Security Considerations

### Sensitive Data in Evidence

**pstore contents:**
- May contain kernel memory dumps
- May include sensitive kernel data structures
- Limit sharing to trusted support channels

**EFI variables:**
- May contain boot parameters
- Rarely sensitive but device-specific

**Journal logs:**
- May contain process arguments, paths
- Redact before sharing externally

### Permissions

**Read-only operations:**
- Tool does not modify system state
- Safe to run as non-root (reduced journal access)

**Best practice:**
- Run with sudo for full journal access
- Store reports securely (may contain system internals)
- Rotate/archive reset reason reports regularly

---

## Troubleshooting

### Issue: UNKNOWN classification

**Symptom:**
```json
{
  "reason_code": "UNKNOWN",
  "confidence": 30
}
```

**Causes:**
1. First boot after installation
2. Previous boot journal not available
3. Insufficient permissions

**Solutions:**
- Run with `sudo` for full journal access
- Check journald persistence: `/var/log/journal` exists?
- Accept UNKNOWN for first boots after install

---

### Issue: Permission denied errors

**Symptom:**
```json
{
  "errors": ["Previous boot journal not accessible: ..."]
}
```

**Cause:** Non-root user cannot access all journal entries

**Solution:**
```bash
sudo reset_reason_reporter.py
```

---

### Issue: Empty pstore

**Symptom:**
pstore section shows `"files": []` even after suspected crash

**Causes:**
1. pstore not enabled in kernel config
2. EFI backend not loaded
3. Crash did not trigger pstore write
4. systemd-pstore already archived to /var/lib/systemd/pstore

**Solutions:**
```bash
# Check if pstore is mounted
mount | grep pstore

# Check if efi_pstore is loaded
lsmod | grep efi_pstore

# Check archived pstore
ls /var/lib/systemd/pstore/
```

---

### Issue: No previous boot journal

**Symptom:**
```json
{
  "errors": ["Previous boot journal not accessible: Specifying boot ID or boot offset has no effect"]
}
```

**Cause:** Journal storage not persistent (volatile/auto mode)

**Solution:**
```bash
# Check journald storage mode
journalctl | head -1

# Enable persistent storage
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

---

## JSON Schema

### Top-Level Structure

```json
{
  "ok": true|false,
  "data": { ... },
  "errors": [ "..." ],
  "meta": {
    "tool": "reset_reason_reporter",
    "version": "0.1.0",
    "collected_at_utc": "...",
    "truncation": {
      "max_lines": 200,
      "max_bytes": 200000
    }
  }
}
```

### data.current_boot

```json
{
  "boot_id": "a1b2c3d4-...",
  "kernel": "6.14.0-1015-nvidia",
  "uptime_seconds": 3600
}
```

### data.last_reset

```json
{
  "reason_code": "PLANNED_REBOOT|KERNEL_PANIC_OR_OOPS|...",
  "confidence": 85,
  "summary": "Planned reboot with clean shutdown sequence",
  "evidence": [
    {
      "source": "journald_prev_boot|pstore|efi_vars|...",
      "detail": "...",
      "severity": "strong|warn|info"
    }
  ]
}
```

### data.signals (excerpt)

```json
{
  "systemd_boot_list": {
    "lines": [ "..." ],
    "truncated": false
  },
  "prev_boot_shutdown_markers": {
    "lines": [ "..." ],
    "truncated": false
  },
  "pstore": {
    "mounted": true,
    "backend": "efi_pstore",
    "files": [ "dmesg-efi-...", "..." ],
    "samples": [ { "file": "...", "content": "...", "truncated": false } ],
    "truncated": false
  },
  "efi_vars": [
    {
      "name": "CapsuleLast",
      "guid": "8be4df61-93ca-11d2-aa0d-00e098032b8c",
      "attributes": 7,
      "decoded_text": "...|null",
      "raw_hex": "...|null",
      "truncated": false
    }
  ]
}
```

---

## Integration

### With Support Bundles

Collect reset reason as part of support bundle:

```bash
# In support bundle script:
sudo reset_reason_reporter.py --record
tar czf support_bundle.tar.gz \
  /var/lib/dgx_spark_management/remote_ops_remediation/reset_reason_reporter/ \
  /var/log/dgx_spark/ \
  ...
```

### With Fleet Telemetry

Periodically report reset reasons to central management:

```bash
# Cron/systemd timer:
0 * * * * /usr/local/bin/reset_reason_reporter.py --record
# Central collector fetches last_reset.json
```

### With Automated Remediation

Trigger actions based on reset reason:

```bash
#!/bin/bash
REASON=$(reset_reason_reporter.py | jq -r '.data.last_reset.reason_code')

if [[ "$REASON" == "KERNEL_PANIC_OR_OOPS" ]]; then
    # Collect diagnostics
    spark_diagctl.py collect-all --tarball
    # Alert administrators
    send_alert "Kernel panic detected on $(hostname)"
fi
```

---

## Related Tools

This tool integrates with:

1. **spark_updatectl** (controlled_sw_fw_updates)
   - Correlate reboots with update operations
   - Verify planned reboots were executed

2. **spark_diagctl** (remote_ops_remediation)
   - Collect comprehensive diagnostics after unexpected resets
   - Include reset reason in diagnostic bundle

3. **Clear Asset Information Tools**
   - Include reset reason in device inventory

---

## Known Limitations

1. **Best-Effort Classification:**
   - Not all resets can be classified with high confidence
   - UNKNOWN is a valid outcome

2. **Journal Dependency:**
   - Requires persistent journald storage
   - Cannot classify if previous boot journal unavailable

3. **pstore Dependency:**
   - pstore must be enabled and configured
   - Not all crashes write to pstore

4. **Timing:**
   - Run soon after boot for best results
   - Evidence may be overwritten by subsequent boots

5. **Root Requirement:**
   - Full journal access requires root
   - Non-root users get partial data

---

## License

MIT License - See repository root LICENSE file.

---

## Changelog

### v0.1.0 (2025-01-08)
- Initial implementation
- 7 evidence sources
- 7 reason codes with confidence scoring
- JSON-first design with --human option
- --record mode for runtime artifacts
- Comprehensive documentation

---

**End of Documentation**
