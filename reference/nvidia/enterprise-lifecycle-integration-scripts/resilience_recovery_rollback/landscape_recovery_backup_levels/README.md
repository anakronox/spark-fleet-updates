# Recovery Partition & Backup Levels - Landscape Reference Script

## Purpose

Probes recovery environment configuration and creates backup artifacts at different levels (probe-only, config snapshot, or rebuild manifest). Provides read-only assessment of recovery capabilities and local backup tarballs suitable for system restoration planning.

## Recovery Environment on Ubuntu

**Important:** Ubuntu typically does NOT use a dedicated recovery partition. Instead, recovery capabilities are provided through:

1. **GRUB Recovery Mode** - Special boot entries in GRUB menu (single-user mode, read-only root, etc.)
2. **Rescue/Emergency Targets** - systemd targets accessible via kernel parameters
3. **Live USB/Installation Media** - Primary recovery mechanism for reinstallation

This script probes for recovery partition candidates (if present) and identifies GRUB recovery mode entries or systemd-boot configuration.

## Backup Levels

### Level 0: Probe Only (Default)
- Detects UEFI mode, EFI mount, bootloader type
- Identifies recovery partition candidates (searches for "recovery", "rescue", "restore", "OEM" labels)
- Finds GRUB recovery mode entries or systemd-boot entries
- Creates `level0_recovery_probe.json` with findings
- **No tarball created**

### Level 1: Config Snapshot
- **Includes Level 0 probe** +
- APT repository configuration (sources.list, preferences, keyring checksums)
- Partition evidence (lsblk, blkid, findmnt, GPT tables)
- Boot evidence (efibootmgr, EFI binaries, GRUB config excerpts)
- Existing DGX Spark tool outputs (if present)
- **Creates:** `level1_config_backup_<UTC>.tar.gz`

### Level 2: Rebuild Manifest
- **Includes Level 0 probe** +
- Full dpkg package list (Package + Version)
- Kernel/NVIDIA/firmware package subset
- Snap list and version
- Boot evidence pointers (efibootmgr, GRUB entries, EFI binaries)
- **Creates:** `level2_rebuild_manifest_<UTC>.tar.gz`
- **Also creates:** `backup_tarballs_sha256.txt` with checksums

## Landscape Integration

**Deployment:** Canonical Landscape Remote Script Execution

**Usage:**
- Upload to Landscape Script Library
- Execute with parameters: `--level <0|1|2>`
- Requires root privileges for full access (sudo recommended)
- **Deb client recommended** (snap client may have filesystem restrictions)

**Output:** Single-line JSON to stdout + artifacts saved locally

## Command-Line Options

- `--level <0|1|2>` - Backup level (default: 0)
- `--out-root <path>` - Override output directory (default: `/var/lib/dgx_spark_management/...`)
- `--json` - JSON output enabled (default)

## Usage Examples

**Level 0: Probe only**
```bash
sudo bash resilience_recovery_rollback/landscape_recovery_backup_levels/recovery_backup_levels.sh
# or explicitly:
sudo bash .../recovery_backup_levels.sh --level 0
```

**Level 1: Config snapshot**
```bash
sudo bash .../recovery_backup_levels.sh --level 1
```

**Level 2: Rebuild manifest**
```bash
sudo bash .../recovery_backup_levels.sh --level 2
```

## Output

**Stdout:** Single-line JSON with status and artifact paths

**Artifacts location:** `/var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_recovery_backup_levels/run_<UTC_TIMESTAMP>/`

**Level 0 output:**
- `level0_recovery_probe.json`
- `payload/` directory with probe evidence

**Level 1 output:**
- `level1_config_backup_<UTC>.tar.gz` (tarball)
- `level1_config/` directory (before compression)

**Level 2 output:**
- `level2_rebuild_manifest_<UTC>.tar.gz` (tarball)
- `level2_manifest/` directory (before compression)
- `backup_tarballs_sha256.txt` (checksums for verification)

## JSON Output Fields

- `status`: PASS | FAIL | UNKNOWN
- `run_id`: UTC timestamp
- `level`: 0 | 1 | 2
- `uefi_mode`: YES | NO
- `efi_mount`: YES | NO | LIKELY | UNKNOWN
- `bootloader`: grub | systemd-boot | UNKNOWN
- `recovery_partition_candidate_lines`: count of matches
- `grub_recovery_entry_lines`: count of GRUB recovery entries
- `systemd_boot_entry_lines`: count of systemd-boot entries
- `out_dir`: absolute path to run directory
- `level0_json`: path to probe JSON
- `level1_tarball`: path to config tarball (or null)
- `level2_tarball`: path to manifest tarball (or null)
- `sha256`: object with level1/level2 checksums
- `missing_optional`: array of optional items not found
- `notes`: Landscape limitations note

## Exit Codes

- **0 (PASS)**: Requested level artifacts created successfully
- **1 (FAIL)**: Failed to create requested level artifacts
- **2 (UNKNOWN)**: Missing core prerequisites (tar, sha256sum, lsblk)

## Security Notes

**What this script collects:**
- ✅ System configuration files (non-sensitive)
- ✅ Package lists and boot configuration
- ✅ Partition layout and filesystem information

**What is explicitly EXCLUDED:**
- ❌ `/etc/shadow`, `/etc/gshadow` (password hashes)
- ❌ NetworkManager system-connections (network credentials)
- ❌ Netplan YAML with credentials
- ❌ Wi-Fi passwords
- ❌ SSH host keys or user keys
- ❌ Authentication tokens

**Read-Only Operations:**
- Does not modify partitions, filesystems, or boot configuration
- Does not create or modify recovery partitions
- Does not change bootloader entries or kernel parameters

## Limitations

**Recovery Partition:**
- Most Ubuntu systems do NOT have a dedicated recovery partition
- GRUB recovery mode entries are the primary recovery mechanism
- Script can detect recovery partition if present but does not create one

**Artifacts:**
- Tarballs stored locally only (not uploaded)
- For large systems, Level 2 manifest can be several MB
- Landscape stdout is size-limited (JSON summary only)

**Snap Client:**
- Landscape snap client may have AppArmor restrictions
- May not access all `/etc/apt` or `/boot` paths
- Deb client recommended for full functionality

**Boot Configuration:**
- GRUB config read requires root access
- Some boot evidence may be incomplete without root
- Does not parse complex GRUB scripting

## Acceptance Tests

**Test 1: Level 0 Probe**
```bash
sudo bash .../recovery_backup_levels.sh --level 0
```
**Expected:** JSON output, exit code 0, level0_recovery_probe.json created

**Test 2: Level 1 Config Snapshot**
```bash
sudo bash .../recovery_backup_levels.sh --level 1
ls -lh /var/lib/dgx_spark_management/.../run_*/level1_config_backup_*.tar.gz
```
**Expected:** Tarball created, JSON shows tarball path and SHA256

**Test 3: Level 2 Rebuild Manifest**
```bash
sudo bash .../recovery_backup_levels.sh --level 2
cat /var/lib/dgx_spark_management/.../run_*/backup_tarballs_sha256.txt
```
**Expected:** Both tarballs created, checksums file present

**Test 4: Extract and Verify**
```bash
cd /var/lib/dgx_spark_management/.../run_<TIMESTAMP>/
tar -tzf level1_config_backup_*.tar.gz | head -20
sha256sum -c backup_tarballs_sha256.txt
```
**Expected:** Tarball contents listed, checksums verify

## Use Cases

1. **Pre-Update Backup** - Capture config before system updates
2. **Disaster Recovery Planning** - Document recovery environment and boot configuration
3. **System Cloning** - Create manifest for rebuilding similar systems
4. **Compliance Auditing** - Document system configuration and package versions
5. **Troubleshooting** - Capture boot and partition configuration for support

## Reference Links

- [Ubuntu Recovery Mode](https://wiki.ubuntu.com/RecoveryMode)
- [GRUB Recovery](https://help.ubuntu.com/community/Grub2/Troubleshooting)
- [systemd-boot](https://www.freedesktop.org/software/systemd/man/systemd-boot.html)
- [efibootmgr](https://linux.die.net/man/8/efibootmgr)
- [Canonical Landscape](https://ubuntu.com/landscape)
