# Upgrade Guide

This page is for people who already run SwitchPilot and want to move to the latest version
without losing anything or being surprised by what changed.

**The short version:** your data lives in `./data/` (one SQLite file) and is kept across upgrades.
Database changes are applied automatically the first time the new version starts. Nothing is
written to your switches by an upgrade.

## 1. Before you start

- Know where you are: `git log -1 --oneline` prints the version you run today. Keep that line,
  it is what you check out again if you ever need to roll back.
- Make sure nobody is in the middle of a VLAN change on the Vlans page; an upgrade restarts the
  container.

## 2. Standard upgrade (Docker Compose)

```bash
cd xike_manager
docker compose down                                   # stop (releases the database file)
cp -r data/ data-backup-$(date +%Y%m%d)/              # backup, takes a second
git pull                                              # fetch the new version
docker compose build --no-cache                       # rebuild the image (frontend + backend)
docker compose up -d                                  # start
docker compose logs -f --tail=50                      # watch the first start, Ctrl+C to leave
```

A healthy start ends with `Application startup complete.` and `Uvicorn running on http://127.0.0.1:8000`.

Then, in your browser, do a hard refresh (**Ctrl+Shift+R**, or **Cmd+Shift+R** on macOS) once so it
drops the old cached frontend. Coming from a version before the session key change (section 3),
you are asked to log in again once; after that, sessions survive upgrades as long as
`data/secret_key` (or your own `SECRET_KEY`) is kept.

> **You edited `docker-compose.yml` (port, secret, volume path)?** `git pull` keeps your edits
> unless the same lines changed upstream. If it refuses to pull, run `git stash`, then `git pull`,
> then `git stash pop` and resolve the conflict in that one file.

> **Demo branch:** `git checkout demo && git pull`, then the same build/up commands.

> **Installed from a ZIP, no git:** download the new ZIP, extract it next to the old folder,
> copy your old `data/` folder into the new one, and run the build/up commands from there.

## 3. What changed, and what to check after upgrading

### The interface looks different

The web UI was rebuilt: the navigation moved to a sidebar with a switch picker, the pages have
a dark mode (top bar, next to the language), and confirmations are in-app dialogs. Everything
you could do before is still there, in the same places, with two moves: **static MAC entries**
now live on the **MAC Table** page, and the **System** page shows the **change log**. If a page
looks broken right after the upgrade, do a hard refresh (Ctrl+Shift+R) once.

### You will be asked to log in again (once)

Earlier versions signed login sessions with a key that was part of the repository. The new
version generates its own key on first start and keeps it in `data/secret_key`, so every
existing session stops being valid: log in again, that is all. If you had set your own
`SECRET_KEY` in `docker-compose.yml`, it is still honoured. The example line was removed from
the file; you do not need one.

### VLAN page: safer, and one change to verify on your switch

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

### Behind a reverse proxy: set `TRUSTED_PROXIES`

Login attempts are now throttled: ten wrong passwords for one account from one client address
block that account for ten minutes (for that address). If a reverse proxy sits in front of the
container, every browser arrives from the proxy's address, so add the proxy's address to
`docker-compose.yml` (`- TRUSTED_PROXIES=172.17.0.1`) and make the proxy send
`X-Forwarded-For` (nginx: `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`;
Caddy and Traefik do it by default). The container also sends `X-Frame-Options: DENY` now, so
SwitchPilot no longer loads inside another dashboard's iframe; link to it instead.

### Changing a password logs that user out

Resetting someone's password (Users page) ends their current sessions, including your own if you
change your own password. Log in again with the new one.

### Management port protection

Disabling port 1 from the Ports page asks for confirmation. Scripts must send
`"force": true` to do it.

### SFP+ ports 9 and 10 can be numbered per switch (issue #3)

Earlier versions assumed that on every SKS3200 the firmware's index 9 was the SFP+ cage labelled
10 on the front panel, and swapped the two. That is true for some units and wrong for others
(and nothing in the switch's API tells which is which), so it is now a setting on each switch.

- **Your existing switches keep the old behaviour.** The upgrade marks them as "swapped", so the
  Ports page shows exactly what it showed before. Descriptions, VLAN and LAG assignments stay
  where you left them.
- **Switches you add from now on start in the firmware's own numbering** (what the switch's web UI
  shows), with the swap off.
- **Check each switch once:** plug a cable into the cage labelled **9** on the front panel and open
  the Ports page. The link must appear on port **9**. If it appears on port 10, go to
  **System → SFP+ Port Numbering** and flip the toggle. Leave "Move port descriptions with their
  physical port" ticked so the descriptions follow the cages. This only changes labels in
  SwitchPilot; the switch itself is not touched.
- On the Ports page, hovering a port number shows the switch's internal index when the two differ.

### Port mirroring works from the UI

Applying a mirror session from the System page used to fail silently (the backend answered
HTTP 422 and nothing reached the switch). If you believed a mirror was configured, open
**System → Port Mirroring** and apply it again. The "Apply Mirror" button is now also available
with the destination set to *Disabled*, which turns mirroring off.

### Static MAC entries are listed

The static MAC table on the System page was always empty. It now lists the entries with their
port numbers.

### Safer handling of wrong input

A port number outside 1-10 is refused with a clear 400 error. Earlier versions either crashed
(HTTP 500) or, for static MAC entries, silently used **port 1** (the management port).

### Snapshots

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

See [CHANGELOG.md](../CHANGELOG.md) for the complete list.

## 4. Rolling back

If something does not work for you, going back is two commands and your backup:

```bash
docker compose down
git checkout <the commit line you noted in step 1>       # e.g. git checkout 7ff0af8
docker compose build --no-cache && docker compose up -d
```

The previous version ignores the new database column, so restoring the backup is optional. To be
on the safe side anyway: `rm -rf data && cp -r data-backup-YYYYMMDD data` before `up -d`.
Switches you add *while* rolled back are shown with the 9/10 swap on by that version; after
upgrading again they appear with the swap off (the column already exists, so the one-time
migration does not run twice): flip them under **System → SFP+ Port Numbering** if needed.
Please open an issue with the `docker compose logs` output so it can be fixed.

## 5. Troubleshooting

| Symptom | What to do |
|---|---|
| `no such column: swap_sfp_9_10` in the logs | The startup migration did not run. Check the first lines of `docker compose logs` for an error before `Application startup complete`, make sure `./data` is writable by the container, then `docker compose restart`. |
| Ports page still looks like the old version | Hard refresh the browser (Ctrl+Shift+R). |
| `database is locked` at startup | Another SwitchPilot container is using the same `data/` folder. Stop it first. |
| Ports 9 and 10 look inverted after the upgrade | Nothing changed for existing switches; see "Check each switch once" above and flip the setting under System. |
| Logged out right after the upgrade | Expected once: the session key changed. Log in again. |
| `Too many failed logins` | 10 wrong passwords for that account within 10 minutes from the same client address (or 100 across accounts). Wait a few minutes; behind a reverse proxy set `TRUSTED_PROXIES` (section 3). |
| Live stats stay on "Connecting" | Hard refresh the browser: the old frontend uses the old stream URL. |
