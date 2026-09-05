#!/usr/bin/env bash
# Collect everything the off-box scorer needs from one or more nodes.
#
#   ./collect_facts.sh <out-dir> <node> [node ...]
#
# Unprivileged except for the two commands NVIDIA's firmware check needs; those
# are attempted with `sudo -n` and simply come back empty when not permitted.
# Passing --oracle also runs the node's own root checker for comparison.
# `is-ota-available` is deliberately NOT run: it is the one subcommand that
# apt-get installs a newer checker as a side effect.
set -uo pipefail

ORACLE=0
[[ "${1:-}" == "--oracle" ]] && { ORACLE=1; shift; }
OUT="${1:?usage: collect_facts.sh [--oracle] <out-dir> <node>...}"; shift
mkdir -p "$OUT"
date -u +"collected %Y-%m-%dT%H:%M:%SZ" > "$OUT/CAPTURED-AT.txt"

for h in "$@"; do
  d="$OUT/$h"; mkdir -p "$d"
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$h" \
      "dpkg-query -W -f '\${Package},\${Version}\n'"        > "$d/dpkg-query.txt"      2>/dev/null
  ssh -o BatchMode=yes "$h" 'uname -r'                       > "$d/uname-r.txt"         2>/dev/null
  ssh -o BatchMode=yes "$h" 'nvidia-smi -q 2>/dev/null | grep -m1 "Driver Version" || true' \
                                                             > "$d/driver.txt"          2>/dev/null
  ssh -o BatchMode=yes "$h" 'fwupdmgr get-devices --json 2>/dev/null'  > "$d/fwupd-devices.json" 2>/dev/null
  ssh -o BatchMode=yes "$h" 'cat /sys/class/dmi/id/board_vendor'       > "$d/board_vendor.txt"   2>/dev/null
  ssh -o BatchMode=yes "$h" 'busctl call com.nvidia.dgx.dashboard.admin1 /com/nvidia/dgx/dashboard/admin com.nvidia.dgx.dashboard.admin1 GetOTAAvailabilitySnapshot 2>&1' \
                                                             > "$d/dbus-snapshot.txt"   2>/dev/null
  ssh -o BatchMode=yes "$h" 'ls /opt/nvidia/spark-ota-check/metadata/' > "$d/recipes-present.txt" 2>/dev/null

  # root-only: the two commands that actually cost privilege
  ssh -o BatchMode=yes "$h" 'sudo -n dmidecode -t 45 2>/dev/null'      > "$d/dmidecode-45.txt"   2>/dev/null
  ssh -o BatchMode=yes "$h" 'lspci 2>/dev/null | grep -i "Ethernet controller: Mellanox" || true' \
                                                             > "$d/lspci-mlnx.txt"      2>/dev/null
  ssh -o BatchMode=yes "$h" 'a=$(lspci 2>/dev/null | grep -i "Ethernet controller: Mellanox" | head -1 | cut -d" " -f1); [ -n "$a" ] && sudo -n mstflint -d "$a" q 2>/dev/null | grep -i "FW Version" || true' \
                                                             > "$d/mstflint.txt"        2>/dev/null

  if (( ORACLE )); then
    for cmd in summary installed-name torn-score; do
      ssh -o BatchMode=yes "$h" \
        "sudo -n python3 /opt/nvidia/spark-ota-check/check_ota_status.py $cmd" \
        > "$d/oracle-$cmd.json" 2>/dev/null
    done
  fi

  printf "%-10s %5s pkgs  kernel=%-20s board=%s\n" \
    "$h" "$(wc -l < "$d/dpkg-query.txt" | tr -d ' ')" \
    "$(cat "$d/uname-r.txt")" "$(cat "$d/board_vendor.txt")"
done
