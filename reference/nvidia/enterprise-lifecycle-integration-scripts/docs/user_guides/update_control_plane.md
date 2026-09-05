# Update Control Plane — Quick Smoke-Test Guide

`spark_updatectl` v2.0.0 adds full update policy management on top of the
existing reboot and kernel-rollback commands.

---

## Prerequisites

```bash
# Install (from repo root)
bash reinstall_all.sh

# Verify binary is present
ls -la bin/spark_updatectl.py bin/apt_policy.py bin/fwupd_policy.py \
       bin/internet_policy.py bin/repo_manager.py
```

---

## Smoke Tests

### 1. Self-test (no root required)

```bash
python3 bin/spark_updatectl.py --self-test
```

Expected: `"ok": true` with all checks passed.

---

### 2. Status (no root required)

```bash
python3 bin/spark_updatectl.py status
```

Expected: JSON envelope with `"ok": true`, `policy` block, `apt_timers`, `fwupd_timer`.

---

### 3. Updates — check current state

```bash
python3 bin/spark_updatectl.py updates status
```

Expected: `"updates_enabled": true` (default), timer active/enabled states.

---

### 4. Updates — disable / re-enable (requires sudo)

```bash
# Disable automatic updates
sudo python3 bin/spark_updatectl.py updates disable

# Confirm timers are stopped
python3 bin/spark_updatectl.py updates status

# Re-enable
sudo python3 bin/spark_updatectl.py updates enable
```

---

### 5. Repo — configure local APT mirror (requires sudo)

```bash
# Set a local mirror
sudo python3 bin/spark_updatectl.py repo set \
    --mirror-url http://192.168.1.10/ubuntu

# Inspect result
python3 bin/spark_updatectl.py repo status

# Reset (removes dgx-spark-local-mirror.list)
sudo python3 bin/spark_updatectl.py repo reset
```

---

### 6. Internet — deny / allow (requires sudo)

```bash
# Enforce local-mirror-only (disables internet .list files)
sudo python3 bin/spark_updatectl.py internet deny

# Verify
python3 bin/spark_updatectl.py internet status
# Expect: "mode": "deny", disabled_sources listed

# Re-allow internet
sudo python3 bin/spark_updatectl.py internet allow
python3 bin/spark_updatectl.py internet status
# Expect: "mode": "allow"
```

---

### 7. Policy — unified view and reset (requires sudo for reset)

```bash
# Read full policy
python3 bin/spark_updatectl.py policy status

# Set a key
sudo python3 bin/spark_updatectl.py policy set updates_enabled=false

# Reset everything to defaults
sudo python3 bin/spark_updatectl.py policy reset
```

---

### 8. Update — dry-run check (no root required)

```bash
python3 bin/spark_updatectl.py update check
```

Runs `apt-get update` + `apt-get upgrade --dry-run` and `fwupdmgr get-updates`.
No packages are installed.

---

### 9. Update — apply now (requires sudo)

```bash
sudo python3 bin/spark_updatectl.py update now
```

Runs `apt-get upgrade -y` then `fwupdmgr update -y`.

---

## State File

All policy changes are persisted to:

```
/var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane/state.json
```

Inspect with:

```bash
cat /var/lib/dgx_spark_management/controlled_sw_fw_updates/update_control_plane/state.json
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | `ok: true` — command succeeded |
| 1    | `ok: false` — command failed (see `errors[]` in JSON) |
| 2    | Invalid arguments |
| 3    | Permission denied (run with sudo) |

---

## File Permissions Installed

| File | Mode |
|------|------|
| `bin/spark_updatectl.py` | `0755` (executable) |
| `bin/apt_policy.py` | `0644` (library) |
| `bin/fwupd_policy.py` | `0644` (library) |
| `bin/internet_policy.py` | `0644` (library) |
| `bin/repo_manager.py` | `0644` (library) |
