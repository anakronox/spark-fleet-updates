# Architecture

How spark-fleet-updates is put together: one controller service on a host that
is not a Spark, nothing resident on the Sparks, and every decision below traced
to something measured in [`fleet-updates.md`](fleet-updates.md) or recorded in
[`../NOTES.md`](../NOTES.md).

## 1. The shape, in one picture

```
 control host (not a Spark)                         each Spark
┌──────────────────────────────────────────┐       ┌──────────────────────────────┐
│  controller service                      │  ssh  │  nothing resident            │
│                                          │──────▶│                              │
│  inventory ─┐                            │       │  ~spark-collect/.ssh         │
│  recipes ───┼─▶ collector ─▶ scorer ─┐   │       │  ~spark-apply/.ssh           │
│             │                        ▼   │       │  /etc/sudoers.d/spark-fleet  │
│             │                   posture  │       │  (dashboard auto-update off) │
│             │                        │   │       │                              │
│             └─▶ planner ◀────────────┘   │       │  during an apply only:       │
│                    │                     │       │   systemd-run transient unit │
│                    ▼                     │       │   spark-apply-<run>.service  │
│   executor: precheck→apply→reboot→post   │──────▶│   (gone after reboot)        │
│                    │                     │       └──────────────────────────────┘
│                    ▼                     │
│   run records (envelope + raw stdout)    │◀──── read-only ──── spark-dash, humans
│   front-end reads posture + runs         │
└──────────────────────────────────────────┘
```

Three loops run over that shape:

| loop | cadence | privilege on node | writes on node |
|---|---|---|---|
| **collect → score → posture** | scheduled, e.g. hourly, and on demand | unprivileged + `dmidecode -t 45` + `mstflint … q` | none |
| **plan** | on demand, before a ring | unprivileged (`apt-get -s`, `fwupdmgr get-updates`) | none (apt dry-run) |
| **execute** | human-triggered per ring | root, via a narrow sudoers set | the update itself |

## 2. Why no agent on the Sparks

The obvious alternative is a daemon on each node that the controller talks to.
Rejected, for reasons that each stand alone:

- **It is what NVIDIA's own framework says not to do.** "This model
  intentionally avoids requiring a resident management agent on the DGX Spark
  endpoint" (guide §1.5). Fleet tooling that departs from the vendor model
  inherits every future incompatibility alone.
- **Who updates the updater.** An agent is a package; it needs the dpkg lock
  the update needs, it needs to survive the reboot it triggers, and it needs
  its own upgrade path. That is a fifth claimant on a lock that already has
  four.
- **It changes the thing being measured.** The scorer's job is to say what is
  on the node. The node stack should be byte-identical to a stock Spark plus a
  sudoers file, so that "current" here means the same as "current" on a Spark
  we have never touched.
- **SSH already exists and already works.** Key-based, unprivileged, with
  `sudo -n` available. Measured on all three nodes on 2026-09-05.
- **Three nodes.** Push events and fan-in scale are agent arguments; neither
  applies here, and the design leaves room to add one later if it ever does.

The one thing an agent genuinely provides — an apply step that survives the
controller's SSH session dropping — is provided instead by running the apply
under `systemd-run` as a transient unit and polling it. That is a temporary
agent that removes itself, and it is the same trick NVIDIA's shipped
`spark_updatectl.py reboot schedule` uses (a transient timer).

## 3. What lives on a node

Exactly this, and nothing else persists:

| item | purpose | notes |
|---|---|---|
| the controller's SSH key in the user's `authorized_keys` | login | one key, generated on the controller host |
| `/etc/sudoers.d/spark-fleet` | two read-only commands without a password | `dmidecode -t 45`, `mstflint -d * q` — the firmware reads the release check needs |
| `/opt/nvidia/dgx-dashboard/settings.json` with `update.enabled: false` | the Dashboard's admin stops auto-upgrading the OTA metapackage on its own timer | **the one persistent config change**, made the first time Update is pressed; without it the Dashboard applies releases outside our control and races our apt runs |

**Privilege follows the DGX Dashboard's model** (decided 2026-09-05). The
Dashboard runs its web UI unprivileged and asks for your password, which its
root helper checks before doing the work. Here, the hourly check is
unprivileged apart from the two reads above, and pressing Update asks for the
user's password on that Spark; the controller holds it in memory for that run,
feeds it to `sudo -S` for each privileged command (`systemd-run`, the journal
read, unit cleanup, `systemctl reboot`, the settings write), and forgets it.
It is never written to state, logs or envelopes. The page is served over HTTPS
(self-signed by default) and a password is refused over plain HTTP unless a
TLS-terminating proxy vouches with `X-Forwarded-Proto`. A Spark that grants
the user `NOPASSWD: ALL` is detected and the dialog does not ask — the
unattended mode, for a lab that accepts a standing root credential.

NVIDIA's own tools (`spark_updatectl.py`, `os_build_identity.py`,
`reset_reason_reporter.py`) are **not installed** on the node. They are stdlib
Python; the controller copies them to `/tmp/spark-fleet/` at the start of a run
and removes them at the end. Same for our apply script. Nothing accumulates.

## 4. Controller components

All of it is files under one directory on the control host. No database
service; the run record is the store (NOTES.md, "Decided: self-contained").

```
spark-fleet-updates/
├── fleet.yaml                  inventory and rings
├── recipes/spark-ota-*.json    carried copy of the OTA recipes
├── tools/                      otascore.py, collect_facts.sh, validate_against_nodes.py, …
├── state/
│   ├── posture/<node>.json     latest per-node posture, overwritten each collect
│   ├── posture/history/        one file per collect, for trend
│   └── runs/<run-id>/
│       ├── plan.json           what the ring was going to do
│       ├── <node>/<step>.json  envelope per step
│       └── <node>/<step>.out   raw stdout, verbatim
└── docs/, reference/, NOTES.md
```

### 4.1 Inventory and rings (`fleet.yaml`)

```yaml
nodes:
  sparky:   {host: 192.0.2.11, board: oem}
  sparketa: {host: sparketa,      board: fe}
  sparkjr:  {host: sparkjr,       board: oem}

units:                      # nodes that must end a ring on the same release
  inference-pair: [sparketa, sparkjr]

rings:
  pilot: [sparky]
  broad: [inference-pair]
```

Rings are inventory groups, as the guide prescribes. **`units` is the one idea
added**: `sparketa` and `sparkjr` are the cabled pair that pools memory for
distributed inference, and the current fleet has them split across two OTA
levels, which is exactly the drift this project exists to end. A unit is
updated as one thing — both nodes or neither, and the ring gate for a unit
requires both to postcheck clean. `sparky` is the natural pilot: standalone,
and the furthest behind, so it exercises the largest jump first.

### 4.2 Recipes

`recipes/` is a carried copy of `/opt/nvidia/spark-ota-check/metadata/`. The
controller refreshes it from any node on each collect (`recipes-present.txt`
already detects a changed set) and computes "newest stable" offline. A node
whose recipe set differs from the carried copy is flagged, because its checker
would disagree with ours about the target.

### 4.3 Collector and scorer

`tools/collect_facts.sh` today, growing to also gather: `apt-check` counts and
the `updates-available` mtime, `/run/reboot-required(.pkgs)`, `boot_id`,
`GetOTAAvailabilitySnapshot`, and the pushed-over-stdin outputs of
`spark_updatectl.py status` and `reboot plan`. `spark_fleet/otascore.py` scores it.
The result is the **posture record**:

```json
{
  "node": "sparky", "collected_at": "…", "board": "ASUSTeK COMPUTER INC.",
  "ota": {"detected": "OTA2.2", "newest_stable": "OTA2607", "available": true,
          "torn": 3.3, "failed": ["…"]},
  "apt": {"pending": 210, "security": 133, "as_of": "…"},
  "firmware": {"fwupd_updates": [...], "cx7": "not-verifiable: no cable"},
  "reboot": {"required": false, "safe_to_proceed": true, "inhibitors": []},
  "recipes_match_carried_copy": true,
  "dashboard_auto_update": "enabled"
}
```

That file is the API. The front-end renders it; `spark-dash` may read it and
nothing more. Note `firmware.cx7` carries a **third state**: NVIDIA's checker
reports an absent CX7 as a silent pass, and the hotplug driver removes the
card from PCI whenever no cable is present (NOTES.md, Traps), so "verified",
"failed" and "not verifiable" must be distinct.

### 4.4 Planner

For a ring, per node, unprivileged: `apt-get -s full-upgrade` parsed off-box
(the package delta), `fwupdmgr get-updates --json` (the firmware delta), and
the scorer's `failed` list against the newest stable recipe (the release
delta). Written to `state/runs/<run-id>/plan.json` before anything runs. Until
NVIDIA ships the v2 `update check`, this *is* "what would change".

### 4.5 Executor

The per-node state machine, straight from `fleet-updates.md` §7.3 with the
guards NVIDIA leaves implicit made explicit:

```
PRECHECK   collect + score (baseline)
           spark_updatectl.py reboot plan  →  safe_to_proceed, no blocking inhibitors
           dpkg lock not held; disk headroom; dashboard auto-update disabled
           recipes match carried copy
           gate: all true, else HOLD

APPLY      systemd-run --unit spark-apply-<run> --wait=false …/apply.sh
           apply.sh:  wait on /var/lib/dpkg/lock-frontend (as NVIDIA's self_update.py does)
                      apt-get update
                      DEBIAN_FRONTEND=noninteractive apt-get full-upgrade -y     # full-, never plain upgrade
                      fwupdmgr refresh ; fwupdmgr upgrade -y <non-interactive flags, verified on fwupd 2.0.20>
           controller polls: systemctl status / journalctl -u, 25 min firmware budget (NVIDIA's own)
           gate: unit exited 0, else HOLD with journal attached

REBOOT     spark_updatectl.py reboot now --reason "spark-fleet <run-id>"   (honours inhibitors)
           controller waits for ssh; requires boot_id changed; timeout → HOLD

POSTCHECK  collect + score again
           gate: ota.available == false AND ota.detected == newest_stable
                 reboot.required == false
                 reset_reason_reporter.py shows an intended reboot
                 firmware.cx7 ∈ {verified, not-verifiable}   — never "failed"
           HOLD otherwise

RING GATE  every node in the ring (and both halves of every unit) postcheck-clean → next ring
           any HOLD → stop, attach evidence, human decides
```

Every step produces one envelope (`tool, ts, host, status, rc, duration_ms,
summary, warnings, artifacts` — the guide's §2.4 record) plus raw stdout, and
the scorer's `summary` before and after is the pair that says exactly which
packages moved. Failures are classed with NVIDIA's taxonomy — transport/auth,
privilege, tool execution, endpoint degraded — so a HOLD says what kind of
thing went wrong before anyone reads a log.

### 4.6 The service, and the GUI

The controller is one program with two entry points. As a CLI: `collect`,
`score`, `plan`, `apply`, `status` — every screen has a scriptable equivalent,
and the executor can be driven without the GUI. As a service: the same code on
a timer for collect/score, serving the GUI over HTTP on the control host.

**The GUI is deliberately as simple as the DGX Dashboard's update card, for
every Spark at once.** Decided 2026-09-05: it does not surface the internals.
One screen, one row per Spark:

| element | what it shows or does | backed by |
|---|---|---|
| status | "up to date with NVIDIA" or "update available · July 2026", plus "N updates, M security" | posture record |
| show updates ▾ | the release and its description, each firmware device now → after, the package list; says when the network card can't be checked | posture + planner |
| update | one button; confirms, then runs the executor's state machine and shows a progress bar and a log inline; keeps going if the page is closed | executor, transient unit |
| afterwards | "Updated to July 2026 at 14:17 · what changed" | run record, scorer before → after |
| + add a spark | hostname/IP and optional name; connects with the user's SSH key; tests reachability | inventory |
| ⋯ menu | check now · rename · remove | inventory |

What stays *behind* the screen, unchanged: rings, units, prechecks, the
orchestrator envelope, raw stdout, the sudoers split, the recipe copy. The
GUI shows their consequences in plain words — "sparketa and sparkjr work as a
pair, so updating one updates both", "1 thing to fix first" — never their
names. The full plan, the exact commands and the run records exist on disk and
through the CLI for whoever wants them. Copy on screen is written the way a
person thinks: release names, counts, plain verbs.

Nothing in the GUI talks to a Spark directly; it reads files the service
wrote and asks the service to start an update. The service should live on a
host that is not a Spark — it reboots them. `spark-dash` stays read-only and
may consume `posture/*.json`; it never gets a button.

## 5. Safety properties, and where each comes from

| property | mechanism | source |
|---|---|---|
| a node is never updated outside a ring | Dashboard auto-update disabled; `apply` is human-triggered | §4.3, NOTES Traps |
| never fights for the dpkg lock | wait on `lock-frontend`; Dashboard timer off | `self_update.py`, NOTES Traps |
| never undoes NVIDIA's pins | plain `apt-get full-upgrade`, never named packages/repos | `fleet-updates.md` §3.1 |
| never leaves a release half-arrived | `full-upgrade`, not `upgrade` | §3.2 (metapackage `Depends:` growth), NOTES |
| never reboots into a blocked state | `reboot plan` gate, `reboot now` honours inhibitors | shipped `spark_updatectl.py` 1.1.0 |
| survives the controller dropping mid-apply | transient systemd unit | `systemd-run`; NVIDIA's `reboot schedule` precedent |
| never reports a behind node as current | scorer keeps `dmidecode`/`mstflint`; validated bit-for-bit on all nodes | NOTES, "Decided: reimplement the scorer" |
| never mistakes a missing CX7 for a passing one | explicit `not-verifiable` state | NOTES Traps, hotplug investigation |
| the pair never ends split | `units` in inventory | measured fleet state, §8 |
| every action is reconstructible | envelope + verbatim stdout per step, scorer before/after | guide §2.4, §7.3 |
| the vendor's status query never mutates the node | our scorer replaces `is-ota-available` | §3.3 self-update trap |

## 6. Build order

1. **Collector to posture.** Extend `collect_facts.sh`, emit the posture
   record for all three nodes. Read-only. *(scorer already done and validated)*
2. **The list.** The service on a timer plus the one screen, read-only: each
   Spark, its status, "show updates". Add/remove/rename a Spark.
3. **Planner behind "show updates".** `apt-get -s full-upgrade` and
   `fwupdmgr get-updates` parsed off-box, so the reveal shows real deltas.
4. **Node prep.** The two users, the sudoers drop-in, Dashboard auto-update
   off — on `sparky` only.
5. **The Update button, against `sparky`.** March 2026 → July 2026, the
   whole state machine, progress and log inline, run records on disk. Then
   re-validate the scorer against a fresh oracle, since
   `nvidia-spark-ota-check` itself will have moved.
6. **The pair.** Updating one of `sparketa`/`sparkjr` updates both, and the
   screen says so before you press the button. History.

Each step leaves the previous one working and adds no privilege it does not
use.
