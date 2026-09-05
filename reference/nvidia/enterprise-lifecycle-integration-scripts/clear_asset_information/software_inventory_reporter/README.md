# Software Inventory Reporter

Enterprise software inventory collector for DGX Spark management.

## Requirement Statement

**Key device-side requirement:** Installed software / package enumeration

**Scope:**
- Enumerate all installed software packages (dpkg, snaps)
- Optionally enumerate Python packages (pip) and Docker images/containers
- Produce deterministic software manifest with counts and hashes
- Enable fast drift detection via software fingerprinting
- Support enterprise asset tracking, CMDB integration, and support baselining

**Sources:**
- OS inventory (`dpkg-query`, `snap list`)
- Optional: `pip`, `docker`

**Why this matters:**
- **Support Baselining**: Quickly identify what software is installed on a device for troubleshooting
- **Configuration Drift Detection**: Compare software fingerprints across devices or over time
- **Compliance Auditing**: Verify only approved packages are installed
- **CMDB Integration**: Populate Configuration Management Database with accurate software inventory
- **Security Posture**: Track package versions for vulnerability assessment

---

## DGX Spark Validated Capabilities

### Tools Present

Validated on DGX Spark via SSH:

| Tool | Status | Purpose |
|------|--------|---------|
| `dpkg-query` | ✅ Present | Debian package inventory |
| `snap` | ✅ Present | Snap package inventory |
| `python3` + `pip3` | ✅ Present | Python package inventory (optional) |
| `docker` | ✅ Present | Docker image/container inventory (optional) |
| `apt-mark` | ✅ Present | Held package detection |

### Sample Evidence

**dpkg packages** (example entries):
```
dgx-release                     7.3.1
nvidia-driver-535-open          535.183.06-0ubuntu1
linux-image-6.14.0-1015-nvidia  6.14.0-1015.15
snapd                           2.65.3+24.04build1
ubuntu-pro-client               33ubuntu1
```

**snap packages** (example):
```
Name               Version    Rev    Tracking       Publisher      Notes
core22             20250120   1722   latest/stable  canonical✓     base
firefox            134.0-3    5337   latest/stable  mozilla✓       -
firmware-updater   0+git.76   175    latest/stable  canonical✓     -
snapd              2.65.3     23258  latest/stable  canonical✓     snapd
```

**pip packages** (example):
```json
[
  {"name": "pip", "version": "24.0"},
  {"name": "setuptools", "version": "59.6.0"},
  {"name": "wheel", "version": "0.43.0"}
]
```

**docker** (if daemon running):
```
Docker version 27.4.1, build b9d17ea
```

---

## Data Sources and Collection Strategy

### 1. **dpkg (Debian Packages)** — Primary

**Tool:** `dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n'`

**Why:**
- Standard package manager for Ubuntu/Debian systems
- Comprehensive inventory of all installed .deb packages
- Includes system packages, drivers, libraries, applications

**Data Collected:**
- Package name
- Version
- Architecture (amd64, arm64, all, etc.)
- Held packages (via `apt-mark showhold`)

**Modes:**
- **full** (default): All packages (~2000-5000 on typical systems)
- **curated**: Only packages matching regex (e.g., `^(dgx|nvidia|linux-image|snapd)`)

**Why Curated Mode:**
- Reduces output size for CMDB ingestion
- Focuses on enterprise-relevant packages
- Still captures key system/driver packages

---

### 2. **snap (Ubuntu Snaps)** — Primary

**Tool:** `snap list`

**Why:**
- Modern package format for Ubuntu applications
- Self-contained applications with automatic updates
- Common for firmware updater, browsers, utilities

**Data Collected:**
- Snap name
- Version
- Revision
- Tracking channel (e.g., `latest/stable`)
- Publisher
- Notes (classic, devmode, etc.)

**Modes:**
- **full** (default): All snaps
- **curated**: Only snaps in configured list (e.g., `firmware-updater`, `snapd`, `firefox`)

---

### 3. **pip (Python Packages)** — Optional (disabled by default)

**Tool:** `python3 -m pip list --format=json`

**Why:**
- Python packages installed system-wide or in user environments
- Relevant for data science / AI workloads on DGX Spark

**When to Enable:**
- If you need to track Python library versions (e.g., numpy, pytorch)
- For security auditing of Python dependencies

**Why Disabled by Default:**
- Can be large (hundreds of packages in ML environments)
- May vary per user
- Not typically managed by enterprise IT

**Data Collected:**
- Package name
- Version

---

### 4. **docker (Images and Containers)** — Optional (disabled by default)

**Tools:**
- `docker --version`
- `docker images --format ...`
- `docker ps -a --format ...`

**Why:**
- DGX Spark may run containerized workloads
- Track deployed images and running containers

**When to Enable:**
- For environments where Docker is actively used
- To inventory container images for security scanning

**Why Disabled by Default:**
- Requires Docker daemon to be running
- May require elevated permissions
- Can be large output (many images/containers)
- Fails gracefully if daemon not running

**Data Collected:**
- Docker version
- Images: repository, tag, ID, created, size
- Containers: ID, image, status, name

---

### 5. **Software Manifest (Deterministic Fingerprinting)**

**Purpose:**
- Enable fast comparison of software state across devices or over time
- Detect configuration drift without comparing full package lists

**Computed:**
- **Counts**: Number of packages/snaps/pip/docker items
- **Hashes**: SHA256 over sorted "name=version" lines for each inventory
- **Overall Fingerprint**: SHA256 over OS identity + kernel + all inventory hashes

**Use Cases:**
1. **Drift Detection**: Compare fingerprints; if different, dive into hashes to see which inventory changed
2. **Compliance Baseline**: Store known-good fingerprint; alert on deviations
3. **Support Correlation**: Group devices with identical software fingerprints

---

## Manual Verification Commands

### dpkg Packages

```bash
# List all packages (full inventory)
dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n'

# Count total packages
dpkg-query -W | wc -l

# List key packages (curated)
dpkg-query -W -f='${Package}\t${Version}\n' | grep -E '^(dgx|nvidia|linux-image|snapd|ubuntu-pro-client)\b'

# Show held packages
apt-mark showhold
```

**Example output:**
```
dgx-release	7.3.1	all
nvidia-driver-535-open	535.183.06-0ubuntu1	arm64
linux-image-6.14.0-1015-nvidia	6.14.0-1015.15	arm64
snapd	2.65.3+24.04build1	arm64
ubuntu-pro-client	33ubuntu1	all
```

---

### snap Packages

```bash
# List all snaps
snap list

# Count snaps
snap list | tail -n +2 | wc -l

# Show snap details
snap info firefox
```

**Example output:**
```
Name               Version      Rev    Tracking         Publisher    Notes
core22             20250120     1722   latest/stable    canonical✓   base
firefox            134.0-3      5337   latest/stable    mozilla✓     -
firmware-updater   0+git.76     175    latest/stable    canonical✓   -
snapd              2.65.3       23258  latest/stable    canonical✓   snapd
```

---

### pip Packages (if enabled)

```bash
# List pip packages (JSON format)
python3 -m pip list --format=json

# Count pip packages
python3 -m pip list --format=json | jq '. | length'

# Check specific package
python3 -m pip show numpy
```

**Example output:**
```json
[
  {"name": "pip", "version": "24.0"},
  {"name": "setuptools", "version": "59.6.0"},
  {"name": "wheel", "version": "0.43.0"}
]
```

---

### docker Images and Containers (if enabled)

```bash
# Docker version
docker --version

# List images
docker images

# List containers (all)
docker ps -a

# Docker system info (verbose)
docker info
```

**Example output:**
```
Docker version 27.4.1, build b9d17ea

REPOSITORY          TAG       IMAGE ID       CREATED         SIZE
ubuntu              24.04     e4c58958181a   3 weeks ago     78.1MB
nvidia/cuda         12.6.1    a1b2c3d4e5f6   2 months ago    4.5GB
```

**Note:** If Docker daemon is not running, commands will fail with:
```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock
```

---

## Output Schema

### Default Output Path

```
/var/lib/dgx_spark_management/clear_asset_information/software_inventory_reporter/software_inventory.json
```

### Logging

**Repo logs (development):**
```
logs/clear_asset_information/software_inventory_reporter/software_inventory_reporter.log
```

**Runtime logs (production):**
```
/var/log/dgx_spark/clear_asset_information/software_inventory_reporter/software_inventory_reporter.log
```

Fallback to stderr if log paths not writable.

---

### JSON Schema (Stable Keys)

```json
{
  "collected_at_utc": "2025-01-08T12:34:56.789012Z",
  "asset_id": "1983925017704",
  "asset_id_source": "smbios_serial",
  "platform": {
    "sys_vendor": "NVIDIA",
    "product_name": "NVIDIA_DGX_Spark",
    "product_version": "A.7",
    "product_serial": "1983925017704",
    "product_uuid": "d69955b2-bfde-11d3-8000-4cbb472e0f5f"
  },
  "os": {
    "os_release": {
      "NAME": "Ubuntu",
      "VERSION": "24.04.3 LTS (Noble Numbat)",
      "ID": "ubuntu",
      "VERSION_ID": "24.04",
      "PRETTY_NAME": "Ubuntu 24.04.3 LTS"
    },
    "kernel_uname_r": "6.14.0-1015-nvidia"
  },
  "dpkg": {
    "available": true,
    "mode": "full",
    "packages": [
      {
        "name": "dgx-release",
        "version": "7.3.1",
        "arch": "all"
      },
      {
        "name": "nvidia-driver-535-open",
        "version": "535.183.06-0ubuntu1",
        "arch": "arm64"
      }
    ],
    "holds": [],
    "errors": []
  },
  "snaps": {
    "available": true,
    "mode": "full",
    "snaps": [
      {
        "name": "core22",
        "version": "20250120",
        "revision": "1722",
        "tracking": "latest/stable",
        "publisher": "canonical✓",
        "notes": "base"
      },
      {
        "name": "firefox",
        "version": "134.0-3",
        "revision": "5337",
        "tracking": "latest/stable",
        "publisher": "mozilla✓",
        "notes": null
      }
    ],
    "errors": []
  },
  "pip": {
    "enabled": false,
    "available": false,
    "packages": [],
    "errors": []
  },
  "docker": {
    "enabled": false,
    "available": false,
    "docker_version": null,
    "images": [],
    "containers": [],
    "errors": []
  },
  "manifest": {
    "counts": {
      "dpkg": 2145,
      "snaps": 8,
      "pip": 0,
      "docker_images": 0,
      "docker_containers": 0
    },
    "hashes": {
      "dpkg_sha256": "a1b2c3d4e5f6...",
      "snaps_sha256": "f6e5d4c3b2a1...",
      "pip_sha256": null,
      "docker_images_sha256": null
    },
    "software_fingerprint_sha256": "9f8e7d6c5b4a3...",
    "fingerprint_material": {
      "os_pretty_name": "Ubuntu 24.04.3 LTS",
      "os_version_id": "24.04",
      "kernel_uname_r": "6.14.0-1015-nvidia",
      "dpkg_sha256": "a1b2c3d4e5f6...",
      "snaps_sha256": "f6e5d4c3b2a1...",
      "pip_sha256": null,
      "docker_images_sha256": null
    }
  },
  "sources": {
    "dpkg": "dpkg-query",
    "snaps": "snap list",
    "pip": "none",
    "docker": "none"
  }
}
```

---

## Using the Hashes and Fingerprint

### 1. **Quick Drift Detection**

Compare `software_fingerprint_sha256` across devices:

```bash
# Device A
jq '.manifest.software_fingerprint_sha256' device_a.json
# => "9f8e7d6c5b4a3..."

# Device B
jq '.manifest.software_fingerprint_sha256' device_b.json
# => "9f8e7d6c5b4a3..."  # MATCH: identical software

# Device C
jq '.manifest.software_fingerprint_sha256' device_c.json
# => "1a2b3c4d5e6f7..."  # DIFFERENT: investigate further
```

**If fingerprints differ**, drill down to individual hashes:

```bash
jq '.manifest.hashes' device_c.json
```

Identify which inventory changed (dpkg, snaps, pip, docker).

---

### 2. **Compliance Baseline**

Store known-good fingerprint:

```bash
BASELINE_FP="9f8e7d6c5b4a3..."

DEVICE_FP=$(jq -r '.manifest.software_fingerprint_sha256' software_inventory.json)

if [[ "$DEVICE_FP" != "$BASELINE_FP" ]]; then
  echo "ALERT: Software configuration drift detected!"
fi
```

---

### 3. **Support Correlation**

Group devices by fingerprint:

```bash
# Collect all devices
for device in device*.json; do
  fp=$(jq -r '.manifest.software_fingerprint_sha256' "$device")
  asset=$(jq -r '.asset_id' "$device")
  echo "$fp $asset"
done | sort | uniq -c
```

Output:
```
   45 9f8e7d6c5b4a3... (45 devices with identical software)
    3 1a2b3c4d5e6f7... (3 devices with different config)
```

---

## Operational Usage

### Installation

```bash
cd clear_asset_information/software_inventory_reporter
bash install.sh
```

This installs the script to `bin/software_inventory_reporter.py`.

---

### Basic Usage

**1. Print inventory to stdout (no root required):**

```bash
python3 bin/software_inventory_reporter.py --print
```

**2. Write to default output path (requires sudo):**

```bash
sudo python3 bin/software_inventory_reporter.py
```

Output:
```
Software inventory written to: /var/lib/dgx_spark_management/clear_asset_information/software_inventory_reporter/software_inventory.json
```

**3. Enable pip and docker inventories:**

```bash
sudo python3 bin/software_inventory_reporter.py --enable-pip --enable-docker
```

**4. Curated mode (smaller output for CMDB):**

```bash
python3 bin/software_inventory_reporter.py --mode curated --print
```

**5. Custom output path:**

```bash
python3 bin/software_inventory_reporter.py --output /tmp/software_inventory.json
```

**6. Verbose logging:**

```bash
sudo python3 bin/software_inventory_reporter.py --verbose
```

---

### CLI Reference

```
usage: software_inventory_reporter.py [-h] [--print] [--output PATH]
                                       [--mode {full,curated}] [--enable-pip]
                                       [--enable-docker] [--docker-include-info]
                                       [--max-items N] [--config PATH] [--verbose]

Software inventory reporter for DGX Spark management

optional arguments:
  -h, --help            show this help message and exit
  --print               Print JSON to stdout only (do not write file)
  --output PATH         Override output file path
  --mode {full,curated} Inventory mode (default: full)
  --enable-pip          Enable pip package inventory
  --enable-docker       Enable docker images/containers inventory
  --docker-include-info Include docker info (verbose)
  --max-items N         Maximum items per inventory (default: 50000)
  --config PATH         Path to config JSON file
  --verbose             Enable verbose logging
```

---

## Configuration

### Config File: `config/default.json`

```json
{
  "output_path": "/var/lib/dgx_spark_management/clear_asset_information/software_inventory_reporter/software_inventory.json",
  "mode": "full",
  "enable_pip": false,
  "enable_docker": false,
  "docker_include_info": false,
  "curated_dpkg_regex": "^(dgx|nvidia|linux-image|linux-headers|snapd|ubuntu-pro-client)\\b",
  "curated_snaps": [
    "firmware-updater",
    "snapd",
    "core22",
    "bare",
    "snap-store",
    "firefox",
    "thunderbird"
  ],
  "max_items": 50000
}
```

**Key Settings:**

- `mode`: `"full"` or `"curated"`
- `enable_pip`: `true` to enable pip inventory
- `enable_docker`: `true` to enable docker inventory
- `curated_dpkg_regex`: Regex pattern for curated dpkg mode
- `curated_snaps`: List of snap names for curated mode
- `max_items`: Hard cap on list sizes (safety limit)

**CLI overrides config.**

---

## Troubleshooting

### Issue: Docker daemon not running

**Symptom:**
```json
"docker": {
  "enabled": true,
  "available": true,
  "docker_version": "Docker version 27.4.1, build b9d17ea",
  "images": [],
  "containers": [],
  "errors": [
    "docker images failed (daemon not running?): Command '['docker', 'images', ...]' returned non-zero exit status 1"
  ]
}
```

**Cause:**
Docker daemon is not running or user lacks permissions.

**Solutions:**
1. Start Docker daemon: `sudo systemctl start docker`
2. Run with sudo: `sudo python3 bin/software_inventory_reporter.py --enable-docker`
3. Add user to docker group: `sudo usermod -aG docker $USER` (requires logout/login)

**Note:** Collector does NOT fail if Docker commands fail; errors are recorded in output.

---

### Issue: pip not available in minimal images

**Symptom:**
```json
"pip": {
  "enabled": true,
  "available": false,
  "packages": [],
  "errors": [
    "pip not available or failed: Command '['python3', '-m', 'pip', 'list', '--format=json']' returned non-zero exit status 1"
  ]
}
```

**Cause:**
pip is not installed or not available for the current Python interpreter.

**Solution:**
- Install pip: `sudo apt install python3-pip`
- Or: Disable pip inventory (default behavior)

**Note:** pip inventory is disabled by default because it's not universally needed.

---

### Issue: Large dpkg output and max_items behavior

**Symptom:**
```json
"dpkg": {
  "packages": [...2000+ entries...],
  "errors": []
}
```

**Concern:**
Output file is too large for CMDB ingestion.

**Solutions:**
1. **Use curated mode:**
   ```bash
   python3 bin/software_inventory_reporter.py --mode curated --print
   ```
   This will only include packages matching `curated_dpkg_regex` (e.g., dgx, nvidia, linux-image).

2. **Adjust curated regex** in config:
   ```json
   "curated_dpkg_regex": "^(dgx|nvidia|linux-|ubuntu-pro-|snapd)\\b"
   ```

3. **Use manifest hashes** instead of full lists:
   - Gateway/broker can extract only `manifest.counts` and `manifest.hashes`
   - Full package lists remain available for troubleshooting

4. **Set lower max_items** (emergency cap):
   ```bash
   python3 bin/software_inventory_reporter.py --max-items 1000 --print
   ```

---

### Issue: Permission denied writing to default output path

**Symptom:**
```
ERROR: Could not create output directory: [Errno 13] Permission denied: '/var/lib/dgx_spark_management/...'
```

**Cause:**
Default output path requires root permissions.

**Solutions:**
1. **Run with sudo:**
   ```bash
   sudo python3 bin/software_inventory_reporter.py
   ```

2. **Use custom output path:**
   ```bash
   python3 bin/software_inventory_reporter.py --output /tmp/software_inventory.json
   ```

3. **Use --print for read-only testing:**
   ```bash
   python3 bin/software_inventory_reporter.py --print
   ```

---

### Issue: snap list fails in container or chroot

**Symptom:**
```json
"snaps": {
  "available": false,
  "errors": [
    "snap not found"
  ]
}
```

**Cause:**
Running in minimal environment without snap support.

**Solution:**
- This is expected in containers or minimal images
- Collector continues without snap inventory
- `snaps.available` will be `false`

---

## Security and Compliance Posture

### Dependency Profile

- **Python 3.6+ stdlib only** (no pip dependencies)
- No external binaries required (all tools are optional)
- Runs on stock Ubuntu without additional packages

### Security Characteristics

| Aspect | Implementation |
|--------|----------------|
| **Network Access** | None (all data collected locally) |
| **File System Access** | Read-only queries + single atomic write to output path |
| **Privilege Requirements** | User-level for read operations; root for default output path |
| **External Commands** | Best-effort; failures do not crash collector |
| **Data Sensitivity** | Software inventory (low sensitivity; no credentials/secrets) |
| **Output Format** | JSON with stable schema (machine-parseable) |
| **Atomic Writes** | Temp file + `os.replace()` ensures no partial writes |
| **Logging** | Minimal (summary + errors only; no huge command outputs) |

### Hardening Recommendations

1. **Run as dedicated service user** (not root) with:
   - Read access to `/sys/class/dmi/id`
   - Read access to `/etc/os-release`
   - Execute access to `dpkg-query`, `snap`, `uname`
   - Write access to output directory (or use custom path)

2. **Restrict optional inventories:**
   - Disable `--enable-pip` unless Python packages are enterprise-managed
   - Disable `--enable-docker` unless containers are actively used
   - Both are disabled by default for security reasons

3. **Use curated mode for CMDB:**
   - Reduces attack surface (smaller output)
   - Focuses on enterprise-relevant packages

4. **Log rotation:**
   - Implement log rotation for production deployments
   - Collector appends to log file (does not truncate)

---

## Integration Notes

### Gateway/Broker Mapping

**For CMDB Integration:**

1. **Asset Correlation:**
   - Use `asset_id` to correlate with hardware inventory
   - Map to CMDB CI (Configuration Item) by serial/UUID

2. **Software Inventory Table:**
   - Store `manifest.counts` and `manifest.hashes` for fast queries
   - Optionally store full `dpkg.packages` and `snaps.snaps` for detailed view

3. **Drift Detection:**
   - Compare `manifest.software_fingerprint_sha256` across devices
   - Alert on deviations from baseline

4. **Compliance Reporting:**
   - Query `dpkg.packages` for specific package versions
   - Check for required packages (e.g., `ubuntu-pro-client`)
   - Identify held packages (`dpkg.holds`)

### API Mapping Example

```python
# Pseudo-code for gateway ingestion
def ingest_software_inventory(inventory_json):
    asset_id = inventory_json["asset_id"]
    
    # Store manifest for fast queries
    db.upsert("software_manifest", {
        "asset_id": asset_id,
        "fingerprint": inventory_json["manifest"]["software_fingerprint_sha256"],
        "dpkg_count": inventory_json["manifest"]["counts"]["dpkg"],
        "snaps_count": inventory_json["manifest"]["counts"]["snaps"],
        "collected_at": inventory_json["collected_at_utc"]
    })
    
    # Optionally store full inventory
    for pkg in inventory_json["dpkg"]["packages"]:
        db.insert("installed_packages", {
            "asset_id": asset_id,
            "source": "dpkg",
            "name": pkg["name"],
            "version": pkg["version"],
            "arch": pkg["arch"]
        })
    
    # Detect drift
    baseline_fp = db.query("baseline_fingerprint", asset_id)
    if inventory_json["manifest"]["software_fingerprint_sha256"] != baseline_fp:
        alert("Software drift detected", asset_id)
```

---

## Known Limitations

1. **dpkg/snap only:**
   - Does not enumerate flatpak, appimage, or manually compiled software
   - Focused on standard Ubuntu package managers

2. **pip is system-level only:**
   - Does not enumerate virtual environment packages
   - Use `--enable-pip` only if system-wide pip packages are relevant

3. **docker requires daemon:**
   - If Docker daemon not running, inventory will be empty (with errors recorded)
   - Container inventory is snapshot at collection time (not historical)

4. **Large output size (full mode):**
   - Typical Ubuntu system has 2000-5000 dpkg packages
   - Use curated mode or manifest hashes for CMDB

5. **No version history:**
   - This is a point-in-time snapshot
   - For change tracking, run periodically and compare fingerprints

---

## Testing

### Unit Tests

Run unit tests:

```bash
python3 -m unittest tests/unit/clear_asset_information/test_software_inventory_reporter.py -v
```

### Manual Testing

**1. Test basic collection:**

```bash
python3 bin/software_inventory_reporter.py --print | jq '.manifest.counts'
```

**2. Test curated mode:**

```bash
python3 bin/software_inventory_reporter.py --mode curated --print | jq '.dpkg.packages | length'
```

**3. Test pip inventory:**

```bash
python3 bin/software_inventory_reporter.py --enable-pip --print | jq '.pip.packages | length'
```

**4. Test docker inventory:**

```bash
python3 bin/software_inventory_reporter.py --enable-docker --print | jq '.docker.images | length'
```

**5. Test fingerprint determinism:**

```bash
# Run twice
python3 bin/software_inventory_reporter.py --print > run1.json
python3 bin/software_inventory_reporter.py --print > run2.json

# Compare fingerprints (should match if no changes)
diff <(jq '.manifest.software_fingerprint_sha256' run1.json) \
     <(jq '.manifest.software_fingerprint_sha256' run2.json)
```

---

## Maintenance

### When to Re-run

- **After package installations/updates** (apt upgrade, snap refresh)
- **Periodically** (daily/weekly) for drift detection
- **Before/after maintenance windows**
- **On-demand for troubleshooting**

### Automation

Consider running via:
- **Cron job** (daily collection)
- **systemd timer** (periodic runs)
- **Post-update hook** (after apt/snap updates)

Example cron entry (daily at 3 AM):

```cron
0 3 * * * /usr/bin/python3 /path/to/bin/software_inventory_reporter.py 2>&1 | logger -t software_inventory
```

---

## Related Tools

This tool integrates with other Clear Asset Information collectors:

1. **Device Identity** (`device_identity.py`)
   - Provides stable `asset_id` for correlation

2. **Hardware Configuration** (`hardware_config.py`)
   - Provides hardware context (CPU, memory, GPU)

3. **Firmware Version Reporter** (`firmware_reporter.py`)
   - Provides firmware inventory (BIOS, NVMe, GPU VBIOS)

4. **OS Build Identity** (`os_build_identity.py`)
   - Provides OS version and DGX build identity

5. **Driver Inventory Reporter** (`driver_inventory_reporter.py`)
   - Provides driver/module inventory

**Together, these tools provide complete asset inventory for enterprise management.**

---

## Support

For issues, feature requests, or questions:

1. Check troubleshooting section above
2. Review log file for detailed error messages
3. Run with `--verbose` for debug output
4. Contact DGX Spark Management Team

---

## License

MIT License - See repository root LICENSE file.

---

## Changelog

### v1.0.0 (2025-01-08)
- Initial implementation
- dpkg and snap inventory (full and curated modes)
- Optional pip and docker inventory
- Deterministic manifest with counts and hashes
- Software fingerprinting for drift detection
- Stdlib-only (no external dependencies)
