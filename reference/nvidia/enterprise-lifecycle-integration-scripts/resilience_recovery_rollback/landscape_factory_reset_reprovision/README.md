# Factory Reset with Secure Re-provisioning

## Purpose

Landscape reference script for **factory reset with secure re-provisioning** on DGX Spark devices.

Maps to requirement: "Factory reset with secure re-provisioning"

Provides multi-level reset capability with gated execution, probe-only mode, and comprehensive re-provisioning guidance.

## Multi-Level Model

### Level 0: Probe Only (Safe)
- Collects readiness evidence (boot config, Pro/Landscape state, identity elements)
- Generates detailed execution plan file
- NO system modifications

### Level 1: Deprovision Management + Identity Reset (DESTRUCTIVE)
Requires: `--execute --confirm=FACTORY_RESET_EXECUTE`
- Removes Landscape client config/state
- Resets `/etc/machine-id`
- Removes SSH host keys
- Optional: Detaches Ubuntu Pro (`--detach-pro=true`)
- Optional: Re-enables cloud-init (`--reenable-cloud-init=true`)

### Level 2: Tenant Cleanup (VERY DESTRUCTIVE)
Requires: `--execute --confirm=FACTORY_RESET_EXECUTE`
- Level 1 actions +
- Optional user data cleanup (`--preserve-users=false`): DELETES `/home/*` (excludes `/home/nvidia`)
- Optional network cleanup (`--preserve-network=false`): REMOTE LOCKOUT

### Level 3: Full Wipe / Reimage Plan (PLAN ONLY)
- Generates reimage instructions (manual execution required)
- Does NOT execute wipe operations

## DGX Spark Specifics

**Bootloader: GRUB**
- Recovery mode entries exist in `/boot/grub/grub.cfg` (root-only access: rw-------)
- Recovery accessed via GRUB menu at boot (NOT a dedicated recovery partition)
- See: https://help.ubuntu.com/community/RecoveryMode

**Ubuntu Pro:**
- Client installed but machine NOT attached on baseline
- Landscape service available via Pro but not enabled
- Script provides placeholders for `pro attach <TOKEN>` (do NOT run automatically)
- Requires `pro attach` before `pro enable landscape`

**cloud-init:**
- Installed but disabled by `/etc/cloud/cloud-init.disabled` marker file
- Enabling requires `--reenable-cloud-init=true` with `--execute`
- WARNING: Enabling cloud-init is optional and may change boot behavior

**NetworkManager:**
- System connections in `/etc/NetworkManager/system-connections/`
- Removing connections causes remote lockout (requires console access)

## Usage via SSH

```bash
# Probe readiness (safe; always run first)
ssh root@dgx-spark 'bash -s' < factory_reset_reprovision.sh -- --level 0

# Execute level 1 (management deprovision)
ssh root@dgx-spark 'bash -s' < factory_reset_reprovision.sh -- \
  --level 1 --execute --confirm=FACTORY_RESET_EXECUTE

# Execute level 1 + Pro detach (if attached)
ssh root@dgx-spark 'bash -s' < factory_reset_reprovision.sh -- \
  --level 1 --execute --confirm=FACTORY_RESET_EXECUTE --detach-pro=true
```

## Usage via Landscape Remote Script Execution

Upload script to Landscape, then execute on target machines:

```bash
# Probe only
--level 0

# Execute with confirmation
--level 1 --execute --confirm=FACTORY_RESET_EXECUTE

# Execute with Pro detach
--level 1 --execute --confirm=FACTORY_RESET_EXECUTE --detach-pro=true
```

**Note:** Landscape Remote Script Execution has size limits (`script_output_limit`). Artifacts are stored locally in `/var/lib/dgx_spark_management/.../run_<UTC>/`.

## Output

**JSON Fields:**
- `status`: PASS / FAIL / UNKNOWN
- `level`: 0-3
- `mode`: plan / execute
- `pro_attached`, `landscape_service_available`, `landscape_client_installed`
- `cloud_init_disabled_marker_present`
- `machine_id_present`, `ssh_hostkey_count`, `nm_connection_count`
- `dgx_tools`: Detection of spark_updatectl, spark_diagctl
- `plan_file`, `out_dir`
- `actions_taken[]`, `fail_reasons[]`, `missing_optional[]`

**Exit Codes:**
- `0` = PASS (probe succeeded or execution completed)
- `1` = FAIL (execution failed or missing confirmation)
- `2` = UNKNOWN (missing prerequisites or cannot create output dir)

## Acceptance Tests

### Test 1: Plan-Only Mode (Safe)
```bash
sudo bash resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh --level 0
```

Expected:
- Prints JSON with `status: "PASS"`
- Creates `run_<UTC>/` directory with evidence files + plan file
- `pro_attached: false` (on baseline)
- `cloud_init_disabled_marker_present: true` (on baseline)
- `landscape_service_available: "yes"` (if Pro client present)

### Test 2: Execute Gate Check
```bash
sudo bash resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh --level 1 --execute
```

Expected:
- `status: "FAIL"`
- `fail_reasons: ["Execute mode requires --confirm=FACTORY_RESET_EXECUTE"]`

### Test 3: Root Requirement Check
```bash
bash resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh --level 0
```

Expected (without sudo):
- `grub_recovery_entry_lines: -1` (permission denied)
- `missing_optional: ["grub_cfg_permission_denied"]`

## References

- **Landscape Remote Script Execution:**  
  https://documentation.ubuntu.com/landscape/explanation/features/remote-script-execution/

- **Configure Landscape Client:**  
  https://documentation.ubuntu.com/landscape/how-to-guides/landscape-installation-and-set-up/configure-landscape-client/

- **Enable Landscape via Ubuntu Pro:**  
  https://documentation.ubuntu.com/landscape/how-to-guides/ubuntu-pro/enable-landscape/  
  https://documentation.ubuntu.com/pro-client/en/latest/howtoguides/enable_landscape/

- **cloud-init CLI Reference:**  
  https://cloudinit.readthedocs.io/en/latest/reference/cli.html

- **Ubuntu Recovery Mode:**  
  https://help.ubuntu.com/community/RecoveryMode
