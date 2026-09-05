# Encryption-at-Rest Management

## Purpose

Comprehensive encryption management for DGX Spark devices with **three encryption methods**:

1. **LUKS Full-Disk Encryption** (RECOMMENDED - direct in-place workflow supported)
2. **fscrypt Directory Encryption** (in-place, safe for data directories)
3. **cryptsetup reencrypt** (in-place full-disk)

Also provides status reporting and guided local execution for encryption workflows.

## Scripts

### `encryption_at_rest.sh` - Default Text UI + Reporting
- Launches a text-based interactive UI by default
- Probes current encryption state (no modifications in report mode)
- Collects evidence files (LUKS signatures, dm-crypt mappings, crypttab, TPM presence)
- Generates enablement plan file with high-level instructions
- `--json` mode is available for machine-readable output

### `encryption_operations.sh` - Encryption Enablement (NEW)
- Enables encryption using fscrypt, direct in-place LUKS root encryption, or cryptsetup reencrypt
- **Multiple operation modes** for different use cases
- Supports unattended automation for fscrypt and reencrypt acknowledgement

## Behavior

**DEFAULT MODE (Interactive Text UI):**
- Guided local menu for report + encryption operations

**READ-ONLY REPORTING MODE (`--json`):**
- Does NOT modify partitions, LUKS headers, or filesystems
- Does NOT enable encryption in-place
- Does NOT enroll TPM tokens
- Safe for compliance scanning and JSON integration

**OPERATIONAL MODES (encryption_operations.sh):**
- `report`: Runs read-only state check (same as encryption_at_rest.sh)
- `fscrypt`: Enables fscrypt on target directory (in-place, safe)
- `reencrypt`: Generic offline LUKS conversion helper (DANGEROUS, requires backup)
- `encrypt|resume|verify`: Direct root encryption workflow (`cryptsetup reencrypt --encrypt`)
- `encrypt-once`: One-time USB boot path + unattended encryption run (then returns to normal boot)
- `usb-key`: Create/check/arm temporary USB boot key with offline runner OS and unattended policy file
- `tpm-status` / `tpm-enable`: TPM visibility + TPM2 token enrollment on LUKS device
- `luks-guide`: Prints the direct root encryption runbook

## DGX Spark Baseline

Expected state on unconfigured DGX Spark:
- `encryption_state`: **DISABLED**
- `root_on_dmcrypt`: false
- `luks_count`: 0
- `tpm_present`: true (SBSA TPM 2.0 typical on ARM64 servers)
- `systemd_cryptenroll_present`: true (if systemd 248+)

## Usage

### UI + Reporting

```bash
# Launch text UI (default)
sudo bash security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh

# JSON report mode (safe, read-only)
sudo bash security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh --json

# Or use operations script in report mode
sudo bash security_posture_vuln_response/landscape_encryption_at_rest/encryption_operations.sh report
```

### Enable Encryption - Method 1: Direct In-Place LUKS Root Encryption

```bash
# Step 0: TPM visibility check
sudo bash encryption_operations.sh tpm-status /dev/nvme0n1p2

# Step 1A: Prepare temporary USB boot key and unattended config file
# (creates ESP + USB rootfs + offline encryption runner)
# (installs prerequisites automatically: debootstrap, rsync, cryptsetup, grub EFI tools, etc.)
sudo bash encryption_operations.sh usb-key create /dev/sdX --wipe --i-accept-risks
# Edit USB file: dgx-fde/unattended.conf

# Step 1B: One-time USB boot path for encryption run (returns to normal boot after)
sudo bash encryption_operations.sh encrypt-once /dev/nvme0n1p2 --usb-key /dev/sdX --i-accept-risks

# Alternative Step 1: Start direct in-place reencryption immediately
sudo bash encryption_operations.sh encrypt /dev/nvme0n1p2 --i-accept-risks

# Optional unattended mode gated by USB config
sudo bash encryption_operations.sh encrypt /dev/nvme0n1p2 --unattended --usb-key /dev/sdX

# If interrupted, resume reencryption
sudo bash encryption_operations.sh resume /dev/nvme0n1p2 --i-accept-risks

# Step 2: Enroll TPM2 auto-unlock token (PCR0+PCR7 by default)
sudo bash encryption_operations.sh tpm-enable /dev/nvme0n1p2

# Step 3: Verify
sudo bash encryption_operations.sh verify /dev/nvme0n1p2

# Or print a concise workflow
sudo bash encryption_operations.sh luks-guide
```

**Advantages:**
- ✅ Encrypts root in-place (no reimage required)
- ✅ TPM2 auto-unlock available
- ✅ Meets compliance requirements

**Disadvantages:**
- ❌ High-risk workflow; backup is mandatory
- ❌ Reencryption time can be long on large NVMe devices

### Enable Encryption - Method 2: fscrypt (IN-PLACE, Safe)

```bash
# Enable fscrypt on a data directory (e.g., /data)
sudo bash encryption_operations.sh fscrypt /data

# Then encrypt the directory (interactive mode)
sudo fscrypt encrypt /data

# Verify
sudo fscrypt status /data
```

Unattended mode (remote automation):

```bash
sudo FSCRYPT_AUTO_ENCRYPT=true \
  FSCRYPT_PASSPHRASE='StrongPassphraseHere' \
  FSCRYPT_PROTECTOR_NAME='dgx_auto' \
  bash encryption_operations.sh fscrypt /data
```

Preferred unattended mode (pre-generated 32-byte raw key file):

```bash
sudo FSCRYPT_AUTO_ENCRYPT=true \
  FSCRYPT_RAW_KEY_FILE='/root/fscrypt.key' \
  FSCRYPT_PROTECTOR_NAME='dgx_auto' \
  bash encryption_operations.sh fscrypt /data
```

**Advantages:**
- ✅ Can be done in-place (no reimage)
- ✅ Safe (no risk to root filesystem)
- ✅ Can be deployed remotely via Landscape
- ✅ Per-directory encryption keys

**Disadvantages:**
- ❌ Does NOT encrypt root filesystem
- ❌ Does NOT encrypt swap partition

**Use Case:** Encrypt ML model directories, datasets, user workspaces on existing systems

### Enable Encryption - Method 3: cryptsetup reencrypt (Offline Generic, DANGEROUS)

```bash
# ⚠️ WARNING: EXTREMELY RISKY - Only use with complete backups
# In-place full-disk encryption (can cause permanent data loss if interrupted)

sudo bash encryption_operations.sh reencrypt /dev/nvme0n1p2 'YourPassphrase' --i-accept-risks

# Non-interactive safety acknowledgement is required:
# - pass --i-accept-risks (4th argument), OR
# - set I_ACCEPT_THE_RISKS=true in the environment
# Script runs cryptsetup in batch mode (no YES prompt)
# Mounted targets are blocked; run from offline/live environment
# Process takes hours/days for large disks
# CANNOT be interrupted without data loss
```

**Advantages:**
- ✅ Can encrypt root filesystem without reimage

**Disadvantages:**
- ❌ RISKY - data loss if interrupted
- ❌ No rollback if it fails
- ❌ Requires manual boot reconfiguration after

**Use Case:** Generic non-root/offline conversion when you explicitly manage boot integration yourself

**This method is intended for advanced maintenance scenarios.**

## Output

**Runtime directory:** `/var/lib/dgx_spark_management/security_posture_vuln_response/landscape_encryption_at_rest/run_<UTC_TIMESTAMP>/`

**Evidence Files:**
- `baseline.txt`: OS release, kernel, cmdline
- `root_mount.txt`: Root filesystem mount info (source, fstype, options)
- `lsblk.txt`, `blkid.txt`: Block device listings
- `dev_mapper_ls.txt`: `/dev/mapper/` contents
- `dmsetup_crypt_targets.txt`: Active dm-crypt targets
- `crypttab_redacted.txt`: `/etc/crypttab` with keys redacted
- `luks_signature_scan.txt`: LUKS signature detection results
- `cryptenroll_tokens.txt`: TPM2 token evidence (if LUKS devices present)
- `ext4_features.txt`: ext4 fscrypt readiness (if applicable)

**Enablement Plan:**
- `enablement_plan.txt`: High-level instructions for enabling encryption

**JSON Fields:**
- `status`: PASS (ENABLED) / FAIL (DISABLED or PARTIAL) / UNKNOWN
- `encryption_state`: ENABLED / PARTIAL / DISABLED / UNKNOWN
- `root_source`, `root_fstype`, `root_on_dmcrypt`
- `luks_devices[]`, `luks_count`
- `dm_crypt_targets_present`, `crypttab_present`, `active_crypttab_lines`
- `tpm_present`, `systemd_cryptenroll_present`, `tpm2_token_found`
- `fscrypt_tool_present`, `fscrypt_ready`
- `evidence_files[]`, `enablement_plan`, `fail_reasons[]`

## Encryption State Classification

- **ENABLED:** Root on dm-crypt AND LUKS devices present
- **PARTIAL:** Root not on dm-crypt BUT LUKS devices present (data partitions encrypted, root not)
- **DISABLED:** Root not on dm-crypt AND no LUKS devices
- **UNKNOWN:** Cannot determine (missing tools)

## Exit Codes

- `0` = PASS (encryption_state == ENABLED)
- `1` = FAIL (encryption_state == DISABLED or PARTIAL)
- `2` = UNKNOWN (required tooling missing)

## Landscape Integration

**Via Remote Script Execution:**
- Single-line JSON to stdout (size-limited)
- Evidence and plan files stored locally
- Run periodically for fleet compliance reporting

**Compliance Workflow:**
1. Run script across fleet
2. Tag systems by `encryption_state`
3. Generate compliance reports
4. Orchestrate direct in-place encryption or reimage for non-compliant systems

### Recommended Approach by Scenario

**New DGX Spark deployment:**
→ Use **LUKS during imaging** where possible, or direct in-place if conversion is required.

**Existing production system (temporary solution):**
→ Use **fscrypt** (Method 2) for data directories
- Encrypt `/data`, `/models`, `/home` immediately
- Plan for LUKS reimage in next maintenance window

**Existing system (no other option):**
→ Use **cryptsetup reencrypt** (Method 3) ONLY if:
- Complete backup exists and has been tested
- Reimage is absolutely impossible
- Risk of data loss is accepted
- Expert guidance is available

## TPM2 Auto-Unlock (LUKS Only)

After enabling LUKS encryption, you can configure TPM2 auto-unlock:

```bash
# Script-managed enrollment (recommended)
sudo bash encryption_operations.sh tpm-enable /dev/nvme0n1p2

# Under the hood this runs systemd-cryptenroll with PCR0+PCR7 (default)
```

**Requirements:**
- TPM 2.0 device present and enabled
- systemd 248+ with cryptenroll support
- LUKS2-encrypted root partition

**PCR Bindings:**
- PCR 0: UEFI firmware + boot configuration
- PCR 7: Secure Boot state

**Important:**
- Always maintain recovery passphrase in separate key slot
- TPM unlock fails if firmware/Secure Boot changes
- System will fallback to passphrase prompt if TPM fails

## Limitations and Warnings

### encryption_at_rest.sh (State Reporting)
- Default behavior is interactive (text UI)
- Use `--json` when you need non-interactive report output
- Does NOT modify LUKS headers or enroll TPM tokens in `--json` report mode
- Snap client confinement may limit filesystem access vs deb client

### encryption_operations.sh (Operational)

**fscrypt mode:**
- Does NOT encrypt root filesystem (only data directories)
- Does NOT encrypt swap partition or /tmp
- Requires ext4/f2fs filesystem with `encrypt` feature
- May require filesystem remount or live USB to enable encrypt feature
- Full unattended encryption uses raw-key mode (`--source=raw_key`) under the hood

**reencrypt mode:**
- ⚠️ **EXTREMELY DANGEROUS** - can cause permanent data loss
- Power failure during reencryption = **UNRECOVERABLE DATA LOSS**
- Requires hours/days to complete (cannot be stopped)
- No rollback mechanism if operation fails
- Requires manual boot reconfiguration after completion
- **NOT SUPPORTED** for production DGX systems without expert guidance
- **ALWAYS** test restore from backup before attempting

**luks-guide mode:**
- Provides guidance for the direct in-place root workflow
- Does not require initramfs shell intervention
- Can be orchestrated with Landscape in phased maintenance windows

**usb-key / encrypt-once modes:**
- USB boot path is intended for the encryption run window only (`BootNext` one-time boot)
- USB OS build is staged locally first, then copied to USB for better robustness on flaky media
- Encryption executes from USB offline environment, targeting unmounted NVMe root
- Normal boot order is preserved after that run
- Unattended run requires explicit USB config approval (`ALLOW_UNATTENDED=true`)

## References

### LUKS Full-Disk Encryption
- Ubuntu Full Disk Encryption: https://ubuntu.com/core/docs/uc20/full-disk-encryption
- LUKS Documentation: https://gitlab.com/cryptsetup/cryptsetup
- LUKS2 Specification: https://gitlab.com/cryptsetup/LUKS2-docs
- systemd-cryptenroll: https://www.freedesktop.org/software/systemd/man/systemd-cryptenroll.html
- TPM2 Integration: https://systemd.io/TPM2/

### fscrypt Directory Encryption
- fscrypt Documentation: https://github.com/google/fscrypt
- ext4 Encryption: https://www.kernel.org/doc/html/latest/filesystems/fscrypt.html
- fscrypt Usage Guide: https://wiki.archlinux.org/title/Fscrypt

### cryptsetup reencrypt (Use with Caution)
- cryptsetup-reencrypt man page: https://man7.org/linux/man-pages/man8/cryptsetup-reencrypt.8.html
- LUKS Reencryption Guide: https://gitlab.com/cryptsetup/cryptsetup/-/wikis/FrequentlyAskedQuestions#6-backup-and-data-recovery

### Compliance and Standards
- NIST SP 800-111: Guide to Storage Encryption Technologies
- FIPS 140-2: Security Requirements for Cryptographic Modules
- GDPR Article 32: Security of Processing (Encryption Requirements)
