# Health Watchdogs

## Purpose

Landscape reference script for probing system and service watchdog configuration on DGX Spark devices, with optional self-test capability using transient systemd units.

## DGX Spark Validation

**Hardware Watchdog:**
- Present: `/dev/watchdog0` (SBSA Generic Watchdog)
- sysfs: `/sys/class/watchdog/watchdog0/`
- Detected via `wdctl` if available

**systemd Configuration:**
- `RuntimeWatchdogUSec=0` by default (hardware watchdog NOT enabled at system level)
- Service-level watchdog proven via `Type=notify` + `WatchdogSec` transient test

**Service Restart Policies:**
- Services like `ssh.service`, `NetworkManager.service` have restart policies
- Auto-restart behavior validated via transient unit tests

## Usage

### Probe Mode (Default, Safe)
```bash
sudo bash resilience_recovery_rollback/landscape_health_watchdogs/health_watchdogs.sh
```

Collects evidence:
- systemd manager watchdog settings (`RuntimeWatchdogUSec`, `ShutdownWatchdogUSec`, `WatchdogDevice`)
- Hardware watchdog presence (`/dev/watchdog*`, `/sys/class/watchdog`)
- sysfs watchdog0 fields (identity, timeout, nowayout, state, status, timeleft)
- `wdctl` output for `/dev/watchdog0` (if available)
- `fuser` check (who is holding watchdog device open)
- Kernel journal watchdog lines
- Service policy snapshot (ssh, NetworkManager, systemd-journald)

### Self-Test Mode (Gated, Creates Transient Units)
```bash
sudo bash resilience_recovery_rollback/landscape_health_watchdogs/health_watchdogs.sh \
  --self-test --execute --confirm FACTORY_TEST_EXECUTE
```

Runs two tests:
1. **Auto-restart test:** Creates transient unit with `Restart=always` that exits with failure; validates `NRestarts` increases
2. **Watchdog timeout test:** Creates transient unit with `Type=notify` + `WatchdogSec=5s` that stops pinging; validates watchdog timeout and restart

## Output

**Runtime directory:** `/var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_health_watchdogs/run_<UTC_TIMESTAMP>/`

**JSON Fields:**
- `status`: PASS / FAIL / UNKNOWN
- `mode`: probe / self_test
- `watchdog_device_present`, `watchdog_device_path`
- `wdctl_present`, `wdctl_timeout_seconds`, `wdctl_settimeout_supported`
- `sysfs`: identity, timeout, nowayout, state, status, timeleft
- `systemd_manager`: RuntimeWatchdogUSec, ShutdownWatchdogUSec, WatchdogDevice
- `services[]`: Restart policies for monitored services
- `self_test`: restart_test and watchdog_test results
- `evidence_files[]`, `fail_reasons[]`

**Exit Codes:**
- `0` = PASS (watchdog device found and evidence collected, or self-test passed)
- `1` = FAIL (self-test failed or gating requirements not met)
- `2` = UNKNOWN (systemctl/journalctl missing or no watchdog device)

## Landscape Integration

Designed for **Landscape Remote Script Execution**:
- Single-line JSON output to stdout
- Evidence files saved locally (output size limits apply)
- Self-test is intentionally gated to prevent accidental execution

## Limitations

- Script does **NOT** enable system-wide `RuntimeWatchdogSec` (policy decision; requires systemd config change)
- Self-test creates transient units with known names (includes run_id to avoid collisions)
- Watchdog timeout test requires `systemd-notify` to be available
- Hardware watchdog may already be claimed by another process (check `fuser` output)

## References

- systemd watchdog: https://www.freedesktop.org/software/systemd/man/systemd.service.html#WatchdogSec=
- Hardware watchdog: https://www.kernel.org/doc/html/latest/watchdog/watchdog-api.html
