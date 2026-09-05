# Retrieve Logs to Stdout - Landscape Reference Script

## Purpose

Enables remote retrieval of logs and diagnostic outputs without interactive SSH access by emitting content to stdout in either plaintext or gzip+base64 encoding. Designed for copy/paste from Landscape activity output with enforced size limits.

## Landscape Integration

**Deployment Method:** Canonical Landscape Remote Script Execution

**Usage Context:**
- Upload to Landscape Script Library
- Execute with preset selection via script parameters
- Retrieve output from Landscape activity log
- Copy payload between markers and decode locally

**Size Enforcement:** `--max-bytes` (default 200KB) respects Landscape `script_output_limit` to prevent truncation.

## Usage

**Direct execution:**
```bash
sudo bash network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh \
  --preset journal_boot_tail \
  --encoding b64gz \
  --max-bytes 200000
```

**Via Landscape:**
1. Upload script to Landscape Script Library
2. Create execution with parameters: `--preset <name> --encoding b64gz`
3. Run on target device
4. View output in Landscape activity log
5. Copy payload between BEGIN/END markers
6. Decode locally

## Command-Line Options

- `--preset <name>` (required): Select what to retrieve (see Presets below)
- `--encoding text|b64gz` (default: b64gz): Output encoding
- `--max-bytes <N>` (default: 200000): Maximum source bytes before encoding
- `--out-dir <path>` (optional): Override output directory

## Available Presets

**System logs:**
- `journal_boot_tail`: Last 2000 boot log entries (`journalctl -b`)
- `journal_kernel_tail`: Last 2000 kernel log entries (`journalctl -k -b`)
- `dmesg_T`: Timestamped kernel ring buffer
- `systemd_failed`: Failed systemd services

**Package management:**
- `apt_history`: APT history log (`/var/log/apt/history.log`)
- `dpkg_log`: DPKG package management log

**Crash/dump indicators:**
- `pstore_ls`: Persistent store listing (`/sys/fs/pstore`)
- `coredump_ls`: Systemd coredump listing
- `crash_ls`: Crash dump directory listing

## Output Format

**Structure:**
1. Single-line JSON header
2. `BEGIN_DGX_PAYLOAD` marker
3. Payload content (plaintext or base64-encoded gzip)
4. `END_DGX_PAYLOAD` marker

**JSON Header Fields:**
- `status`: PASS | FAIL | UNKNOWN
- `run_id`: UTC timestamp
- `preset`: Selected preset name
- `encoding`: text | b64gz
- `max_bytes`: Enforced byte limit
- `truncated`: true if content was truncated
- `source_bytes`: Original content size
- `sha256`: Checksum of original content
- `out_path`: Local saved file path
- `decode_hint`: Decoding command
- `markers`: Begin/end marker strings
- `notes`: Landscape limitations note

## Decoding Payloads

### For b64gz encoding:

**Extract payload from Landscape output:**
```bash
# Copy lines between BEGIN_DGX_PAYLOAD and END_DGX_PAYLOAD to file
vi payload.b64

# Decode and decompress
base64 -d < payload.b64 | gunzip > recovered.txt

# Verify checksum (compare with sha256 in JSON header)
sha256sum recovered.txt
```

### For text encoding:

Simply copy the text between markers to a file (no decoding needed).

## Exit Codes

- **0 (PASS)**: Payload emitted successfully
- **1 (FAIL)**: Preset generation failed
- **2 (UNKNOWN)**: Preset not available or missing prerequisite

## Examples

**Example 1: Retrieve recent boot log (gzip+base64)**
```bash
sudo bash network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh \
  --preset journal_boot_tail \
  --encoding b64gz \
  --max-bytes 150000
```

**Example 2: Retrieve failed services (plaintext)**
```bash
sudo bash network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh \
  --preset systemd_failed \
  --encoding text
```

**Example 3: Check for kernel panics**
```bash
sudo bash network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh \
  --preset dmesg_T \
  --encoding b64gz
```

## Acceptance Tests

**Test 1: Basic Execution**
```bash
sudo bash network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh \
  --preset journal_boot_tail --encoding b64gz --max-bytes 200000
```
**Expected:**
- JSON header printed (one line)
- BEGIN_DGX_PAYLOAD marker
- Base64-encoded content
- END_DGX_PAYLOAD marker
- Exit code 0

**Test 2: Decode and Verify**
```bash
# Run script and save output
OUTPUT=$(sudo bash .../retrieve_logs_stdout.sh --preset journal_boot_tail --encoding b64gz)

# Extract JSON header sha256
SHA256=$(echo "$OUTPUT" | head -n1 | python3 -c "import sys,json; print(json.load(sys.stdin)['sha256'])")

# Extract payload (lines between markers)
echo "$OUTPUT" | sed -n '/BEGIN_DGX_PAYLOAD/,/END_DGX_PAYLOAD/p' | grep -v DGX_PAYLOAD > payload.b64

# Decode
base64 -d < payload.b64 | gunzip > recovered.txt

# Verify checksum
echo "$SHA256  recovered.txt" | sha256sum -c
```
**Expected:** Checksum matches

**Test 3: Plaintext Encoding**
```bash
sudo bash .../retrieve_logs_stdout.sh --preset systemd_failed --encoding text
```
**Expected:** Readable text between markers (no decoding needed)

**Test 4: Truncation Detection**
```bash
sudo bash .../retrieve_logs_stdout.sh --preset dmesg_T --max-bytes 5000
```
**Expected:** JSON shows `"truncated":true` if dmesg output exceeds 5000 bytes

## Limitations

**Landscape Compatibility:**
- Stdout limited by `script_output_limit` (default ~1MB)
- Enforce `--max-bytes` conservatively (default 200KB leaves headroom)
- For larger logs, use multiple executions or separate file transfer

**Preset Whitelist:**
- Only predefined presets allowed (security: prevents arbitrary file exfiltration)
- Cannot specify arbitrary file paths

**Size Enforcement:**
- Content truncated at `--max-bytes` (before encoding)
- Truncation flag indicates incomplete data

**Client Compatibility:**
- Snap-based Landscape client may have path restrictions
- Deb client recommended

## Use Cases

1. **Quick troubleshooting** - Retrieve recent logs without SSH access
2. **Incident response** - Capture kernel panics or failed services
3. **Compliance audits** - Retrieve APT history or dpkg logs
4. **Support escalation** - Gather diagnostics for vendor support

## Security Notes

- Whitelist-only presets prevent arbitrary file access
- No sensitive content in presets (logs only)
- Size limits prevent excessive data exfiltration
- Content saved locally with restricted permissions
- Does not upload data anywhere (stdout to Landscape only)
