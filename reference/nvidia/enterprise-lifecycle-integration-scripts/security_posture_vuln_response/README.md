# Security Posture & Vulnerability Response

**Status:** ✅ Landscape Reference Scripts

This functional area provides reference implementations for security configuration management, vulnerability assessment, and security posture monitoring.

## Purpose

Maintain and verify security posture across devices, enable rapid vulnerability response, and ensure continuous compliance with security baselines. Provide visibility into security configuration state and facilitate remediation workflows.

## Landscape Reference Scripts

Reference scripts provide integration examples and are designed for use with Canonical Landscape management workflows. These are simpler than production tools and focus on demonstrating specific capabilities.

**Structure:**
- Minimal error handling (reference implementations)
- Brief inline documentation
- Simple configuration
- No extensive testing framework

### Implemented Reference Scripts

#### 1. Encryption-at-Rest State Reporting (`landscape_encryption_at_rest/`)

**Purpose:** Read-only reporting of LUKS/dm-crypt encryption state with enablement planning.

**Key Features:**
- Probes current encryption state (root filesystem, LUKS devices, dm-crypt mappings)
- Collects evidence files (LUKS signatures, crypttab, TPM presence)
- Classifies encryption state: ENABLED / PARTIAL / DISABLED / UNKNOWN
- Generates enablement plan (high-level instructions, no destructive actions)
- TPM2 auto-unlock readiness detection (if TPM + systemd-cryptenroll present)
- ext4 fscrypt readiness check (informational)

**Encryption State:**
- **ENABLED:** Root on dm-crypt AND LUKS devices present
- **PARTIAL:** Root not encrypted BUT some LUKS devices present
- **DISABLED:** No encryption detected (DGX Spark baseline)

**Usage:**
```bash
# Default interactive UI
sudo bash security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh

# Machine-readable report mode
sudo bash security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh --json
```

**Exit Codes:** 0=PASS (ENABLED), 1=FAIL (DISABLED/PARTIAL), 2=UNKNOWN

**Documentation:** See `landscape_encryption_at_rest/README.md`

**Important:** `encryption_at_rest.sh --json` is READ-ONLY and does NOT enable encryption.
The default UI mode can invoke operational flows.

For operational enablement flows, use:
- `security_posture_vuln_response/landscape_encryption_at_rest/encryption_operations.sh fscrypt <dir>`
  - supports unattended automation via raw-key mode
- `security_posture_vuln_response/landscape_encryption_at_rest/encryption_operations.sh encrypt <device> --i-accept-risks`
  - direct in-place root encryption
- `security_posture_vuln_response/landscape_encryption_at_rest/encryption_operations.sh encrypt-once <device> --usb-key <source> --i-accept-risks`
  - one-time USB boot path for encryption run

LUKS reimage remains the recommended approach for production full-disk encryption.

---

**Last Updated:** January 15, 2026  
**Maintainer:** DGX Spark Management Team
