# Working notes carried over from the investigation

Things learned while researching `docs/fleet-updates.md` that are decisions,
open questions or traps rather than facts about NVIDIA's system. Kept
separate so the reference document stays descriptive.

## Why this is a separate project

`spark-dash` is a read-only monitoring dashboard, and that is a rule it has
held itself to since it allowed alert silencing (its roadmap section G): a
permitted write must be one that "cannot repoint an agent, load a model or
touch a process". Applying an OS-and-firmware update that reboots an
inference node is the maximal version of everything that rule excludes, and
the spark-dash agent is unprivileged by design. So updates are a different
product with a different permission model, and this repo is that product.
The dashboard may one day *display* per-node update posture; it will not
*drive* it.

## Decided: self-contained, no external control plane

**2026-09-05.** This project depends on nothing but SSH to the nodes and the
update sources the nodes already use — NVIDIA's apt repos, Ubuntu's archive and
ESM, LVFS for firmware. No Landscape, no SaaS, no broker, no database service.
That resolves what was starting point 4: **this project owns the apply step**,
and Landscape is prior art rather than a dependency.

What follows from it:

- **Rings, inventory and history live in this repo, as files.** Landscape's
  groups and Ansible's inventory are patterns to copy, not systems to call.
- **No resident agent on the nodes.** That was already NVIDIA's model, so
  self-containment and NVIDIA's design agree here rather than pulling apart.
- **The run record is the store.** The section 5.4 orchestrator envelope plus
  the raw stdout of every step, written to disk under this repo. No external
  CMDB, ITSM or monitoring sink.
- **The OTA recipes ship with the front-end.** They are world-readable on every
  node, so carry a copy and refresh it from a node — "what is the newest stable
  release" must be answerable with every node offline.
- **Landscape's half has to be built here**: the pending-package view and
  scheduled upgrades. Section 7.1's unprivileged reads plus `apt-get -s
  full-upgrade` cover the view; section 7.2 covers the apply.

## The root requirement in the OTA checker is narrower than it looks

`check_ota_status.py` calls `_require_root()` once in `main()`, before any
subcommand, so every command demands sudo. Reading the sources underneath it,
only two of the things it runs actually need root:

| step | command | privilege |
|---|---|---|
| installed packages | `dpkg-query -W`, `dpkg --compare-versions` | none |
| firmware, via fwupd | `fwupdmgr get-devices --json` | none |
| firmware cross-check | `dmidecode -t 45` | **root** |
| ConnectX firmware | `lspci`, then `mstflint -d <addr> q` | **root** |
| the recipes themselves | `/opt/nvidia/spark-ota-check/metadata/*.json` | none, world-readable |

`check_firmware.py` picks one of two firmware paths on `_is_nvidia_fe()`, which
tests `/sys/class/dmi/id/board_vendor` for `NVIDIA`. **That flag is not constant
across a fleet**, which was the surprise:

| node | `board_vendor` | firmware path NVIDIA takes |
|---|---|---|
| `sparketa` | `NVIDIA` | fwupd **and** dmidecode, both must pass |
| `sparky` | `ASUSTeK COMPUTER INC.` | **dmidecode only** — fwupd is never consulted |
| `sparkjr` | `ASUSTeK COMPUTER INC.` | **dmidecode only** |

Both paths use `dmidecode`, so firmware scoring needs root on every node, and on
the two OEM boards the recipes' fwupd GUIDs do not resolve at all.

## Decided: reimplement the scorer off-box, keep two narrow sudo commands

**2026-09-05, measured.** `spark_fleet/otascore.py` is a port of NVIDIA's scoring;
`tools/validate_against_nodes.py` checks it against each node's own root checker.
Result: **identical on all three nodes** — same detected OTA, same torn score,
and every per-recipe `detection_rank`, `match`, `torn`, `total_checks`,
`passed_checks` and `failed` list across all eleven recipes. The pure-Python
Debian version comparator was separately differential-tested against a real
`dpkg` on `sparky` over 482 comparisons, including epoch, tilde and revision
edge cases: zero mismatches. Fixtures are in `reference/collector-inputs/`, so
the check re-runs offline.

**Dropping the two root commands is not a safe trade.** Scored with fwupd only
and no `dmidecode`/`mstflint`:

| node | truth | unprivileged says |
|---|---|---|
| `sparketa` | OTA2607 (current) | OTA2607 — right, but only by luck |
| `sparkjr` | OTA2604 | **OTA2607** — falsely current |
| `sparky` | OTA2.2 | **OTA2607** — falsely current |

The failure is not a false *failure*, it is a false *pass*, and it lands on
exactly the nodes that need updating. Mechanism: on the OEM boards fwupd returns
nothing for the recipes' firmware GUIDs, so firmware scores 0% against *every*
recipe uniformly, contributes no signal, and detection falls to packages alone —
which drifts to the newest recipe, precisely what NVIDIA's own comment warns
about ("packages alone can misleadingly favor a newer recipe"). A fleet view
built that way would report the fleet current and quietly stop updating it.

So: **collect unprivileged, plus exactly two commands via sudo.**

```
spark-fleet ALL=(root) NOPASSWD: /usr/sbin/dmidecode -t 45, /usr/bin/mstflint -d * q
```

Keep `q` pinned as the final argument — `mstflint` can also burn firmware.

What this buys, beyond self-containment: NVIDIA's CLI never runs, so the
`is-ota-available` self-update side effect cannot fire; the control host needs
no `dpkg`; and scoring happens off-box exactly as the framework prescribes. What
it costs: this repo now owns a reimplementation of NVIDIA's scoring. Re-run
`validate_against_nodes.py` whenever `nvidia-spark-ota-check` is upgraded — that
is the regression test, and it needs a node to produce a fresh oracle.

## Decided: passwords at Update time, not passwordless sudo (the Dashboard's model)

**2026-09-05.** The DGX Dashboard does not use `NOPASSWD`: its web UI runs
unprivileged, a root helper is reachable only over D-Bus by the UI's own
group, and it asks for the user's password (`Authenticate`) before privileged
work. This project now does the equivalent: two read-only `NOPASSWD` commands
for the hourly check (`dmidecode -t 45`, `mstflint -d * q`), and the user's
password typed when pressing Update, used via `sudo -S` for that run only and
never stored. HTTPS is on by default (self-signed into `data/tls/`), and a
password over plain HTTP is refused unless a TLS proxy sets
`X-Forwarded-Proto: https`. Verified: dry-run through the password path on
`sparky`; the wrong-password detector matched real `sudo` output; the
plain-HTTP refusal and proxy allowance both behave. A Spark with `NOPASSWD:
ALL` is detected and not asked — the lab's own fleet keeps that, by choice,
on a trusted LAN.

## Decided: partner boards are judged against their vendor, on three lines

**2026-09-07.** Prompted by a second opinion (ChatGPT, reviewing where ASUS is
in its GX10 firmware cycle), which was right on the point and wrong on two
details, both checked against the boards before shipping.

**The point.** ASUS's newest published GX10 bundle is 0105 (2026-08-11).
Through `dmidecode -t 45` it reads as FLASH 2.152.15 / EC 3.3.2, which is exactly
NVIDIA's *April 2026* firmware baseline. July 2026 wants 2.155.11 / 3.5.8, which
only NVIDIA-built boards have. So a GX10 on 0105 with zero package updates is
simultaneously "as current as ASUS allows" and "not on NVIDIA's latest", and a
single status word cannot say both. It now says `waiting on ASUS firmware`,
and the expanded row shows three lines — **Software**, **Platform firmware**,
**NVIDIA July 2026 baseline** — each judged on its own evidence. The posture
record carries them as `software`, `platform_firmware` and `firmware_gap`.

**The two corrections.**

- *Compare in NVIDIA's numbering, not the vendor's.* ASUS lists "SOC FW 3.0.7";
  the recipes say "SOCFW 2.155.11"; the board reports the recipe-style number.
  The scorer's found-versus-expected is the comparison shown; ASUS's component
  list is kept in the vendor table only for the person reading it.
- *Key on `board_vendor`, never on `GX10DGX.*`.* NVIDIA's own checker branches
  on the board vendor; so does `vendors.platform_firmware()`. Every partner
  board takes the partner path; the model string only selects which bundle
  regex to read the BIOS version with. An unlisted partner still gets
  "pending vendor firmware" — just without a "vendor's newest" to compare to.

**What the second opinion missed, and the three lines catch.** At the time,
`sparky` was *not* as updated as it could be: its packages sat at OTA2.2 (an
ordinary apt run fixed that) and its USB-PD controller had not taken 0105's PD
5.22 while `sparkjr`'s had. A GX10 special case reading "waiting on vendor"
would have covered both. Software is therefore judged on packages, kernel and
driver alone; USB-PD stays in the outstanding list with found → expected.

**TPM.** The GX10 answers the TPM row of `dmidecode -t 45` with `SOCTS`, not a
version, so NVIDIA's TPM check can never pass on that board. It is reported as
"not reported by this board (SOCTS)" and excluded from the outstanding count,
rather than shown as forever behind.

**The vendor table is hand-maintained** (`spark_fleet/vendors.py`), carries the
date each entry was last checked, and the page prints that date. There is no
API for a vendor's download page; a stale table should read as stale.
`bios_version`, `bios_date` and `product_name` are three more world-readable
sysfs reads in the collector; no new privilege.

## Design constraints inherited from NVIDIA's own model

- **Agentless.** Fan SSH out from a central host; do not install a resident
  agent on the Sparks. NVIDIA's framework says so explicitly, and it is also
  what keeps the node stack byte-identical.
- **Collectors unprivileged, controllers root, separated.** Every "what is the
  state" question in `docs/fleet-updates.md` §7.1 works as an ordinary SSH
  user except the OTA scorer, and its root gate is blanket rather than earned —
  see the root-scope section above. Every "change something" action in §7.2
  needs root. Design the sudoers policy along that line and it stays small.
- **stdout JSON is the API; parse off-box.** Store the raw stdout of every
  step verbatim plus the orchestrator envelope (`tool, ts, host, status, rc,
  duration_ms, summary, warnings, artifacts`). That record *is* the audit
  trail.
- **Target of record = the newest stable OTA recipe.** Not "zero packages
  pending". The recipes are world-readable JSON on every node; the front-end
  should carry its own copy of the newest one (or fetch it from a node) and
  treat `is-ota-available: false` on every node as the definition of "fleet
  is current".

## Things not yet verified

- The **first boolean** in `GetOTAAvailabilitySnapshot` (`ssbbs`). It read
  `true` on all three nodes, all of which have automatic updates enabled. It
  is probably that setting. A node with the Dashboard's updates disabled
  (`POST /updates/available` locally, or `settings.json` with
  `update.enabled: false`) would settle it.
- Whether **`GetOTAAvailabilitySnapshot` refreshes on call or returns a
  cached value**, and how often the admin's `refreshUpdatesCache` runs. The
  timestamp in the reply looked live (seconds old on each call), which
  suggests on-call, but it was not measured against an apt change.
- Whether NVIDIA will ship the **v2.0.0 `spark_updatectl.py`** its own user
  guide describes (`update check`, `update now`, `repo set`, `internet deny`,
  `policy`). If it does, several rows of §7 collapse into one tool. Worth
  re-downloading the zip periodically and diffing `bin/spark_updatectl.py`'s
  `VERSION`.
- What `UpdateAndReboot` does when apt fails part-way, and whether it holds
  the reboot. The binary's error strings suggest it reports rather than
  rolls back; only observing a failing run would tell.
- **Firmware update duration and behaviour on the ConnectX-7** — the recipes
  check a CX7 firmware version separately from fwupd (there is a
  `spark-mlnx-firmware-manager` directory under `/opt/nvidia/` that was not
  investigated). **Why `sparky` shows no CX7 at all is now explained** — see
  "The CX7 disappears from PCI when no cable is plugged in" under Traps.
- **Whether an OEM board ever resolves the recipes' firmware GUIDs through
  fwupd.** On both ASUS nodes every recipe GUID is absent from
  `fwupdmgr get-devices`, which is what makes the dmidecode path load-bearing.
  If a future release ships matching GUIDs, the unprivileged path becomes
  viable and the sudo rule could be dropped — worth re-testing after each OTA.

## Traps

- **The dpkg lock has four claimants on a stock node**: the Dashboard admin's
  cache refresh and metapackage auto-upgrade, `apt-daily` /
  `unattended-upgrades`, `nvidia-spark-run-apt-upgrade-once` on first boot
  after some upgrades, and the OTA checker's own `self_update`. A controller
  must wait on `/var/lib/dpkg/lock-frontend` (as `self_update.py` does) and
  should probably disable the Dashboard's updates on managed nodes rather
  than race it.
- **Do not bypass the apt pins.** `/etc/apt/preferences.d/` pins the 580
  driver family, fabricmanager, imex, persistenced and nsight to NVIDIA's
  Spark/DGX repos with `-1` against the generic CUDA repo. Plain
  `apt-get full-upgrade` respects this; anything that names packages and
  repos explicitly can undo it.
- **`is-ota-available` is not idempotent** on a node whose Dashboard admin is
  disabled: it will `apt-get install` a newer `nvidia-spark-ota-check` first.
- **The `updates-available` text varies by node** (ESM line present or not).
  Regex it. Its mtime is the "as of"; `apt-daily.timer` refreshes it roughly
  daily.
- **`apt-check` and `apt list --upgradable` disagree** (210 vs 184 on
  `sparky`) by the ESM set. Pick one and label it.
- **The CX7 disappears from PCI when no cable is plugged in.** Investigated on
  `sparky` 2026-09-05. `dgx-spark-mlnx-hotplug` (26.01-1, pulled in by the
  26.02.1 metapackage) ships a udev rule for the ACPI device `MTKP0001`, driven
  by the kernel's `cx7-pcie-hotplug` platform driver, and a handler
  `/opt/nvidia/dgx-spark-mlnx-hotplug/mtk-hotplug-handler.sh`. It is opted in on
  all three nodes (`/etc/nvidia/cx7-hotplug-enabled` exists,
  `pcie_hotplug/hotplug_enabled = 1`). The driver exposes cable presence as
  `/sys/devices/platform/MTKP0001:00/pcie_hotplug/debug_state`; when it reads
  `0` the handler **hot-removes every PCI function under root ports
  `0000:00:00.0` and `0002:00:00.0`** (`echo 1 > .../remove`), and on `1` it
  rescans them. On `sparky` the journal shows all four CX7 functions enumerate
  at boot (fw `28.45.4028`), `mlx5_core` logs `Cable unplugged` on every port,
  `debug_state` is `0`, and the functions are gone; the root ports remain, link
  idling at 2.5 GT/s with no child. `sparkjr` and `sparketa` read `1`, keep
  all four functions, and show carrier on all ports — they are the cabled pair.
  Consequences for this project: on an uncabled node `lspci`, `mstflint` and
  the scorer's `check_connectx` see no device, so **CX7 firmware can be neither
  verified nor updated until a cable is present**, and the OTA checker silently
  skips that check rather than failing it. The `mlx5_core` warning `Detected
  insufficient power on the PCIe slot (27W)` appears on the working nodes too
  and is not the cause.
- **A firmware-flashing reboot on a GX10 takes ~15 minutes, not 4.** First real
  run (sparky, 2026-09-05, March → April 2026): apt 4.3 min, `fwupdmgr upgrade`
  staged three capsules in 12 s, then the reboot — with the EC, system firmware
  and USB-PD updates applied pre-boot — took about 15 minutes to answer ssh
  again. The controller's 10-minute wait gave up and reported a hold while the
  node was fine. Wait is now 30 minutes, the prior 15, and a run held at the
  restart can be finished later with "it's back, verify now".
- **On an OEM board, "July 2026 available" can be unsatisfiable.** After a
  complete update sparky scores as OTA2604 (April 2026), exactly like sparkjr:
  0 package updates, fwupd offers nothing more, but the recipe's SOCFW 2.155.11
  and EC 3.5.8 are absent because ASUS has not published them to LVFS yet
  (`fwupdmgr get-releases` is empty; dmidecode reads 2.152.15 / 3.3.2). The
  NVIDIA-built `sparketa` got them. NVIDIA's own Dashboard would keep saying
  "System Update Available" with nothing to install. So the verify gate is
  "nothing left to install and no restart pending", and the release gap is
  reported as "waiting on ASUS firmware", with the Update button disabled —
  see "Decided: partner boards" below for how that is told apart from a Spark
  that is genuinely behind.
- **`nvidia-system-station-{apps,games}` fail the recipe check on `sparky` by
  design.** They were removed deliberately. They are pulled in by
  `nvidia-system-station`, not by the OTA metapackage, so `full-upgrade` never
  brings them back; two of sparky's "behind" items are permanently this.
  Cosmetic — NVIDIA's own checker counts them the same way.
- **`sparkjr` runs NVIDIA's DGX OS image on ASUS hardware.** It was flashed
  with the NVIDIA image rather than the ASUS GX10 recovery image after
  onboarding trouble. Measured consequences (2026-09-05): `/etc/dgx-release`
  says `DGX_SWBUILD_VERSION="7.5.0"`, `DGX_PLATFORM="DGX Server for KVM"` and
  carries no `DGX_OTA_VERSION`, versus sparky's `7.2.3` / `GX10` / OTA `7.5.0`;
  the ASUS customisation packages (`asus-ascent-gx10-*`) and the
  `nvidia-oem-config-*` set are absent. Nothing an update touches differs: apt
  sources are identical, the OTA recipe set is identical, and firmware is
  matched by the board's ESRT GUIDs, so both ASUS boards sit on the same
  BIOS/EC/USB-PD versions and the same LVFS stream. `board_vendor` is still
  ASUS, so the scorer takes the same OEM path. Nothing in this project reads
  `dgx-release` for decisions; NVIDIA's own OOBE tooling might.
- **Landscape enrollment is interactive** (`pro enable landscape` prompts). For
  automation use the `landscape-config` non-interactive flags or the
  Landscape API; the guide only shows the interactive path.

## What the dashboard side left open, for cross-reference

`spark-dash`'s roadmap (Phase 4, "Report OS/firmware updates per node") holds
the idea of surfacing per-node update posture read-only, and records that it
was set down deliberately. If this project produces a per-node JSON posture
record, that entry is the natural consumer of it — the dashboard would read a
file or an endpoint, never run anything.

## Starting points

1. Read `docs/fleet-updates.md` §1, §7 and §6, in that order.
2. Open `reference/observed/` and diff `sparketa` against `sparky` — that is
   what "current" versus "behind" looks like in every data source at once.
3. Run the shipped tools against one node from this machine:
   `reference/nvidia/enterprise-lifecycle-integration-scripts/bin/spark_updatectl.py status`
   over SSH, unprivileged, and look at the envelope.
4. Decided, see above: the scorer is reimplemented off-box in
   `spark_fleet/otascore.py`, validated against all three nodes. Next open question is
   the orchestrator envelope and where run records live on disk.
