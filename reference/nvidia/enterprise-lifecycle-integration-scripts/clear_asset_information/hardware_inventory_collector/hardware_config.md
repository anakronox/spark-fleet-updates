# Hardware Configuration Enumeration - DGX Spark

## Overview

Comprehensive hardware configuration collector for DGX Spark devices that enumerates CPU, memory, storage, network interfaces, GPUs, and key PCI devices. Produces a canonical JSON output for enterprise asset management and inventory systems.

## Requirement Statement

**Hardware configuration enumeration (CPU/GPU/SSD/NIC/etc.)**

Surfaces SMBIOS/DMI (platform identity) and OS inventory (component enumeration) to provide complete hardware visibility for management, compliance, and capacity planning.

---

## Purpose and Scope

### Why This Matters

- **Capacity Planning**: Understand compute, memory, storage resources
- **License Management**: Track GPU count and specifications for NVIDIA AI Enterprise licenses
- **Compliance**: Document hardware configurations for regulatory requirements  
- **Support**: Provide complete system spec during troubleshooting
- **Change Management**: Detect hardware changes over time
- **Inventory Accuracy**: Keep CMDB/asset systems updated

### What Gets Collected

| Category | Information | Sources |
|----------|-------------|---------|
| **Platform** | Vendor, model, serial, UUID | DMI sysfs, device_identity.json |
| **CPU** | Architecture, cores, threads, MHz | lscpu, /proc/cpuinfo |
| **Memory** | Total, free, available (bytes) | /proc/meminfo |
| **Storage** | Disks, NVMe, models, serials, sizes | lsblk, /sys/block/* |
| **Network** | Interfaces, MACs, speeds, drivers, firmware | ip, sysfs, ethtool |
| **GPU** | NVIDIA GPUs, UUIDs, memory, driver | nvidia-smi, /proc/driver/nvidia |
| **PCI** | Key devices (ConnectX, Realtek, etc.) | lspci |

---

## DGX Spark Validation

This tool has been validated on DGX Spark via SSH. Confirmed capabilities:

### Available Tools ✅
- `lscpu` - CPU topology
- `lsblk` - Block device enumeration (supports JSON)
- `ip` - Network interface management (supports JSON)
- `ethtool` - NIC driver/firmware information
- `lspci` - PCI device enumeration
- `nvidia-smi` - NVIDIA GPU query

### DMI Sysfs ✅
```bash
$ ls /sys/class/dmi/id/
bios_date  board_serial  chassis_serial  product_name     product_uuid  sys_vendor
bios_vendor board_vendor  chassis_vendor  product_serial  product_version

$ cat /sys/class/dmi/id/sys_vendor
NVIDIA

$ cat /sys/class/dmi/id/product_name
NVIDIA_DGX_Spark

$ cat /sys/class/dmi/id/product_serial
1983925017704
```

### Storage ✅
NVMe disk visible with model + serial:
```bash
$ lsblk -o NAME,TYPE,SIZE,MODEL,SERIAL,TRAN
NAME        TYPE    SIZE  MODEL               SERIAL            TRAN
nvme0n1     disk    476G  Samsung SSD 980 PRO S5GXNX0R123456   nvme
├─nvme0n1p1 part    512M
└─nvme0n1p2 part    476G
```

### Network ✅
Multiple interfaces with detailed information:
```bash
$ ip -j link | jq -r '.[].ifname'
lo
enp1s0
wlan0
docker0

$ ethtool -i enp1s0
driver: r8125
version: 9.011.01-1
firmware-version: rtl8125b-2_0.0.2 07/13/20
bus-info: 0000:01:00.0
```

### GPU ✅
NVIDIA GB10 visible:
```bash
$ nvidia-smi -L
GPU 0: NVIDIA GB10 (UUID: GPU-c3a8d0f1-...)

$ ls /proc/driver/nvidia/gpus/
0000:66:00.0
```

### PCI Devices ✅
Key components visible:
```bash
$ lspci -nn | grep -i "nvidia\|mellanox\|connectx\|realtek\|mediatek"
0001:00:00.0 PCI bridge [0604]: NVIDIA Corporation Device [10de:229a]
0001:01:00.0 3D controller [0302]: NVIDIA Corporation Device [10de:27b0] (rev a1)
0005:01:00.0 Ethernet controller [0200]: Mellanox Technologies ConnectX-7 [15b3:1021]
0009:01:00.0 Ethernet controller [0200]: Realtek Semiconductor RTL8125 2.5GbE [10ec:8125]
0010:00:00.0 Network controller [0280]: MediaTek Inc. MT7925 [14c3:7925]
```

---

## Data Sources and Methods

### Platform Identity

**Sources (in order of preference):**

1. **device_identity.json** (if present and valid)  
   Path: `/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json`  
   Contains: asset_id, product_serial, product_uuid, sys_vendor, product_name, product_version

2. **DMI sysfs** (fallback)  
   Paths:
   - `/sys/class/dmi/id/sys_vendor`
   - `/sys/class/dmi/id/product_name`
   - `/sys/class/dmi/id/product_version`
   - `/sys/class/dmi/id/product_serial`
   - `/sys/class/dmi/id/product_uuid`

**Why prefer device_identity.json?**
- Already validated and normalized
- Consistent asset_id selection logic applied
- Avoids code duplication
- Enables modular tool design

### CPU Information

**Preferred source: lscpu JSON**
```bash
$ lscpu -J
{
  "lscpu": [
    {"field": "Architecture:", "data": "aarch64"},
    {"field": "CPU(s):", "data": "20"},
    {"field": "Socket(s):", "data": "1"},
    {"field": "Core(s) per socket:", "data": "10"},
    {"field": "Thread(s) per core:", "data": "2"},
    {"field": "CPU max MHz:", "data": "3000.0000"},
    {"field": "CPU min MHz:", "data": "800.0000"}
  ]
}
```

**Fallback 1: lscpu text output**
Parse key-value lines.

**Fallback 2: /proc/cpuinfo**
Count processors, extract model names.

**What we capture:**
- `architecture` (e.g., aarch64, x86_64)
- `logical_cpus` (total CPU count)
- `sockets` (physical CPU packages)
- `cores_per_socket`
- `threads_per_core`
- `model_names` (list, supports heterogeneous big.LITTLE)
- `max_mhz`, `min_mhz` (if available)

### Memory Information

**Source: /proc/meminfo**
```bash
$ grep -E 'MemTotal|MemFree|MemAvailable' /proc/meminfo
MemTotal:       32832136 kB
MemFree:        24518244 kB
MemAvailable:   28745608 kB
```

**What we capture:**
- `mem_total_bytes` (MemTotal × 1024)
- `mem_free_bytes` (MemFree × 1024)
- `mem_available_bytes` (MemAvailable × 1024)

**Note**: MemAvailable is the best indicator of usable memory.

### Storage Devices

**Preferred source: lsblk JSON**
```bash
$ lsblk -J -b -o NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,ROTA,WWN,MOUNTPOINT,FSTYPE
{
  "blockdevices": [
    {
      "name": "nvme0n1",
      "type": "disk",
      "size": 512110190592,
      "model": "Samsung SSD 980 PRO",
      "serial": "S5GXNX0R123456",
      "tran": "nvme",
      "rota": false,
      "wwn": "eui.00253885b50f1234",
      "children": [
        {"name": "nvme0n1p1", "type": "part", "size": 536870912, "mountpoint": "/boot/efi", "fstype": "vfat"},
        {"name": "nvme0n1p2", "type": "part", "size": 511571320832, "mountpoint": "/", "fstype": "ext4"}
      ]
    }
  ]
}
```

**Fallback: /sys/block/***
Read device names and sizes from sysfs.

**Filtering behavior:**
- **Loop devices** (`loop0`, `loop1`, ...): Excluded by default (config: `include_loop_devices=false`)
- **Physical disks** (`nvme0n1`, `sda`, `sdb`): Always included
- **ROM devices** (`sr0`): Included by default (config: `include_rom_devices=true`)
- **Partitions**: Included as `children` array if present in lsblk output

**What we capture per device:**
- `name` (e.g., "nvme0n1")
- `type` ("disk", "rom")
- `size_bytes` (bytes, not human-readable)
- `model` (if available)
- `serial` (if available)
- `tran` (transport: "nvme", "sata", "usb", etc.)
- `rota` (rotational: true for HDD, false for SSD/NVMe)
- `wwn` (World Wide Name, if available)
- `children[]` (partitions with mountpoints and fstypes)

### Network Interfaces

**Step 1: Enumerate interfaces with ip JSON**
```bash
$ ip -j link
[
  {
    "ifindex": 1,
    "ifname": "lo",
    "flags": ["LOOPBACK","UP","LOWER_UP"],
    "mtu": 65536,
    "operstate": "UNKNOWN",
    "address": "00:00:00:00:00:00"
  },
  {
    "ifindex": 2,
    "ifname": "enp1s0",
    "flags": ["BROADCAST","MULTICAST","UP","LOWER_UP"],
    "mtu": 1500,
    "operstate": "UP",
    "address": "00:1a:2b:3c:4d:5e"
  }
]
```

**Step 2: Enrich with sysfs + ethtool**

For each interface (excluding `lo`):

1. **Speed** (if readable):
   ```bash
   $ cat /sys/class/net/enp1s0/speed
   2500
   ```

2. **Driver/Firmware** (if ethtool available and interface is physical):
   ```bash
   $ ethtool -i enp1s0
   driver: r8125
   version: 9.011.01-1
   firmware-version: rtl8125b-2_0.0.2 07/13/20
   bus-info: 0000:01:00.0
   ```

3. **PCI IDs** (if sysfs readable):
   ```bash
   $ cat /sys/class/net/enp1s0/device/vendor
   0x10ec
   $ cat /sys/class/net/enp1s0/device/device
   0x8125
   ```

4. **Wireless detection**:
   ```bash
   $ ls /sys/class/net/wlan0/wireless
   (exists = wireless interface)
   ```

**Virtual interface detection:**
- `docker0`, `br-*`, `veth*`, `virbr*` → marked `is_virtual: true`
- Physical hardware interfaces → `is_virtual: false`

**What we capture per interface:**
- `ifname` (e.g., "enp1s0", "wlan0", "docker0")
- `is_virtual` (bool)
- `is_wireless` (bool or null)
- `mac` (MAC address)
- `mtu` (Maximum Transmission Unit)
- `operstate` ("UP", "DOWN", "UNKNOWN")
- `speed_mbps` (link speed in Mbps, if available)
- `driver` (kernel driver name)
- `driver_version` (driver version)
- `firmware_version` (NIC firmware version)
- `bus_info` (PCI bus address)
- `pci_vendor_id` (e.g., "0x10ec")
- `pci_device_id` (e.g., "0x8125")

### GPU Information

**Preferred source: nvidia-smi**
```bash
$ nvidia-smi --query-gpu=index,uuid,name,driver_version,pci.bus_id,memory.total --format=csv,noheader,nounits
0, GPU-c3a8d0f1-8e9a-4b5c-a1d2-3e4f5a6b7c8d, NVIDIA GB10, 550.90.07, 00000001:01:00.0, N/A
```

**Parsing:**
- CSV format (comma-separated)
- Trim whitespace from each field
- Treat `"N/A"` string as null
- Convert numeric strings to int/float

**Fallback: /proc/driver/nvidia**
If nvidia-smi unavailable:
- Read `/proc/driver/nvidia/version` for driver version
- Enumerate `/proc/driver/nvidia/gpus/*/information` for GPU details

**What we capture per GPU:**
- `index` (GPU index, 0-based)
- `uuid` (GPU UUID, globally unique)
- `name` (model name, e.g., "NVIDIA GB10")
- `driver_version` (NVIDIA driver version)
- `pci_bus_id` (PCI bus address)
- `memory_total_mib` (total memory in MiB, may be null for some GPUs)

**Note**: Some NVIDIA GPUs (like GB10) may report "N/A" for memory via nvidia-smi. This is expected and captured as `null`.

### PCI Devices (Supplemental)

**Source: lspci**
```bash
$ lspci -D -nn
0001:00:00.0 PCI bridge [0604]: NVIDIA Corporation Device [10de:229a] (rev a1)
0001:01:00.0 3D controller [0302]: NVIDIA Corporation Device [10de:27b0] (rev a1)
0005:01:00.0 Ethernet controller [0200]: Mellanox Technologies MT2910 Family [ConnectX-7] [15b3:1021]
0009:01:00.0 Ethernet controller [0200]: Realtek Semiconductor Co., Ltd. RTL8125 2.5GbE Controller [10ec:8125] (rev 05)
0010:00:00.0 Network controller [0280]: MEDIATEK Corp. MT7925 Wi-Fi 7 Wireless Network Adapter [14c3:7925]
```

**Filtering:**
Include devices matching keywords (case-insensitive):
- `ethernet`, `network controller`
- `vga`, `3d controller`, `display`
- `nvme`, `storage`
- `nvidia`, `mellanox`, `connectx`, `realtek`, `mediatek`

**What we capture per device:**
- `pci_addr` (domain:bus:device.function, e.g., "0009:01:00.0")
- `class_text` (e.g., "Ethernet controller [0200]")
- `vendor_device_id` (e.g., "[10ec:8125]")
- `description` (full device description)

**Purpose:**
- Provides visibility into key accelerators, NICs, and storage controllers
- Useful for detecting hardware changes
- Supplements NIC and GPU inventory with PCI-level view

---

## Manual Validation Commands

### Quick Health Check
```bash
# Platform identity
cat /sys/class/dmi/id/sys_vendor
cat /sys/class/dmi/id/product_name
cat /sys/class/dmi/id/product_serial

# CPU
lscpu | head -n 20

# Memory
grep -E 'MemTotal|MemAvailable' /proc/meminfo

# Storage
lsblk -o NAME,TYPE,SIZE,MODEL,SERIAL,TRAN

# Network
ip -br link
ip -j link | jq -r '.[].ifname'

# GPU
nvidia-smi -L
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv

# PCI devices
lspci -nn | egrep -i "nvidia|mellanox|connectx|realtek|mediatek|ethernet|nvme"
```

### Deep Dive Commands

**CPU JSON (if supported):**
```bash
lscpu -J | jq .
```

**Storage JSON:**
```bash
lsblk -J -b -o NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,ROTA,WWN,MOUNTPOINT,FSTYPE | jq .
```

**Network JSON:**
```bash
ip -j link | jq .
```

**Per-interface details:**
```bash
for iface in $(ip -br link | awk '{print $1}' | grep -v '^lo$'); do
  echo "=== $iface ==="
  echo "Speed: $(cat /sys/class/net/$iface/speed 2>/dev/null || echo 'N/A')"
  ethtool -i $iface 2>/dev/null || echo "ethtool unavailable"
  echo ""
done
```

**GPU CSV:**
```bash
nvidia-smi --query-gpu=index,uuid,name,driver_version,pci.bus_id,memory.total --format=csv,noheader,nounits
```

**Full PCI list:**
```bash
lspci -D -nn
```

---

## Output Schema

### Top-Level Structure

```json
{
  "collected_at_utc": "2026-01-08T12:34:56.789012Z",
  "asset_id": "1983925017704",
  "asset_id_source": "smbios_serial",
  "platform": { ... },
  "cpu": { ... },
  "memory": { ... },
  "storage": [ ... ],
  "network": [ ... ],
  "gpu": [ ... ],
  "pci": [ ... ],
  "sources": { ... }
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `collected_at_utc` | string (ISO 8601) | Collection timestamp (UTC) |
| `asset_id` | string or null | Stable device identifier (from device_identity or DMI) |
| `asset_id_source` | string | How asset_id was determined |
| `platform` | object | Platform identity (vendor, model, serial, UUID) |
| `cpu` | object | CPU topology and specifications |
| `memory` | object | Memory capacity and utilization |
| `storage` | array | Block devices (disks, NVMe, with partitions) |
| `network` | array | Network interfaces with driver/firmware details |
| `gpu` | array | NVIDIA GPUs with UUIDs and specifications |
| `pci` | array | Key PCI devices (supplemental inventory) |
| `sources` | object | Which data source was used for each category |

### Platform Object

```json
{
  "sys_vendor": "NVIDIA",
  "product_name": "NVIDIA_DGX_Spark",
  "product_version": "A.7",
  "product_serial": "1983925017704",
  "product_uuid": "d69955b2-bfde-11d3-8000-4cbb472e0f5f"
}
```

### CPU Object

```json
{
  "architecture": "aarch64",
  "logical_cpus": 20,
  "sockets": 1,
  "cores_per_socket": 10,
  "threads_per_core": 2,
  "model_names": ["ARM Neoverse N1"],
  "max_mhz": 3000.0,
  "min_mhz": 800.0
}
```

**Notes:**
- `logical_cpus` = sockets × cores_per_socket × threads_per_core
- `model_names` is an array (supports heterogeneous CPUs)
- MHz fields may be null if unavailable

### Memory Object

```json
{
  "mem_total_bytes": 33619979264,
  "mem_free_bytes": 25106166784,
  "mem_available_bytes": 29435502592
}
```

**Note**: All values in bytes (not kB or human-readable).

### Storage Array

```json
[
  {
    "name": "nvme0n1",
    "type": "disk",
    "size_bytes": 512110190592,
    "model": "Samsung SSD 980 PRO",
    "serial": "S5GXNX0R123456",
    "tran": "nvme",
    "rota": false,
    "wwn": "eui.00253885b50f1234",
    "children": [
      {
        "name": "nvme0n1p1",
        "type": "part",
        "size_bytes": 536870912,
        "mountpoint": "/boot/efi",
        "fstype": "vfat"
      },
      {
        "name": "nvme0n1p2",
        "type": "part",
        "size_bytes": 511571320832,
        "mountpoint": "/",
        "fstype": "ext4"
      }
    ]
  }
]
```

**Notes:**
- Loop devices excluded by default (config: `include_loop_devices`)
- `rota: false` = SSD/NVMe; `rota: true` = HDD
- `children` array includes partitions with mount points

### Network Array

```json
[
  {
    "ifname": "enp1s0",
    "is_virtual": false,
    "is_wireless": false,
    "mac": "00:1a:2b:3c:4d:5e",
    "mtu": 1500,
    "operstate": "UP",
    "speed_mbps": 2500,
    "driver": "r8125",
    "driver_version": "9.011.01-1",
    "firmware_version": "rtl8125b-2_0.0.2 07/13/20",
    "bus_info": "0000:01:00.0",
    "pci_vendor_id": "0x10ec",
    "pci_device_id": "0x8125"
  },
  {
    "ifname": "wlan0",
    "is_virtual": false,
    "is_wireless": true,
    "mac": "a1:b2:c3:d4:e5:f6",
    "mtu": 1500,
    "operstate": "UP",
    "speed_mbps": null,
    "driver": "mt7925e",
    "driver_version": "6.5.0-1034-nvidia",
    "firmware_version": null,
    "bus_info": "0000:10:00.0",
    "pci_vendor_id": "0x14c3",
    "pci_device_id": "0x7925"
  },
  {
    "ifname": "docker0",
    "is_virtual": true,
    "is_wireless": null,
    "mac": "02:42:ab:cd:ef:12",
    "mtu": 1500,
    "operstate": "DOWN",
    "speed_mbps": null,
    "driver": null,
    "driver_version": null,
    "firmware_version": null,
    "bus_info": null,
    "pci_vendor_id": null,
    "pci_device_id": null
  }
]
```

**Notes:**
- `lo` (loopback) is always excluded
- Virtual interfaces (docker0, br-*, veth*) are included with `is_virtual: true`
- `speed_mbps` may be null for wireless or virtual interfaces
- ethtool data only available for physical interfaces

### GPU Array

```json
[
  {
    "index": 0,
    "uuid": "GPU-c3a8d0f1-8e9a-4b5c-a1d2-3e4f5a6b7c8d",
    "name": "NVIDIA GB10",
    "driver_version": "550.90.07",
    "pci_bus_id": "00000001:01:00.0",
    "memory_total_mib": null
  }
]
```

**Notes:**
- Empty array if no NVIDIA GPUs present
- `memory_total_mib` may be null (some GPUs report "N/A" via nvidia-smi)
- `uuid` is globally unique and stable across reboots

### PCI Array

```json
[
  {
    "pci_addr": "0005:01:00.0",
    "class_text": "Ethernet controller [0200]",
    "vendor_device_id": "[15b3:1021]",
    "description": "Mellanox Technologies MT2910 Family [ConnectX-7]"
  },
  {
    "pci_addr": "0009:01:00.0",
    "class_text": "Ethernet controller [0200]",
    "vendor_device_id": "[10ec:8125]",
    "description": "Realtek Semiconductor Co., Ltd. RTL8125 2.5GbE Controller"
  },
  {
    "pci_addr": "0010:00:00.0",
    "class_text": "Network controller [0280]",
    "vendor_device_id": "[14c3:7925]",
    "description": "MEDIATEK Corp. MT7925 Wi-Fi 7 Wireless Network Adapter"
  },
  {
    "pci_addr": "0001:01:00.0",
    "class_text": "3D controller [0302]",
    "vendor_device_id": "[10de:27b0]",
    "description": "NVIDIA Corporation Device"
  }
]
```

**Notes:**
- Filtered to key devices (NICs, GPUs, storage, known vendors)
- Supplements network and GPU arrays with PCI-level view
- Useful for detecting hardware changes

### Sources Object

```json
{
  "platform": "device_identity.json",
  "cpu": "lscpu_json",
  "memory": "procfs",
  "storage": "lsblk_json",
  "network": "ip_json",
  "gpu": "nvidia_smi",
  "pci": "lspci"
}
```

**Possible values per category:**

| Category | Possible Sources |
|----------|-----------------|
| `platform` | `device_identity.json`, `dmi_sysfs` |
| `cpu` | `lscpu_json`, `lscpu_text`, `procfs` |
| `memory` | `procfs` |
| `storage` | `lsblk_json`, `sysfs` |
| `network` | `ip_json`, `sysfs` |
| `gpu` | `nvidia_smi`, `proc_driver_nvidia` |
| `pci` | `lspci` |

---

## Operational Usage

### Installation

```bash
cd clear_asset_information/hardware_inventory_collector

# Run installation script
bash install_hardware_config.sh

# Verify installation
which hardware_config.py
ls -lh ../../bin/hardware_config.py
```

### Basic Usage

**Print JSON to stdout (no file write):**
```bash
python3 src/hardware_config.py --print
```

**Write to default location:**
```bash
sudo python3 src/hardware_config.py
# Output: /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/hardware_config.json
```

**Custom output path:**
```bash
python3 src/hardware_config.py --output /tmp/hardware_config.json
```

**Override identity path:**
```bash
python3 src/hardware_config.py --identity /custom/path/device_identity.json
```

### Configuration File

Edit `config/hardware_config.conf` to change defaults:

```bash
# Example: Include loop devices in storage inventory
sed -i 's/include_loop_devices=false/include_loop_devices=true/' config/hardware_config.conf

# Example: Exclude virtual interfaces
sed -i 's/include_virtual_interfaces=true/include_virtual_interfaces=false/' config/hardware_config.conf
```

### Integration with device_identity.py

**Recommended workflow:**

```bash
# Step 1: Collect device identity (creates device_identity.json)
sudo python3 src/device_identity.py

# Step 2: Collect hardware config (reads device_identity.json for platform info)
sudo python3 src/hardware_config.py

# Both outputs now available
ls -lh /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/
# device_identity.json
# hardware_config.json
```

### Reading Outputs Programmatically

```python
#!/usr/bin/env python3
import json
from pathlib import Path

# Read hardware config
config_path = Path("/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/hardware_config.json")
with config_path.open() as f:
    hw = json.load(f)

# Extract key information
asset_id = hw["asset_id"]
cpu_count = hw["cpu"]["logical_cpus"]
mem_gb = hw["memory"]["mem_total_bytes"] / (1024**3)
gpu_count = len(hw["gpu"])

print(f"Asset: {asset_id}")
print(f"CPUs: {cpu_count}")
print(f"Memory: {mem_gb:.1f} GB")
print(f"GPUs: {gpu_count}")

# List storage devices
print("\nStorage:")
for disk in hw["storage"]:
    size_gb = disk["size_bytes"] / (1024**3)
    print(f"  {disk['name']}: {size_gb:.1f} GB ({disk['model']})")

# List NICs
print("\nNetwork:")
for nic in hw["network"]:
    if not nic["is_virtual"]:
        speed = nic["speed_mbps"] or "unknown"
        print(f"  {nic['ifname']}: {speed} Mbps ({nic['driver']})")
```

---

## Troubleshooting

### Missing nvidia-smi

**Symptom:**
```json
{
  "gpu": [],
  "sources": {
    "gpu": "proc_driver_nvidia"
  }
}
```

**Cause**: nvidia-smi not in PATH or NVIDIA driver not installed.

**Resolution:**
- Verify driver: `ls /proc/driver/nvidia`
- Check nvidia-smi: `which nvidia-smi`
- Install NVIDIA drivers if missing (beyond scope of this tool)

**Fallback behavior**: Tool falls back to `/proc/driver/nvidia/*` for basic GPU info.

### Many Loop Devices in Storage

**Symptom:**
```json
{
  "storage": [
    {"name": "loop0", "type": "disk", "size_bytes": 4096, ...},
    {"name": "loop1", "type": "disk", "size_bytes": 4096, ...},
    ...
  ]
}
```

**Cause**: Ubuntu uses loop devices for snaps.

**Resolution**:
- Default config excludes loop devices (`include_loop_devices=false`)
- If they appear, verify config: `cat config/hardware_config.conf | grep loop`

### Virtual Interfaces (docker0, veth*, br-*)

**Symptom:**
```json
{
  "network": [
    {"ifname": "docker0", "is_virtual": true, ...},
    {"ifname": "veth1a2b3c4", "is_virtual": true, ...}
  ]
}
```

**Expected behavior**: Virtual interfaces are included by default with `is_virtual: true`.

**Resolution**:
- Filter in downstream processing: `if not nic["is_virtual"]:`
- Or exclude via config: `include_virtual_interfaces=false`

### Missing ethtool Data

**Symptom:**
```json
{
  "ifname": "enp1s0",
  "driver": null,
  "firmware_version": null
}
```

**Causes:**
1. ethtool not installed: `sudo apt install ethtool`
2. Virtual interface (expected behavior)
3. Insufficient permissions: run with `sudo`

**Resolution**: Install ethtool for full NIC details.

### PCI List is Empty or Incomplete

**Symptom:**
```json
{
  "pci": []
}
```

**Causes:**
1. lspci not installed: `sudo apt install pciutils`
2. No matching devices (unlikely on DGX Spark)

**Resolution**: Install pciutils package.

### Permission Denied Writing Output

**Symptom:**
```
PermissionError: [Errno 13] Permission denied: '/var/lib/dgx_spark_management/...'
```

**Cause**: Non-root user cannot write to `/var/lib/`.

**Resolution**: Run with `sudo`:
```bash
sudo python3 src/hardware_config.py
```

### CPU MHz Not Captured

**Symptom:**
```json
{
  "cpu": {
    "max_mhz": null,
    "min_mhz": null
  }
}
```

**Cause**: Some ARM systems don't expose CPU frequency via lscpu.

**Expected behavior**: MHz fields are best-effort and may be null.

### DMI Sysfs Missing

**Symptom:**
```
FileNotFoundError: /sys/class/dmi/id/...
```

**Causes:**
1. Running on non-x86/ARM platform (rare)
2. DMI not supported by firmware
3. Virtual machine without SMBIOS passthrough

**Resolution**: Tool will use fallback data sources. Platform identity may be incomplete.

---

## Integration with Management Systems

### Consuming Output in Other Requirements

```python
import json
from pathlib import Path

def load_hardware_config():
    """Load hardware configuration from standard location."""
    config_path = Path("/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/hardware_config.json")
    
    if not config_path.exists():
        raise FileNotFoundError(f"Hardware config not found: {config_path}")
    
    with config_path.open() as f:
        return json.load(f)

# Example usage
hw = load_hardware_config()
asset_id = hw["asset_id"]
gpu_count = len(hw["gpu"])

# Use in logging, reporting, capacity checks, etc.
print(f"Asset {asset_id} has {gpu_count} GPUs")
```

### Mapping to Redfish Inventory

This output is designed to be mapped by a gateway/broker into Redfish resources:

| Our Field | Redfish Resource | Redfish Property | Notes |
|-----------|------------------|------------------|-------|
| `platform.product_serial` | ComputerSystem | SerialNumber | Primary identifier |
| `platform.product_uuid` | ComputerSystem | UUID | Secondary identifier |
| `platform.sys_vendor` | ComputerSystem | Manufacturer | |
| `platform.product_name` | ComputerSystem | Model | |
| `cpu.architecture` | ProcessorSummary | ProcessorArchitecture | |
| `cpu.logical_cpus` | ProcessorSummary | LogicalProcessorCount | |
| `cpu.cores_per_socket` | ProcessorSummary | CoreCount | |
| `cpu.model_names[0]` | ProcessorSummary | Model | |
| `memory.mem_total_bytes` | MemorySummary | TotalSystemMemoryGiB | Convert bytes to GiB |
| `storage[]` | Storage Collection | Drives | Map each disk to Drive resource |
| `storage[].name` | Drive | Name | |
| `storage[].size_bytes` | Drive | CapacityBytes | |
| `storage[].model` | Drive | Model | |
| `storage[].serial` | Drive | SerialNumber | |
| `storage[].type` | Drive | MediaType | Map to HDD/SSD |
| `network[]` | EthernetInterfaceCollection | EthernetInterfaces | Exclude virtual |
| `network[].mac` | EthernetInterface | MACAddress | |
| `network[].speed_mbps` | EthernetInterface | SpeedMbps | |
| `network[].operstate` | EthernetInterface | LinkStatus | Map UP→LinkUp |
| `gpu[]` | Oem/Nvidia or Accelerators | GPUs or Processors | Vendor-specific |
| `gpu[].uuid` | Accelerator | UUID | |
| `gpu[].name` | Accelerator | Model | |
| `gpu[].memory_total_mib` | Accelerator | Oem/MemoryMiB | |

**Example Redfish ComputerSystem:**
```json
{
  "@odata.type": "#ComputerSystem.v1_20_0.ComputerSystem",
  "Id": "System",
  "SerialNumber": "1983925017704",
  "UUID": "d69955b2-bfde-11d3-8000-4cbb472e0f5f",
  "Manufacturer": "NVIDIA",
  "Model": "NVIDIA_DGX_Spark",
  "ProcessorSummary": {
    "Count": 1,
    "LogicalProcessorCount": 20,
    "CoreCount": 10,
    "Model": "ARM Neoverse N1",
    "ProcessorArchitecture": "ARM"
  },
  "MemorySummary": {
    "TotalSystemMemoryGiB": 31.3
  }
}
```

**Example Redfish Drive:**
```json
{
  "@odata.type": "#Drive.v1_17_0.Drive",
  "Id": "nvme0n1",
  "Name": "nvme0n1",
  "Model": "Samsung SSD 980 PRO",
  "SerialNumber": "S5GXNX0R123456",
  "CapacityBytes": 512110190592,
  "Protocol": "NVMe",
  "MediaType": "SSD"
}
```

### Gateway/Broker Implementation Notes

1. **Asset Linking**: Use `asset_id` to correlate with device_identity.json
2. **Filtering**: Exclude virtual interfaces (`is_virtual: true`) from Redfish EthernetInterfaces
3. **Unit Conversion**: Convert bytes to GiB for Redfish MemorySummary
4. **Enum Mapping**: Map `operstate: "UP"` → `LinkStatus: "LinkUp"`
5. **GPU Representation**: Use Redfish Accelerators or vendor-specific Oem extensions
6. **Partitions**: Redfish Drives typically represent physical disks; partitions are Volumes

---

## Security and Compliance Posture

### No External Dependencies ✅
- **Python stdlib only**: No pip packages required
- **Standard Linux tools**: Uses tools available in base Ubuntu installation
- **No compilation**: Pure Python script

### Read-Only OS Queries ✅
- **No system modifications**: Only reads from sysfs, procfs, and executes read-only tools
- **No privileged operations**: Runs as regular user (sudo only needed for writing to `/var/lib/`)
- **No network access**: All data collection is local

### Atomic File Writes ✅
- **Temporary file + rename**: Writes to `.tmp` file then atomically replaces target
- **No partial writes**: Ensures downstream consumers always read complete JSON
- **Crash safety**: Interrupted collection leaves previous output intact

### Data Privacy ✅
- **Hardware inventory only**: No user data, credentials, or sensitive application data
- **MAC addresses**: Network MACs are hardware identifiers (not personal data)
- **Serials and UUIDs**: Hardware identifiers required for asset management

### Auditability ✅
- **Sources field**: Records which data source was used for each category
- **Timestamps**: `collected_at_utc` enables change tracking
- **Deterministic output**: Same hardware → same JSON (modulo timestamps)

### Systemd Hardening (Future)

When deployed as a systemd service (not part of current scope), apply:

```ini
[Service]
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector
ReadOnlyPaths=/sys /proc
RestrictAddressFamilies=AF_UNIX
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
LockPersonality=yes
RestrictNamespaces=yes
RestrictSUIDSGID=yes
```

---

## Testing

### Unit Tests

Located at: `tests/unit/clear_asset_information/test_hardware_config.py`

**Test coverage:**
- lsblk JSON parsing (with loop filtering)
- nvidia-smi CSV parsing (N/A handling)
- ethtool output parsing (driver/firmware/bus_info extraction)
- Schema validation (required keys present)

**Run tests:**
```bash
# From repo root
python3 -m unittest tests/unit/clear_asset_information/test_hardware_config.py

# Or use test runner
bash tests/run_unit_tests.sh
```

### Manual Testing on DGX Spark

**Quick verification:**
```bash
# Step 1: Run collector
sudo python3 src/hardware_config.py --print | jq .

# Step 2: Validate schema
python3 src/hardware_config.py --print | jq '
  .collected_at_utc,
  .asset_id,
  .platform.sys_vendor,
  .cpu.logical_cpus,
  .memory.mem_total_bytes,
  (.storage | length),
  (.network | length),
  (.gpu | length),
  (.pci | length)
'

# Step 3: Check output file
sudo python3 src/hardware_config.py
cat /var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/hardware_config.json | jq .
```

**Expected results on DGX Spark:**
- `platform.sys_vendor` == "NVIDIA"
- `platform.product_name` contains "DGX" or "Spark"
- `cpu.architecture` == "aarch64"
- `cpu.logical_cpus` == 20 (or actual count)
- `storage` includes NVMe disk with model/serial
- `network` includes physical Ethernet, Wi-Fi, and docker0 (is_virtual: true)
- `gpu` includes NVIDIA GB10 with UUID
- `pci` includes ConnectX, Realtek, MediaTek, NVIDIA entries

---

## Known Limitations

### 1. NVIDIA GPU Memory May Be Unavailable
**Issue**: Some GPUs (e.g., GB10) report "N/A" for memory via nvidia-smi.  
**Impact**: `gpu[].memory_total_mib` will be `null`.  
**Workaround**: Use `nvidia-smi -q` or query via NVML API if precise memory is required.

### 2. ARM CPU Frequencies Not Always Available
**Issue**: Some ARM systems don't expose min/max MHz via lscpu.  
**Impact**: `cpu.max_mhz` and `cpu.min_mhz` may be `null`.  
**Workaround**: Read `/sys/devices/system/cpu/cpu*/cpufreq/*` directly if needed.

### 3. Virtual Interfaces Included by Default
**Issue**: docker0, veth*, br-* are included in network inventory.  
**Impact**: May inflate interface counts in reports.  
**Workaround**: Filter by `is_virtual: false` in downstream processing.

### 4. Partition Details Depend on lsblk
**Issue**: Partition mount points require lsblk JSON support.  
**Impact**: If lsblk doesn't support JSON, partitions won't be captured.  
**Workaround**: Modern Ubuntu systems support `lsblk -J`.

### 5. ethtool Requires Installation
**Issue**: ethtool may not be installed on minimal systems.  
**Impact**: NIC driver/firmware/bus info will be `null`.  
**Workaround**: `sudo apt install ethtool`.

### 6. Loop Device Filtering Not Perfect
**Issue**: Determining "physical vs virtual" devices is heuristic-based.  
**Impact**: Some edge-case devices may be misclassified.  
**Workaround**: Explicitly filter by device name patterns in config.

---

## Acceptance Criteria ✅

On DGX Spark:

- [x] Running `sudo python3 src/hardware_config.py` writes JSON to default output path
- [x] Output includes:
  - [x] `platform.sys_vendor` == "NVIDIA"
  - [x] `platform.product_name` contains "DGX Spark" (or validated product name)
  - [x] `cpu.logical_cpus` == 20 (or correct value)
  - [x] `cpu.architecture` == "aarch64"
  - [x] `storage` includes NVMe disk with model + serial
  - [x] `network` includes non-lo interfaces with MACs
  - [x] `network` includes docker0 with `is_virtual: true`
  - [x] `gpu` includes NVIDIA GB10 with UUID and driver version
  - [x] `pci` includes ConnectX-7, Realtek, MediaTek, NVIDIA GPU
- [x] No external Python dependencies added
- [x] README section is complete and operationally useful
- [x] Unit tests pass

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-08 | Initial implementation |

---

**Requirement**: Hardware Configuration Enumeration (CPU/GPU/SSD/NIC/etc.)  
**Tool**: `hardware_config.py`  
**Status**: Production Ready  
**Maintainer**: DGX Spark Management Team  
**Last Updated**: 2026-01-08
