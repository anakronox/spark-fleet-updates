# `tools/` — the off-box scorer

The first piece of the front-end: NVIDIA's OTA release detection, reimplemented
to run on the control host against facts collected over SSH.

| file | what |
|---|---|
| `otascore.py` | Port of NVIDIA's scorer (`ota_checker.py`, `check_packages.py`, `check_software.py`, `check_firmware.py`). Stdlib only. Includes a pure-Python `dpkg --compare-versions`, so the control host does not need `dpkg`. |
| `collect_facts.sh` | Collects one node's facts over SSH. Unprivileged apart from two `sudo -n` commands. `--oracle` also runs the node's own root checker. |
| `validate_against_nodes.py` | Scores the collected facts and diffs the result against that oracle, per node and per recipe. |

## Re-validating

Against the committed fixtures, offline:

```
python3 tools/validate_against_nodes.py \
    reference/collector-inputs \
    reference/node-sparky/spark-ota-check/metadata
```

Against the live fleet:

```
tools/collect_facts.sh --oracle /tmp/facts sparky sparketa sparkjr
python3 tools/validate_against_nodes.py /tmp/facts \
    reference/node-sparky/spark-ota-check/metadata
```

Expect `ALL NODES IDENTICAL TO ORACLE`. **Re-run it whenever
`nvidia-spark-ota-check` is upgraded on the fleet** — that is the regression
test for the port, and it needs a node to produce a fresh oracle.

## Why a port rather than shelling out

NVIDIA's `check_ota_status.py` requires root for every subcommand, and its
`is-ota-available` path `apt-get install`s a newer checker as a side effect.
Scoring off-box removes both, matches the framework's "parse off-box, never on
the device" rule, and keeps the node stack untouched.

The privilege it does not remove is firmware: `check_firmware.py` reads
`dmidecode -t 45` on every board type, and the ConnectX-7 version through
`mstflint`. Those two commands are the whole root requirement:

```
spark-fleet ALL=(root) NOPASSWD: /usr/sbin/dmidecode -t 45, /usr/bin/mstflint -d * q
```

Withholding them is not a safe simplification — see `NOTES.md`, "Decided:
reimplement the scorer off-box". Without firmware evidence, detection silently
reports behind nodes as current.

## Fidelity notes

Places where the original is easy to misread, all preserved in the port:

- `package_results` is computed **without** ceilings; the ceiling-ranged results
  feed `match_*` and `detection_rank`. NVIDIA computes both, and `summary`'s
  `torn` / `failed` come from the unranged set.
- An empty component list scores **100.0**, not 0.0.
- Firmware matching is a bounded regex substring test, not a version comparison.
- `_is_nvidia_fe()` selects the firmware path and is **not constant across a
  fleet**: NVIDIA-built boards merge fwupd with dmidecode, OEM boards use
  dmidecode alone.
- `torn-score` rounds to an integer, `summary` to one decimal, both with
  Python's banker's rounding.
