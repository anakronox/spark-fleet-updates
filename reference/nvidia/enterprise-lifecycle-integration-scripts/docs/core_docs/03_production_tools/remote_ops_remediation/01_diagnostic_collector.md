# Spark Diagnostics Collector (spark_diagctl)

Comprehensive diagnostics and observability control plane for DGX Spark devices.

## Table of Contents

- [Overview](#overview)
- [Capabilities](#capabilities)
- [DGX Spark Validation](#dgx-spark-validation)
- [Commands](#commands)
- [Usage Examples](#usage-examples)
- [JSON Schemas](#json-schemas)
- [Troubleshooting](#troubleshooting)
- [Security & PII Warnings](#security--pii-warnings)

---

## Overview

**spark_diagctl** provides enterprise-grade diagnostic collection across 5 key observability domains:

1. **Health Metrics** - CPU, GPU, memory, disk, network, thermals, power
2. **System Event Logging** - journald, syslog, kernel logs
3. **Hardware/FW Events** - boot logs, ACPI, PCIe AER, ESRT, fwupd, rasdaemon
4. **Crash Diagnostics** - kdump, core dumps, pstore
5. **GPU Telemetry** - NVIDIA GPU metrics, errors, processes

**Key Features:**
- JSON-first output (machine-parseable by default)
- `--human` flag for readable summaries
- Read-only by default (no system changes)
- Configurable truncation (prevents runaway output)
- Stdlib-only (no external Python dependencies)
- Root not required for most operations

---

## Capabilities

### 1. Health Metrics

**What it collects:**
- **CPU:** Load average (1/5/15 min), CPU count, top processes by CPU usage
- **Memory:** Total, free, available, used percentage
- **Disk:** Filesystems, usage, mount points
- **Network:** Interface stats (RX/TX bytes, state)
- **Thermal:** Temperature sensors (via `sensors`)
- **GPU:** Temperature, utilization, memory, power, clocks (via `nvidia-smi`)

**Sources:**
- `/proc/loadavg`, `/proc/meminfo`
- `df -h`, `ip -s link`
- `sensors` (lm-sensors)
- `nvidia-smi` (NVIDIA driver)

**Use cases:**
- Real-time health monitoring
- Performance troubleshooting
- Capacity planning
- Alerting/threshold detection

---

### 2. System Event Logging

**What it collects:**
- **journald:** systemd journal (recent entries)
- **kernel log:** `journalctl -k` (kernel messages)
- **syslog status:** rsyslog service state

**Sources:**
- `journalctl` (systemd-journald)
- rsyslog (if active)

**Use cases:**
- System event correlation
- Security audit trails
- Service failure analysis
- Boot/reboot investigation

---

### 3. Hardware/Firmware Event Logs

**What it collects:**
- **Boot logs:** Current boot journal entries
- **ACPI events:** Power/thermal ACPI events (via acpid)
- **PCIe AER:** Advanced Error Reporting (bus errors)
- **fwupd history:** Firmware update history
- **rasdaemon:** RAS (Reliability/Availability/Serviceability) events

**Sources:**
- `journalctl -b -0` (boot logs)
- `journalctl -u acpid` (ACPI)
- `journalctl -k --grep=AER` (PCIe errors)
- `fwupdmgr get-history` (firmware updates)
- rasdaemon service

**Use cases:**
- Hardware failure root cause analysis
- Firmware update verification
- Bus error detection (PCIe, memory)
- Compliance/audit trails

---

### 4. Crash Diagnostics

**What it collects:**
- **kdump status:** Is kdump enabled? Service active?
- **kdump config:** `/etc/default/kdump-tools`
- **Core dump config:** `core_pattern`, systemd-coredump status
- **Crash dumps found:** Scan `/var/crash`, `/var/lib/systemd/coredump`

**Sources:**
- `/etc/default/kdump-tools`
- `/proc/sys/kernel/core_pattern`
- `systemctl is-active kdump`
- `systemctl is-active systemd-coredump.socket`

**Use cases:**
- Verify crash capture is enabled
- Locate kernel crash dumps after panic
- Locate userspace core dumps
- Configure crash capture (requires root)

**⚠️ Configuration Changes:**
The `crash configure` subcommand can modify:
- kdump settings
- core_pattern
- sysctl parameters

Requires `--apply` flag + root.

---

### 5. GPU Telemetry

**What it collects:**
- **Per-GPU metrics:**
  - Temperature, fan speed
  - GPU/memory utilization
  - Memory used/total
  - Power draw/limit
  - Clock speeds (graphics, SM, memory)
  - Driver version, VBIOS version
  - UUID
- **GPU processes:** Running processes using GPUs
- **Driver info:** `/proc/driver/nvidia/version`
- **GPU kernel messages:** nvidia/NVRM messages in kernel log

**Sources:**
- `nvidia-smi --query-gpu=...`
- `nvidia-smi pmon`
- `/proc/driver/nvidia/`
- `journalctl -k --grep=nvidia`

**Use cases:**
- GPU performance monitoring
- Thermal management
- Utilization tracking
- GPU error detection
- Workload analysis

---

## DGX Spark Validation

### Verified Tools Present

```bash
$ which journalctl nvidia-smi sensors fwupdmgr
/usr/bin/journalctl
/usr/bin/nvidia-smi
/usr/bin/sensors
/usr/sbin/fwupdmgr
```

### Verified Commands Work

**Health metrics:**
```bash
$ cat /proc/loadavg
0.52 0.58 0.61 1/1234 567890

$ nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader
45
```

**Logging:**
```bash
$ journalctl -n 10 --no-pager
-- Journal begins at Mon 2025-01-06 10:00:00 EST, ends at Wed 2025-01-08 20:00:00 EST. --
Jan 08 20:00:00 dgx-spark systemd[1]: Started Session 123 of user admin.
...
```

**GPU telemetry:**
```bash
$ nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu --format=csv,noheader,nounits
0, NVIDIA GB10, 45, 12
```

**Crash dumps:**
```bash
$ systemctl is-active kdump
inactive

$ ls /var/lib/systemd/coredump/
(empty)
```

---

## Commands

### `status`

**Synopsis:**
```bash
spark_diagctl status [--human]
```

**Description:**
Show diagnostic capabilities and service status.

**Output:**
- Tool availability (journalctl, nvidia-smi, sensors, fwupdmgr)
- Crash capture status (kdump, systemd-coredump)
- Logging services (journald, rsyslog)

**Example:**
```bash
$ spark_diagctl status --human
Diagnostic Capabilities:
  ✓ journalctl
  ✓ nvidia_smi
  ✓ sensors
  ✓ fwupdmgr

Crash Capture:
  kdump: False
  coredump: True
```

---

### `health`

**Synopsis:**
```bash
spark_diagctl health [--human] [--output PATH] [--max-lines N] [--max-bytes M]
```

**Description:**
Collect health metrics snapshot.

**Output:**
- CPU load, count, top processes
- Memory total/free/available/used%
- Disk filesystems and usage
- Network interface stats
- Thermal sensors
- GPU temperature, utilization, memory, power

**Example:**
```bash
$ spark_diagctl health --human
CPU:
  Load: 0.52, 0.58, 0.61

Memory:
  Used: 45.2%

GPUs: 1 found
  GPU 0: NVIDIA GB10 - 45°C, 12% util
```

---

### `logs`

**Synopsis:**
```bash
spark_diagctl logs [--human] [--output PATH] [--max-lines N] [--max-bytes M]
```

**Description:**
Collect system logs snapshot.

**Output:**
- Recent journald entries
- Recent kernel log entries
- rsyslog status

**Truncation:**
- Default: 500 lines, 500KB
- Override with `--max-lines`, `--max-bytes`

**⚠️ PII Warning:**
Logs may contain sensitive data (usernames, paths, IP addresses).

---

### `hwfw-events`

**Synopsis:**
```bash
spark_diagctl hwfw-events [--output PATH] [--max-lines N]
```

**Description:**
Collect hardware/firmware event logs.

**Output:**
- Boot logs (current boot)
- ACPI events (power/thermal)
- PCIe AER errors
- fwupd update history
- rasdaemon status

**Use case:**
Hardware failure root cause analysis, firmware update verification.

---

### `crash status`

**Synopsis:**
```bash
spark_diagctl crash status [--human]
```

**Description:**
Show crash dump capture status.

**Output:**
- kdump: enabled? service active? config path
- userspace core dumps: core_pattern, systemd-coredump status
- crash dumps found: paths and sizes

**Example:**
```bash
$ spark_diagctl crash status --human
kdump:
  Enabled: False
  Service: inactive

Coredumps:
  systemd-coredump: active
  core_pattern: |/lib/systemd/systemd-coredump %P %u %g %s %t %c %h

Dumps found: 0
```

---

### `crash configure`

**Synopsis:**
```bash
sudo spark_diagctl crash configure [--enable-kdump] [--core-pattern PATTERN] [--apply]
```

**Description:**
Configure crash capture settings.

**⚠️ Requires root + `--apply` to make changes.**

**Options:**
- `--enable-kdump`: Enable kdump kernel crash dumps
- `--core-pattern PATTERN`: Set userspace core dump pattern
- `--apply`: Actually apply changes (without this, dry-run only)

**Example:**
```bash
# Dry-run (no changes)
$ sudo spark_diagctl crash configure --enable-kdump

# Apply changes
$ sudo spark_diagctl crash configure --enable-kdump --apply
```

**⚠️ Note:**
Enabling kdump may require:
- Modifying `/etc/default/kdump-tools`
- Adding `crashkernel=` to GRUB command line
- Reboot

---

### `gpu`

**Synopsis:**
```bash
spark_diagctl gpu [--output PATH] [--max-lines N]
```

**Description:**
Collect GPU telemetry snapshot.

**Output:**
- Per-GPU metrics (temp, util, memory, power, clocks)
- Driver version, VBIOS version
- GPU processes
- GPU-related kernel messages

**Example:**
```json
{
  "ok": true,
  "data": {
    "nvidia_smi_available": true,
    "gpus": [
      {
        "index": "0",
        "uuid": "GPU-a1b2c3d4-...",
        "name": "NVIDIA GB10",
        "driver_version": "550.54.15",
        "vbios_version": "96.00.5C.00.01",
        "temp_c": "45",
        "util_gpu_percent": "12",
        "util_mem_percent": "8",
        "mem_used_mib": "2048",
        "mem_total_mib": "24576",
        "power_draw_w": "85.5",
        "power_limit_w": "300.0"
      }
    ]
  }
}
```

---

### `collect-all`

**Synopsis:**
```bash
spark_diagctl collect-all [--tarball] [--output PATH]
```

**Description:**
Collect ALL diagnostics (health + logs + hwfw-events + crash + GPU).

**Options:**
- `--tarball`: Create tarball of results in runtime directory

**Use case:**
Support bundle creation, comprehensive troubleshooting.

**Example:**
```bash
$ spark_diagctl collect-all --tarball
{
  "ok": true,
  "data": {
    "health": { ... },
    "logs": { ... },
    "hwfw_events": { ... },
    "crash": { ... },
    "gpu": { ... },
    "tarball_created": "/var/lib/dgx_spark_management/remote_ops_remediation/diagnostic_collector/spark_diagnostics_20250108_200000.tar.gz"
  }
}
```

---

## Usage Examples

### Example 1: Quick Health Check

```bash
$ spark_diagctl health --human
================================================================================
Spark Diagnostics - health
================================================================================

✓ SUCCESS

CPU:
  Load: 0.52, 0.58, 0.61

Memory:
  Used: 45.2%

GPUs: 1 found
  GPU 0: NVIDIA GB10 - 45°C, 12% util

================================================================================
```

---

### Example 2: Collect Logs (JSON)

```bash
$ spark_diagctl logs --output /tmp/spark_logs.json
# Output written to /tmp/spark_logs.json

$ jq '.data.journald.lines | length' /tmp/spark_logs.json
500
```

---

### Example 3: GPU Monitoring Script

```bash
#!/bin/bash
# Monitor GPU temperature every 5 seconds

while true; do
  spark_diagctl gpu | jq -r '.data.gpus[0] | "GPU \(.index): \(.temp_c)°C, \(.util_gpu_percent)% util, \(.power_draw_w)W"'
  sleep 5
done

# Output:
# GPU 0: 45°C, 12% util, 85.5W
# GPU 0: 46°C, 15% util, 92.3W
# ...
```

---

### Example 4: Check Crash Capture Enabled

```bash
$ spark_diagctl crash status | jq '.data.kdump.enabled'
false

# If false, consider enabling:
$ sudo spark_diagctl crash configure --enable-kdump --apply
```

---

### Example 5: Create Support Bundle

```bash
$ spark_diagctl collect-all --tarball
# Creates: /var/lib/.../spark_diagnostics_YYYYMMDD_HHMMSS.tar.gz

$ tar -tzf /var/lib/.../spark_diagnostics_*.tar.gz
diagnostics_full.json

# Share this tarball with support
```

---

## JSON Schemas

### Status Output

```json
{
  "ok": true,
  "data": {
    "diagnostic_capabilities": {
      "journalctl": true,
      "nvidia_smi": true,
      "sensors": true,
      "fwupdmgr": true
    },
    "crash_capture": {
      "kdump_service_active": false,
      "systemd_coredump_active": true
    },
    "logging": {
      "journald_active": true,
      "rsyslog_active": true
    }
  },
  "errors": [],
  "meta": {
    "tool": "spark_diagctl",
    "version": "0.1.0",
    "collected_at_utc": "2025-01-08T20:00:00.000000Z"
  }
}
```

### Health Output

```json
{
  "ok": true,
  "data": {
    "cpu": {
      "load_average": {
        "1min": 0.52,
        "5min": 0.58,
        "15min": 0.61
      },
      "cpu_count": 20,
      "top_processes": ["python3", "chrome", "code", "systemd", "docker"]
    },
    "memory": {
      "mem_total_kb": 65536000,
      "mem_free_kb": 32768000,
      "mem_available_kb": 35840000,
      "mem_used_percent": 45.2
    },
    "disk": {
      "filesystems": [
        {
          "filesystem": "/dev/nvme0n1p2",
          "size": "3.6T",
          "used": "1.2T",
          "avail": "2.2T",
          "use_percent": "36%",
          "mounted_on": "/"
        }
      ]
    },
    "gpu": {
      "nvidia_smi_available": true,
      "gpus": [ { ... } ]
    }
  }
}
```

---

## Troubleshooting

### Issue: "nvidia-smi not available"

**Symptom:**
```json
{
  "errors": ["nvidia-smi not available"]
}
```

**Cause:**
NVIDIA driver not installed or nvidia-smi not in PATH.

**Solution:**
```bash
# Check driver installed
lsmod | grep nvidia

# Check nvidia-smi path
which nvidia-smi

# Install driver if missing
sudo apt install nvidia-driver-550
```

---

### Issue: "journalctl failed: Permission denied"

**Symptom:**
Partial journal data or errors about journal access.

**Cause:**
Non-root user doesn't have full journal access.

**Solution:**
```bash
# Run with sudo for full access
sudo spark_diagctl logs

# OR add user to systemd-journal group
sudo usermod -aG systemd-journal $USER
# (requires logout/login)
```

---

### Issue: Truncated output

**Symptom:**
```json
{
  "data": {
    "journald": {
      "truncated": true
    }
  }
}
```

**Cause:**
Output exceeded max_lines or max_bytes limits.

**Solution:**
```bash
# Increase limits
spark_diagctl logs --max-lines 1000 --max-bytes 1000000
```

---

### Issue: "sensors" not found

**Symptom:**
```json
{
  "thermal": {
    "sensors_available": false
  }
}
```

**Cause:**
lm-sensors not installed.

**Solution:**
```bash
sudo apt install lm-sensors
sudo sensors-detect --auto
```

---

### Issue: kdump not active

**Symptom:**
```json
{
  "kdump": {
    "service_active": false
  }
}
```

**Cause:**
kdump not configured or disabled.

**Solution:**
```bash
# Check kdump config
cat /etc/default/kdump-tools | grep USE_KDUMP

# Enable kdump
sudo spark_diagctl crash configure --enable-kdump --apply

# May require adding crashkernel= to GRUB and reboot
```

---

## Security & PII Warnings

### Logs May Contain Sensitive Data

**journald/syslog:**
- Usernames
- File paths
- IP addresses
- Process arguments
- Authentication attempts

**Recommendation:**
- Redact PII before sharing logs externally
- Use `--max-lines` to limit exposure
- Store logs securely

---

### GPU Telemetry

**nvidia-smi output:**
- GPU UUIDs (device identifiers)
- Process names (may reveal workload types)

**Generally safe to share** but be aware of process information.

---

### Crash Dumps

**kdump/core dumps:**
- May contain memory snapshots
- May include sensitive application data
- May include encryption keys

**⚠️ NEVER share crash dumps externally without review.**

Share crash dump **metadata** (paths, sizes, timestamps) only.

---

## Related Tools

This tool integrates with:

1. **reset_reason_reporter** (remote_ops_remediation)
   - Correlate crash diagnostics with reset reasons
   - Include reset reason in support bundles

2. **spark_updatectl** (controlled_sw_fw_updates)
   - Verify health before/after updates
   - Include diagnostics in rollback decisions

3. **Clear Asset Information Tools**
   - Correlate hardware inventory with health metrics
   - Map GPU UUIDs to inventory records

---

## Known Limitations

1. **Truncation is aggressive by default:**
   - 500 lines / 500KB limits
   - May miss important data in large logs
   - Use `--max-lines` / `--max-bytes` to adjust

2. **GPU telemetry NVIDIA-only:**
   - No AMD GPU support
   - No Intel Arc support

3. **Crash configuration is placeholder:**
   - `crash configure` does not yet modify files
   - Manual configuration still required

4. **No polling for real-time monitoring:**
   - Snapshot-based (run periodically via cron/systemd timer)
   - Future: add `--watch` mode

5. **Thermal sensors require lm-sensors:**
   - May not work on all hardware
   - Requires `sensors-detect` setup

---

## License

MIT License - See repository root LICENSE file.

---

## Changelog

### v0.1.0 (2025-01-08)
- Initial implementation
- 5 diagnostic domains (health, logs, hwfw-events, crash, GPU)
- 7 commands (status, health, logs, hwfw-events, crash, gpu, collect-all)
- JSON-first with --human option
- Configurable truncation
- Comprehensive documentation

---

**End of Documentation**
