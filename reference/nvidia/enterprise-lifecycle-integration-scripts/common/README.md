# `common/` — shared Python runtime

All production tools import from `cli_base`, `output`, and `asset_id` here. They must be copied into `bin/common/` before tools run.

## Install (recommended)

From the **repository root** (parent of `common/`):

```bash
bash install.sh
```

That runs `reinstall_all.sh`, which installs `common/` first, then every tool’s `install.sh`, and sets execute bits on `*.sh`.

To install **only** the shared modules:

```bash
bash common/install.sh
```

## Do not rely on `./install.sh` unless you know it is executable

Clones and zip copies often arrive with `install.sh` **not** marked executable (`-rw-r--r--`). Then:

- `sudo ./install.sh` → `sudo: ./install.sh: command not found`
- Use **`bash common/install.sh`** or **`bash ./install.sh`** instead (does not require `+x`).

## If you see `required file not found` or `No such file or directory` when running `./install.sh`

The script likely has **Windows CRLF** line endings. The kernel tries to run `/bin/bash\r`, which does not exist.

Fix in a Git clone:

```bash
git config core.autocrlf false
git add --renormalize .
git checkout -- .
```

Or convert scripts: `dos2unix common/install.sh` (repeat for `*.sh` as needed).
