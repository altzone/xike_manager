# Upgrade Guide

This page is for people who already run SwitchPilot and want to move to the latest version
without losing anything or being surprised by what changed.

**The short version:** your data lives in `./data/` (one SQLite file) and is kept across updates.
Database changes are applied automatically the first time the new version starts, after a copy of
the database to `data/backups/` (from 2.3.0). Nothing is written to your switches by an update.

1. [Before you start](#1-before-you-start): see which version you run.
2. [Update](#2-update): Linux/macOS/Raspberry Pi, Windows, ZIP or Synology.
3. [What to check](#3-what-to-check-by-the-version-you-come-from), by the version you come from.
4. [Rolling back](#4-rolling-back) and [troubleshooting](#5-troubleshooting).

New to SwitchPilot? Follow the [installation guide](installation.md) instead.

## 1. Before you start

- **See which version you run.** From 2.2.1 it is shown at the bottom of the side menu. From the
  command line, with any version (the container must be running):

  ```bash
  docker exec switchpilot grep -rhoE "VERSION = .[0-9.]+.|version=.[0-9.]+." /app/backend --include=main.py --include=version.py
  ```

- **Note where you are**, in case you want to go back: `git log -1 --oneline` in the
  `xike_manager` folder prints the commit you run. Keep that line (see section 4).
- An update restarts SwitchPilot for a minute. From 2.3.0 a change still being sent to a switch is
  finished first; with an older version, wait until nobody is applying VLANs or port settings.

## 2. Update

### Linux, macOS, Raspberry Pi

```bash
cd xike_manager
docker compose down                                   # stop (releases the database file)
cp -r data/ data-backup-$(date +%Y%m%d)/              # your own backup, takes a second
git pull                                              # fetch the new version
docker compose build --no-cache                       # rebuild the image (frontend + backend)
docker compose up -d                                  # start
docker compose logs -f --tail=50                      # watch the first start, Ctrl+C to leave
```

### Windows (PowerShell)

```powershell
cd xike_manager
docker compose down
Copy-Item -Recurse data "data-backup-$(Get-Date -Format yyyyMMdd)"
git pull
docker compose build --no-cache
docker compose up -d
docker compose logs -f --tail=50
```

### Installed from a ZIP (no git), or on a Synology NAS

1. Stop SwitchPilot (`docker compose down`, or **Container Manager → Project → Stop**).
2. Download the new ZIP from GitHub and extract it into a **new** folder.
3. Copy your old `data/` folder into the new one. If you changed the port or other settings in
   the old `docker-compose.yml`, make the same change in the new one.
4. Start from the new folder: `docker compose up -d --build`, or on Synology create the project
   again on that folder (see [installation](installation.md#synology-nas)) and build it.
5. Once everything works, delete the old folder.

### After the update

A healthy start ends with `Application startup complete.` and `Uvicorn running on
http://127.0.0.1:8000`. From 2.3.0 it may start with `Database copied to /app/data/backups/…`:
SwitchPilot keeps a copy of the database before changing it (5 copies kept).

Open SwitchPilot and check that the side menu shows the new version. It comes from the server: the
page asks when it is loaded, when you come back to it (other tab or window) and when you open
another section, at most once a minute. A page left open during the update offers a **Reload**
button next to the version.

Updating to 2.2.1 or an older version, refresh the page once without the cache (**Ctrl+Shift+R**,
**Cmd+Shift+R** on macOS) so the browser drops the old page; later updates are picked up by the
browser on its own. Coming from the first release you are also asked to log in again once (see
section 3); after that, sessions survive updates as long as `data/secret_key` (or your own
`SECRET_KEY`) is kept.

> **You edited `docker-compose.yml` (port, secret, volume path)?** `git pull` keeps your edits
> unless the same lines changed upstream. If it refuses to pull, run `git stash`, then `git pull`,
> then `git stash pop` and resolve the conflict in that one file.

> **Demo branch:** `git checkout demo && git pull`, then the same build/up commands.

## 3. What to check, by the version you come from

Every row that matches the version you ran applies to you; an older version matches several rows.

| You ran | Once after the update | Details |
|---|---|---|
| 2.3.0 or older, with a 2.0.0.x switch | LAG and storm control are now read-only on it. If you changed a LAG on it with SwitchPilot, check it on the switch's own Link Aggregation page. | [CHANGELOG 2.3.1](../CHANGELOG.md) |
| 2.2.1 or older | Nothing to do. From now on the database is copied to `data/backups/` before an update changes it, and a stop lets a change being sent to a switch finish. | [2.3.0](#230-safer-updates) |
| 2.2.0 or older | Refresh the page once without the cache (Ctrl+Shift+R). | [After the update](#after-the-update) |
| 2.1.x or older, with a 2.0.0.x switch | Its settings can now be changed from SwitchPilot. If you changed IGMP, loop detection or STP on it with an earlier version, check them once. | [2.2.0](#220-200x-switches-settings-can-be-changed) |
| 2.1.0 or older | Check each switch's SFP+ port numbering under **System**. | [2.1.0 / 2.1.1](#210--211-sfp-ports-9-and-10-numbered-per-switch-issue-3) |
| 1.0.0 (the first release) | Log in again; behind a reverse proxy set `TRUSTED_PROXIES`; apply your VLANs once and check tagged traffic. | [2.1.0 sections below](#210-the-interface-looks-different) |

### 2.3.0: safer updates

- **Automatic copy of the database.** When a new version starts for the first time, it copies
  `data/switchpilot.db` to `data/backups/switchpilot-<previous>-to-<new>-<date>.db` before
  changing anything (5 copies kept; your own `data-backup-…` copy from step 2 is still a good idea).
  The first update to 2.3.0 names the copy `switchpilot-earlier-to-2.3.0-…`. If the copy cannot
  be written (disk full, permissions), the start stops with a message in `docker compose logs` and
  the database is left as it was.
- **A clean stop.** `docker compose down` and updates now wait for a change being sent to a
  switch to finish and to be answered (about two minutes at most; the container gets 150 seconds,
  `stop_grace_period` in `docker-compose.yml`); a normal stop takes a second or two. With `docker run` or another tool, give it the same time (for example
  `docker stop -t 150 switchpilot`).
- **Watchtower** no longer updates SwitchPilot on its own: the image and `docker-compose.yml` carry
  the label `com.centurylinklabs.watchtower.enable=false`.
- **2.0.0.3 switches** do the check with the temporary VLAN 4094 once, not after every restart.
- **Published images.** From 2.3.0 each version is also available as
  `ghcr.io/altzone/switchpilot:<version>`. Nothing changes for you yet: `docker-compose.yml` keeps
  building the image, and the next version explains the switch to the published one.

### 2.2.0: 2.0.0.x switches, settings can be changed

On switches running **2.0.0.x** firmware, SwitchPilot can now change VLANs, link aggregation,
STP, loop detection, storm control, IGMP snooping, port mirroring and the MAC table, using the
requests the switch's own web pages send. Only port settings have been confirmed on a real switch
so far (a 2.0.0.3 unit); the rest was checked against the firmware's code and a simulated switch,
so please report anything that does not behave as expected.

After each change SwitchPilot reads the setting back from the switch and saves it on the switch
only if it matches. The exceptions are port settings, the management address and clearing the MAC
table. If the switch does not apply a change, SwitchPilot puts the previous setting back, checks
it, and reports an error; nothing is saved.

EEE and the clock (time/SNTP) stay read-only, because that firmware's own web interface no longer
offers them. From 2.3.1, link aggregation and storm control are read-only on 2.0.0.x too, until
they are confirmed on a real switch (see the change log).

Things that work differently on 2.0.0.x, as on the switch's own pages:
- VLANs live in one table of up to 100 VLANs, with their names stored on the switch (16
  characters), and any VLAN ID can be an access or native VLAN.
- Loop detection is one setting for the whole switch, and it is an alternative to STP: turning
  one on turns the other off.
- Storm control is set in Mbps, per kind of traffic.
- IGMP has report flooding instead of a querier.
- Static MAC entries are keyed by VLAN ID.

The first VLAN change SwitchPilot makes on a **2.0.0.3** switch creates a VLAN named
"SwitchPilot test" (VLAN 4094, or the highest free ID) for a moment and deletes it right away. That firmware reads its VLAN table back
in a different layout from earlier 2.0.0.x builds, and this one-time check confirms how it stores
VLAN members before any real VLAN is written.

**If you changed settings on a 2.0.0.x switch with an earlier version, check them once.**
Earlier versions sent 1.0.0.x requests that this firmware misread:
- **IGMP snooping:** any IGMP change turned **Fast Leave** and **report flooding** off.
- **Loop detection:** any change there turned loop detection off.
- **STP:** any STP change cleared the edge ports and reset the mode to RSTP.
- **VLANs created in SwitchPilot** were never created on the switch. They are created there
  (with their names) as soon as a port is assigned to them, or when you add them again.

Open **System** and **VLANs** on each 2.0.0.x switch and set these as you want them.

### 2.1.0 / 2.1.1: SFP+ ports 9 and 10 numbered per switch (issue #3)

Earlier versions assumed that on every SKS3200 the firmware's index 9 was the SFP+ cage labelled
10 on the front panel, and swapped the two. As far as we know this follows the firmware line:
**1.0.0.x firmware swaps the two SFP+ cages, 2.0.0.x firmware does not** (confirmed on an
SKS3200-8E2X 1.0.0.4 and an SKS3200-8E2X-P 2.0.0.x, both hardware A0). The switch's API does not
say it, so it is a setting on each switch, chosen from the firmware version.

- **On the first start of 2.1.1, each existing switch gets the numbering of its firmware line,
  once** (whether you come from the first release or from 2.1.0):
  - switches recorded with **1.0.0.x** are swapped. Coming from the first release nothing
    changes for them; a 1.0.0.x switch added under 2.1.0 (which started every new switch
    unswapped) is corrected;
  - switches recorded with **2.0.0.x** are not swapped, which fixes ports 9 and 10 being shown
    (and configured) the wrong way round on them (issue #3);
  - switches whose firmware version is unknown keep their setting.

  When a switch is changed, its port 9 and 10 descriptions move with the cages and the change
  appears in its change log (System and Overview) as made by "SwitchPilot". VLAN, LAG and other
  settings on the switch itself are not touched: only SwitchPilot's labels change. If you had
  deliberately set a switch against its firmware line under 2.1.0, set it again under System.
- **Switches you add from now on get the numbering of their firmware line automatically**
  (Add Switch → "SFP+ ports 9 and 10": Automatic; an unreadable version gives the firmware's own
  numbering); you can force either choice there.
- **The System page shows a warning** when a switch's setting does not match what its firmware
  usually needs (a choice forced when adding it, or a unit that differs): check and flip it.
- **Check each switch once:** plug a cable into the cage labelled **9** on the front panel and open
  the Ports page. The link must appear on port **9**. If it appears on port 10, go to
  **System → SFP+ Port Numbering** and flip the toggle. Leave "Move port descriptions with their
  physical port" ticked so the descriptions follow the cages. This only changes labels in
  SwitchPilot; the switch itself is not touched.
- On the Ports page, hovering a port number shows the switch's internal index when the two differ.

### 2.1.0: the interface looks different

The web UI was rebuilt: the navigation moved to a sidebar with a switch picker, the pages have
a dark mode (top bar, next to the language), and confirmations are in-app dialogs. Everything
you could do before is still there, in the same places, with two moves: **static MAC entries**
now live on the **MAC Table** page, and the **System** page shows the **change log**. If a page
looks broken right after the upgrade, do a hard refresh (Ctrl+Shift+R) once.

### 2.1.0: you are asked to log in again (once)

Earlier versions signed login sessions with a key that was part of the repository. The new
version generates its own key on first start and keeps it in `data/secret_key`, so every
existing session stops being valid: log in again, that is all. If you had set your own
`SECRET_KEY` in `docker-compose.yml`, it is still honoured. The example line was removed from
the file; you do not need one.

### 2.1.0: VLAN page safer, one change to verify on your switch

- Applying VLANs used to rebuild the tagged-VLAN table from scratch, which dropped the tagged
  VLANs of the management port (port 1) and of any port not shown in the request, and saved
  that to flash. Apply now reads the current configuration first and only changes the ports
  you touched. If your uplink had lost its tagged VLANs after an Apply in the past, this was
  why.
- Tagged VLANs are now written to their own bridge (VLAN 10 → bridge 10) instead of bridge 0,
  so tagged traffic reaches that VLAN's access ports. This matches what the other open-source
  tools for this switch do, but it could not be tested on hardware before release. The whole
  tagged table is normalised on each Apply, so entries written by earlier versions (bridge 0)
  move to their VLAN's bridge too, and a VLAN above 63 (the hardware has 64 bridges; such a
  VLAN can only be tagged) gets a free bridge of its own, kept from one Apply to the next.
  **After upgrading, take a snapshot (System → Configuration Snapshots), apply your VLAN
  configuration once from the VLAN page, and check that a tagged VLAN still reaches its access
  ports and the trunk.** If anything behaves differently from before, open an issue with the
  snapshot; the previous behaviour can be restored by rolling back (section 4).
- Port 1 is kept out of VLAN edits by the UI as before; the API now also preserves it.

### 2.1.0: behind a reverse proxy, set `TRUSTED_PROXIES`

Login attempts are now throttled: ten wrong passwords for one account from one client address
block that account for ten minutes (for that address). If a reverse proxy sits in front of the
container, every browser arrives from the proxy's address, so add the proxy's address to
`docker-compose.yml` (`- TRUSTED_PROXIES=172.17.0.1`) and make the proxy send
`X-Forwarded-For` (nginx: `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`;
Caddy and Traefik do it by default). The container also sends `X-Frame-Options: DENY` now, so
SwitchPilot no longer loads inside another dashboard's iframe; link to it instead.

### 2.1.0: changing a password logs that user out

Resetting someone's password (Users page) ends their current sessions, including your own if you
change your own password. Log in again with the new one.

### 2.1.0: management port protection

Disabling port 1 from the Ports page asks for confirmation. Scripts must send
`"force": true` to do it.

### 2.1.0: port mirroring works from the UI

Applying a mirror session from the System page used to fail silently (the backend answered
HTTP 422 and nothing reached the switch). If you believed a mirror was configured, open
**System → Port Mirroring** and apply it again. The "Apply Mirror" button is now also available
with the destination set to *Disabled*, which turns mirroring off.

### 2.1.0: static MAC entries are listed

The static MAC table on the System page was always empty. It now lists the entries with their
port numbers.

### 2.1.0: safer handling of wrong input

A port number outside 1-10 is refused with a clear 400 error. Earlier versions either crashed
(HTTP 500) or, for static MAC entries, silently used **port 1** (the management port).

### 2.1.0: snapshots

New snapshots carry a `meta` block (`port_numbering: "user"`, `swap_sfp_9_10`) and use the
user-facing port numbers everywhere. Snapshots taken before this version are still readable; in
those, the `lag`, `mirror` and `loop` sections used the switch's internal indexes.

### For scripts that call the API directly

- Switch problems return `502` with a `detail` message (they used to be `500`). Input
  problems return `400`/`422`; a duplicate VLAN or username returns `409`.
- The SSE stream `GET /api/switches/{id}/sse?token=` needs a token from
  `POST /api/auth/stream-token` (valid 5 minutes); the session token is refused there.
- `POST /api/switches/{id}/vlans/apply` only needs the ports you change; others are kept.
  `GET /api/switches/{id}/vlans` entries carry `in_use` and `defined` and nothing is written.
- `POST /api/switches/{id}/ports/config` refuses `enabled: false` on port 1 without
  `force: true`; `speed` must be one of the values the UI offers.
- `POST /api/switches` takes `swap_sfp_9_10` as `true`, `false` or omitted/`null` (= chosen from the
  switch's firmware line; unreadable version = not swapped) and returns `swap_sfp_9_10` and `swap_auto`. `GET /api/switches/{id}/status`
  adds `swap_sfp_suggested` (`true` for 1.0.0.x, `false` for 2.0.0.x, `null` if unknown).
- `POST /api/switches/{id}/network` validates the addresses and returns the new `ip`, `accepted`
  and `note`. SwitchPilot's stored address only follows the change when the switch accepted it
  and SwitchPilot was talking to the switch's own address (not a hostname or a NAT address);
  a refusal by the switch is a `502` and nothing is changed.
- `POST /api/switches/{id}/vlans/apply` also accepts `"mode": "unknown"` (what
  `GET /vlans/assignments` reports for a port enabled with neither untag nor tag): the port is
  left as it is. `access_vlan` may be `0`. Tagged entries get their VLAN's bridge (see above).
- `POST /api/switches/{id}/mac/static/add` and `/delete` return `warnings` when the flash save
  timed out (the entry is applied regardless). `/delete` now takes the same validated body as
  `/add` (`{"mac", "port", "fid"}`, user-facing port) and builds the firmware payload itself.
- New: `PUT /api/switches/{id}/vlans/{vid}` with `{"name"}` renames a defined VLAN in place.
- `POST /api/switches/{id}/time` and `/sntp` validate their fields (`timezone` as `+HH:MM`).
- New: `GET /api/switches/{id}/changes` (audit log), `PUT /api/switches/{id}/lag/names`.
- New: `PUT /api/switches/{id}` (edit name, IP, credentials) and
  `PUT /api/switches/{id}/port-mapping` (`{"swap_sfp_9_10": true|false, "move_descriptions": true}`).
  `GET /api/switches` and `/info` now include `swap_sfp_9_10`; `POST /api/switches` accepts it.
- `POST /api/switches/{id}/mirror` takes `{"monitoring_port", "mirrored_ports", "ingress", "egress"}`
  (the format the UI always sent). The old `{"monitoring_port", "ports": {...}}` body is gone.
- `POST /api/switches/{id}/lag` is validated: `{"system_priority", "ports": [{"port","type","timeout","group"}], "group_names"}`.
- `GET /api/switches/{id}/mac/static` returns a list `[{"mac","port","fid",...}]` instead of the raw payload.
- `DELETE /api/switches/{id}` also removes that switch's local data (descriptions, LAG names,
  VLAN names, snapshots).
- Python: `switch_client.PORT_MAP` no longer exists. Create a `SwitchClient(ip, user, password,
  swap_sfp=...)` and use `to_internal()` / `to_user()`.
- 2.2.0, switches on 2.0.0.x firmware (1.0.0.x switches answer as before):
  - `GET /loop` returns `{"model": "global", "enabled", "prevention", "interval", "recovery",
    "ports": [{"port", "violation"}]}`.
  - `POST /loop` takes `{"enabled"?, "prevention"?, "interval"?, "recovery"?}` and answers
    `stp_turned_off`.
  - `GET /storm` returns `{"model": "per_port", "enabled", "rate", "types", "uniform", "ports"}`.
  - `POST /storm` takes `types` (default `["broadcast"]`), and its `rate` is in Mbps (1-1000).
  - `POST /igmp` takes `report_flood`; `querier` does not exist there.
  - `POST /stp` answers `loop_turned_off`.
  - Static MAC add/delete take `vlan_id` instead of `fid`. A delete needs no port (the entry's VLAN
    is looked up when it has only one), and an entry that does not exist is a `404`.
  - `GET /mac/dynamic` carries `truncated` when not all of the table could be read.
  - `GET /vlans/limits` returns `max_vlans`/`used_vlans`, and the `POST /vlans/apply` answer has
    `vlans`/`created` instead of `tag_entries`.
  - LAG groups go up to 31.
  - A write the switch answered but did not apply is a `502` ("did not apply", nothing saved).
    `warnings` lists a save that did not complete.
- 2.2.0, every switch:
  - MAC entries carry `vlan` (`null` on 1.0.0.x).
  - `GET /vlans` entries carry `deletable`; on 2.0.0.x also `on_switch`.
  - `GET /switches`, `/info` and `/status` carry `firmware_line` and `read_only`.
  - A write a firmware cannot take answers `501` and nothing is sent.

See [CHANGELOG.md](../CHANGELOG.md) for the complete list.

## 4. Rolling back

If something does not work for you, going back is two commands and your backup:

```bash
docker compose down
git checkout <the commit you noted in section 1>          # e.g. git checkout 7ff0af8
docker compose build --no-cache && docker compose up -d
```

The previous version ignores the new database columns, so restoring the backup is optional. To be
on the safe side anyway: `rm -rf data && cp -r data-backup-YYYYMMDD data` before `up -d`. From
2.3.0 the copy made automatically before the update is in `data/backups/`: with the container
stopped, `cp data/backups/switchpilot-<previous>-to-<new>-<date>.db data/switchpilot.db`.
Switches you add *while* rolled back are shown with the 9/10 swap on by that version; after
upgrading again they appear with the swap off (the column already exists, so the one-time
migration does not run twice): flip them under **System → SFP+ Port Numbering** if needed.
Please open an issue with the `docker compose logs` output so it can be fixed.

## 5. Troubleshooting

| Symptom | What to do |
|---|---|
| `no such column: swap_sfp_9_10` in the logs | The startup migration did not run. Check the first lines of `docker compose logs` for an error before `Application startup complete`, make sure `./data` is writable by the container, then `docker compose restart`. |
| Ports page still looks like the old version | Hard refresh the browser (Ctrl+Shift+R). From 2.2.1, click **Reload** at the bottom of the side menu if it is shown. |
| The side menu still shows the old version number | Reload the page (F5) first. If the number does not change, the new container is not running: check `docker compose ps` and that `docker compose build` ended without error, then `docker compose up -d` again. |
| `database is locked` at startup | Another SwitchPilot container is using the same `data/` folder. Stop it first. |
| `must update the database and could not copy it first` in the logs | 2.3.0 and later copy the database to `data/backups/` before changing it. Free some disk space, or make `data/` writable by the container, then `docker compose restart`. Nothing was changed. |
| `docker compose down` takes a while | A change was still being sent to a switch (often a slow or unreachable one): SwitchPilot finishes it, or puts the previous settings back, before stopping. It waits about two minutes at most; Docker stops the container after 150 seconds. |
| `docker compose build` fails | A download error (npm, pip, apt): check the machine's internet access and run it again. With Docker older than 20.10, update Docker first. Otherwise open an issue with the full output. Until then `docker compose up -d` starts the version you had. |
| Ports 9 and 10 look inverted after the upgrade | Switches were set to the numbering of their firmware line (1.0.0.x swapped, 2.0.0.x not; see the change log). Check the cage labelled 9 as described above and flip the setting under System if your unit differs. |
| Logged out right after the upgrade | Expected once: the session key changed. Log in again. |
| `Too many failed logins` | 10 wrong passwords for that account within 10 minutes from the same client address (or 100 across accounts). Wait a few minutes; behind a reverse proxy set `TRUSTED_PROXIES` (section 3). |
| Live stats stay on "Connecting" | Hard refresh the browser: the old frontend uses the old stream URL. |
