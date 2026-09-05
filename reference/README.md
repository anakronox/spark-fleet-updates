# Reference material — what each thing is and where it came from

Everything under `reference/` is **evidence**, not project code. It was
gathered on 2026-09-04 and 2026-09-05 while writing
[`docs/fleet-updates.md`](../docs/fleet-updates.md), and is kept so that the
document's claims can be checked and so the front-end can be built against
real inputs rather than remembered ones.

## `nvidia/` — NVIDIA's published material

| file | what | licence / origin |
|---|---|---|
| `enterprise-lifecycle-integration-scripts/` | The same zip, extracted, with directory permissions repaired (the zip ships `dr-x` dirs). **This is the shipped v1.1.0 code.** `bin/spark_updatectl.py` is the shipped tool; `docs/user_guides/update_control_plane.md` describes a v2.0.0 that is not in the zip — see section 6 of the main document. | as above |

Not included here, because they are NVIDIA's copyrighted documentation: the original zip and the Enterprise Manageability Guide PDF. Fetch them from [NVIDIA's docs](https://docs.nvidia.com/dgx/dgx-spark/enterprise-manageability.html) (PDF: `https://docs.nvidia.com/pdf/enterprise-manageability-guide-dgx-spark.pdf`). The extracted scripts above are redistributed under their own MIT/BSD licences, notices intact.

## `node-sparky/` — files copied from a live GB10 (`sparky`, DGX OS 7.2.3 / OTA 7.5.0)

Copied verbatim over SSH on 2026-09-05 from the node.

| path | what |
|---|---|
| `spark-ota-check/*.py` | The `nvidia-spark-ota-check` package (1.0.16-1) as installed at `/opt/nvidia/spark-ota-check/`. `check_ota_status.py` is the CLI the DGX Dashboard shells out to; `ota_checker.py` is the scorer; `self_update.py` is the apt side effect. BSD-3-Clause per their headers. |
| `spark-ota-check/metadata/spark-ota-*.json` | Every OTA recipe on the node, eleven releases from `spark-ota-0.json` to `spark-ota-2607.json` ("July 2026"). **These are the target-of-record for "is this node current".** |
| `dgx-dashboard/dgx-dashboard.service`, `dgx-dashboard-admin.service` | The two systemd units. Bodies are below the licence banner. |
| `dgx-dashboard/com.nvidia.dgx.dashboard.admin1.conf` | The D-Bus policy. Note the `context="default"` block: any local user may call `GetOTAAvailabilitySnapshot` and nothing else. |
| `dgx-dashboard/dgx-dashboard-reboot.sh` | What runs after `UpdateAndReboot`: log, `sleep 10`, `systemctl reboot`. |
| `dgx-dashboard/dgx-dashboard` | `/usr/bin/dgx-dashboard`, the browser-launcher wrapper. |
| `dgx-dashboard/binary-strings-of-interest.txt` | Selected `strings` output from the two Go binaries: D-Bus method names, HTTP routes, and the literals that show how updates are driven (`org.debian.apt.transaction.Run`, `Auto-upgrading OTA metapackage`, `Firmware phase polling timed out after 25 minutes`, `host must be localhost`). The binaries themselves are not copied. |
| `apt/sources.list.d/`, `apt/preferences.d/` | The repositories and pins NVIDIA configures. The pins are why a fleet tool must run plain `apt full-upgrade` and not construct its own resolver calls. |
| `apt/dgx-spark-ota-update-meta.apt-cache-show.txt` | Every version of the OTA metapackage in the apt cache with its `Depends:`, which is how each release pulls in new components. |
| `etc/dgx-release` | Image build, OTA stamp, platform. The device serial is redacted. |
| `etc/nvidia-spark-run-apt-upgrade-once.sh`, `.service` | NVIDIA's own one-shot post-upgrade apt run; a competitor for the dpkg lock on first boot after certain upgrades. |

## `observed/` — live outputs from all three nodes

Captured at the time in `CAPTURED-AT.txt`. One directory per node
(`sparky`, `sparketa`, `sparkjr`).

| file | command |
|---|---|
| `dbus-GetOTAAvailabilitySnapshot.txt` | `busctl call com.nvidia.dgx.dashboard.admin1 /com/nvidia/dgx/dashboard/admin com.nvidia.dgx.dashboard.admin1 GetOTAAvailabilitySnapshot` — **unprivileged** |
| `ota-is-ota-available.json` | `sudo python3 /opt/nvidia/spark-ota-check/check_ota_status.py is-ota-available` |
| `ota-installed-name.json`, `ota-torn-score.json`, `ota-summary.json` | the other checker subcommands, as root |
| `apt-check-and-updates-available.txt` | `/usr/lib/update-notifier/apt-check` (`total;security`), the `updates-available` text file, its mtime, and the reboot-required flag |
| `fwupdmgr-get-devices.json` | `fwupdmgr get-devices --json` — the firmware inventory the OTA scorer matches GUIDs against |
| `dgx-release.txt` | `/etc/dgx-release` |

The interesting comparison is `sparketa` (current, snapshot ends `true false ""`)
against `sparky` and `sparkjr` (behind, `true true "July 2026"`): that pair is
what pins the meaning of the D-Bus booleans.

## `collector-inputs/` — the inputs the off-box scorer consumes

Captured by `tools/collect_facts.sh --oracle` at the time in its own
`CAPTURED-AT.txt`, one directory per node. Where `observed/` is a snapshot of
NVIDIA's *outputs*, this is the set of *inputs* `spark_fleet/otascore.py` scores
off-box, kept so the port can be re-validated without touching a node.

| file | command | privilege |
|---|---|---|
| `dpkg-query.txt` | `dpkg-query -W -f '${Package},${Version}\n'` | none |
| `uname-r.txt`, `driver.txt` | `uname -r`; the `Driver Version` line of `nvidia-smi -q` | none |
| `fwupd-devices.json` | `fwupdmgr get-devices --json` | none |
| `board_vendor.txt` | `/sys/class/dmi/id/board_vendor` — selects NVIDIA's firmware path | none |
| `dmidecode-45.txt` | `dmidecode -t 45` | **root** |
| `lspci-mlnx.txt`, `mstflint.txt` | the ConnectX-7 firmware version | **root** |
| `dbus-snapshot.txt`, `recipes-present.txt` | the unprivileged OTA snapshot; the recipe set on the node | none |
| `oracle-*.json` | `check_ota_status.py summary` / `installed-name` / `torn-score`, as root — the ground truth the port is checked against | **root** |

`is-ota-available` is deliberately not captured here: it is the one subcommand
with an apt side effect. Run
`python3 tools/validate_against_nodes.py reference/collector-inputs reference/node-sparky/spark-ota-check/metadata`
to re-check the port against these.

## Not copied, on purpose

- The Go binaries (`dashboard-service`, `dashboard-admin`) — 32 MB and
  proprietary; the strings that matter are in `binary-strings-of-interest.txt`.
- Anything from the `spark-dash` dashboard repo — that project stays focused
  on monitoring; this one owns updates.
