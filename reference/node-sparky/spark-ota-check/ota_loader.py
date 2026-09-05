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
import glob
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OTARecipe:
    path: Path
    metadata: dict
    packages: list[dict]
    firmware: list[dict]
    connectx: list[dict]
    software: list[dict]
    raw: dict

    @property
    def name(self) -> str:
        return self.metadata.get("name", "UNKNOWN")

    @property
    def external_name(self) -> str:
        return self.metadata.get("external_name") or self.name

    @property
    def description(self) -> str:
        return self.metadata.get("description", "")

    @property
    def release_notes_url(self) -> str:
        return self.metadata.get("releaseNotesUrl", "")

    @property
    def required_match(self) -> list[str]:
        return self.metadata.get("required_match", [])

    @property
    def release_date_str(self) -> str:
        return self.metadata.get("releaseDate", "")

    @property
    def release_date(self) -> datetime:
        if not self.release_date_str:
            return datetime.min
        return datetime.fromisoformat(self.release_date_str.replace("Z", "+00:00"))


def load_recipe(path: Path) -> OTARecipe:
    with open(path) as f:
        data = json.load(f)
    return OTARecipe(
        path=path,
        metadata=data.get("metadata", {}),
        packages=data.get("package", []),
        firmware=data.get("firmware", []),
        connectx=data.get("connectx", []),
        software=data.get("software", []),
        raw=data,
    )


def discover_recipes(directory: Path) -> list[OTARecipe]:
    """Find all spark-ota-*.json files, load them, return sorted newest-first."""
    pattern = str(directory / "spark-ota-*.json")
    paths = [Path(p) for p in glob.glob(pattern)]

    recipes = []
    for p in paths:
        try:
            recipes.append(load_recipe(p))
        except (json.JSONDecodeError, KeyError) as e:
            print(f"WARNING: Skipping {p.name}: {e}")

    recipes.sort(key=lambda r: r.release_date, reverse=True)
    return recipes


if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent / "metadata"
    recipes = discover_recipes(script_dir)

    print(f"Found {len(recipes)} OTA recipe(s), sorted newest-first:\n")
    for i, r in enumerate(recipes):
        latest = " <- LATEST" if i == 0 else ""
        print(f"  {r.name:>8}  {r.release_date.strftime('%Y-%m-%d')}  {r.path.name}{latest}")
