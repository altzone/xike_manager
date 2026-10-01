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
drops the old cached frontend. You stay logged in: sessions are not invalidated by an upgrade as
long as `SECRET_KEY` in `docker-compose.yml` did not change.

> **You edited `docker-compose.yml` (port, secret, volume path)?** `git pull` keeps your edits
> unless the same lines changed upstream. If it refuses to pull, run `git stash`, then `git pull`,
> then `git stash pop` and resolve the conflict in that one file.

> **Demo branch:** `git checkout demo && git pull`, then the same build/up commands.

> **Installed from a ZIP, no git:** download the new ZIP, extract it next to the old folder,
> copy your old `data/` folder into the new one, and run the build/up commands from there.

## 3. What changed, and what to check after upgrading

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
Please open an issue with the `docker compose logs` output so it can be fixed.

## 5. Troubleshooting

| Symptom | What to do |
|---|---|
| `no such column: swap_sfp_9_10` in the logs | The startup migration did not run. Check the first lines of `docker compose logs` for an error before `Application startup complete`, make sure `./data` is writable by the container, then `docker compose restart`. |
| Ports page still looks like the old version | Hard refresh the browser (Ctrl+Shift+R). |
| `database is locked` at startup | Another SwitchPilot container is using the same `data/` folder. Stop it first. |
| Ports 9 and 10 look inverted after the upgrade | Nothing changed for existing switches; see "Check each switch once" above and flip the setting under System. |
