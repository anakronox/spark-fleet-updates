# APT Signing Verification - Landscape Reference Script

## Purpose

Verifies that cryptographic signing is properly enforced for all APT package repository updates, ensuring packages are authenticated before installation.

## Landscape Integration

This reference script is designed for execution via **Canonical Landscape Remote Script Execution**. 

**Recommended deployment:**
- Use the **deb package client** for Landscape (recommended for full system access)
- The **snap-based Landscape client** has AppArmor confinement that may restrict access to `/etc/apt` and `/var/lib` paths

**Execution context:**
- Must run as root (`sudo`) to access APT configuration and perform repository updates
- Can be deployed via Landscape Script Library or executed on-demand

## What It Checks

1. **Baseline**: OS version, APT version, gpgv availability
2. **APT Configuration**: Detects insecure settings like `AllowUnauthenticated`, `AllowInsecureRepositories`
3. **Repository Sources**: Scans `/etc/apt/sources.list` and `/etc/apt/sources.list.d/` for insecure flags (`trusted=yes`, `allow-insecure=yes`)
4. **Signature Verification**: Runs `apt-get update` with GPG debug logging to verify cryptographic signatures on repository metadata

## Usage

```bash
# Direct execution (requires root)
sudo bash attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh

# Via Landscape Remote Script Execution
# Upload to Script Library and execute with sudo privileges
```

## Output

**Stdout:** Single-line JSON object with verification results

**Persistent Log:** Saved to `/var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/apt-signature-verify-<UTC_TIMESTAMP>.log`

The log contains full `apt-get update` debug output including GPG signature verification details.

## Exit Codes

- **0 (PASS)**: Signing verification is properly enforced, no insecure configuration detected
- **1 (FAIL)**: Signature verification failure OR insecure APT settings detected
- **2 (UNKNOWN)**: Prerequisites missing (apt-get/gpgv unavailable) OR unable to verify

## JSON Output Fields

- `status`: PASS | FAIL | UNKNOWN
- `run_id`: UTC timestamp of execution
- `os`: Operating system version
- `apt_version`: APT package manager version
- `gpgv_present`: GPG verification tool availability
- `allow_insecure_repos`: Whether insecure repository settings are enabled
- `insecure_source_flags_found`: Whether insecure flags found in sources
- `insecure_source_matches`: Array of file:line:content matches for insecure flags
- `signed_by_lines`: Array of Signed-By references (informational)
- `apt_update_exit_code`: Exit code from apt-get update
- `signature_error_matches`: Array of signature verification errors found
- `gpgv_evidence_sample`: Sample lines showing successful signature verification
- `log_path`: Absolute path to persistent log file
- `notes`: Additional information (e.g., snap client limitations)

## Interpretation

**PASS** means:
- No insecure APT configuration settings
- No insecure flags in repository sources
- `apt-get update` completed successfully
- GPG signature verification evidence present
- No signature errors detected

**FAIL** means:
- Insecure APT configuration detected (e.g., `AllowUnauthenticated=true`), OR
- Insecure source flags found (e.g., `trusted=yes`), OR
- Signature verification errors (NO_PUBKEY, BADSIG, EXPKEYSIG, GPG error)

**UNKNOWN** means:
- Required tools missing (apt-get, gpgv), OR
- Unable to run apt-get update, OR
- Unable to confirm signature verification occurred

## Scope and Limitations

**In Scope:**
- APT repository metadata signing (InRelease, Release.gpg files)
- Repository-level signature verification enforcement
- Detection of configuration that bypasses signature checks

**Out of Scope:**
- Snap package signing (separate mechanism)
- Container image signing (Docker, OCI)
- Individual .deb package signing beyond repository metadata
- Firmware update package signing (covered by separate fwupd mechanisms)

## Acceptance Tests

On a healthy DGX Spark system:

```bash
sudo bash attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh
```

**Expected results:**
- Prints single-line JSON with `"status":"PASS"`
- Creates log file in `/var/lib/dgx_spark_management/.../apt-signature-verify-*.log`
- Log contains `GOODSIG` or `VALIDSIG` lines
- Log does NOT contain `NO_PUBKEY`, `BADSIG`, or `EXPKEYSIG`
- Exit code: 0

**Validation:**
```bash
# Check exit code
echo $?  # Should be 0

# Verify log exists and contains signature evidence
ls -lh /var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/
grep -E '(GOODSIG|VALIDSIG)' /var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/apt-signature-verify-*.log
```

## Security Notes

- This script does NOT modify APT configuration
- Read-only verification of signing enforcement
- No secrets are printed to stdout or logs
- Requires root access for APT operations
