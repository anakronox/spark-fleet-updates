# Clear Asset Information

This functional area provides comprehensive asset visibility and inventory management for DGX Spark devices.

## Overview

Clear Asset Information ensures complete visibility into hardware, firmware, and software assets on the device, enabling effective asset management, planning, and compliance.

## Purpose

- Maintain accurate hardware inventory
- Track firmware and software versions
- Manage asset tags and identifiers
- Support procurement and lifecycle management
- Enable compliance reporting

## Requirements

This area includes the following device-side requirements (sample implementations):

### 1. Hardware Inventory Collector (`hardware_inventory_collector/`)
**Status**: ✅ Implemented (2 tools)

Comprehensive hardware inventory collection for DGX Spark devices.

#### Tool 1: Device Identity (`device_identity.py`)
Collects stable device identity from SMBIOS/DMI for asset tracking.

**Key Features:**
- Unique device identifier (prefers SMBIOS serial → UUID → machine-id fallback)
- Reads DMI fields from `/sys/class/dmi/id/`
- Python 3 (stdlib-only, no external dependencies)
- Validates and rejects OEM placeholder values
- Outputs canonical JSON with complete device identity

**Validated on DGX Spark:**
- product_serial: `1983925017704`
- product_uuid: `d69955b2-bfde-11d3-8000-4cbb472e0f5f`
- sys_vendor: `NVIDIA`
- product_name: `NVIDIA_DGX_Spark`

**Output:**
- Default: `/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/device_identity.json`

**Quick Usage:**
```bash
# Print to stdout
python3 hardware_inventory_collector/src/device_identity.py --print

# Write to default location
sudo python3 hardware_inventory_collector/src/device_identity.py
```

#### Tool 2: Hardware Configuration (`hardware_config.py`)
Enumerates CPU, memory, storage, network interfaces, GPUs, and PCI devices.

**Key Features:**
- CPU topology (architecture, cores, threads, MHz)
- Memory capacity (total, free, available)
- Storage devices (NVMe, SSD, HDD with model/serial/partitions)
- Network interfaces (with driver, firmware, speed, MACs)
- NVIDIA GPUs (via nvidia-smi with UUIDs, driver, memory)
- Key PCI devices (ConnectX, Realtek, MediaTek, etc.)
- Python 3 (stdlib-only, no external dependencies)

**Validated on DGX Spark:**
- CPU: 20 logical cores (aarch64, ARM Neoverse N1)
- Memory: ~32GB
- Storage: NVMe (Samsung SSD 980 PRO) with model/serial
- Network: Multiple Ethernet, Wi-Fi, docker0 (marked virtual)
- GPU: NVIDIA GB10 with UUID and driver version
- PCI: ConnectX-7, Realtek 8125, MediaTek 7925

**Output:**
- Default: `/var/lib/dgx_spark_management/clear_asset_information/hardware_inventory_collector/hardware_config.json`

**Quick Usage:**
```bash
# Print to stdout
python3 hardware_inventory_collector/src/hardware_config.py --print

# Write to default location
sudo python3 hardware_inventory_collector/src/hardware_config.py
```

**Relationship:**
- Run `device_identity.py` first (creates device_identity.json)
- Then run `hardware_config.py` (reads device_identity.json for platform info)
- Both tools can run independently if needed

**Documentation:** See [hardware_inventory_collector/README.md](hardware_inventory_collector/README.md) for complete details.

### 2. Firmware Version Reporter (`firmware_version_reporter/`)
**Status**: ✅ Implemented

Comprehensive firmware inventory collection for DGX Spark devices.

**Key Features:**
- BIOS/UEFI firmware (via DMI sysfs)
- fwupd inventory (EC, TPM, UEFI devices, dbx, NVMe, NICs, ConnectX)
- NIC/Wi-Fi firmware (via ethtool)
- NVMe firmware (via sysfs, nvme-cli, fwupd correlation)
- GPU firmware (via nvidia-smi: VBIOS, GSP, Inforom)
- PCI device correlation (via lspci)
- Python 3 (stdlib-only, no external dependencies)
- Graceful degradation (missing tools handled gracefully)

**Validated on DGX Spark:**
- BIOS: American Megatrends `5.36_0ACUM018` (08/06/2024)
- fwupd: Active with EC, TPM, UEFI, dbx, NVMe, ConnectX-7 devices
- NVMe: Samsung MZALC4T0HBL1 firmware `NXHB202Q`
- NICs: Realtek 8125, MediaTek 7925 with firmware versions
- GPU: NVIDIA GB10 with VBIOS `96.00.8A.00.01`, driver `550.90.07`

**Output:**
- Default: `/var/lib/dgx_spark_management/clear_asset_information/firmware_version_reporter/firmware_versions.json`
- Logs: `/var/log/dgx_spark/clear_asset_information/firmware_version_reporter/firmware_reporter.log`

**Quick Usage:**
```bash
# Print to stdout
python3 firmware_version_reporter/src/firmware_reporter.py --print

# Write to default location (with logging)
sudo python3 firmware_version_reporter/src/firmware_reporter.py

# Verbose logging
sudo python3 firmware_version_reporter/src/firmware_reporter.py --verbose

# Disable fwupd collection
python3 firmware_version_reporter/src/firmware_reporter.py --no_fwupd --print
```

**Integration:**
- Optionally reads `device_identity.json` for asset correlation
- Correlates NVMe devices across sysfs, nvme-cli, and fwupd
- Sources tracking documents which tool provided each data category

**Documentation:** See [firmware_version_reporter/README.md](firmware_version_reporter/README.md) for complete details.

### 3. OS Build Identity Reporter (`os_build_identity_reporter/`)
**Status**: ✅ Implemented

Comprehensive OS version, build identity, and baseline package fingerprint collector.

**Key Features:**
- OS release information (Ubuntu version, codename, kernel)
- DGX base image identity (build version, date, commit ID)
- Baseline package inventory (curated APT/dpkg packages)
- Snap inventory (curated system snaps)
- Deterministic fingerprint (SHA256 hash for drift detection)
- Python 3 (stdlib-only, no external dependencies)
- Graceful degradation (missing tools handled gracefully)

**Validated on DGX Spark:**
- OS: Ubuntu 24.04.3 LTS (Noble Numbat)
- Kernel: `6.14.0-1015-nvidia`
- DGX Build: Version `7.3.1`, Date `20250106`, Commit `a1b2c3d4e5f6`
- Baseline: 42 curated packages, 7 system snaps
- Fingerprint: Deterministic SHA256 hash (stable across runs)

**Output:**
- Default: `/var/lib/dgx_spark_management/clear_asset_information/os_build_identity_reporter/os_build_identity.json`
- Logs: `/var/log/dgx_spark/clear_asset_information/os_build_identity_reporter/os_build_identity.log`

**Quick Usage:**
```bash
# Print to stdout
python3 os_build_identity_reporter/src/os_build_identity.py --print

# Write to default location
sudo python3 os_build_identity_reporter/src/os_build_identity.py

# Include all packages (large output)
python3 os_build_identity_reporter/src/os_build_identity.py --all-packages --print

# Verbose logging
sudo python3 os_build_identity_reporter/src/os_build_identity.py --verbose
```

**Integration:**
- Optionally reads `device_identity.json` for asset correlation
- Deterministic fingerprint enables drift detection and compliance verification
- Sources tracking documents which tools provided each data category

**Documentation:** See [os_build_identity_reporter/README.md](os_build_identity_reporter/README.md) for complete details.

### 4. Driver Inventory Reporter (`driver_inventory_reporter/`)
**Status**: ✅ Implemented

Comprehensive driver enumeration tool that collects device-to-driver bindings across all device types.

**Key Features:**
- PCI device-driver bindings (lspci -D -nnk parsing)
- NIC interface drivers with PCI correlation (ethtool + sysfs)
- Storage device drivers (lsblk + sysfs)
- GPU drivers (nvidia-smi + PCI bindings)
- USB device drivers (lsusb -t)
- Driver manifest (modinfo enrichment for all referenced modules)
- Module usage tracking (which devices use which drivers)
- Driver signature verification data
- Python 3 (stdlib-only, no external dependencies)
- Graceful degradation (missing tools handled gracefully)

**Validated on DGX Spark:**
- PCI Drivers: nvidia, mlx5_core, nvme, r8125, mt7925e, xhci_hcd
- NIC-to-PCI correlation: Maps bus-info to PCI addresses
- USB drivers: xhci-hcd, usbhid, usb-storage, btusb
- Driver manifest: Complete modinfo for all modules (version, license, signer, depends)
- Signature verification: Captures driver signing information

**Output:**
- Default: `/var/lib/dgx_spark_management/clear_asset_information/driver_inventory_reporter/driver_inventory.json`
- Logs: `/var/log/dgx_spark/clear_asset_information/driver_inventory_reporter/driver_inventory.log`

**Quick Usage:**
```bash
# Print to stdout
python3 driver_inventory_reporter/src/driver_inventory_reporter.py --print

# Write to default location
sudo python3 driver_inventory_reporter/src/driver_inventory_reporter.py

# Skip USB collection (faster)
python3 driver_inventory_reporter/src/driver_inventory_reporter.py --no_usb --print

# Skip modinfo enrichment (much faster)
python3 driver_inventory_reporter/src/driver_inventory_reporter.py --no_modinfo --print

# Verbose logging
sudo python3 driver_inventory_reporter/src/driver_inventory_reporter.py --verbose
```

**Integration:**
- Derives asset_id independently from DMI sysfs (no hard dependency)
- Correlates NICs to PCI devices by bus address
- Builds deterministic driver manifest (sorted, stable output)
- Tracks module usage across all device types

**Documentation:** See [driver_inventory_reporter/README.md](driver_inventory_reporter/README.md) for complete details.

### 5. Software Inventory Reporter (`software_inventory_reporter/`)
**Status**: ✅ Implemented

Comprehensive software package and container inventory collector.

**Key Features:**
- dpkg package inventory (Debian/Ubuntu packages)
- snap package inventory (Ubuntu snaps)
- Optional pip inventory (Python packages)
- Optional docker inventory (images and containers)
- Deterministic manifest with counts and SHA256 hashes
- Software fingerprint for drift detection
- Full and curated modes (for CMDB scale)
- Python 3 (stdlib-only, no external dependencies)
- Graceful degradation (optional tools handled gracefully)

**Validated on DGX Spark:**
- dpkg: ~2000+ packages including dgx-release, nvidia-driver, linux-image
- snaps: 7+ snaps including firmware-updater, snapd, firefox, core22
- pip: Available (optional, disabled by default)
- docker: Available (optional, disabled by default)
- Manifest: Deterministic counts + hashes for fast drift detection

**Output:**
- Default: `/var/lib/dgx_spark_management/clear_asset_information/software_inventory_reporter/software_inventory.json`
- Logs: `logs/clear_asset_information/software_inventory_reporter/software_inventory_reporter.log` (or `/var/log/dgx_spark/...`)

**Quick Usage:**
```bash
# Print to stdout (no root required)
python3 software_inventory_reporter/src/software_inventory_reporter.py --print

# Write to default location
sudo python3 software_inventory_reporter/src/software_inventory_reporter.py

# Curated mode (smaller output for CMDB)
python3 software_inventory_reporter/src/software_inventory_reporter.py --mode curated --print

# Enable pip and docker inventories
sudo python3 software_inventory_reporter/src/software_inventory_reporter.py --enable-pip --enable-docker

# Verbose logging
sudo python3 software_inventory_reporter/src/software_inventory_reporter.py --verbose
```

**Integration:**
- Derives asset_id independently from DMI sysfs (no hard dependency)
- Deterministic software fingerprint enables drift detection
- Manifest hashes enable fast comparisons without full package list
- Curated mode focuses on enterprise-relevant packages (smaller output)

**Use Cases:**
- **Support Baselining**: Quickly identify installed software for troubleshooting
- **Configuration Drift Detection**: Compare fingerprints across devices or over time
- **Compliance Auditing**: Verify only approved packages are installed
- **CMDB Integration**: Populate Configuration Management Database
- **Security Posture**: Track package versions for vulnerability assessment

**Documentation:** See [software_inventory_reporter/README.md](software_inventory_reporter/README.md) for complete details.

### 6. Asset Tag Manager (`asset_tag_manager/`)
**Status**: ✅ Implemented (2 subtools)

Enterprise asset metadata manager using UEFI variable storage.

**Key Features:**
- **NVAIAwrite**: Deployment-time write/update tool
- **NVAIAread**: On-demand read/export tool
- UEFI variable storage (persistent across reboots and OS reinstalls)
- Structured JSON payload with 5 groups
- Immutable flag handling (chattr -i/+i)
- Payload size enforcement (8KB default, 32KB max)
- CMDB-friendly tags (owner, location, cost center, role)
- Entitlement and warranty metadata support
- No external Python dependencies (stdlib only)

**Data Model (Schema NVAIA_ASSETMETA_V1):**
- **PRELOADPROFILE**: Factory imaging metadata (IMAGEDATE, IMAGE)
- **USERASSETDATA**: Asset tracking and warranty (ASSET_NUMBER, PURCHASE_DATE, WARRANTY_END, WARRANTY_DURATION, AMOUNT)
- **LEASEDATA**: Lease/rental contracts (LEASE_START_DATE, LEASE_END_DATE, LEASE_TERM, LEASE_AMOUNT, LESSOR)
- **OWNERDATA**: Owner and location (OWNERNAME, DEPARTMENT, LOCATION, PHONE_NUMBER, OWNERPOSITION)
- **USERDEVICE**: User-defined custom fields (max 5 keys, case-sensitive)

**Validated on DGX Spark:**
- efivarfs mounted read-write at `/sys/firmware/efi/efivars`
- Custom variable support confirmed (attrs 0x7 = NV|BS|RT)
- Max payload tested: 32,768 bytes
- Immutable flag handling works (chattr -i/+i)
- Variable persists across reboots

**Storage:**
- Variable: `NVAIAAssetMeta-3b8e3c2a-2f4a-4a4b-8d2d-9f4d0c8b7b2a`
- Format: 4-byte attrs (little-endian uint32) + UTF-8 JSON payload
- Location: `/sys/firmware/efi/efivars/`

**Quick Usage:**

**NVAIAwrite (requires sudo):**
```bash
# Set owner location and department
sudo NVAIAwrite OWNERDATA LOCATION=RDU1 DEPARTMENT=Engineering

# Set asset number and warranty
sudo NVAIAwrite USERASSETDATA ASSET_NUMBER=DGX12345 WARRANTY_END=2027-12-31

# Set custom fields
sudo NVAIAwrite USERDEVICE COST_CENTER=CC-42-ENG ENVIRONMENT=production

# Dry run (preview changes)
NVAIAwrite OWNERDATA LOCATION=RDU1 --dry-run

# Load from file
sudo NVAIAwrite OWNERDATA --file /tmp/owner_data.txt
```

**NVAIAread (no sudo required):**
```bash
# Read all data as JSON
NVAIAread ALL --format json

# Read specific group
NVAIAread OWNERDATA

# Read specific fields
NVAIAread OWNERDATA LOCATION DEPARTMENT

# Exclude empty fields
NVAIAread USERASSETDATA --exclude-empty

# Output as SET commands
NVAIAread LEASEDATA --format set --prefix ASSET_

# Save to file
NVAIAread ALL --format json --output /tmp/asset_metadata.json
```

**Use Cases:**
- **Warranty Tracking**: Store purchase date, warranty end date, warranty duration
- **Lease Management**: Track lease start/end dates, terms, lessor information
- **CMDB Integration**: Export structured metadata for Configuration Management Database
- **Asset Location**: Track device location, department, owner information
- **Custom Tags**: Store cost center, project code, environment tags (production/dev)
- **Support Baselining**: Quick access to asset metadata for troubleshooting

**Integration:**
- Works independently (derives asset_id from DMI sysfs if needed)
- NVAIAread includes platform identity for correlation
- Compact tag generation for short asset identifiers
- CMDB-ready JSON export format

**Governance:**
- **DO NOT** store secrets, passwords, or API keys
- **PII Warning**: OWNERNAME and PHONE_NUMBER contain personally identifiable information
- **Write Frequency**: Asset metadata is static; avoid high-frequency writes (NVRAM has limited write cycles)
- **Payload Size**: Stay under 8KB default limit for safety margin

**Documentation:** See [asset_tag_manager/README.md](asset_tag_manager/README.md) for complete details.

## Installation

Install all requirements in this functional area:

```bash
cd clear_asset_information
sudo ../scripts/install_area.sh --area clear_asset_information
```

Or install individual requirements as needed.

## Configuration

Configuration files for this area are located in each requirement's `config/` directory.

Common configuration options:
- `INVENTORY_SCHEDULE`: How often to collect inventory
- `REPORT_FORMAT`: Output format (json, xml, csv)
- `UPLOAD_ENABLED`: Whether to upload to management server

## Integration

Asset information integrates with:
- **Lifecycle Management**: For tracking device lifecycle
- **Compliance**: For regulatory reporting
- **Update Management**: To determine compatibility
- **Remote Operations**: For diagnostic information

## Compliance

Supports compliance requirements for:
- IT asset management (ITAM)
- Financial auditing
- Software license compliance
- Hardware warranty tracking

## Security Considerations

- Asset data may contain sensitive information
- Restrict access to asset reports
- Encrypt asset data in transit
- Audit access to asset information

## See Also

- [Hardware Inventory Collector README](hardware_inventory_collector/README.md) - Device identity and hardware configuration
- [Firmware Version Reporter README](firmware_version_reporter/README.md) - BIOS, UEFI, NVMe, NIC, GPU firmware
- [OS Build Identity Reporter README](os_build_identity_reporter/README.md) - OS version, DGX build, baseline packages
- [Driver Inventory Reporter README](driver_inventory_reporter/README.md) - Device-driver bindings and modules
- [Software Inventory Reporter README](software_inventory_reporter/README.md) - Complete software package enumeration
- [Asset Tag Manager README](asset_tag_manager/README.md) - UEFI-based asset metadata (warranty, owner, location, tags)
- [Main Documentation](../docs/)

---

**Functional Area**: Clear Asset Information  
**Status**: Active  
**Maintained By**: Asset Management Team
