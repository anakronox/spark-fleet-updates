# Verified Boot Chain Integrity - Landscape Reference Script

## Purpose

Validates end-to-end boot chain integrity on DGX Spark devices by checking UEFI Secure Boot status, kernel lockdown configuration, signature evidence, and TPM-based measured boot signals. Provides read-only verification suitable for compliance auditing and security posture assessment.

**"End-to-end" in this context means:**
- **UEFI Secure Boot:** Firmware verifies bootloader signatures
- **Kernel lockdown:** Kernel enforces integrity/confidentiality restrictions
- **Signature evidence:** Bootloader, kernel, and EFI binaries are signed
- **TPM measured boot (optional):** Boot measurements recorded in TPM PCRs and event log

## Landscape Integration

**Deployment Method:** Canonical Landscape Remote Script Execution

**Usage:**
- Upload to Landscape Script Library
- Execute on-demand or on schedule
- Requires root privileges (`sudo`)
- **Deb client recommended** (snap client has AppArmor restrictions on `/sys/firmware/efi/efivars` and `/sys/kernel/security`)

**Output:** Single-line JSON to stdout + detailed evidence files saved locally

## What It Checks

### 1. UEFI Mode
- Verifies `/sys/firmware/efi` exists
- **FAIL** if not in UEFI mode

### 2. Secure Boot State
- Reads `SecureBoot` EFI variable (expected: 1 = enabled)
- Reads `SetupMode` EFI variable (expected: 0 = user mode)
- Corroborates with `mokutil --sb-state` if available
- **FAIL** if Secure Boot disabled or SetupMode enabled

### 3. Kernel Lockdown
- Reads `/sys/kernel/security/lockdown` (active mode: none/integrity/confidentiality)
- Checks `/proc/sys/kernel/module_sig_enforce` (expected: 1)
- Collects dmesg evidence of Secure Boot and lockdown activation

### 4. EFI Boot Configuration
- Lists EFI boot entries via `efibootmgr -v`
- Enumerates EFI binaries under `/boot/efi/EFI` or `/efi/EFI`

### 5. Signature Evidence
- Uses `sbverify --list` on kernel, shim, GRUB, and BOOTAA64.EFI
- **Note:** `sbverify` shows signatures but does not validate trust chains against platform DB/MOK
- Provides evidence that binaries are signed (full trust verification requires platform-specific validation)

### 6. TPM Measured Boot (Optional)
- Detects TPM presence (`/dev/tpmrm0` or `/dev/tpm0`)
- Captures TPM event log (`/sys/kernel/security/tpm0/binary_bios_measurements`)
- Reads PCRs 0, 2, 7 via `tpm2_pcrread` if available
- **Not required for PASS** (measured boot is an additional signal, not a requirement)

## Usage

**Direct execution:**
```bash
sudo bash resilience_recovery_rollback/landscape_verified_boot_integrity/verified_boot_integrity.sh
```

**Via Landscape:**
1. Upload script to Landscape Script Library
2. Set execution mode: Run as root
3. Execute on target devices
4. Review JSON output in Landscape activity log
5. Retrieve evidence files from device for detailed analysis

## Output

**Stdout:** Single-line JSON with verification summary

**Evidence files:** `/var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_verified_boot_integrity/run_<UTC_TIMESTAMP>/`

**Evidence collected:**
- `baseline.txt` - OS release, kernel, cmdline
- `mokutil_list_enrolled_head.txt` - Enrolled MOK keys (first 40 lines)
- `dmesg_secureboot_lockdown.txt` - Kernel boot messages
- `efibootmgr_v.txt` - EFI boot configuration
- `efi_binaries.txt` - List of EFI executables
- `sbverify_kernel.txt` - Kernel signature info
- `sbverify_shim.txt` - Shim signature info
- `sbverify_grub.txt` - GRUB signature info
- `sbverify_bootaa64.txt` - BOOTAA64.EFI signature info
- `kernel_filetype.txt` - Kernel file type
- `tpm_eventlog_sha256.txt` - TPM event log checksum and size
- `tpm_eventlog_head.txt` - TPM event log first 80 entries
- `tpm_pcrread_sha256_0_2_7.txt` - PCR 0/2/7 values
- `tpm_pcrread_head.txt` - All PCRs (first 120 lines)

## JSON Output Fields

- `status`: PASS | FAIL | UNKNOWN
- `run_id`: UTC timestamp
- `uefi_mode`: true | false
- `efi_mount`: YES | NO | LIKELY | UNKNOWN
- `secureboot_var`: "1" | "0" | "missing"
- `setupmode_var`: "1" | "0" | "missing"
- `mokutil_sb_state`: mokutil output or "MISSING"
- `lockdown_state_raw`: raw lockdown string
- `lockdown_active_mode`: none | integrity | confidentiality | UNKNOWN
- `module_sig_enforce`: "1" | "0" | "UNKNOWN"
- `sbverify_present`: true | false
- `kernel_image`: path to kernel
- `tpm_present`: true | false
- `tpm_eventlog_present`: true | false
- `tpm2_pcrread_present`: true | false
- `fail_reasons`: array of failure reasons
- `evidence_dir`: path to evidence directory
- `evidence_files`: array of collected evidence filenames
- `notes`: Landscape limitations note

## Exit Codes

- **0 (PASS)**: Secure Boot enabled, UEFI mode, SetupMode disabled
- **1 (FAIL)**: Secure Boot disabled, not in UEFI mode, or SetupMode enabled
- **2 (UNKNOWN)**: Cannot determine state (missing prerequisites)

## Limitations

**Signature Verification:**
- `sbverify --list` shows signatures but does not validate trust chains
- Full validation requires checking against platform DB, KEK, PK, and MOK
- This script provides evidence; trust chain validation requires additional tooling

**TPM Remote Attestation:**
- Event log and PCRs collected as signals
- Full remote attestation (quote verification, AK validation) is out of scope
- For attestation, use dedicated tools (e.g., Keylime, TPM2 attestation protocols)

**Snap Client:**
- Landscape snap client has AppArmor restrictions
- May not access `/sys/firmware/efi/efivars` or `/sys/kernel/security`
- **Recommendation:** Use deb client for full functionality

**Read-Only:**
- Does not modify UEFI variables, boot config, kernel parameters, or TPM state
- Does not enroll keys or change Secure Boot configuration

## Acceptance Tests

**Test 1: Basic Execution**
```bash
sudo bash resilience_recovery_rollback/landscape_verified_boot_integrity/verified_boot_integrity.sh
```
**Expected:** Single-line JSON, exit code 0 (on Secure Boot enabled system), evidence files created

**Test 2: Verify Secure Boot State**
```bash
# Check JSON output
OUTPUT=$(sudo bash .../verified_boot_integrity.sh)
echo "$OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print('SecureBoot:', d['secureboot_var']); print('Status:', d['status'])"
```
**Expected:** SecureBoot=1, Status=PASS

**Test 3: Review Evidence Files**
```bash
ls -lh /var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_verified_boot_integrity/run_*/
cat /var/lib/dgx_spark_management/resilience_recovery_rollback/landscape_verified_boot_integrity/run_*/baseline.txt
```
**Expected:** Evidence files present with OS, kernel, and boot chain information

## Security Notes

- Read-only verification (no system modifications)
- No secrets printed to stdout (only paths and status)
- Evidence files contain boot configuration details (not sensitive)
- Does not expose private keys or TPM sealed data
- Does not modify EFI variables or TPM state

## Reference Links

- [Ubuntu Secure Boot](https://wiki.ubuntu.com/UEFI/SecureBoot)
- [Kernel Lockdown](https://www.kernel.org/doc/html/latest/security/lockdown.html)
- [TPM2 Tools](https://github.com/tpm2-software/tpm2-tools)
- [sbsigntools](https://git.kernel.org/pub/scm/linux/kernel/git/jejb/sbsigntools.git)
- [Canonical Landscape](https://ubuntu.com/landscape)
