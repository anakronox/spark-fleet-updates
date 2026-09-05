# APT Signing Verification Reference Script - Implementation Notes

**Date:** January 8, 2026  
**Type:** Landscape Reference Script  
**Status:** ✅ Complete - Ready for Testing

---

## Implementation Summary

First Landscape Reference Script implemented for DGX Spark Management Platform, focusing on APT package repository signature verification for Canonical Landscape integration.

### Files Created

1. **signing_verification.sh** (9,506 bytes)
   - Bash script with minimal error handling
   - Single-line JSON output to stdout
   - Persistent log file creation
   - Exit codes: 0 (PASS), 1 (FAIL), 2 (UNKNOWN)

2. **README.md** (5,190 bytes)
   - Purpose and Landscape integration context
   - Usage instructions
   - Exit code definitions
   - JSON output field descriptions
   - Scope and limitations
   - Acceptance tests

3. **IMPLEMENTATION_NOTES.md** (this file)
   - Implementation details
   - Testing guidance
   - Integration notes

### Files Updated

1. **attestable_conformance_regulatory/README.md**
   - Added "Implemented Reference Scripts" section
   - Listed APT Signing Verification with features and usage
   - Moved remaining scripts to "Planned" section

---

## Script Functionality

### Checks Performed

#### 1. Baseline Information
- OS version from `/etc/os-release` (PRETTY_NAME)
- APT version from `apt-get --version`
- gpgv tool presence check

#### 2. APT Configuration Analysis
Scans `apt-config dump` for insecure settings:
- `APT::Get::AllowUnauthenticated`
- `Acquire::AllowInsecureRepositories`
- `Acquire::AllowDowngradeToInsecureRepositories`

If any are set to "true", marks as FAIL.

#### 3. Repository Sources Scan
Scans `/etc/apt/sources.list` and `/etc/apt/sources.list.d/` for:
- **Fail conditions:** `trusted=yes`, `allow-insecure=yes`, `Trusted: yes`, `Allow-Insecure: yes`
- **Observations:** `signed-by=`, `Signed-By:` (informational only)

Records file:line:content for all matches.

#### 4. Signature Verification Evidence
Runs:
```bash
apt-get --no-allow-insecure-repositories -o Debug::Acquire::gpgv=true update
```

**Signature errors detected:**
- NO_PUBKEY
- BADSIG
- EXPKEYSIG
- "signatures couldn't be verified"
- "is not signed"
- "GPG error:"

**Success evidence:**
- GOODSIG
- VALIDSIG
- "gpgv exited with status 0"

### Status Determination Logic

**FAIL if:**
- Insecure APT configuration detected, OR
- Insecure source flags found, OR
- Signature verification errors found

**UNKNOWN if:**
- apt-get or gpgv not available, OR
- No GPG evidence found AND apt update failed, OR
- Unable to determine verification status

**PASS if:**
- No failures AND
- apt-get update succeeded AND
- No signature errors

---

## Output Specification

### JSON Output (stdout)

Single-line JSON with fields:
- `status`: "PASS" | "FAIL" | "UNKNOWN"
- `run_id`: UTC timestamp (format: YYYYMMDDTHHMMSSz)
- `os`: Operating system PRETTY_NAME
- `apt_version`: APT package manager version string
- `gpgv_present`: boolean
- `allow_insecure_repos`: boolean (derived from APT config)
- `insecure_source_flags_found`: boolean
- `insecure_source_matches`: array of strings ("file:line:content")
- `signed_by_lines`: array of strings (informational)
- `apt_update_exit_code`: integer
- `signature_error_matches`: array of strings (error lines)
- `gpgv_evidence_sample`: array of strings (up to 10 GOODSIG/VALIDSIG lines)
- `log_path`: absolute path to persistent log
- `notes`: string (Landscape snap client limitation note)

### Persistent Log

**Location:** `/var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/apt-signature-verify-<UTC_TIMESTAMP>.log`

**Contents:**
- Timestamp headers
- Baseline information
- APT config dump
- Sources scan results
- Full `apt-get update` output with GPG debug
- Final status determination
- Timestamp footer

---

## Acceptance Tests

### Test 1: Basic Execution

```bash
sudo bash attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh
```

**Expected:**
- Single-line JSON printed to stdout
- Exit code 0 (on healthy DGX Spark)
- JSON contains `"status":"PASS"`

### Test 2: Log File Creation

```bash
ls -lh /var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/
```

**Expected:**
- Log file exists: `apt-signature-verify-*.log`
- File size > 0 (contains apt-get update output)
- Timestamp in filename matches run_id in JSON

### Test 3: Signature Evidence

```bash
grep -E '(GOODSIG|VALIDSIG)' /var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/apt-signature-verify-*.log
```

**Expected:**
- Multiple GOODSIG or VALIDSIG lines found
- Lines show GPG key IDs and repository information

### Test 4: No Signature Errors

```bash
grep -E '(NO_PUBKEY|BADSIG|EXPKEYSIG)' /var/lib/dgx_spark_management/attestable_conformance_regulatory/landscape_signing_verification/apt-signature-verify-*.log
```

**Expected:**
- No matches (exit code 1 from grep is success)

### Test 5: JSON Parsing

```bash
sudo bash attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh | python3 -m json.tool
```

**Expected:**
- Valid JSON output (no parsing errors)
- All required fields present
- Status field is "PASS", "FAIL", or "UNKNOWN"

---

## Landscape Integration

### Remote Script Execution

**Deployment:**
1. Upload `signing_verification.sh` to Landscape Script Library
2. Set execution mode: **Run as root** (sudo required)
3. Schedule or execute on-demand

**Snap Client Limitations:**
- Landscape snap client has AppArmor confinement
- May restrict access to `/etc/apt`, `/var/lib`, `/var/cache/apt`
- **Recommendation:** Use deb package client for full functionality

**Result Handling:**
- Parse JSON from stdout
- Check exit code for PASS/FAIL/UNKNOWN
- Retrieve log file path from JSON for detailed diagnostics
- Use `log_path` field to fetch full verification log if needed

### Integration with Landscape Compliance

**Use Cases:**
1. **Compliance Reporting:** Schedule weekly verification runs
2. **Pre-Update Checks:** Run before major system updates
3. **Audit Trail:** Persistent logs provide verification history
4. **Alert on Failure:** Configure Landscape alerts for exit code 1

**Example Landscape Script Configuration:**
```yaml
Name: DGX Spark - APT Signature Verification
Description: Verify cryptographic signing for APT repositories
Script: signing_verification.sh
Run as: root
Timeout: 300 seconds
Success exit codes: 0
Alert on failure: Yes
Schedule: Weekly (Sunday 02:00 UTC)
```

---

## Scope and Limitations

### In Scope

✅ APT repository metadata signing (InRelease, Release.gpg)  
✅ Repository-level signature verification enforcement  
✅ Detection of insecure APT configuration  
✅ Detection of insecure repository source flags  
✅ Evidence of GPG signature verification execution

### Out of Scope

❌ Snap package signing (separate Snap Store mechanism)  
❌ Container image signing (Docker, OCI registries)  
❌ Individual .deb package signatures beyond repository metadata  
❌ Firmware update package signing (handled by fwupd)  
❌ Python pip package signing  
❌ Modification of APT configuration (read-only verification)

### Known Limitations

1. **Snap Client Confinement:** May fail with Landscape snap client due to AppArmor restrictions
2. **Network Required:** Requires network connectivity for apt-get update
3. **Root Access:** Must run as root for APT operations
4. **Read-Only:** Does not remediate issues, only reports
5. **Repository Availability:** Fails if repositories are unreachable

---

## Security Considerations

### What This Script Does

✅ Read APT configuration (read-only)  
✅ Read repository source lists (read-only)  
✅ Run `apt-get update` (downloads metadata only)  
✅ Create log files in managed directory  
✅ Output JSON to stdout (no secrets)

### What This Script Does NOT Do

❌ Modify APT configuration  
❌ Install or remove packages  
❌ Print GPG keys or secrets  
❌ Modify repository sources  
❌ Change system state (beyond logs)

### Data Privacy

- No personally identifiable information (PII) collected
- No authentication credentials logged
- Repository URLs logged (may contain organizational info)
- GPG key IDs logged (public information)

---

## Troubleshooting

### Exit Code 2 (UNKNOWN)

**Possible causes:**
- apt-get command not found → Install apt package manager
- gpgv not found → Install gpgv package
- Unable to run apt-get update → Check network, repository configuration
- No GPG debug output → Check APT version compatibility

### Exit Code 1 (FAIL)

**Possible causes:**
- Insecure APT configuration → Review apt-config dump output in log
- Insecure source flags → Check insecure_source_matches in JSON
- Signature verification failure → Check signature_error_matches in JSON
- Missing GPG keys → Review log for NO_PUBKEY errors

### Log File Not Created

**Possible causes:**
- Permission denied for /var/lib → Run with sudo
- Disk full → Check available space
- Path does not exist → Script creates path automatically, check for filesystem errors

---

## Next Steps

1. **Test on DGX Spark:** Run acceptance tests on actual hardware
2. **Landscape Deployment:** Upload to Landscape Script Library
3. **Baseline Run:** Execute on all DGX Spark devices to establish baseline
4. **Schedule:** Configure weekly compliance checks
5. **Alerting:** Set up Landscape alerts for FAIL status
6. **Documentation:** Add results to compliance documentation

---

**Implementation:** Complete  
**Testing:** Execute on target DGX Spark (or equivalent) as needed  
**Status:** Ready for deployment via Canonical Landscape
