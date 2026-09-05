# Asset Tag Manager (NVAIAwrite / NVAIAread)

**Functional Area:** Clear Asset Information
**Purpose:** Store and retrieve custom metadata in UEFI variables that persist across reboots
**Version:** 1.0.0

---

## Overview

The Asset Tag Manager provides a mechanism for storing custom asset metadata directly in the device's UEFI firmware. This data persists across reboots, OS reinstalls, and storage replacements.

**Key Features:**
- ✅ UEFI-backed persistent storage
- ✅ Survives OS reinstalls
- ✅ Survives storage replacement
- ✅ Multiple metadata groups (OWNERDATA, USERASSETDATA, SUPPORTDATA)
- ✅ JSON export capability
- ✅ Programmatic access via Python

---

## Use Cases

### Asset Tracking
Store asset numbers, cost centers, and ownership information directly in the hardware.

```bash
sudo NVAIAwrite USERASSETDATA \
  ASSET_NUMBER="DGX-12345" \
  COST_CENTER="CC-9876" \
  PURCHASE_DATE="2026-01-15"

NVAIAread USERASSETDATA
```

### Support Information
Store warranty, support tier, and contact information.

```bash
sudo NVAIAwrite SUPPORTDATA \
  WARRANTY_END="2029-01-15" \
  SUPPORT_TIER="Premium" \
  SUPPORT_CONTACT="support@example.com"

NVAIAread SUPPORTDATA --format json
```

### Owner Information
Store department, location, and owner details.

```bash
sudo NVAIAwrite OWNERDATA \
  OWNERNAME="IT Department" \
  LOCATION="Building A, Floor 3" \
  DEPARTMENT="Operations"

NVAIAread OWNERDATA
```

---

## Installation

### Prerequisites

- DGX Spark device with UEFI firmware
- UEFI boot mode (not legacy BIOS)
- Python 3.8+
- Root/sudo access for write operations

### Install

```bash
cd clear_asset_information/asset_tag_manager
sudo bash install.sh
```

This installs:
- `/usr/local/bin/NVAIAwrite` - Write asset tags
- `/usr/local/bin/NVAIAread` - Read asset tags
- Configuration to `/etc/dgx_spark/`

### Verify Installation

```bash
# Check commands are available
which NVAIAwrite NVAIAread

# Test read (no sudo needed)
NVAIAread OWNERDATA

# Test write (requires sudo)
sudo NVAIAwrite OWNERDATA TEST="Hello"
NVAIAread OWNERDATA
```

---

## Usage

### Writing Asset Tags

**Basic syntax:**
```bash
sudo NVAIAwrite <GROUP> <FIELD1>="value1" <FIELD2>="value2" ...
```

**Available groups:**
- `OWNERDATA` - Owner/department information
- `USERASSETDATA` - Asset tracking information
- `SUPPORTDATA` - Support and warranty information

**Examples:**
```bash
# Write single field
sudo NVAIAwrite OWNERDATA OWNERNAME="IT Department"

# Write multiple fields
sudo NVAIAwrite OWNERDATA \
  OWNERNAME="IT Department" \
  LOCATION="Building A" \
  DEPARTMENT="Operations"

# Update existing field (preserves other fields)
sudo NVAIAwrite OWNERDATA LOCATION="Building B"

# Clear a field (write empty string)
sudo NVAIAwrite OWNERDATA LOCATION=""
```

### Reading Asset Tags

**Basic syntax:**
```bash
NVAIAread <GROUP> [OPTIONS]
```

**Options:**
- `--format json` - Output as JSON
- `--exclude-empty` - Exclude empty fields
- `--all` - Read all groups

**Examples:**
```bash
# Read one group
NVAIAread OWNERDATA

# Read as JSON
NVAIAread OWNERDATA --format json

# Read all groups
NVAIAread --all

# Read without empty fields
NVAIAread OWNERDATA --exclude-empty
```

---

## Metadata Groups

### OWNERDATA
**Purpose:** Owner and location information

**Common fields:**
- `OWNERNAME` - Owner name or department
- `LOCATION` - Physical location
- `DEPARTMENT` - Department or business unit
- `CONTACT_EMAIL` - Contact email
- `CONTACT_PHONE` - Contact phone

### USERASSETDATA
**Purpose:** Asset tracking and inventory

**Common fields:**
- `ASSET_NUMBER` - Asset tag number
- `COST_CENTER` - Cost center code
- `PURCHASE_DATE` - Purchase date (YYYY-MM-DD)
- `PURCHASE_ORDER` - Purchase order number
- `VENDOR` - Vendor/supplier

### SUPPORTDATA
**Purpose:** Support and warranty information

**Common fields:**
- `WARRANTY_END` - Warranty expiration (YYYY-MM-DD)
- `SUPPORT_TIER` - Support tier (Basic/Standard/Premium)
- `SUPPORT_CONTACT` - Support contact
- `SERVICE_TAG` - Service tag number
- `NEXT_MAINTENANCE` - Next maintenance date

---

## Testing

### Automated Testing (Recommended)

The Asset Tag Manager includes automated SSH-based tests via the testing framework.

**Quick Start:**
```bash
cd testing_framework

# Enable asset tag tests in config
nano config/user_config.yaml
# Set run_asset_tag_tests: true

# Run tests
python -m src.cli run --include asset_tag_write_read asset_tag_multi_group

# View HTML report
firefox reports/latest/report.html
```

**See:** [AUTOMATED_TESTING.md](AUTOMATED_TESTING.md) for complete guide

**Tests included:**
- ✅ Basic write-read cycle with validation
- ✅ Multiple groups independence
- ✅ Data integrity checks
- ✅ JSON format validation

### Manual Testing

For comprehensive manual testing procedures, see:

**📖 [TESTING_GUIDE.md](TESTING_GUIDE.md)**

This guide includes:
- ✅ Basic write and read tests
- ✅ Multiple groups test
- ✅ Update preservation test
- ✅ Empty values test
- ✅ Large payload test
- ✅ **Reboot persistence test** (critical!)
- ✅ Error handling test
- ✅ JSON export test
- ✅ Delete/clear tags test

### Reboot Persistence Test (Critical!)

**⚠️ This is the most important test for UEFI persistence!**

```bash
# Phase 1: Before reboot
sudo bash test_reboot_persistence.sh pre-reboot

# Reboot the system
sudo reboot

# Phase 2: After reboot
sudo bash test_reboot_persistence.sh post-reboot
```

**See:** [test_reboot_persistence.sh](test_reboot_persistence.sh)

---

## Integration Test

A comprehensive bash-based integration test is available:

```bash
# Run integration test
cd tests/integration/production_tools
sudo bash test_asset_tag_manager_integration.sh

# Skip cleanup to inspect results
SKIP_CLEANUP=true sudo bash test_asset_tag_manager_integration.sh
```

**See:** [test_asset_tag_manager_integration.sh](../../tests/integration/production_tools/test_asset_tag_manager_integration.sh)

---

## Programmatic Usage

### Python Example

```python
import subprocess
import json

# Write asset tags
subprocess.run([
    'sudo', 'NVAIAwrite', 'OWNERDATA',
    'OWNERNAME="IT Department"',
    'LOCATION="Building A"'
], check=True)

# Read asset tags
result = subprocess.run(
    ['NVAIAread', 'OWNERDATA', '--format', 'json'],
    capture_output=True,
    text=True,
    check=True
)

# Parse JSON
data = json.loads(result.stdout)
print(f"Owner: {data['fields']['OWNERNAME']}")
print(f"Location: {data['fields']['LOCATION']}")
```

### JSON Output Format

```json
{
  "group": "OWNERDATA",
  "fields": {
    "OWNERNAME": "IT Department",
    "LOCATION": "Building A",
    "DEPARTMENT": "Operations"
  },
  "schema": {
    "group": "OWNERDATA",
    "version": "1.0",
    "fields": [
      {"name": "OWNERNAME", "type": "string"},
      {"name": "LOCATION", "type": "string"},
      {"name": "DEPARTMENT", "type": "string"}
    ]
  }
}
```

---

## Architecture

### Storage Backend

Asset tags are stored in UEFI variables using the `efivarfs` interface:

```
/sys/firmware/efi/efivars/NVAIAAssetMeta-<UUID>
```

Each metadata group has its own UEFI variable with attributes:
- `0x00000007` (NON_VOLATILE | BOOTSERVICE_ACCESS | RUNTIME_ACCESS)

This ensures persistence across:
- ✅ Reboots
- ✅ OS reinstalls
- ✅ Storage replacements
- ✅ Power loss

### Schema Management

Schemas are defined in `nvaia_schema.py`:
- Field definitions
- Data types
- Validation rules
- Size limits

### UEFI Interface

Low-level UEFI access via `nvaia_uefi_store.py`:
- Read UEFI variables
- Write UEFI variables
- Handle attributes
- Error handling

---

## Troubleshooting

### Issue: "efivarfs not found"

**Cause:** UEFI variables not accessible

**Solution:**
```bash
# Check if in UEFI mode
[ -d /sys/firmware/efi ] && echo "UEFI mode" || echo "Legacy BIOS"

# Mount efivarfs
sudo mount -t efivarfs efivarfs /sys/firmware/efi/efivars

# Verify
mount | grep efivarfs
```

### Issue: "Permission denied"

**Cause:** Not running as root

**Solution:**
```bash
# Write operations require sudo
sudo NVAIAwrite OWNERDATA FIELD="value"

# Read operations don't
NVAIAread OWNERDATA
```

### Issue: "Variable not found after reboot"

**Cause:** UEFI variable not persisting

**Check:**
```bash
# Check variable attributes
sudo ls -l /sys/firmware/efi/efivars/NVAIAAssetMeta-*

# Should show persistent attributes (0x7)
```

**Possible causes:**
1. UEFI firmware bug
2. Secure Boot interference
3. Variable attributes incorrect

**Solution:** Contact firmware support

### Issue: "Data corrupted"

**Cause:** Payload too large or JSON malformed

**Check:**
```bash
# Check payload size (should be < 8KB)
NVAIAread --all --format json | wc -c

# Validate JSON
NVAIAread --all --format json | python3 -m json.tool
```

---

## Configuration

Configuration files in `/etc/dgx_spark/asset_tag_manager/`:

- `default.conf` - Default settings
- `schemas.json` - Metadata schemas

**Example config:**
```ini
[storage]
max_payload_size = 8192
enable_compression = false

[validation]
strict_mode = true
allow_custom_fields = true
```

---

## Limitations

### Size Limits
- **Per-group payload:** ~8KB (JSON encoded)
- **Total UEFI storage:** Firmware-dependent (typically ~64KB)

### Field Names
- Alphanumeric + underscore only
- No spaces
- Case-sensitive

### Performance
- Write operations: ~100-500ms per operation
- Read operations: ~10-50ms per operation

---

## Documentation

- **Automated Testing:** [AUTOMATED_TESTING.md](AUTOMATED_TESTING.md)
- **Manual Testing:** [TESTING_GUIDE.md](TESTING_GUIDE.md)
- **Reboot Test:** [test_reboot_persistence.sh](test_reboot_persistence.sh)
- **Integration Test:** [tests/integration/production_tools/test_asset_tag_manager_integration.sh](../../tests/integration/production_tools/test_asset_tag_manager_integration.sh)
- **Implementation Notes:** [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md)
- **API Reference:** [docs/core_docs/03_production_tools/clear_asset_information/06_asset_tag_manager.md](../../docs/core_docs/03_production_tools/clear_asset_information/06_asset_tag_manager.md)

---

## Source Files

```
asset_tag_manager/
├── src/
│   ├── nvaiawrite.py         # Write tool
│   ├── nvaiaread.py          # Read tool
│   ├── nvaia_schema.py       # Schema definitions
│   ├── nvaia_uefi_store.py   # UEFI interface
│   └── platform_dmi.py       # DMI utilities
├── config/
│   └── default.conf          # Configuration
├── install.sh                # Installation script
├── README.md                 # This file
├── TESTING_GUIDE.md          # Manual testing guide
├── AUTOMATED_TESTING.md      # Automated testing guide
└── test_reboot_persistence.sh # Reboot test
```

---

## Support

**Questions?**
1. Review this README
2. Check [TESTING_GUIDE.md](TESTING_GUIDE.md) for testing procedures
3. Check [AUTOMATED_TESTING.md](AUTOMATED_TESTING.md) for automated testing
4. Review troubleshooting section above

**Issues?**
1. Verify UEFI mode: `[ -d /sys/firmware/efi ] && echo "UEFI"`
2. Check efivarfs: `mount | grep efivarfs`
3. Test permissions: `sudo -v`
4. Run tests: See [AUTOMATED_TESTING.md](AUTOMATED_TESTING.md)

---

**Version:** 1.0.0
**Last Updated:** February 13, 2026
**Functional Area:** Clear Asset Information
**DGX Spark Management Project**
