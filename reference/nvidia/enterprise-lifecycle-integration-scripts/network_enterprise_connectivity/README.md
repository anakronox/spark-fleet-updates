# Network & Enterprise Connectivity

**Status:** ✅ Landscape Reference Scripts

This functional area provides reference implementations for enterprise network connectivity and management workflows.

## Purpose

Enable enterprise-grade network management, secure connectivity, and integration with organizational IT infrastructure. Ensure reliable management channel connectivity and support for enterprise network policies.

## Landscape Reference Scripts

Reference scripts provide integration examples and are designed for use with Canonical Landscape management workflows. These are simpler than production tools and focus on demonstrating specific capabilities.

**Structure:**
- Minimal error handling (reference implementations)
- Brief inline documentation
- Simple configuration
- No extensive testing framework

### Implemented Reference Scripts

#### 1. Collect Package (`landscape_collect_package/`)

**Purpose:** Generates standardized support bundle locally (tar.gz with checksums) for troubleshooting.

**Key Features:**
- Consolidates system logs, diagnostics, and crash indicators
- Bounded log collection (2000 journal entries, etc.)
- Includes existing DGX Spark tool outputs (if present)
- Creates SHA256 checksums for all payload files
- Single-line JSON output suitable for Landscape stdout

**Collects:**
- System baseline (os-release, uname, failed services)
- Journal logs (boot + kernel, last 2000 entries each)
- dmesg output, APT/dpkg logs
- Crash/dump listings (coredump, pstore, crash directories)
- Existing tool outputs (diagnostics, reset reason, update status)

**Usage:**
```bash
sudo bash network_enterprise_connectivity/landscape_collect_package/collect_package.sh
```

**Bundle Location:** `/var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_<UTC_TIMESTAMP>/`

**Exit Codes:** 0=PASS (bundle created), 1=FAIL, 2=UNKNOWN

**Documentation:** See `landscape_collect_package/README.md`

---

#### 2. Retrieve Logs to Stdout (`landscape_retrieve_logs_stdout/`)

**Purpose:** Remote log/diagnostic retrieval without interactive SSH access via stdout (text or gzip+base64).

**Key Features:**
- Whitelist-only preset selection (prevents arbitrary file access)
- Size enforcement (default 200KB max, respects Landscape output limits)
- Two encoding modes: plaintext or gzip+base64
- BEGIN/END payload markers for easy extraction
- SHA256 checksum for verification

**Available Presets:**
- `journal_boot_tail`, `journal_kernel_tail` (journal logs)
- `dmesg_T` (kernel ring buffer)
- `systemd_failed` (failed services)
- `apt_history`, `dpkg_log` (package logs)
- `pstore_ls`, `coredump_ls`, `crash_ls` (crash indicators)

**Usage:**
```bash
sudo bash network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh \
  --preset journal_boot_tail \
  --encoding b64gz \
  --max-bytes 200000
```

**Decoding:**
```bash
base64 -d < payload.b64 | gunzip > recovered.txt
```

**Exit Codes:** 0=PASS (payload emitted), 1=FAIL, 2=UNKNOWN

**Documentation:** See `landscape_retrieve_logs_stdout/README.md`

---

**Last Updated:** January 15, 2026  
**Maintainer:** DGX Spark Management Team
