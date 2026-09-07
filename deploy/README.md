# Deploying spark-fleet-updates

One container on a machine that is **not one of your Sparks** — it reboots
them. About 15 minutes end to end, most of it waiting for the first check.

```
 your laptop / a VM / a NAS               each Spark
 ┌──────────────────────────┐   ssh      ┌────────────────────┐
 │ docker: spark-fleet-     │──────────▶ │ nothing installed  │
 │ updates  · port 8080     │  (key +    │ (one ssh key,      │
 │ ./data   ./ssh           │   sudo)    │  passwordless sudo)│
 └──────────────────────────┘            └────────────────────┘
```

## Before you start

You need:

- [ ] A Linux host with **Docker** and **Docker Compose v2** (`docker compose version`), on the same network as the Sparks. Not a Spark.
- [ ] Each Spark's **IP address** (hostnames often don't resolve from inside a container).
- [ ] A **login on each Spark** that can `sudo`. The account you set the Spark up with is fine; you'll type its password when you press Update.
- [ ] A free **port** on the host (default 8080; check with `ss -ltn | grep :8080`).

## Step 1 — get the code and make a key

On the Docker host:

```bash
git clone https://github.com/anakronox/spark-fleet-updates.git
cd spark-fleet-updates
cp .env.example .env
mkdir -p ssh data
ssh-keygen -t ed25519 -N "" -C spark-fleet-updates -f ssh/id_ed25519
```

Edit `.env` and set `SPARK_FLEET_SSH_USER` to the login on your Sparks. Change
`SPARK_FLEET_PORT` if 8080 is taken. That's the only editing there is.

## Step 2 — let the controller into each Spark

This follows the same model as NVIDIA's own DGX Dashboard: the hourly checks
need nothing special, and when you press **Update** you type your password,
which is used for that one update and never stored.

**2a. Trust the key** — from the Docker host, for every Spark (you'll be asked
for that Spark's password once):

```bash
ssh-copy-id -i ssh/id_ed25519.pub user@192.0.2.11
```

**2b. Two read-only commands without a password** — the release check reads
firmware versions with `dmidecode` and `mstflint`, which need root. Log in to
the Spark and allow exactly those two:

```bash
printf '%s ALL=(root) NOPASSWD: /usr/sbin/dmidecode -t 45, /usr/bin/mstflint -d * q\n' "$USER" \
  | sudo tee /etc/sudoers.d/spark-fleet >/dev/null \
  && sudo chmod 440 /etc/sudoers.d/spark-fleet && sudo visudo -cf /etc/sudoers.d/spark-fleet
```

Expected: `/etc/sudoers.d/spark-fleet: parsed OK`. Everything else — the
install itself, the restart — asks for your password in the dashboard at the
time.

<details>
<summary>Unattended alternative: passwordless sudo for everything</summary>

If you'd rather never type a password — a lab on a network you trust — grant
the user full passwordless sudo instead:

```bash
echo "$USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/spark-fleet >/dev/null \
  && sudo chmod 440 /etc/sudoers.d/spark-fleet && sudo visudo -cf /etc/sudoers.d/spark-fleet
```

The dashboard notices and stops asking. Understand what it means: the key in
`./ssh` is then root on every Spark.
</details>

**2c. Prove it** — from the Docker host:

```bash
ssh -i ssh/id_ed25519 user@192.0.2.11 'sudo -n dmidecode -t 45 | head -1'
```

Expected: `# dmidecode 3.x`. If it asks for a password, step 2b did not take.

## Step 3 — start it

```bash
sudo chown -R 1000:1000 ssh data     # the container runs as uid 1000 and must read the key and write data/
docker compose up -d --build
```

Expected, after ~1 minute: `docker compose ps` shows `spark-fleet-updates …
Up … (healthy)`.

Open **https://\<docker-host\>:8080**. It's HTTPS from the start — that is
what keeps the password you type for an update off the wire — and you have to
pick one of three ways to trust it:

1. **Accept the self-signed certificate** it made on first run. Your browser
   warns once; accept, and it stays trusted. Simplest, and fine on a LAN.
2. **Give it your own certificate** (from your LAN CA or Let's Encrypt), so
   there is no warning at all.
3. **Put it behind your reverse proxy.** Read "HTTPS" below first — where the
   proxy runs decides whether the hop to the controller is encrypted.

There is no fourth option: over plain HTTP the controller refuses to accept a
password.

## Step 4 — add your Sparks

Click **+ add a spark**, enter the IP, click **test connection** — you should
see `✓ reachable · <board vendor>` — then **add**. The first check runs
immediately and takes about 10 seconds per Spark. Repeat for each one.

You'll see, per Spark: **up to date with NVIDIA**, **update available**, or
**waiting on ASUS firmware** (naming whoever built the board), with the number
of package updates. The last one means the Spark has everything its vendor has
published and NVIDIA's newer firmware has not reached that vendor's bundle yet —
nothing to install, and not your doing. Open **show updates ▾** to see the
software, the vendor's bundle and NVIDIA's baseline as three lines. Sparks that
are cabled together over their 200 GbE ports appear grouped automatically.

That's the deployment. Everything from here is use.

## Using it

- **show updates ▾** — what an update would install: the NVIDIA release and its
  notes, firmware devices now → after, and the packages (see all → a paged
  list with a filter).
- **update** — confirms (and asks for your password on the Spark, unless it
  has passwordless sudo), then installs, restarts the Spark and verifies.
  Expect 15–35 minutes; a restart that flashes firmware takes ~15 minutes on
  its own. Sparks in a group are updated together, one after the other.
  Nothing ever updates without you pressing this.
- **⋯ → Rehearse an update** — runs every step except the install and the
  restart, to prove the plumbing works. Changes nothing.
- **⋯ → Check now / Rename / Remove.**
- **⚙** — theme.

## If something goes wrong

| you see | it means | do |
|---|---|---|
| `unreachable` on a row | ssh from the container failed | `docker compose exec spark-fleet-updates ssh -i /ssh/id_ed25519 <user>@<ip> true` and read the error |
| `Host key verification failed` | the container's known_hosts is empty and strict | should not happen (it accepts new hosts); if it does, `docker compose restart` |
| `Permission denied (publickey)` | key not on that Spark | redo step 2a |
| Update holds at "check": *the password was not accepted* | wrong password for that user on that Spark | try again; it's the Spark's login password, not the dashboard host's |
| the dialog says *the controller will refuse the password* | you opened the page over plain HTTP | use `https://`, or see "HTTPS" below |
| `can't check firmware` on a row | the two read-only sudo rules are missing | step 2b — the release verdict is withheld until firmware can be read |
| a Spark added by name never becomes reachable | name doesn't resolve inside Docker | remove it, add it by IP |
| the container exits at start | `.env` missing or `SPARK_FLEET_SSH_USER` unset | `docker compose logs`; fix `.env` |
| "the Spark has not come back within 30 minutes" after an update | slow restart, or it really is down | when it answers ssh again, the row offers **it's back — verify now** |

The log for any update is one click away on its row; the same records are
under `data/runs/<run-id>/` as plain files (`state.json`, per-step envelopes,
verbatim output).

## HTTPS

The password you type for an update travels from your browser to the
controller, then inside SSH to the Spark. SSH was always encrypted; HTTPS
closes the browser-to-controller half. Pick whichever of these fits.

**Self-signed (the default).** On first start the controller makes a
certificate at `data/tls/cert.pem` + `key.pem`, valid ten years, and reuses
it. The encryption is real; what's missing is a public authority vouching for
it, so your browser asks once. Accept it and you're done.

**Your own certificate.** Put the files where the container can read them
and set `SPARK_FLEET_TLS_CERT` and `SPARK_FLEET_TLS_KEY` in `.env`. No
warning.

**A reverse proxy — where it runs matters.**

- *Proxy on the same host as the controller* (a Caddy/Traefik/nginx container
  on the same Docker host): set `SPARK_FLEET_TLS=off`. The proxy does TLS to
  the world and talks plain HTTP to the container over the Docker network,
  which never leaves the machine. The proxy must send
  `X-Forwarded-Proto: https` (all of those do by default); the controller
  accepts a password on plain HTTP only when that header is present.
- *Proxy on a different machine*: **leave `SPARK_FLEET_TLS` at `auto`**, so
  the proxy's connection to the controller is HTTPS too — otherwise that hop
  crosses your LAN in the clear, and the controller would accept the password
  anyway on the strength of the header. Point the proxy at
  `https://<docker-host>:8080` and tell it to trust the self-signed
  certificate (Caddy: `reverse_proxy https://host:8080 { transport http {
  tls_insecure_skip_verify } }`; nginx: `proxy_pass https://…;
  proxy_ssl_verify off;`), or give the controller a certificate the proxy
  already trusts.

One caution that follows from all this: the controller believes
`X-Forwarded-Proto`. Anything that can reach port 8080 directly and set that
header could hand it a password over plain HTTP. Keep the port reachable only
from the proxy when you run one, or leave HTTPS on regardless.

**Plain HTTP, no proxy.** Everything works except typing a password — that is
refused, deliberately. `SPARK_FLEET_ALLOW_PLAIN_PASSWORD=1` overrides it if
you truly want to, on a network you truly trust.

## Upgrading the controller

```bash
cd spark-fleet-updates && git pull && docker compose up -d --build
```

Your Sparks, settings and history are in `./data` and `./ssh`, untouched.

## Backing up

`./data` is everything: the Spark list, what each one looked like at every
check, every update's record. `./ssh` is the key. Copy both.

## Undoing it

- Remove a Spark from the list: its **⋯ → Remove**.
- Take the controller off a Spark entirely: delete the `spark-fleet-updates`
  line from `~/.ssh/authorized_keys` and `sudo rm /etc/sudoers.d/spark-fleet`.
- Give the Spark's own Dashboard its automatic updates back:
  `sudo rm /opt/nvidia/dgx-dashboard/settings.json` (the controller wrote
  `{"update": {"enabled": false}}` there the first time you pressed Update;
  it is the only persistent change it makes to a Spark).
- Stop everything: `docker compose down`. Add `-v` for nothing; state is in
  `./data`, delete that directory if you want it gone.

## What it does and doesn't touch

- **Outbound**: ssh to each Spark as your user. Reads are unprivileged apart
  from `sudo -n dmidecode -t 45` and `sudo -n mstflint … q`. Only **Update**
  runs anything else, and only with the password you type (or passwordless
  sudo, if you chose that).
- **Inbound**: the dashboard port over HTTPS, **no login of its own**. The
  read-only view is safe for anyone on your LAN; the Update button is not —
  though without your Spark password it can do nothing, unless you granted
  passwordless sudo. Front it with whatever already guards your other services
  if that matters.
- **On the Spark**: nothing installed. An update stages a script in `/tmp` and
  a transient systemd unit; both are gone after the restart.

## Without Docker

`python3 -m spark_fleet` from a checkout (Python 3.11+, standard library
only, plus an `ssh` client). State lands in `./state/`. Set
`SPARK_FLEET_SSH_USER`, and `SPARK_FLEET_SSH_KEY` if the key isn't your
default one.
