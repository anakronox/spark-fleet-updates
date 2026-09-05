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

from dataclasses import dataclass, field
from pathlib import Path

from utils import CheckResult
from ota_loader import OTARecipe, discover_recipes
from check_packages import check_packages
from check_software import check_software
from check_firmware import check_firmware

# Weights for ordering recipes for detection (sum = 1.0). Firmware + software
# anchor "which line"; packages alone can misleadingly favor a newer recipe.
DETECTION_FW_WEIGHT = 0.35
DETECTION_SW_WEIGHT = 0.25
DETECTION_PKG_WEIGHT = 0.40


@dataclass
class OTAScore:
    recipe: OTARecipe
    package_results: list[CheckResult]
    software_results: list[CheckResult]
    firmware_results: list[CheckResult]
    match_pct: float = 0.0
    match_failed: list[str] = field(default_factory=list)
    match_pkg_pct: float = 0.0
    match_sw_pct: float = 0.0
    match_fw_pct: float = 0.0

    @property
    def required_satisfied(self) -> bool:
        """True when every required_match component passed in the match context."""
        req = self.recipe.required_match
        if not req:
            return True
        return not any(name in self.match_failed for name in req)

    @property
    def all_results(self) -> list[CheckResult]:
        return self.package_results + self.software_results + self.firmware_results

    @property
    def total_checks(self) -> int:
        return len(self.all_results)

    @property
    def passed_checks(self) -> int:
        return sum(1 for r in self.all_results if r.passed)

    @property
    def torn_pct(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return ((self.total_checks - self.passed_checks) / self.total_checks) * 100

    @staticmethod
    def _torn_pct(results: list[CheckResult]) -> float:
        total = len(results)
        if total == 0:
            return 0.0
        failed = sum(1 for r in results if not r.passed)
        return (failed / total) * 100

    @property
    def torn_fw_pct(self) -> float:
        return self._torn_pct(self.firmware_results)

    @property
    def torn_sw_pct(self) -> float:
        return self._torn_pct(self.software_results)

    @property
    def torn_pkg_pct(self) -> float:
        return self._torn_pct(self.package_results)

    @property
    def failed_names(self) -> list[str]:
        return [r.name for r in self.all_results if not r.passed]

    @property
    def detection_rank(self) -> float:
        """Higher = better fit for get_detected ordering (weighted fw/sw/pkg)."""
        return (
            DETECTION_FW_WEIGHT * self.match_fw_pct
            + DETECTION_SW_WEIGHT * self.match_sw_pct
            + DETECTION_PKG_WEIGHT * self.match_pkg_pct
        )


def _pkg_version_gt(a: str, b: str) -> bool:
    """True if Debian version *a* is strictly greater than *b*."""
    import subprocess
    try:
        proc = subprocess.run(
            ["dpkg", "--compare-versions", a, "gt", b],
            capture_output=True, timeout=10,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _build_ceilings(recipes: list[OTARecipe],
                     component_key: str) -> dict[str, dict[str, str]]:
    """For each recipe's package, the ceiling is the version from the next newer
    recipe that has a strictly higher version for the same package.
    Packages with no ceiling use simple >= comparison.
    """
    by_date = sorted(recipes, key=lambda r: r.release_date)

    all_ceilings: dict[str, dict[str, str]] = {}
    for i, recipe in enumerate(by_date):
        components = getattr(recipe, component_key, [])
        ceilings: dict[str, str] = {}
        for comp in components:
            name, ver = comp["name"], comp["version"]
            for j in range(i + 1, len(by_date)):
                newer_ver = next(
                    (c["version"] for c in getattr(by_date[j], component_key, [])
                     if c["name"] == name),
                    None,
                )
                if newer_ver and _pkg_version_gt(newer_ver, ver):
                    ceilings[name] = newer_ver
                    break
        all_ceilings[recipe.name] = ceilings
    return all_ceilings


def _compute_match_pct(results: list[CheckResult]) -> float:
    total = len(results)
    if total == 0:
        return 0.0
    passed = sum(1 for r in results if r.passed)
    return (passed / total) * 100


def evaluate_recipe(recipe: OTARecipe, verbose: bool = False,
                    pkg_ceilings: dict[str, str] | None = None) -> OTAScore:
    if verbose:
        print(f"\n--- Checking: {recipe.name} ({recipe.path.name}) ---")

    pkg_ranged = check_packages(recipe.packages, ceilings=pkg_ceilings)
    pkg_results = check_packages(recipe.packages)

    if verbose:
        print("\nValidating Packages")
        print("-------------------")
        for r in pkg_results:
            print(r.message)

    if verbose:
        print("\nValidating Software")
        print("-------------------")
    sw_results = check_software(recipe.software)
    if verbose:
        for r in sw_results:
            print(r.message)

    if verbose:
        print("\nValidating Firmware")
        print("-------------------")
    fw_results = check_firmware(recipe.firmware, recipe.connectx)
    if verbose:
        for r in fw_results:
            print(r.message)

    match_all = pkg_ranged + sw_results + fw_results
    match_pct = _compute_match_pct(match_all)
    match_failed = [r.name for r in match_all if not r.passed]
    match_pkg_pct = _compute_match_pct(pkg_ranged) if pkg_ranged else 100.0
    match_sw_pct = _compute_match_pct(sw_results) if sw_results else 100.0
    match_fw_pct = _compute_match_pct(fw_results) if fw_results else 100.0

    return OTAScore(
        recipe=recipe,
        package_results=pkg_results,
        software_results=sw_results,
        firmware_results=fw_results,
        match_pct=match_pct,
        match_failed=match_failed,
        match_pkg_pct=match_pkg_pct,
        match_sw_pct=match_sw_pct,
        match_fw_pct=match_fw_pct,
    )


def get_all_scores(recipe_dir: Path | None = None,
                    verbose: bool = False) -> list[OTAScore]:
    """Evaluate all recipes and return scores sorted best-first."""
    if recipe_dir is None:
        recipe_dir = Path(__file__).resolve().parent / "metadata"

    recipes = discover_recipes(recipe_dir)
    if not recipes:
        raise RuntimeError("No OTA recipes found")

    if verbose:
        print(f"\nFound {len(recipes)} OTA recipe(s), latest: {recipes[0].name}")

    pkg_ceilings = _build_ceilings(recipes, "packages")

    scores: list[OTAScore] = []
    for recipe in recipes:
        score = evaluate_recipe(
            recipe, verbose=verbose,
            pkg_ceilings=pkg_ceilings.get(recipe.name),
        )
        scores.append(score)

        if verbose:
            pkg_pass = sum(1 for r in score.package_results if r.passed)
            pkg_total = len(score.package_results)
            req_info = ""
            if score.recipe.required_match:
                status = "PASS" if score.required_satisfied else "FAIL"
                req_info = f" [required_match: {score.recipe.required_match} {status}]"
            print(f"\n  Match: {score.match_pct:.1f}%  Torn: {score.torn_pct:.1f}% "
                  f"detection_rank: {score.detection_rank:.1f} "
                  f"({score.passed_checks}/{score.total_checks} checks passed) "
                  f"[packages: {pkg_pass}/{pkg_total}]{req_info} \n")

    scores.sort(
        key=lambda s: (s.detection_rank, s.recipe.release_date),
        reverse=True,
    )
    return scores


def get_detected(scores: list[OTAScore]) -> OTAScore:
    """Waterfall: return the best detection_rank OTA whose required_match is satisfied."""
    for s in scores:
        if s.required_satisfied:
            return s
    return scores[0]


def get_best_score(recipe_dir: Path | None = None,
                    verbose: bool = False) -> OTAScore:
    """Evaluate all recipes and return the best-matching OTAScore."""
    return get_detected(get_all_scores(recipe_dir, verbose))


def get_torn_score(recipe_dir: Path | None = None) -> float:
    """Return the torn percentage of the best-matching OTA (0.0 = fully matched)."""
    return get_best_score(recipe_dir).torn_pct


def fw_guid_map(recipe: OTARecipe) -> dict[str, str]:
    """Build a name -> guid lookup from recipe firmware + connectx entries."""
    mapping = {fw["name"]: fw.get("guid", "") for fw in recipe.firmware}
    for cx in recipe.connectx:
        mapping[cx["name"]] = ""
    return mapping
