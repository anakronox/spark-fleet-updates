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

import re

from utils import CheckResult, run_cmd


def _version_tuple(ver: str) -> tuple:
    """Split on '.' and '-', converting numeric parts to ints for proper ordering."""
    parts = re.split(r'[.\-]', ver)
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)


def _version_ge(installed: str, required: str) -> bool:
    return _version_tuple(installed) >= _version_tuple(required)


def check_kernel(expected: str) -> CheckResult:
    found = run_cmd(["uname", "-r"]).strip()

    if _version_ge(found, expected):
        return CheckResult("kernel", expected, found, True,
                           f"- kernel match: {found}")

    return CheckResult("kernel", expected, found, False,
                       f"ERROR: kernel mismatch: {found} < {expected}")


def check_driver(expected: str) -> CheckResult | None:
    raw = run_cmd(["nvidia-smi", "-q"])
    found = ""
    for line in raw.splitlines():
        if "Driver Version" in line:
            found = line.split(":")[-1].strip()
            break

    if not found:
        return CheckResult(
            "driver", expected, "",
            False,
            f"WARN: driver version unavailable (nvidia-smi)",
        )

    if _version_ge(found, expected):
        return CheckResult("driver", expected, found, True,
                           f"- driver match: {found}")

    return CheckResult("driver", expected, found, False,
                       f"ERROR: driver mismatch: {found} < {expected}")


def check_software(software: list[dict]) -> list[CheckResult]:
    results = []
    for item in software:
        name = item["name"]
        expected = item["version"]
        if name == "kernel":
            results.append(check_kernel(expected))
        elif name == "driver":
            results.append(check_driver(expected))
    return results
