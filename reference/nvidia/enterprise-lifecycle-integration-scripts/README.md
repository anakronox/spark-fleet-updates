# DGX Spark Management — Cookbook Code Package

This directory is the companion code package for **Manageability-Cookbook-V1-Draft003.docx**.
It contains all production tools, shared runtime dependencies, Landscape reference scripts,
and user-facing documentation needed to deploy and operate the DGX Spark enterprise
management suite on Ubuntu 22.04 / 24.04 (ARM64).

---

## Directory Map

```
Cookbook_Code/
├── README.md                                  ← this file
├── CHANGELOG.md                               ← version history
├── LANDSCAPE_REFERENCE_SCRIPTS_SETUP.md       ← Landscape scripts setup guide
├── reinstall_all.sh                           ← re-install all tools at once
│
├── common/                                    ← shared Python runtime dependency
│   ├── README.md                              ← install notes (bash, CRLF troubleshooting)
│   ├── cli_base.py                            ← REQUIRED by all Python tools
│   ├── __init__.py
│   └── install.sh
│
├── bin/                                       ← pre-assembled deployment copies of all tools
│   ├── common/                                ← cli_base.py for bin/ scripts
│   ├── device_identity.py
│   ├── driver_inventory_reporter.py
│   ├── firmware_reporter.py
│   ├── hardware_config.py
│   ├── os_build_identity.py
│   ├── reset_reason_reporter.py
│   ├── software_inventory_reporter.py
│   ├── spark_diagctl.py
│   ├── spark_updatectl.py
│   ├── NVAIAread                              ← UEFI asset-tag reader (installed by asset_tag_manager/install.sh)
│   └── NVAIAwrite                             ← UEFI asset-tag writer (installed by asset_tag_manager/install.sh)
│
├── clear_asset_information/                   ← functional area: hardware/software inventory
│   ├── README.md
│   ├── hardware_inventory_collector/          ← hardware topology, GPU/CPU/NIC/SSD
│   ├── firmware_version_reporter/             ← BIOS/EC/NIC/SSD/GPU firmware
│   ├── os_build_identity_reporter/            ← OS release, kernel, DGX build info
│   ├── driver_inventory_reporter/             ← kernel module inventory
│   ├── software_inventory_reporter/           ← dpkg/pip/snap/docker packages
│   └── asset_tag_manager/                     ← UEFI-backed asset metadata
│
├── controlled_sw_fw_updates/                  ← functional area: kernel & firmware updates
│   ├── README.md
│   └── update_control_plane/                  ← GRUB kernel list, reboot coordination
│
├── remote_ops_remediation/                    ← functional area: diagnostics & reboot analysis
│   ├── README.md
│   ├── diagnostic_collector/                  ← GPU health, thermal, crash diagnostics
│   └── reset_reason_reporter/                 ← previous-boot reset cause analysis
│
├── attestable_conformance_regulatory/         ← Landscape script: APT signing verification
│   └── landscape_signing_verification/
│
├── network_enterprise_connectivity/           ← Landscape scripts: log retrieval & bundles
│   ├── README.md
│   ├── landscape_collect_package/
│   └── landscape_retrieve_logs_stdout/
│
├── resilience_recovery_rollback/              ← Landscape scripts: recovery & watchdogs
│   ├── README.md
│   ├── landscape_factory_reset_reprovision/
│   ├── landscape_health_watchdogs/
│   ├── landscape_recovery_backup_levels/
│   └── landscape_verified_boot_integrity/
│
├── security_posture_vuln_response/            ← Landscape script: encryption-at-rest
│   ├── README.md
│   └── landscape_encryption_at_rest/
│
└── docs/                                      ← documentation
    ├── core_docs/                             ← indexed reference documentation
    ├── user_guides/                           ← getting_started.md, faq.md
    ├── deployment/                            ← deployment_guide.md
    ├── templates/                             ← script & README templates
    ├── PROJECT_STRUCTURE.md
    └── LANDSCAPE_INTEGRATION_MANUAL.md
```

---

## Installation

### Recommended: install everything from the repository root

From `Cookbook_Code/` (use `bash` so execute bits are not required):

```bash
bash install.sh
```

This runs `reinstall_all.sh`, which installs `common/` into `bin/common/`, runs each tool’s `install.sh`, and fixes `+x` on `*.sh` under the repo.

Equivalent:

```bash
bash reinstall_all.sh
```

### Install only the shared runtime (`common/`)

From the repository root:

```bash
bash common/install.sh
```

Avoid `sudo ./install.sh` inside `common/` unless the file is executable (`chmod +x`): without `+x`, sudo may report **command not found**. Prefer `bash common/install.sh`.

### Install a single tool

```bash
bash clear_asset_information/hardware_inventory_collector/install.sh
```

### Troubleshooting

| Symptom | Cause | What to do |
|--------|--------|------------|
| `sudo: ./install.sh: command not found` | Script not executable (`-rw-r--r--`) | Run `bash install.sh` or `bash path/to/install.sh` |
| `./install.sh: cannot execute: required file not found` | CRLF (`\r\n`) in the file; kernel looks for `/bin/bash\r` | `git config core.autocrlf false` then `git add --renormalize .` and `git checkout -- .`, or `dos2unix` on `*.sh` |
| `: command not found`, `set: pipefail: invalid option` | CRLF in nested `install.sh` | Same as above; ensure `.gitattributes` is present and re-checkout |

### Verify

```bash
ls -la bin/
python3 bin/firmware_reporter.py --help
python3 bin/hardware_config.py --print
```

---

## Tool Quick Reference

| Tool script | Installed binary | Purpose |
|-------------|-----------------|---------|
| `bin/hardware_config.py` | `/usr/local/sbin/hardware_config` | CPU/GPU/SSD/NIC topology |
| `bin/device_identity.py` | `/usr/local/sbin/device_identity` | Stable device identifier |
| `bin/firmware_reporter.py` | `/usr/local/sbin/firmware_reporter` | Firmware versions via fwupd |
| `bin/os_build_identity.py` | `/usr/local/sbin/os_build_identity` | OS release + DGX build info |
| `bin/driver_inventory_reporter.py` | `/usr/local/sbin/driver_inventory_reporter` | Kernel module inventory |
| `bin/software_inventory_reporter.py` | `/usr/local/sbin/software_inventory_reporter` | dpkg/pip/snap/docker packages |
| `bin/spark_updatectl.py` | `/usr/local/sbin/spark_updatectl` | GRUB kernels, reboot coordination |
| `bin/spark_diagctl.py` | `/usr/local/sbin/spark_diagctl` | GPU health, thermals, crash diagnostics |
| `bin/reset_reason_reporter.py` | `/usr/local/sbin/reset_reason_reporter` | Previous-boot reset cause analysis |
| `bin/NVAIAread` | `/usr/local/sbin/NVAIAread` | Read UEFI asset tag variables |
| `bin/NVAIAwrite` | `/usr/local/sbin/NVAIAwrite` | Write UEFI asset tag variables |

All Python tools emit JSON to stdout:
```json
{"ok": true, "data": { ... }, "errors": [], "meta": {"tool": "...", "version": "0.1.0", "collected_at_utc": "..."}}
```

Use `--human` for a human-readable summary, `--help` for full usage.

---

## Key Dependency: common/cli_base.py

Every Python tool imports from `cli_base`. It provides:

- `format_envelope(ok, data, errors, meta)` — standard JSON output structure
- `create_base_parser()` / `create_subparser_tool_parser()` — consistent argument parsing
- `ExitCode` — standardised exit codes (0 = ok, 1 = partial, 2 = error)
- `setup_logging()` — stderr logging configuration

If you are running tools without `install.sh` (e.g. during development), add
`common/` to `PYTHONPATH`:

```bash
export PYTHONPATH="$(pwd)/common:$PYTHONPATH"
python3 bin/firmware_reporter.py
```

---

## Landscape Reference Scripts

The `landscape_*/` directories contain bash scripts registered as **Canonical Landscape
Remote Script Activities**. Each is self-contained, writes JSON to stdout, and exits
with a standardised code (0 = PASS, 1 = FAIL, 2 = UNKNOWN).

| Script | Purpose |
|--------|---------|
| `attestable_conformance_regulatory/landscape_signing_verification/signing_verification.sh` | APT repository signing checks |
| `network_enterprise_connectivity/landscape_collect_package/collect_package.sh` | Generate support bundle tar.gz |
| `network_enterprise_connectivity/landscape_retrieve_logs_stdout/retrieve_logs_stdout.sh` | Stream logs to stdout |
| `resilience_recovery_rollback/landscape_factory_reset_reprovision/factory_reset_reprovision.sh` | Gated factory reset |
| `resilience_recovery_rollback/landscape_health_watchdogs/health_watchdogs.sh` | Watchdog probe & self-test |
| `resilience_recovery_rollback/landscape_recovery_backup_levels/recovery_backup_levels.sh` | Recovery/backup level probe |
| `resilience_recovery_rollback/landscape_verified_boot_integrity/verified_boot_integrity.sh` | Secure Boot + kernel lockdown |
| `security_posture_vuln_response/landscape_encryption_at_rest/encryption_at_rest.sh` | LUKS/dm-crypt state report |

See `LANDSCAPE_REFERENCE_SCRIPTS_SETUP.md` for registration instructions and
`docs/LANDSCAPE_INTEGRATION_MANUAL.md` for the full integration guide.

---

## Documentation

| Document | Contents |
|----------|----------|
| `docs/core_docs/` | Complete indexed reference documentation |
| `docs/user_guides/getting_started.md` | Installation and first steps |
| `docs/user_guides/faq.md` | Frequently asked questions |
| `docs/deployment/deployment_guide.md` | Production deployment instructions |
| `docs/PROJECT_STRUCTURE.md` | Repository layout reference |
| `docs/LANDSCAPE_INTEGRATION_MANUAL.md` | Canonical Landscape integration guide |
| `LANDSCAPE_REFERENCE_SCRIPTS_SETUP.md` | Landscape script setup guide |
| `CHANGELOG.md` | Version history |
