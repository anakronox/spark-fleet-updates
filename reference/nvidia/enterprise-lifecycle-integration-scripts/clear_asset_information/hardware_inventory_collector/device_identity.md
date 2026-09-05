# Hardware Inventory Collector - Device Identity

## Overview

Collects a unique, stable device identifier from SMBIOS/DMI and OS inventory to provide canonical asset identification for DGX Spark devices.

## Requirement Statement

**Unique, stable device identifier (serial/UUID) via SMBIOS/DMI and OS inventory**

This requirement ensures that each DGX Spark device can be reliably identified throughout its lifecycle using hardware-based identifiers that persist across OS reinstalls and configuration changes.

## Purpose

### Why This Matters

- **Asset Tracking**: Enables accurate tracking of devices across their lifecycle
- **License Management**: Provides stable identifier for software license binding  
- **Compliance**: Supports regulatory requirements for device accountability
- **Inventory Systems**: Integrates with enterprise asset management databases
- **Support**: Facilitates device identification for support cases

### Identity Selection Strategy

#### 1. Product Serial (Preferred) ✅

**Source**: `/sys/class/dmi/id/product_serial`  
**Priority**: 1st (highest)  
**asset_id_source**: `"smbios_serial"`

**Why preferred:**
- Globally unique manufacturer-assigned identifier
- Never changes throughout device lifetime
- Hardware-based (embedded in SMBIOS firmware)
- Human-readable format
- Industry standard for asset management

**DGX Spark example**: `1983925017704`

#### 2. Product UUID (Fallback)

**Source**: `/sys/class/dmi/id/product_uuid`  
**Priority**: 2nd  
**asset_id_source**: `"smbios_uuid"`

**When used:**
- Product serial is missing, empty, or invalid placeholder

**Why UUID is good but not first choice:**
- Also hardware-based and persistent
- Standardized RFC 4122 format
- May be null UUID (`00000000-0000-0000-0000-000000000000`) on some systems
- Less human-friendly than serial

**DGX Spark example**: `d69955b2-bfde-11d3-8000-4cbb472e0f5f`

#### 3. OS Machine ID (Last Resort) ⚠️

**Source**: `/etc/machine-id`  
**Priority**: 3rd (fallback only)  
**asset_id_source**: `"machine_id"`

**Why this is fallback only:**
- ❌ **Changes on OS reinstall** - breaks device tracking
- ❌ **Not globally unique** - collision risk across fleet  
- ❌ **Not hardware-bound** - can't track hardware replacements
- ❌ **Not suitable for license binding** - violates licensing best practices

**When used:**
- Both product_serial and product_uuid are unavailable or invalid
- Virtualized environments without proper SMBIOS passthrough
- Systems with corrupted SMBIOS data

**Note**: Always included as `os_machine_id` field for correlation purposes, but only used as `asset_id` when hardware identifiers unavailable.

## Data Sources

### DGX Spark DMI/SMBIOS Fields

All data is read from Linux kernel's DMI sysfs interface:

| Field | Sysfs Path | DGX Spark Example | Used For |
|-------|-----------|-------------------|----------|
| **product_serial** | `/sys/class/dmi/id/product_serial` | `1983925017704` | Primary identifier |
| **product_uuid** | `/sys/class/dmi/id/product_uuid` | `d69955b2-bfde-11d3-8000-4cbb472e0f5f` | Secondary identifier |
| **board_serial** | `/sys/class/dmi/id/board_serial` | (varies) | Additional tracking |
| **chassis_serial** | `/sys/class/dmi/id/chassis_serial` | (varies) | Additional tracking |
| **sys_vendor** | `/sys/class/dmi/id/sys_vendor` | `NVIDIA` | Vendor identification |
| **product_name** | `/sys/class/dmi/id/product_name` | `NVIDIA_DGX_Spark` | Product model |
| **product_version** | `/sys/class/dmi/id/product_version` | `A.7` | Hardware revision |

### OS Machine ID

| Field | Path | Example | Used For |
|-------|------|---------|----------|
| **machine_id** | `/etc/machine-id` | 32-char hex string | Fallback identifier + correlation |

## Manual Verification Commands

### Quick Check on DGX Spark

```bash
# Primary identifier (serial)
cat /sys/class/dmi/id/product_serial
# Expected output: 1983925017704

# Secondary identifier (UUID)
cat /sys/class/dmi/id/product_uuid
# Expected output: d69955b2-bfde-11d3-8000-4cbb472e0f5f

# Vendor and product info
cat /sys/class/dmi/id/sys_vendor
# Expected output: NVIDIA

cat /sys/class/dmi/id/product_name
# Expected output: NVIDIA_DGX_Spark

cat /sys/class/dmi/id/product_version
# Expected output: A.7

# OS machine ID (always included)
cat /etc/machine-id
# Expected output: 32-character hexadecimal string
```

### Check All DMI Fields at Once

```bash
for field in product_serial product_uuid board_serial chassis_serial \
             sys_vendor product_name product_version; do
    echo "${field}: $(cat /sys/class/dmi/id/${field} 2>/dev/null || echo 'N/A')"
done
echo "machine_id: $(cat /etc/machine-id 2>/dev/null || echo 'N/A')"
```

### Optional: Using dmidecode (if installed)

```bash
# System serial number
sudo dmidecode -s system-serial-number

# System UUID
sudo dmidecode -s system-uuid

# Full system information
sudo dmidecode -t system
```

**Note**: Our collector does **not require dmidecode** - it reads sysfs directly.

## Output Schema

### JSON Structure

```json
{
  "asset_id": "string",
  "asset_id_source": "smbios_serial|smbios_uuid|machine_id",
  "product_serial": "string",
  "product_uuid": "string",
  "board_serial": "string",
  "chassis_serial": "string",
  "sys_vendor": "string",
  "product_name": "string",
  "product_version": "string",
  "os_machine_id": "string",
  "collected_at_utc": "ISO8601 timestamp"
}
```

### Example Output (DGX Spark)

```json
{
  "asset_id": "1983925017704",
  "asset_id_source": "smbios_serial",
  "product_serial": "1983925017704",
  "product_uuid": "d69955b2-bfde-11d3-8000-4cbb472e0f5f",
  "board_serial": "",
  "chassis_serial": "",
  "sys_vendor": "NVIDIA",
  "product_name": "NVIDIA_DGX_Spark",
  "product_version": "A.7",
  "os_machine_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "collected_at_utc": "2026-01-08T20:30:00Z"
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `asset_id` | string | Yes | The selected device identifier |
| `asset_id_source` | enum | Yes | Source of asset_id: `smbios_serial`, `smbios_uuid`, or `machine_id` |
| `product_serial` | string | No* | SMBIOS system serial number (empty if invalid) |
| `product_uuid` | string | No* | SMBIOS system UUID (empty if invalid) |
| `board_serial` | string | No* | Motherboard serial number (empty if invalid) |
| `chassis_serial` | string | No* | Chassis serial number (empty if invalid) |
| `sys_vendor` | string | No* | System vendor/manufacturer name |
| `product_name` | string | No* | Product model/name |
| `product_version` | string | No* | Hardware version/revision |
| `os_machine_id` | string | No* | Systemd machine-id (empty if unavailable) |
| `collected_at_utc` | string | Yes | Collection timestamp in ISO8601 format (UTC) |

\* Field is always present but may contain empty string `""` if unavailable or invalid

### Validation Rules

A DMI value is considered **invalid** if:

1. **Empty or whitespace only**
2. **Matches invalid pattern** (case-insensitive):
   - `"none"`
   - `"not specified"`
   - `"to be filled by o.e.m."`
   - `"to be filled by o.e.m"`
   - `"default string"`
   - `"system serial number"`
   - `"system product name"`
3. **For UUID specifically**: equals null UUID `00000000-0000-0000-0000-000000000000`

## Installation

### From Source (Development)

```bash
# Navigate to project root
cd DGX_spark_management

# Script is ready to use from source
python3 clear_asset_information/hardware_inventory_collector/src/device_identity.py --print
```

### Install to bin/ Directory

```bash
# Run install script
cd clear_asset_information/hardware_inventory_collector
sudo bash install.sh

# This copies device_identity.py to:
# - ../../bin/device_identity.py (project bin)
# - /usr/local/bin/device_identity.py (optional, system-wide)
```

### Manual Installation

```bash
# Copy to project bin
cp clear_asset_information/hardware_inventory_collector/src/device_identity.py bin/
chmod +x bin/device_identity.py

# Optional: Install system-wide
sudo cp bin/device_identity.py /usr/local/bin/
```

## Operational Usage

### Print to Stdout (No File Write)

```bash
# From source
python3 clear_asset_information/hardware_inventory_collector/src/device_identity.py --print

# From project bin (after install)
python3 bin/device_identity.py --print

# System-wide (after install)
device_identity.py --print
```

**Output**: JSON printed to stdout only, no file created.

### Write to Default Location

```bash
# Requires sudo for write access to /var/lib/
sudo python3 clear_asset_information/hardware_inventory_collector/src/device_identity.py

# Output file:
# /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json
```

**Output**: 
- JSON written to file
- Success message printed to stderr
- Shows asset_id and source

### Write to Custom Location

```bash
# Write to /tmp (no sudo needed)
python3 clear_asset_information/hardware_inventory_collector/src/device_identity.py \
    --output /tmp/device_identity.json

# Write to custom directory
sudo python3 clear_asset_information/hardware_inventory_collector/src/device_identity.py \
    --output /var/custom/path/identity.json
```

### View Collected Identity

```bash
# After collection, view the file
cat /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json

# Pretty-print (if jq available)
jq . /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json
```

## Requirements

### System Requirements
- Python 3.6 or later (standard library only, no pip dependencies)
- Linux with DMI sysfs support (`/sys/class/dmi/id/` exists)
- Read access to `/sys/class/dmi/id/` (always available)
- Read access to `/etc/machine-id` (always available)
- Write access to output directory (for file write mode)

### Permissions
- **Read DMI**: No special permissions required (sysfs is world-readable)
- **Read machine-id**: No special permissions required
- **Write to `/var/lib/`**: Requires root/sudo
- **Write to `/tmp/`**: No special permissions required

### Target Platform
- **OS**: Ubuntu Linux Pro 22.04 LTS or later
- **Architecture**: ARM64 (AArch64)
- **Device**: NVIDIA DGX Spark

## Configuration

### Configuration File

**Location**: `clear_asset_information/hardware_inventory_collector/config/default.json`

**Content**:
```json
{
  "output_path": "/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json"
}
```

### Configuration Precedence

1. **CLI `--output` flag** (highest priority)
2. **Config file** (`config/default.json`)
3. **Hardcoded default** (if config missing)

### Modifying Default Output Path

Edit `config/default.json`:
```json
{
  "output_path": "/your/custom/path/device_identity.json"
}
```

## Troubleshooting

### Issue 1: DMI Sysfs Not Available

**Symptoms**:
```
Warning: No valid asset identifier found
```

**Diagnosis**:
```bash
# Check if DMI sysfs exists
ls -la /sys/class/dmi/id/

# Expected: Directory with multiple files
# If missing: DMI not supported on this system
```

**Possible Causes**:
- Non-x86/ARM64 system without DMI support
- Virtualized environment without SMBIOS passthrough
- Kernel without DMI support

**Resolution**:
- **DGX Spark**: Should never occur (DMI is always present)
- **VM**: Configure hypervisor to pass through SMBIOS data
- **Other**: Check kernel config for `CONFIG_DMI=y`

### Issue 2: Invalid OEM Placeholder Strings

**Symptoms**:
```json
{
  "asset_id": "a1b2c3d4...",
  "asset_id_source": "machine_id",
  "product_serial": "",
  "product_uuid": ""
}
```

**Diagnosis**:
```bash
# Check raw DMI values
cat /sys/class/dmi/id/product_serial
# Output: "To be filled by O.E.M."

cat /sys/class/dmi/id/product_uuid
# Output: "00000000-0000-0000-0000-000000000000"
```

**Cause**: Manufacturer did not program valid SMBIOS data

**Resolution**:
- **OEM System**: Contact vendor to properly program SMBIOS
- **Custom Build**: Flash BIOS with proper values
- **Workaround**: Use machine_id (acceptable if unique tracking not critical)

### Issue 3: Permission Denied Writing File

**Symptoms**:
```
Error: [Errno 13] Permission denied: '/var/lib/dgx_spark_management/...'
```

**Cause**: Insufficient permissions to write to `/var/lib/`

**Resolution**:
```bash
# Run with sudo
sudo python3 device_identity.py

# Or write to user-writable location
python3 device_identity.py --output ~/device_identity.json
```

### Issue 4: Empty or Missing Fields

**Symptoms**:
```json
{
  "board_serial": "",
  "chassis_serial": ""
}
```

**Cause**: These fields may legitimately be empty on some systems

**Resolution**: 
- This is **normal** - not all systems populate all DMI fields
- Primary identifiers (product_serial, product_uuid) should be populated on DGX Spark
- Empty supporting fields do not affect functionality

### Issue 5: UUID in Uppercase

**Symptoms**:
```
Expected: d69955b2-bfde-11d3-8000-4cbb472e0f5f
Got:      D69955B2-BFDE-11D3-8000-4CBB472E0F5F
```

**Resolution**: 
- Script automatically normalizes UUIDs to lowercase
- If seeing uppercase, check script version
- Both are valid, lowercase is preferred for consistency

### Diagnostic Commands

```bash
# Complete diagnostic check
echo "=== DMI Sysfs Availability ==="
ls -la /sys/class/dmi/id/ 2>&1

echo -e "\n=== DMI Field Values ==="
for field in product_serial product_uuid sys_vendor product_name; do
    echo "${field}: $(cat /sys/class/dmi/id/${field} 2>/dev/null || echo 'ERROR')"
done

echo -e "\n=== Machine ID ==="
cat /etc/machine-id 2>&1

echo -e "\n=== Python Version ==="
python3 --version

echo -e "\n=== Collector Test ==="
python3 clear_asset_information/hardware_inventory_collector/src/device_identity.py --print
```

## Integration Notes

### For Other Modules/Requirements

To consume the device identity:

```python
import json
from pathlib import Path

IDENTITY_FILE = Path("/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json")

def get_device_identity():
    """Read device identity from file."""
    if IDENTITY_FILE.exists():
        with IDENTITY_FILE.open() as f:
            return json.load(f)
    return None

# Usage
identity = get_device_identity()
if identity:
    asset_id = identity["asset_id"]
    source = identity["asset_id_source"]
    print(f"Device: {asset_id} (source: {source})")
```

### For Gateway/Broker Mapping to Redfish

Mapping device identity fields to Redfish ComputerSystem resource:

| Our Field | Redfish Property | Redfish Path |
|-----------|------------------|--------------|
| `asset_id` | `SerialNumber` or `UUID` | `/redfish/v1/Systems/{id}/` |
| `product_serial` | `SerialNumber` | `/redfish/v1/Systems/{id}/SerialNumber` |
| `product_uuid` | `UUID` | `/redfish/v1/Systems/{id}/UUID` |
| `sys_vendor` | `Manufacturer` | `/redfish/v1/Systems/{id}/Manufacturer` |
| `product_name` | `Model` | `/redfish/v1/Systems/{id}/Model` |
| `product_version` | `SKU` or `PartNumber` | `/redfish/v1/Systems/{id}/SKU` |
| `board_serial` | `Oem.BoardSerial` | `/redfish/v1/Systems/{id}/Oem/Nvidia/BoardSerial` |
| `chassis_serial` | Chassis resource | `/redfish/v1/Chassis/{id}/SerialNumber` |

**Example Redfish mapping** (pseudocode):
```python
def map_to_redfish(identity):
    return {
        "@odata.type": "#ComputerSystem.v1_13_0.ComputerSystem",
        "Id": identity["asset_id"],
        "SerialNumber": identity["product_serial"],
        "UUID": identity["product_uuid"],
        "Manufacturer": identity["sys_vendor"],
        "Model": identity["product_name"],
        "SKU": identity["product_version"],
        "Oem": {
            "Nvidia": {
                "AssetIdSource": identity["asset_id_source"],
                "BoardSerial": identity["board_serial"],
                "ChassisSerial": identity["chassis_serial"],
                "OSMachineId": identity["os_machine_id"],
                "CollectedAt": identity["collected_at_utc"]
            }
        }
    }
```

### Refresh Strategy

**When to refresh the identity file:**
- **After hardware changes** (motherboard replacement, BIOS flash)
- **After OS reinstall** (machine_id changes)
- **Periodically** (daily or weekly, for consistency checks)
- **Before inventory audits**

**How to refresh:**
```bash
# Simple refresh
sudo python3 device_identity.py

# With verification
sudo python3 device_identity.py --print | jq .asset_id
```

## Performance

- **Execution Time**: <100ms typical
- **Resource Usage**: Minimal (<10MB memory)
- **I/O**: Only reads from sysfs and writes one small JSON file
- **Suitable For**: Manual execution, cron jobs, triggered by other scripts

## Security Considerations

- **No Network Access**: Script never accesses network
- **Read-Only DMI**: Only reads from sysfs (no write access)
- **No External Dependencies**: Standard library only (no supply chain risk)
- **Minimal Permissions**: Runs as regular user (sudo only needed for /var/lib/ write)
- **Atomic Writes**: Uses temp file + atomic move to prevent corruption

## Testing

### Unit Tests

```bash
# Run unit tests
python3 -m pytest tests/unit/clear_asset_information/test_device_identity.py

# Or with unittest
python3 -m unittest tests/unit/clear_asset_information/test_device_identity.py
```

### Manual Testing

```bash
# Test 1: Print mode (no file write)
python3 device_identity.py --print

# Test 2: Validate JSON
python3 device_identity.py --print | python3 -m json.tool

# Test 3: Check asset_id source
python3 device_identity.py --print | grep asset_id_source
# Expected on DGX Spark: "asset_id_source": "smbios_serial"

# Test 4: Write to temp location
python3 device_identity.py --output /tmp/test_identity.json
cat /tmp/test_identity.json

# Test 5: Verify deterministic output
ID1=$(python3 device_identity.py --print | grep '"asset_id"')
ID2=$(python3 device_identity.py --print | grep '"asset_id"')
diff <(echo "$ID1") <(echo "$ID2")
# Expected: No difference (same asset_id)
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-08 | Initial implementation |

## References

- **SMBIOS Specification**: https://www.dmtf.org/standards/smbios
- **Linux DMI Sysfs**: https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-firmware-dmi
- **Redfish API**: https://www.dmtf.org/standards/redfish
- **Project Documentation**: `../../docs/`

## Support

For issues or questions:
1. Check this README troubleshooting section
2. Verify DMI sysfs availability with diagnostic commands
3. Review `../../docs/troubleshooting/`
4. Contact DGX Spark Management Team

---

**Requirement**: Hardware Inventory Collector - Device Identity  
**Functional Area**: Clear Asset Information  
**Version**: 1.0.0  
**Status**: Production Ready  
**Maintained By**: DGX Spark Management Team
