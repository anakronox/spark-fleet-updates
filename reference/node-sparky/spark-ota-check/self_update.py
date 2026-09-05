#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""Upgrade nvidia-spark-ota-check before is-ota-available when dashboard is not."""

import fcntl
import json
import os
import subprocess
import sys

_PKG = "nvidia-spark-ota-check"
_SETTINGS = "/opt/nvidia/dgx-dashboard/settings.json"
_DPKG_LOCK = "/var/lib/dpkg/lock-frontend"
_APT_TIMEOUT = 300


def _run(cmd: list[str], timeout: int = _APT_TIMEOUT) -> int:
    if os.geteuid() != 0:
        cmd = ["sudo", "-n", *cmd]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        ).returncode
    except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
        return -1


def _dashboard_refreshes_ota_check() -> bool:
    """True when dgx-dashboard-admin will apt-update this package on its timer."""
    for arg in ("is-enabled", "is-active"):
        try:
            if subprocess.run(
                ["systemctl", arg, "dgx-dashboard-admin.service"],
                capture_output=True,
                timeout=5,
            ).returncode != 0:
                return False
        except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
            return False

    try:
        with open(_SETTINGS, encoding="utf-8") as fh:
            data: object = json.load(fh)
    except FileNotFoundError:
        return True  # no file → updates enabled (dashboard default)
    except (OSError, json.JSONDecodeError):
        return True  # unreadable → enabled (dashboard default)

    if not isinstance(data, dict):
        return True
    update = data.get("update")
    if isinstance(update, dict) and update.get("enabled") is False:
        return False
    return True


def _policy_versions() -> tuple[str, str]:
    try:
        out = subprocess.check_output(
            ["apt-cache", "policy", _PKG],
            text=True,
            timeout=30,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
        return "", ""
    installed = candidate = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Installed:"):
            installed = line.split(":", 1)[1].strip()
        elif line.startswith("Candidate:"):
            candidate = line.split(":", 1)[1].strip()
    return installed, candidate


def _candidate_newer(candidate: str, installed: str) -> bool:
    if not candidate or candidate == "(none)":
        return False
    if not installed or installed == "(none)":
        return True
    return _run(["dpkg", "--compare-versions", candidate, "gt", installed], timeout=10) == 0


def _dpkg_lock_free() -> bool:
    fd = None
    try:
        fd = os.open(_DPKG_LOCK, os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except (OSError, BlockingIOError):
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def self_update(argv: list[str], verbose: bool = False) -> None:
    if _dashboard_refreshes_ota_check():
        if verbose:
            print("Self-update: skipped (dashboard-admin manages package refresh)")
        return

    if verbose:
        print("\nSelf-update (nvidia-spark-ota-check)\n-------------------")

    rc = _run(["apt-get", "-qq", "update"])
    if verbose:
        print(f"apt-get update: exit {rc}")
    installed, candidate = _policy_versions()
    if verbose:
        print(f"apt-cache policy: Installed={installed!r} Candidate={candidate!r}")
    if not _candidate_newer(candidate, installed):
        if verbose:
            print("Self-update: no newer package; skipping install")
        return
    if not _dpkg_lock_free():
        if verbose:
            print("Self-update: dpkg lock held; skipping install")
        return

    if verbose:
        print(f"Self-update: installing {_PKG} ...")
    if _run(
        [
            "apt-get", "install", "--only-upgrade", "-y",
            "-o", "Dpkg::Options::=--force-confold", _PKG,
        ],
    ) != 0:
        return

    if verbose:
        print("Self-update: re-exec ...")
    try:
        os.execvp(argv[0], argv)
    except OSError as e:
        if verbose:
            print(f"ERROR: re-exec after install failed: {e}", file=sys.stderr)
