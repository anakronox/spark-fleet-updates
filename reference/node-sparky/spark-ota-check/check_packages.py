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

"""Check installed deb packages against an OTA recipe's package list."""

from utils import CheckResult, run_cmd


def _get_installed_packages() -> dict[str, str]:
    out = run_cmd(["dpkg-query", "-W", "-f", "${Package},${Version}\n"])
    packages = {}
    for line in out.splitlines():
        if "," in line:
            name, version = line.split(",", 1)
            packages[name] = version
    return packages


def _dpkg_cmp(a: str, op: str, b: str) -> bool:
    import subprocess
    try:
        proc = subprocess.run(
            ["dpkg", "--compare-versions", a, op, b],
            capture_output=True, timeout=10,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _version_ge(installed: str, required: str) -> bool:
    return _dpkg_cmp(installed, "ge", required)


def _version_lt(installed: str, ceiling: str) -> bool:
    return _dpkg_cmp(installed, "lt", ceiling)


_installed_cache: dict[str, str] | None = None


def _get_installed(refresh: bool = False) -> dict[str, str]:
    global _installed_cache
    if _installed_cache is None or refresh:
        _installed_cache = _get_installed_packages()
    return _installed_cache


def check_packages(packages: list[dict],
                    ceilings: dict[str, str] | None = None) -> list[CheckResult]:
    """Check installed packages using range-based comparison.

    A package passes if:  installed >= expected  AND  installed < ceiling.
    The ceiling is the version from the next newer OTA recipe (if any).
    """
    installed = _get_installed()
    results = []

    for pkg in packages:
        name = pkg["name"]
        req_ver = pkg["version"]
        ceiling = ceilings.get(name) if ceilings else None

        inst_ver = installed.get(name, "")
        if not inst_ver:
            results.append(CheckResult(
                name=name, expected=req_ver, found="",
                passed=False,
                message=f"ERROR: {name} not found, expected >= {req_ver}",
            ))
        elif _version_ge(inst_ver, req_ver) and (ceiling is None or _version_lt(inst_ver, ceiling)):
            results.append(CheckResult(
                name=name, expected=req_ver, found=inst_ver,
                passed=True,
                message=f"- {name} match: {inst_ver}",
            ))
        elif not _version_ge(inst_ver, req_ver):
            results.append(CheckResult(
                name=name, expected=req_ver, found=inst_ver,
                passed=False,
                message=f"ERROR: {name} version too low: {inst_ver} < {req_ver}",
            ))
        else:
            results.append(CheckResult(
                name=name, expected=req_ver, found=inst_ver,
                passed=False,
                message=f"INFO: {name} version beyond this OTA: {inst_ver} >= {ceiling}",
            ))

    return results
