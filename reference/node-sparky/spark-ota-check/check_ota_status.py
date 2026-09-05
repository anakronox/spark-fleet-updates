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

import sys
import os

# Ensure sibling modules are importable when invoked via /usr/bin/ symlink
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import argparse
import json

import subprocess

from ota_checker import OTAScore, get_all_scores, get_detected, fw_guid_map
from self_update import self_update


# When a component is more than this percentage out of date relative to the
# detected OTA, we urge the user to update that component class.
TORN_THRESHOLD_PCT = 70


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_version() -> str:
    try:
        out = subprocess.check_output(
            ["dpkg-query", "-W", "-f", "${Version}", "nvidia-spark-ota-check"],
            stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except Exception:
        return "unknown"

def _output(data: dict) -> None:
    json.dump(data, sys.stdout, indent=2)
    print()


def _error_exit(msg: str) -> None:
    _output({"error": msg})
    sys.exit(1)


def _get_scores(verbose: bool = False) -> list[OTAScore]:
    try:
        return get_all_scores(verbose=verbose)
    except RuntimeError as e:
        _error_exit(str(e))


# ── Subcommand handlers ─────────────────────────────────────────────────────

def _is_ebeta(recipe) -> bool:
    return "ebeta" in recipe.name.lower()


_COMPONENT_ACTIONS = {
    "firmware": "fwupdmgr refresh ; fwupdmgr upgrade",
    "software": "apt update ; apt full-upgrade",
    "packages": "apt update ; apt full-upgrade",
}


def _recommended_actions(score: OTAScore) -> list[dict]:
    """Return one entry per component whose torn% exceeds TORN_THRESHOLD_PCT."""
    by_component = (
        ("firmware", score.torn_fw_pct),
        ("software", score.torn_sw_pct),
        ("packages", score.torn_pkg_pct),
    )
    return [
        {
            "component": component,
            "torn": round(torn, 1),
            "action": _COMPONENT_ACTIONS[component],
        }
        for component, torn in by_component
        if torn > TORN_THRESHOLD_PCT
    ]


def cmd_is_available(recipes: list[OTAScore]) -> None:
    """Available = the detected (best-matching) OTA is not the latest recipe."""
    detected = get_detected(recipes)
    stable = [s for s in recipes if not _is_ebeta(s.recipe)]
    if not stable:
        _output({
            "available": False,
            "name": detected.recipe.external_name,
            "description": detected.recipe.description,
            "releaseNotesUrl": detected.recipe.release_notes_url,
            "releaseDate": detected.recipe.release_date_str,
            "metadataFilePath": "",
            "recommendedActions": _recommended_actions(detected),
        })
        return
    latest = max(stable, key=lambda s: s.recipe.release_date)
    best_stable = detected if not _is_ebeta(detected.recipe) else get_detected(stable)
    available = best_stable.recipe.name != latest.recipe.name

    target = latest if available else best_stable
    _output({
        "available": available,
        "name": target.recipe.external_name,
        "description": target.recipe.description,
        "releaseNotesUrl": target.recipe.release_notes_url,
        "releaseDate": target.recipe.release_date_str,
        "metadataFilePath": str(latest.recipe.path) if available else "",
        "recommendedActions": [] if available else _recommended_actions(detected),
    })


def cmd_torn_score(recipes: list[OTAScore]) -> None:
    """Return how torn/incomplete the best-matching OTA is (0 = fully applied)."""
    best = get_detected(recipes)
    _output({
        "name": best.recipe.name,
        "releaseDate": best.recipe.release_date_str,
        "torn": round(best.torn_pct),
    })


def cmd_installed_name(recipes: list[OTAScore]) -> None:
    """Return the name of the best-matching installed OTA."""
    best = get_detected(recipes)
    _output({"name": best.recipe.name, "releaseDate": best.recipe.release_date_str})


def cmd_installed_versions(recipes: list[OTAScore]) -> None:
    """Return actual installed versions for components in the best-matching OTA."""
    best = get_detected(recipes)
    guids = fw_guid_map(best.recipe)

    _output({
        "packages": [
            {"name": r.name, "installedVersion": r.found}
            for r in best.package_results
        ],
        "firmware": [
            {"name": r.name, "guid": guids.get(r.name, ""), "installedVersion": r.found}
            for r in best.firmware_results
        ],
        "software": [
            {"name": r.name, "installedVersion": r.found}
            for r in best.software_results
        ],
    })


def cmd_summary(recipes: list[OTAScore]) -> None:
    """Full telemetry summary across all OTA recipes."""
    best = get_detected(recipes)

    _output({
        "detected_ota": best.recipe.name,
        "releaseDate": best.recipe.release_date_str,
        "torn": round(best.torn_pct, 1),
        "scores": [
            {
                "ota": s.recipe.name,
                "releaseDate": s.recipe.release_date_str,
                "detection_rank": round(s.detection_rank, 2),
                "match": round(s.match_pct, 1),
                "torn": round(s.torn_pct, 1),
                "total_checks": s.total_checks,
                "passed_checks": s.passed_checks,
                "failed": s.failed_names,
                **( {"required_match": s.recipe.required_match,
                     "required_satisfied": s.required_satisfied}
                    if s.recipe.required_match else {}),
            }
            for s in recipes
        ],
    })


def cmd_ota_versions(recipes: list[OTAScore]) -> None:
    """Return expected versions from the latest OTA recipe."""
    latest = max(recipes, key=lambda s: s.recipe.release_date)
    recipe = latest.recipe

    firmware = [
        {"name": fw["name"], "guid": fw.get("guid", ""), "minRequiredVersion": fw["version"]}
        for fw in recipe.firmware
    ]
    for cx in recipe.connectx:
        firmware.append({"name": cx["name"], "guid": "", "minRequiredVersion": cx["version"]})

    _output({
        "packages": [
            {"name": p["name"], "minRequiredVersion": p["version"]}
            for p in recipe.packages
        ],
        "firmware": firmware,
        "software": [
            {"name": s["name"], "minRequiredVersion": s["version"]}
            for s in recipe.software
        ],
    })


# ── CLI setup ────────────────────────────────────────────────────────────────

_COMMANDS = {
    "is-ota-available": cmd_is_available,
    "torn-score": cmd_torn_score,
    "installed-name": cmd_installed_name,
    "installed-versions": cmd_installed_versions,
    "ota-versions": cmd_ota_versions,
    "summary": cmd_summary,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nvidia-spark-ota-check",
        description="Prints system component information compared to released OTA updates.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Prints detailed per-check results and a full summary for every recipe evaluated.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser(
        "is-ota-available",
        help=(
            "Check if a newer OTA update is available (JSON). Updates this "
            "tool to the latest version first when the DGX Dashboard is not "
            "already handling automatic updates."
        ),
    )
    sub.add_parser(
        "torn-score",
        help="Prints how incomplete the current OTA update is (0 = fully applied).",
    )
    sub.add_parser(
        "installed-name",
        help="Prints the name of the OTA release that best matches the installed system.",
    )
    sub.add_parser(
        "installed-versions",
        help="Prints installed package, firmware, and software versions for the matched OTA.",
    )
    sub.add_parser(
        "ota-versions",
        help="Prints the expected package, firmware, and software versions from the latest OTA.",
    )
    sub.add_parser(
        "summary",
        help="Prints a detailed comparison of system components to all released OTA updates.",
    )

    return parser


def _require_root() -> None:
    if os.geteuid() != 0:
        _error_exit(
            "nvidia-spark-ota-check must run as root "
            "(e.g. sudo nvidia-spark-ota-check <command>)."
        )


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    _require_root()

    if args.command == "is-ota-available":
        self_update(sys.argv, verbose=args.verbose)

    scores = _get_scores(verbose=args.verbose)

    if args.verbose and args.command != "summary":
        cmd_summary(scores)
        print()

    _COMMANDS[args.command](scores)


if __name__ == "__main__":
    main()
