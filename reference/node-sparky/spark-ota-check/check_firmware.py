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

import json
from pathlib import Path

from utils import CheckResult, run_cmd, make_result

_dmi45_output: str | None = None
_fwupdmgr_output: str | None = None


def _fwupd_device_exists(guid: str) -> bool:
    return guid in _get_fwupd_devices()


def filter_firmware(firmware: list[dict]) -> list[dict]:
    filtered = list(firmware)

    tpm_guid = next((fw["guid"] for fw in firmware if fw["name"] == "TPM"), "")
    if tpm_guid and not _fwupd_device_exists(tpm_guid):
        filtered = [fw for fw in filtered if fw["name"] != "TPM"]

    ec_guid = next((fw["guid"] for fw in filtered if fw["name"] == "EC"), "")
    ec_unfused_guid = next((fw["guid"] for fw in filtered if fw["name"] == "EC Unfused"), "")
    if ec_guid and ec_unfused_guid:
        if _fwupd_device_exists(ec_guid):
            # Fused EC is present, remove EC unfused
            filtered = [fw for fw in filtered if fw["name"] != "EC Unfused"]
        elif _fwupd_device_exists(ec_unfused_guid):
            # Unfused EC is present, remove fused EC
            filtered = [fw for fw in filtered if fw["name"] != "EC"]
        else:
            # Both EC and Unfused EC are missing; remove unfused EC and keep only fused EC
            filtered = [fw for fw in filtered if fw["name"] != "EC Unfused"]

    return filtered


def _translate_hex_version(version: str) -> str:
    try:
        v = int(version.strip(), 0)
        x = (v >> 24) & 0xFF
        y = (v >> 8) & 0xFFFF
        z = v & 0xFF
        return f"{x}.{y}.{z}"
    except (ValueError, TypeError):
        return version


def _get_fwupd_devices() -> dict[str, str]:
    """Parse cached fwupdmgr JSON once per process (shared across all recipes)."""
    global _fwupdmgr_output
    if _fwupdmgr_output is None:
        _fwupdmgr_output = run_cmd(["fwupdmgr", "get-devices", "--json"])

    guid_to_version: dict[str, str] = {}
    if _fwupdmgr_output:
        try:
            data = json.loads(_fwupdmgr_output)
            for device in data.get("Devices", []):
                version = device.get("Version", "")
                if version.startswith("0x"):
                    version = _translate_hex_version(version)
                for guid in device.get("Guid", []):
                    guid_to_version[guid] = version
        except json.JSONDecodeError:
            pass

    return guid_to_version


def _check_firmware_fwupdmgr(firmware: list[dict]) -> list[CheckResult]:
    devices = _get_fwupd_devices()
    results = []
    for fw in firmware:
        name = fw["name"]
        expected = fw["version"]
        guid = fw.get("guid", "")
        found = devices.get(guid, "")
        results.append(make_result(name, expected, found))
    return results


def _check_firmware_dmidecode(firmware: list[dict]) -> list[CheckResult]:
    global _dmi45_output
    if _dmi45_output is None:
        _dmi45_output = run_cmd(["dmidecode", "-t", "45"])
    output = _dmi45_output
    results = []
    for fw in firmware:
        name = fw["name"]
        expected = fw["version"]
        if name == "USBPD":
            results.append(_check_usbpd(name, expected, output))
        else:
            section = _dmidecode_section_for(name)
            results.append(_check_dmidecode_section(section, name, expected, output))
    return results


def _dmidecode_section_for(name: str) -> str:
    if name == "SOCFW":
        return "FLASH"
    if name in ("EC", "EC Unfused"):
        return "EC Firmware"
    return name


def _check_dmidecode_section(section: str, name: str, expected: str, output: str) -> CheckResult:
    current = None
    for line in output.splitlines():
        if "Firmware Component Name:" in line:
            current = line.split(":", 1)[1].strip()
        elif "Firmware Version:" in line and current == section:
            found = line.split(":", 1)[1].strip()
            return make_result(name, expected, found)
    return make_result(name, expected, "")


def _check_usbpd(name: str, expected: str, output: str) -> CheckResult:
    exp_ver = expected.removeprefix("0.")
    pd0 = ""
    pd1 = ""
    for line in output.splitlines():
        stripped = line.strip()
        if "PD0" in stripped:
            pd0 = stripped
        if "PD1" in stripped:
            pd1 = stripped

    if pd0 and pd1 and exp_ver in pd0 and exp_ver in pd1:
        return CheckResult(name, expected, f"PD0/PD1 {exp_ver}", True,
                           f"- {name} check passed. Version: PD0/PD1 {exp_ver}")
    if not pd0 and not pd1:
        return make_result(name, expected, "")
    found = f"PD0={pd0 or '<missing>'} PD1={pd1 or '<missing>'}"
    return CheckResult(name, expected, found, False,
                       f"ERROR: {name} mismatch: {found} != {expected}")


def check_connectx(connectx: dict) -> CheckResult | None:
    name = connectx["name"]
    expected = connectx["version"]

    pci_out = run_cmd(["lspci"])
    pci_addr = ""
    for line in pci_out.splitlines():
        if "Ethernet controller: Mellanox" in line:
            pci_addr = line.split()[0]
            break

    found = ""
    if pci_addr:
        mstflint_out = run_cmd(["mstflint", "-d", pci_addr, "q"])
        for line in mstflint_out.splitlines():
            if "FW Version:" in line:
                found = line.split()[-1].strip()
                break

    # Not failing if the ConnectX is not found
    if not found:
        return None
    return make_result(name, expected, found)


def _is_nvidia_fe() -> bool:
    try:
        vendor = Path("/sys/class/dmi/id/board_vendor").read_text().strip()
        return "NVIDIA" in vendor.upper()
    except OSError:
        return False


def _merge_fwupd_dmidecode(
    fwupd_results: list[CheckResult],
    dmi_results: list[CheckResult],
) -> list[CheckResult]:
    """Require both sources to pass (fwupd alone can report a false positive)."""
    dmi_by_name = {r.name: r for r in dmi_results}
    merged: list[CheckResult] = []
    for fw in fwupd_results:
        dmi = dmi_by_name.get(fw.name)
        if dmi is None:
            merged.append(fw)
            continue
        passed = fw.passed and dmi.passed
        found = f"fwupd={fw.found or '<missing>'}; dmidecode={dmi.found or '<missing>'}"
        if passed:
            message = f"- {fw.name} match (fwupd + dmidecode): {dmi.found}"
        else:
            message = (
                f"ERROR: {fw.name} mismatch: {found} != {fw.expected} "
                f"(fwupd passed={fw.passed}, dmidecode passed={dmi.passed})"
            )
        merged.append(CheckResult(fw.name, fw.expected, found, passed, message))
    return merged


def check_firmware(firmware: list[dict], connectx: list[dict] | None = None) -> list[CheckResult]:
    results = []

    if firmware:
        if _is_nvidia_fe():
            fw_to_check = filter_firmware(firmware)
            results.extend(_merge_fwupd_dmidecode(
                _check_firmware_fwupdmgr(fw_to_check),
                _check_firmware_dmidecode(fw_to_check),
            ))
        else:
            results.extend(_check_firmware_dmidecode(firmware))

    if connectx:
        result = check_connectx(connectx[0])
        if result is not None:
            results.append(result)

    return results
