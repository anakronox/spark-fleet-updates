"""Turn one node's collected facts into the record the dashboard shows.

Two questions, answered separately because they are different questions:
  * is this Spark on NVIDIA's latest release?   (the scorer, against carried recipes)
  * how many package updates are pending?       (apt, via the simulation it ran)
and, for the reveal, exactly what an update would change."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .otascore import (NodeFacts, get_all_scores, get_detected, is_ota_available,
                       load_recipes, parse_dpkg_query, parse_fwupd_devices, summary)

_INST = re.compile(r"^Inst (\S+)(?: \[([^\]]*)\])? \(([^ )]+) ([^)]*)\)")
_SUMMARY = re.compile(r"(\d+) upgraded, (\d+) newly installed, (\d+) to remove")


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def parse_apt_sim(text: str) -> dict:
    """`apt-get -s full-upgrade` → the package list a person can read."""
    pkgs = []
    for line in text.splitlines():
        m = _INST.match(line)
        if not m:
            continue
        name, old, new, origin = m.groups()
        src = "nvidia" if "nvidia" in origin.lower() or "cuda" in origin.lower() else \
              "ubuntu-esm" if "esm" in origin.lower() else "ubuntu"
        pkgs.append({"name": name, "from": old or None, "to": new, "new": old is None,
                     "security": "security" in origin.lower(), "source": src})
    counts = {"upgraded": 0, "new": 0, "removed": 0}
    m = _SUMMARY.search(text)
    if m:
        counts = {"upgraded": int(m.group(1)), "new": int(m.group(2)), "removed": int(m.group(3))}
    # security-fix packages first, then new ones, then the rest, alphabetical within
    pkgs.sort(key=lambda p: (not p["security"], not p["new"], p["name"]))
    return {"packages": pkgs, "counts": counts, "total": len(pkgs)}


def _hexver(v: str) -> str:
    if isinstance(v, str) and v.startswith("0x"):
        try:
            n = int(v, 16)
            return f"{(n >> 24) & 0xFF}.{(n >> 8) & 0xFFFF}.{n & 0xFF}"
        except ValueError:
            pass
    return v


def parse_fwupd_updates(text: str) -> list[dict]:
    """`fwupdmgr get-updates --json` → one row per device with an update."""
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = []
    for dev in data.get("Devices", []):
        rels = dev.get("Releases") or []
        if not rels:
            continue
        best = rels[0]
        rows.append({"device": dev.get("Name", "device"), "now": _hexver(dev.get("Version", "")),
                     "after": _hexver(best.get("Version", "")), "size": best.get("Size"),
                     "summary": best.get("Summary", ""), "vendor": dev.get("Vendor", ""),
                     "needs_reboot": "needs-reboot" in (dev.get("Flags") or [])})
    return rows


_FW_NAMES = {"SOCFW": "System firmware", "EC": "Embedded controller", "EC Unfused": "Embedded controller (unfused)",
             "USBPD": "USB-C power controller", "TPM": "TPM firmware", "CX7": "Network card (ConnectX-7)"}


def build(node: dict, facts: dict, recipes_dir: Path) -> dict:
    recipes = load_recipes(recipes_dir)
    nf = NodeFacts(host=node["name"], packages=parse_dpkg_query(facts.get("packages", "")),
                   kernel=facts.get("kernel", ""), driver=facts.get("driver", ""),
                   fwupd_devices=parse_fwupd_devices(facts.get("fwupd_devices", "")),
                   dmidecode_t45=facts.get("dmidecode_t45", ""), connectx_fw=facts.get("mstflint", ""),
                   board_vendor=facts.get("board_vendor", ""))
    scores = get_all_scores(recipes, nf)
    detected = get_detected(scores)
    avail = is_ota_available(scores)
    latest = max((r for r in recipes if not r.is_ebeta), key=lambda r: r.release_date)
    latest_score = next(s for s in scores if s.recipe.name == latest.name)

    behind = []
    for r in latest_score.all_results:
        if r.passed:
            continue
        kind = "firmware" if r in latest_score.firmware_results else "software" if r in latest_score.software_results else "package"
        behind.append({"kind": kind, "name": r.name, "label": _FW_NAMES.get(r.name, r.name),
                       "installed": r.found or None, "target": r.expected})

    if nf.connectx_fw:
        cx = next((r for r in latest_score.firmware_results if r.name == "CX7"), None)
        cx7 = {"state": "ok" if (cx and cx.passed) else "behind", "version": (cx.found if cx else "")}
    else:
        cx7 = {"state": "not-verifiable", "reason": "no cable plugged in — the card is switched off"}

    apt = parse_apt_sim(facts.get("apt_sim", ""))
    total, security = None, None
    if ";" in facts.get("apt_check", ""):
        a, b = facts["apt_check"].split(";")[:2]
        total, security = int(a), int(b)
    if total is None:
        total, security = apt["total"], sum(1 for p in apt["packages"] if p["security"])

    inhibitors_block = [l for l in facts.get("inhibitors", "").splitlines() if l.strip().endswith("block")]

    return {
        "name": node["name"], "host": node["host"], "reachable": True,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hostname": facts.get("hostname"), "board": facts.get("board_vendor"),
        "board_kind": "NVIDIA-built" if nf.is_nvidia_fe else "OEM-built",
        "kernel": facts.get("kernel"), "driver": facts.get("driver"), "boot_id": facts.get("boot_id"),
        "release": {
            "on": detected.recipe.name, "on_name": detected.recipe.external_name,
            "on_date": detected.recipe.release_date_str[:10],
            "latest": latest.name, "latest_name": latest.external_name, "latest_date": latest.release_date_str[:10],
            "available": bool(avail["available"]),
            "description": latest.description, "release_notes_url": latest.release_notes_url,
            "checks_passed": latest_score.passed_checks, "checks_total": latest_score.total_checks,
            "behind": behind,
        },
        "updates": {"total": total, "security": security, "as_of": _iso(facts.get("updates_available_mtime")),
                    "counts": apt["counts"], "packages": apt["packages"]},
        "firmware_updates": parse_fwupd_updates(facts.get("fwupd_updates", "")),
        "cx7": cx7,
        "reboot": {"required": bool(facts.get("reboot_required")), "packages": facts.get("reboot_required_pkgs", []),
                   "blocking_inhibitors": inhibitors_block},
        "dashboard_auto_update": facts.get("dashboard_auto_update"),
        "sudo_passwordless": facts.get("sudo_passwordless"),
        "firmware_readable": facts.get("firmware_readable", True),
        "disk_free_bytes": facts.get("disk_free_bytes"), "dpkg_lock_held": facts.get("dpkg_lock_held"),
        "recipes_match": None,   # filled by the service, which knows the carried set
        "fabric": facts.get("fabric", {"macs": [], "ports": [], "lldp": [], "neigh": []}),
        "ota_check_version": facts.get("ota_check_version"),
        "collect_errors": facts.get("errors", {}),
        "scorer": summary(scores),
    }
