# Hardware Inventory Collector

## Overview

The Hardware Inventory Collector provides comprehensive device identification and hardware configuration enumeration for DGX Spark devices, enabling enterprise asset management and inventory tracking.

## Requirements Implemented

This requirement folder contains two complementary tools:

### 1. Device Identity Collection ✅
**Script**: `src/device_identity.py`  
**Documentation**: [device_identity.md](device_identity.md)  
**Output**: `device_identity.json`

Collects stable, unique device identifier from SMBIOS/DMI.

**Key Features:**
- Stable asset_id (prefers serial → UUID → machine-id)
- Platform identity (vendor, product name, serial, UUID)
- Validates and rejects OEM placeholder values
- Python 3 stdlib-only, no dependencies

**Quick Usage:**
```bash
# Print device identity
python3 src/device_identity.py --print

# Write to default location
sudo python3 src/device_identity.py
```

**Output Example:**
```json
{
  "asset_id": "1983925017704",
  "asset_id_source": "smbios_serial",
  "product_serial": "1983925017704",
  "sys_vendor": "NVIDIA",
  "product_name": "NVIDIA_DGX_Spark"
}
```

---

### 2. Hardware Configuration Enumeration ✅
**Script**: `src/hardware_config.py`  
**Documentation**: [hardware_config.md](hardware_config.md)  
**Output**: `hardware_config.json`

Enumerates CPU, memory, storage, network interfaces, GPUs, and PCI devices.

**Key Features:**
- CPU topology (architecture, cores, threads, MHz)
- Memory (total, free, available)
- Storage devices (NVMe, SSD, HDD with model/serial)
- Network interfaces (with driver, firmware, speed)
- NVIDIA GPUs (via nvidia-smi)
- Key PCI devices (ConnectX, Realtek, MediaTek, etc.)
- Python 3 stdlib-only, no dependencies

**Quick Usage:**
```bash
# Print hardware configuration
python3 src/hardware_config.py --print

# Write to default location
sudo python3 src/hardware_config.py
```

**Output Example:**
```json
{
  "asset_id": "1983925017704",
  "platform": {
    "sys_vendor": "NVIDIA",
    "product_name": "NVIDIA_DGX_Spark"
  },
  "cpu": {
    "architecture": "aarch64",
    "logical_cpus": 20
  },
  "storage": [
    {
      "name": "nvme0n1",
      "type": "disk",
      "size_bytes": 512110190592,
      "model": "Samsung SSD 980 PRO",
      "serial": "S5GXNX0R123456"
    }
  ],
  "gpu": [
    {
      "name": "NVIDIA GB10",
      "uuid": "GPU-...",
      "driver_version": "550.90.07"
    }
  ]
}
```

---

## Installation

### Quick Install (Both Tools)

```bash
cd clear_asset_information/hardware_inventory_collector

# Install device identity tool
bash install.sh

# Install hardware config tool  
bash install_hardware_config.sh
```

Both scripts will be installed to `../../bin/` and optionally to `/usr/local/bin/`.

### Manual Installation

```bash
# Copy scripts to bin
cp src/device_identity.py ../../bin/
cp src/hardware_config.py ../../bin/
chmod +x ../../bin/*.py
```

---

## Output Locations

Both tools write to requirement-specific paths:

```
/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/
├── device_identity.json      # Device identifier and platform identity
└── hardware_config.json       # Complete hardware configuration
```

**Permissions:**
- Directories: `0755` (rwxr-xr-x)
- Files: `0644` (rw-r--r--)
- Owner: `root:root`

---

## Configuration

### Device Identity Configuration
**File**: `config/default.json` (JSON format)

```json
{
  "output_path": "/var/lib/dgx_spark_management/.../device_identity.json"
}
```

### Hardware Config Configuration
**File**: `config/hardware_config.conf` (key=value format)

```bash
output_path=/var/lib/dgx_spark_management/.../hardware_config.json
identity_path=/var/lib/dgx_spark_management/.../device_identity.json
include_loop_devices=false
include_virtual_interfaces=true
include_rom_devices=true
```

---

## Relationship Between Tools

**Device Identity** (device_identity.py):
- Runs first
- Provides stable asset_id
- Lightweight, fast (~100ms)
- Foundation for asset tracking

**Hardware Config** (hardware_config.py):
- Can run independently or after device_identity
- Optionally loads device_identity.json for platform info
- Comprehensive enumeration (~1-2 seconds)
- Detailed inventory for management

**Integration Pattern:**
```bash
# Step 1: Collect device identity
sudo python3 src/device_identity.py

# Step 2: Collect hardware configuration (uses identity)
sudo python3 src/hardware_config.py

# Both files now available for consumption
ls -lh /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/
```

---

## Tested On

**Platform**: NVIDIA DGX Spark  
**OS**: Ubuntu Linux Pro (ARM64)  
**Architecture**: aarch64  
**Validated**:
- ✅ DMI sysfs present and populated
- ✅ lscpu, lsblk, ip, ethtool, nvidia-smi available
- ✅ NVMe storage with model/serial
- ✅ Multiple network interfaces (Ethernet, Wi-Fi, docker0)
- ✅ NVIDIA GPU (GB10) visible via nvidia-smi
- ✅ Key PCI devices (ConnectX-7, Realtek, MediaTek)

---

## Integration with Management Systems

### For Other Requirements
Both JSON files can be read by other requirements:

```python
import json
from pathlib import Path

# Read device identity
identity_path = Path("/var/lib/dgx_spark_management/.../device_identity.json")
with identity_path.open() as f:
    identity = json.load(f)
    asset_id = identity["asset_id"]

# Read hardware config
config_path = Path("/var/lib/dgx_spark_management/.../hardware_config.json")
with config_path.open() as f:
    hardware = json.load(f)
    cpu_count = hardware["cpu"]["logical_cpus"]
    gpus = hardware["gpu"]
```

### For Redfish Gateway/Broker
These outputs are designed to be mapped into Redfish Inventory resources:

| Our Field | Redfish Resource | Redfish Property |
|-----------|------------------|------------------|
| `platform.product_serial` | ComputerSystem | SerialNumber |
| `platform.product_uuid` | ComputerSystem | UUID |
| `cpu.*` | Processor Collection | ProcessorSummary |
| `memory.mem_total_bytes` | Memory Collection | TotalSystemMemoryGiB |
| `storage[]` | Storage Collection | Drives |
| `network[]` | EthernetInterface Collection | EthernetInterfaces |
| `gpu[]` | Accelerators or OEM | Oem/Nvidia/GPUs |

See individual tool documentation for detailed Redfish mapping examples.

---

## Documentation

### Detailed Documentation
- **[device_identity.md](device_identity.md)** - Device identity collection (comprehensive)
- **[hardware_config.md](hardware_config.md)** - Hardware configuration enumeration (comprehensive)

### Quick References
- Installation: See above
- Configuration: See `config/` directory
- Testing: See `tests/unit/clear_asset_information/`
- Troubleshooting: See individual tool documentation

---

## Support

For issues or questions:
1. Check individual tool documentation (device_identity.md or hardware_config.md)
2. Review `../../docs/troubleshooting/`
3. Contact DGX Spark Management Team

---

**Requirement**: Hardware Inventory Collector  
**Functional Area**: Clear Asset Information  
**Status**: Production Ready  
**Tools**: 2 (device_identity.py, hardware_config.py)  
**Maintained By**: DGX Spark Management Team
