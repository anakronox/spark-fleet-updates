# Resilience, Recovery & Rollback Safety

**Status:** ✅ Landscape Reference Scripts

This functional area provides reference implementations for update resilience, system recovery, and rollback safety mechanisms.

## Purpose

Ensure safe, transactional updates with verified boot integrity and rollback protection. Enable recovery from failed updates and maintain system stability through known-good restore points.

## Landscape Reference Scripts

Reference scripts provide integration examples and are designed for use with Canonical Landscape management workflows. These are simpler than production tools and focus on demonstrating specific capabilities.

**Structure:**
- Minimal error handling (reference implementations)
- Brief inline documentation
- Simple configuration
- No extensive testing framework

### Implemented Reference Scripts

#### 1. Verified Boot Chain Integrity (`landscape_verified_boot_integrity/`)

**Purpose:** End-to-end boot chain integrity validation (UEFI Secure Boot + kernel lockdown + signatures + TPM evidence).

**Key Features:**
- Validates UEFI Secure Boot state (SecureBoot and SetupMode EFI variables)
- Checks kernel lockdown mode and module signature enforcement
- Collects signature evidence via `sbverify` (kernel, shim, GRUB, BOOTAA64.EFI)
- Captures TPM measured boot signals (event log + PCRs) if available
- Read-only verification (does not modify boot config, UEFI vars, or TPM state)
- Single-line JSON output + detailed evidence files

**Checks:**
- UEFI mode presence
- Secure Boot enabled (SecureBoot=1, SetupMode=0)
- Kernel lockdown active (integrity or confidentiality)
- Module signature enforcement
- EFI binary signatures
- TPM event log and PCR values (optional)

**Usage:**
```bash
sudo bash resilience_recovery_rollback/landscape_verified_boot_integrity/verified_boot_integrity.sh
```

**Exit Codes:** 0=PASS (Secure Boot enabled), 1=FAIL (disabled or issues), 2=UNKNOWN

**Documentation:** See `landscape_verified_boot_integrity/README.md`

---

#### 2. Recovery Partition & Backup Levels (`landscape_recovery_backup_levels/`)

**Purpose:** Probes recovery environment configuration and creates backup artifacts at different levels (probe-only, config snapshot, or rebuild manifest).

**Key Features:**
- Detects recovery partition candidates and GRUB recovery mode entries
- Identifies bootloader type (GRUB or systemd-boot) and configuration
- Creates backup artifacts at three levels (0, 1, 2)
- Level 0: Probe only (recovery detection + boot configuration)
- Level 1: Config snapshot tarball (APT config + boot evidence + existing tool outputs)
- Level 2: Rebuild manifest tarball (dpkg/snap package lists + boot evidence)
- Read-only operations (does not modify partitions or boot config)

**Backup Levels:**
- **Level 0:** Probe only (`level0_recovery_probe.json`)
- **Level 1:** Config snapshot (`level1_config_backup_<UTC>.tar.gz`)
- **Level 2:** Rebuild manifest (`level2_rebuild_manifest_<UTC>.tar.gz`)

**Usage:**
```bash
sudo bash resilience_recovery_rollback/landscape_recovery_backup_levels/recovery_backup_levels.sh --level 0
sudo bash resilience_recovery_rollback/landscape_recovery_backup_levels/recovery_backup_levels.sh --level 1
sudo bash resilience_recovery_rollback/landscape_recovery_backup_levels/recovery_backup_levels.sh --level 2
```

**Exit Codes:** 0=PASS (artifacts created), 1=FAIL (creation failed), 2=UNKNOWN (missing prereqs)

**Documentation:** See `landscape_recovery_backup_levels/README.md`

**Note:** Ubuntu typically uses GRUB recovery mode entries instead of dedicated recovery partitions.

---

#### 3. Factory Reset with Secure Re-provisioning (`landscape_factory_reset_reprovision/`)

**Purpose:** Probe reset readiness + generate plan + optional gated execution for deprovisioning and secure re-provisioning.

**Key Features:**
- **4 reset levels:** Probe-only (0), management deprovision (1), tenant cleanup (2), full wipe plan (3)
- Collects reset readiness evidence (boot config, Ubuntu Pro/Landscape state, identity elements)
- Generates detailed execution plan with re-provisioning steps
- **DESTRUCTIVE operations gated:** Requires `--execute --confirm=FACTORY_RESET_EXECUTE`
- **Safety defaults:** Preserves network and user data by default
- Level 1: Removes Landscape client config/state, resets machine-id and SSH host keys
- Level 2: Optional user data (`/home/*`) and network cleanup (with explicit flags)
- Level 3: Generates reimage plan (manual execution required)

**Reset Levels:**
- **Level 0:** Probe only (safe; no modifications)
- **Level 1:** Management deprovision + identity reset (DESTRUCTIVE)
- **Level 2:** Tenant cleanup (VERY DESTRUCTIVE if preserve flags disabled)
- **Level 3:** Full wipe / reimage plan (plan-only; no execution)

**Usage:**
```bash
# Probe readiness (safe)
sudo bash resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh --level 0

# Execute level 1 (management deprovision)
sudo bash resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh \
  --level 1 --execute --confirm=FACTORY_RESET_EXECUTE

# Execute level 1 + Pro detach (if attached)
sudo bash resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh \
  --level 1 --execute --confirm=FACTORY_RESET_EXECUTE --detach-pro=true
```

**Exit Codes:** 0=PASS (probe succeeded or execution completed), 1=FAIL (execution failed), 2=UNKNOWN (cannot create output dir)

**Documentation:** See `landscape_factory_reset_reprovision/README.md`

**Warning:** Network removal (`--preserve-network=false`) causes remote lockout. User data removal (`--preserve-users=false`) deletes `/home/*`.

---

#### 4. Health Watchdogs (`landscape_health_watchdogs/`)

**Purpose:** Probe system and service watchdog configuration with optional self-test using transient systemd units.

**Key Features:**
- Collects hardware watchdog evidence (`/dev/watchdog0`, sysfs, `wdctl`)
- Probes systemd manager watchdog settings (`RuntimeWatchdogUSec`)
- Captures service restart policies (ssh, NetworkManager, systemd-journald)
- Optional self-test mode (gated with `--execute --confirm=FACTORY_TEST_EXECUTE`)
- Self-test validates auto-restart and watchdog timeout behavior with transient units
- Single-line JSON output + detailed evidence files

**Modes:**
- **Probe (default):** Safe; collects evidence without modifications
- **Self-test (gated):** Creates transient units to test restart and watchdog timeout

**Usage:**
```bash
# Probe mode (safe)
sudo bash resilience_recovery_rollback/landscape_health_watchdogs/health_watchdogs.sh

# Self-test mode (gated)
sudo bash resilience_recovery_rollback/landscape_health_watchdogs/health_watchdogs.sh \
  --self-test --execute --confirm=FACTORY_TEST_EXECUTE
```

**Exit Codes:** 0=PASS (watchdog detected and evidence collected, or self-test passed), 1=FAIL (self-test failed), 2=UNKNOWN (systemctl/journalctl missing)

**Documentation:** See `landscape_health_watchdogs/README.md`

**DGX Spark Notes:**
- Hardware watchdog present: `/dev/watchdog0` (SBSA Generic Watchdog)
- systemd `RuntimeWatchdogUSec=0` by default (not enabled at system level)
- Service-level watchdog proven via `Type=notify` + `WatchdogSec` transient test

---

**Last Updated:** January 15, 2026  
**Maintainer:** DGX Spark Management Team
