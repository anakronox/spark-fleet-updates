# Third-Party Notices

## DGX Spark Management — Cookbook Code Package

This document contains notices for third-party software related to this project.

---

## Distributed Dependencies

**None.** This project contains no third-party source code, libraries, or
binaries. All Python source files use the Python standard library exclusively.
No third-party packages are required, bundled, or distributed.

---

## Runtime System Dependencies

The following tools are invoked as external processes at runtime on the target
Ubuntu system. They are **not distributed** with this project and must be
installed separately by the system administrator. They are listed here for
transparency.

| Tool | Purpose | Typical Package | License |
|---|---|---|---|
| `dmidecode` | SMBIOS/DMI hardware data | `dmidecode` | GPL-2.0 |
| `nvme-cli` | NVMe drive enumeration | `nvme-cli` | GPL-2.0 |
| `fwupd` / `fwupdmgr` | Firmware update management | `fwupd` | LGPL-2.1 |
| `apt` / `apt-cache` / `dpkg` | Package management and inventory | `apt` / `dpkg` | GPL-2.0 |
| `lspci` | PCI device enumeration | `pciutils` | GPL-2.0 |
| `nvidia-smi` | GPU status and inventory | NVIDIA driver | NVIDIA proprietary |
| `journalctl` / `systemctl` | systemd journal and service control | `systemd` | LGPL-2.1 |
| `snap` | Snap package inventory | `snapd` | GPL-3.0 |
| `docker` | Container runtime inventory | `docker.io` | Apache-2.0 |
| `pip` / `pip3` | Python package inventory | `python3-pip` | MIT |
| `efivar` / `efibootmgr` | UEFI variable access | `efivar` / `efibootmgr` | LGPL-2.1 |
| `mokutil` | Secure Boot key management | `mokutil` | GPL-2.0 |
| `landscape-client` | Canonical Landscape agent | `landscape-client` | GPL-2.0 |

These tools are system utilities available through standard Ubuntu package
repositories. Their licenses are governed by their respective upstream projects.
NVIDIA does not distribute, modify, or hold copyright over these tools.

---

## Python Standard Library

This project uses the Python standard library, which is distributed under the
[Python Software Foundation License (PSF)](https://docs.python.org/3/license.html).
The standard library is not distributed with this project; it is provided by
the Python interpreter installed on the target system.
