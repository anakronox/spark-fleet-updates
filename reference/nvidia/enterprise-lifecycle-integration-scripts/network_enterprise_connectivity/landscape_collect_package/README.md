# Collect Package - Landscape Reference Script

## Purpose

Generates a standardized "collect package" support bundle locally (tar.gz with checksums), consolidating system logs, diagnostics, and indicators for troubleshooting. Outputs a single-line JSON summary suitable for Landscape Remote Script Execution stdout capture.

## Landscape Integration

**Deployment Method:** Canonical Landscape Remote Script Execution

**Usage Context:**
- Upload to Landscape Script Library
- Execute on-demand or on schedule
- Requires root privileges (`sudo`)
- **Deb client recommended** (snap client may have path restrictions)

**Bundle Location:** Local only at `/var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_<UTC_TIMESTAMP>/`

**Important:** Landscape stdout is limited by `script_output_limit`. This script only prints JSON summary; the bundle remains on the device for retrieval via other channels (SCP, management file transfer, etc.).

## What It Collects

**System baseline:**
- `/etc/os-release` (OS version)
- `uname -a` (kernel info)

**System logs (bounded):**
- `journalctl -b` (last 2000 boot entries)
- `journalctl -k -b` (last 2000 kernel entries)
- `dmesg -T` (timestamped kernel ring buffer)
- `systemctl --failed` (failed services)

**Package management logs (if present):**
- `/var/log/apt/history.log`
- `/var/log/apt/term.log`
- `/var/log/dpkg.log`

**Crash/dump indicators (listings only, no large dumps):**
- `ls -al /var/lib/systemd/coredump`
- `ls -al /sys/fs/pstore`
- `ls -al /var/crash`

**Existing DGX Spark tool outputs (copy only, not regenerated):**
- `diagnostics_full.json` (if present)
- `reset_reason_report.json` (if present)
- `update_control_status.json` (if present)

## Usage

**Direct execution:**
```bash
sudo bash network_enterprise_connectivity/landscape_collect_package/collect_package.sh
```

**Via Landscape:**
1. Upload script to Landscape Script Library
2. Set execution mode: Run as root
3. Execute on target devices
4. Review JSON output in Landscape activity log
5. Retrieve bundle file via SCP or management file transfer

## Output

**Stdout:** Single-line JSON with bundle metadata

**Bundle structure:**
```
/var/lib/dgx_spark_management/.../run_<UTC_TIMESTAMP>/
├── dgx_collect_package_<UTC_TIMESTAMP>.tar.gz  (main bundle)
└── payload_sha256sums.txt                       (checksums)
```

**Inside bundle:**
```
payload/
├── os-release
├── uname.txt
├── journal_boot_tail.txt
├── journal_kernel_tail.txt
├── dmesg_T.txt
├── systemd_failed.txt
├── apt_history.log (if present)
├── apt_term.log (if present)
├── dpkg.log (if present)
├── _var_lib_systemd_coredump_ls.txt
├── _sys_fs_pstore_ls.txt
├── _var_crash_ls.txt
├── diagnostics_full.json (if present)
├── reset_reason_report.json (if present)
└── update_control_status.json (if present)
```

## JSON Output Fields

- `status`: PASS | FAIL | UNKNOWN
- `run_id`: UTC timestamp of execution
- `bundle_path`: Absolute path to created tar.gz
- `bundle_sha256`: SHA256 checksum of bundle
- `bundle_size_bytes`: Bundle file size
- `payload_files`: Number of files in payload
- `collected_items`: Array of successfully collected items
- `missing_optional`: Array of optional items not found
- `notes`: Information about Landscape limitations

## Exit Codes

- **0 (PASS)**: Bundle created successfully, checksums computed
- **1 (FAIL)**: Bundle creation failed (e.g., tar error)
- **2 (UNKNOWN)**: Missing prerequisites (tar, sha256sum, etc.)

## Limitations

**Landscape Output:**
- Stdout is limited by `script_output_limit` (typically 1MB)
- JSON summary fits within limits; bundle file remains on device
- For bundle retrieval, use separate file transfer mechanism

**Content Boundaries:**
- Logs are bounded (e.g., 2000 journal entries) to keep bundle reasonable
- Crash/dump listings only (no large core dumps included)
- Tool outputs copied if present, not regenerated

**Client Compatibility:**
- Snap-based Landscape client may have AppArmor restrictions
- Deb client recommended for full filesystem access

## Acceptance Tests

**Test 1: Basic Execution**
```bash
sudo bash network_enterprise_connectivity/landscape_collect_package/collect_package.sh
```
**Expected:**
- Prints single-line JSON
- Exit code 0
- JSON contains `bundle_path` and `bundle_sha256`

**Test 2: Bundle Verification**
```bash
ls -lh /var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_*/
```
**Expected:**
- Bundle tar.gz file exists
- payload_sha256sums.txt exists

**Test 3: Checksum Validation**
```bash
cd /var/lib/dgx_spark_management/network_enterprise_connectivity/landscape_collect_package/run_<TIMESTAMP>/
sha256sum -c payload_sha256sums.txt
```
**Expected:** All checksums pass

**Test 4: Extract and Inspect**
```bash
tar -tzf dgx_collect_package_*.tar.gz | head -20
```
**Expected:** Shows payload/ directory with collected files

## Security Notes

- Read-only operations (does not modify system state)
- No sensitive content printed to stdout (only file paths and metadata)
- Bundle stored locally with restricted permissions
- Does not upload data anywhere
