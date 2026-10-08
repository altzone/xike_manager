# Changelog

All notable changes to SwitchPilot are listed here. Upgrading an existing install is described in
[docs/upgrade.md](docs/upgrade.md).

## [2.3.2] - 2026-10-08

### Security
- **The tools that build the web page are up to date.** `npm audit` reported six high-severity
  advisories in them (nanoid, PostCSS, source-map-js, Vite, Vue's server renderer; nanoid was
  reported in pull request #4). Updating within the versions SwitchPilot already allowed fixes
  them all: nanoid 3.3.20, PostCSS 8.5.29, Vite 8.3.4, Vue 3.5.43, Tailwind CSS 4.3.3. None of
  them could be reached in a running SwitchPilot: they concern building the page, Vite's
  development server on Windows, or rendering pages on a server, which SwitchPilot does not do.
  The page looks and works the same, and there is nothing to do after the update.

## [2.3.1] - 2026-10-07

### Changed
- **On 2.0.0.x switches, link aggregation (LAG) and storm control are read-only for now.** On a
  2.0.0.3 unit (issue #3), a LAG change (two unused ports into an LACP group) was followed by a
  network outage, and storm control limits were answered OK by the switch but not applied
  (SwitchPilot noticed it, put the previous setting back and saved nothing). Both requests match
  what the switch's own pages send, so the cause is not known yet. Until they are confirmed on a
  real switch, SwitchPilot shows these settings as the switch reports them and does not send
  changes (the API answers 501, nothing reaches the switch). Port settings, VLANs, STP and IGMP
  were seen working on that unit and stay editable, as do loop detection, port mirroring and the
  MAC table.

  If you changed a LAG on a 2.0.0.x switch with SwitchPilot 2.2.0 to 2.3.0, check it on the
  switch's own Link Aggregation page.

## [2.3.0] - 2026-10-06

First step towards simple updates: SwitchPilot is now published as a ready-made Docker image, the
database is copied before an update changes it, and stopping the container no longer cuts a change
being sent to a switch.

### Added
- **Docker images.** Each version is built, tested and published to
  `ghcr.io/altzone/switchpilot` (amd64 and arm64, so 64-bit Raspberry Pi too), with a GitHub
  release whose notes are this change log. Tags: the exact version (`2.3.0`), and `2.3`, `2` and
  `latest`, which follow the newest version of their line. The default `docker-compose.yml` still
  builds the image itself; it moves to the published image in the next version.
- **The database is copied before an update changes it**, to `data/backups/`
  (`switchpilot-<previous>-to-<new>-<date>.db`, readable by the container's user only, 5 kept).
  If the copy cannot be written, the update does not touch the database and the start stops with
  a clear message in `docker compose logs`.

### Fixed
- **Stopping or updating the container could cut a change being sent to a switch.** Docker gave
  SwitchPilot 10 seconds, then killed it: a longer change (a slow or unreachable switch, several
  VLAN changes on 2.0.0.x) stopped midway, for example after the VLAN table was written but before
  it was saved, and without its previous settings being put back; the page got no answer either.
  Now a change already under way is finished (read back, put back if refused, saved) and answered
  before SwitchPilot stops, for up to about two minutes; live statistics streams end at once. The
  container gets 150 seconds in all; a normal stop takes a second or two.
- **On 2.0.0.3 switches, the check with a temporary VLAN 4094 ran again after every restart.** Its
  result is now kept with the switch and reused while the switch runs the same firmware.

### Changed
- **Watchtower leaves SwitchPilot alone** (label `com.centurylinklabs.watchtower.enable=false`), so
  a Watchtower that updates every container does not restart it in the middle of a switch change.
  Automatic updates will be an explicit choice.
- The image's web page is built with Node.js 22 (`npm ci`, exact dependency versions). The image
  still builds with Docker 20.10 and docker-compose v1.

## [2.2.1] - 2026-10-06

### Added
- **The version you run is shown** at the bottom of the side menu (thanks to @tavalin for asking).
  It is the version of the server, asked again when you come back to the page or open another
  section; a click opens this change log. Scripts can read it from `GET /api/version` (signed in).
- When SwitchPilot was updated while a page was open, a **Reload** button appears next to the
  version once the page has asked again. Such a page also loads itself again, once, when it fails
  to open a section because the update removed the files it needed.

### Changed
- Browsers now check for a new version of the page each time it is opened (`index.html` is sent with
  `Cache-Control: no-cache`; the other files keep their content hash in their name). The hard
  refresh after an update is no longer needed from the next update on; this once it still is.

## [2.2.0] - 2026-10-06

### Added
- **2.0.0.x (V2) firmware support.** Xikestor's 2.0.0.x firmware has a different web API from
  1.0.0.x for almost every setting. SwitchPilot now speaks it, using the requests the switch's
  own web pages send. They were decoded from the web interface built into Xikestor's official
  2.0.0.x image and from its request handlers, then compared with a capture of the web interface
  of an SKS3200-8E2X-P running 2.0.0.3 (thanks to @tavalin, issue #3). Only port settings have
  been confirmed on a real switch so far; everything else was checked against the firmware's code
  and a simulated switch built from it.

  The firmware answers OK even when it ignores a request. So after each change SwitchPilot reads
  the setting back from the switch, and saves it with the switch's single Save
  (`save_all_configs.json`) only when it matches. The exceptions are port settings, the
  management address and clearing the MAC table.

  When a change was not applied, SwitchPilot puts the previous setting back, checks it and reports
  the error; nothing is saved. What 2.0.0.x switches get:
  - **VLANs:** one 802.1Q table of up to 100 VLANs, each named on the switch (16 bytes).
    - Any VLAN ID from 1 to 4094 can be an access or native VLAN (no 0-63 limit).
    - Applying port changes updates memberships and PVIDs in a safe order: a port only leaves a
      VLAN once its new PVID is confirmed. If the switch refuses part of it, the previous
      configuration is put back and checked.
    - A port whose mode changes gets back "all frames" if the accepted frame types set on the switch
      would drop its new traffic.
    - A trunk set up on the switch's own page with its native VLAN tagged shows as "Unknown" and is
      left as it is: writing it back as a SwitchPilot trunk would change it.
    - A VLAN that is still a port's access or native VLAN cannot be deleted, and deleting a VLAN
      deletes it from the switch (the confirmation says so).
    - 2.0.0.3 reads its VLAN table back in a different layout from the image this support was built
      from (10 port entries instead of 11), while its own page still writes the original layout.
      Before its first VLAN change on such a switch, SwitchPilot checks this once with a temporary
      VLAN "SwitchPilot test" (VLAN 4094, or the highest free ID), with one tagged port, deleted
      right away. If the result is unclear, SwitchPilot changes no VLAN there.
  - **Ports, management IP and reboot.**
    - Port changes are saved.
    - A new static management address is saved at that address when SwitchPilot follows it.
      Otherwise, and with DHCP, the answer says how to keep it.
  - **Link aggregation** (groups 1-31 accepted, as the switch stores them) and **port mirroring.**
  - **STP** and **loop detection.**
    - STP: classic or rapid mode; edge ports through the API.
    - Loop detection is a single setting for the whole switch on this firmware: block the looping
      port, check interval and recovery time (the switch only shows these while detection runs, so
      the System page lets you set them before turning it on), plus the ports where a loop was seen.
    - As on the switch's own page, STP and loop detection are alternatives. Turning one on turns
      the other off, but only once the first is confirmed running, so the network is never left
      with neither. SwitchPilot tells you when it does.
  - **Storm control** in Mbps (1-1000), per kind of traffic (broadcast, multicast, unknown
    unicast, unknown multicast), with the same limit on every port.
  - **IGMP snooping** with Fast Leave and report flooding (2.0.0.x has no global querier).
  - **MAC table:**
    - the whole dynamic table is read (the switch answers 50 entries at a time);
    - the search matches any part of an address, with or without separators;
    - static entries are added and removed by VLAN ID, including entries on several ports;
    - they are saved without the 1.0.0.x save request, which on 2.0.0.x erases the saved static
      entries.
- EEE and time/SNTP stay read-only on 2.0.0.x. The vendor removed both pages from that firmware's
  web interface and their request format there is unconfirmed; their cards say so. Other writes
  that a firmware cannot take are refused with `501` before anything is sent.
- On 2.0.0.x, SwitchPilot sends one request at a time to each switch, because that firmware serves
  one connection at a time and queues only a few.
- `GET /api/switches`, `/info` and `/status` report `firmware_line` (1 or 2) and `read_only`.

### Fixed
- **2.0.0.x: no more misread settings.** Earlier versions sent 1.0.0.x requests to 2.0.0.x
  switches. Some were refused (storm control, EEE). Others were accepted and misread:
  - an IGMP change turned Fast Leave and report flooding off;
  - a loop detection change turned loop detection off;
  - an STP change cleared the edge ports and reset the mode to RSTP.

  A VLAN created in SwitchPilot was never sent to the switch. Apart from port settings, nothing
  was saved on the switch either, so changes were lost at its next restart (issue #3). See the
  upgrade guide for what to check on such a switch.
- Pages the switch formats differently answered `500 Internal Server Error`. They now return
  `502` naming the page and the firmware, and a snapshot keeps every section it could read
  (`meta.unavailable` lists the others).
- The stored model and firmware of a switch are refreshed from its status page: switches added
  by the first release on 2.0.0.x firmware had no model.
- LAG on 2.0.0.x: a system priority of 0, which the switch's own page allows, was changed to 32768
  the next time a LAG was edited. 1.0.0.x still asks for 1-65535.
- MAC table, every firmware: the switch's own address shows as "Switch itself" instead of
  "Port 0".

### Changed
- API: some reads and writes take a 2.0.0.x shape on 2.0.0.x switches:
  - `GET`/`POST` of `loop` and `storm`;
  - `report_flood` for IGMP;
  - `vlan_id` for static MAC entries; on 2.0.0.x a delete needs no port, and an unknown entry is
    a `404`;
  - `max_vlans`/`used_vlans` in `GET /vlans/limits`;
  - `vlans`/`created` instead of `tag_entries` in the `POST /vlans/apply` answer.

  Writes on 2.0.0.x return `warnings` when the save on the switch did not complete. MAC entries
  carry `vlan` on every firmware. See [docs/api.md](docs/api.md).

## [2.1.1] - 2026-10-05

### Changed
- **SFP+ port 9/10 numbering follows the firmware line.** 1.0.0.x firmware numbers the two SFP+
  cages the other way round from the front panel, 2.0.0.x does not (an SKS3200-8E2X on 1.0.0.4
  and an SKS3200-8E2X-P on 2.0.0.x, both hardware A0; issue #3). Adding a switch now picks the
  numbering from its firmware (the Add Switch dialog offers Automatic / Swapped / As numbered by
  the firmware); before, new switches always started unswapped, which was wrong on 1.0.0.x.
- On its first start, 2.1.1 sets every existing switch whose firmware is known to the numbering
  of its firmware line, once, whether the database comes from the first release or from 2.1.0
  (a schema version is now recorded with `PRAGMA user_version`). This fixes 2.0.0.x switches
  shown swapped and 1.0.0.x switches added under 2.1.0 shown unswapped. Port 9/10 descriptions
  move with the cages, and each change is logged in the switch's change log as made by
  "SwitchPilot". Switches with an unknown firmware version keep their setting.
- The System page warns when a switch's setting does not match what its firmware usually needs.
  `GET /status` reports `swap_sfp_suggested`.

### Documentation
- Windows installation: start Docker Desktop / WSL 2 first, check the engine, troubleshooting.
- Firmware note: Xikestor forbids flashing 2.0.0.x onto 1.0.0.x units and the reverse, and the
  -P model has its own images.

## [2.1.0] - 2026-10-01

### Security
- **Session signing key.** Earlier versions signed every login token with a key that was
  committed to the repository (`docker-compose.yml`) or hard-coded as a fallback, so anyone
  could forge an admin token. The key is now generated on first start and kept in
  `data/secret_key` (`SECRET_KEY` from the environment still wins when it is not one of the
  old defaults). Everyone is logged out once after upgrading.
- The user's role is re-read from the database on every request: a demoted or deleted account
  loses access immediately instead of when its 24 h token expires.
- Login attempts are throttled per client address *and* account (10 failures per 10 minutes,
  100 per address across accounts), so one person's typos never lock everybody out when all
  browsers share one address (reverse proxy, Docker Desktop). `TRUSTED_PROXIES` names the
  proxies whose `X-Forwarded-For` is believed; the container's nginx forwards it. The password
  check no longer blocks the server, and an unknown username costs the same time as a wrong
  password. Expired throttle entries are evicted.
- Changing a password ends that user's existing sessions (tokens carry a fingerprint of the
  stored hash); a live-stats stream stops within a minute when its account is deleted or its
  password changes.
- The generated signing key is created with mode 0600 from the start; the database file is
  made private (0600) at startup; `data/` as a whole is ignored by git.
- The live-stats stream (SSE) is opened with a 5-minute, stream-only token instead of the
  session token, which used to end up in access logs (issue #1 contained one).
- CORS is off unless `CORS_ORIGINS` is set (the UI is same-origin); nginx sends
  `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy`.

### Fixed
- **VLAN Apply could wipe the uplink.** The tagged-VLAN table was rebuilt from the request
  alone after a reset, and the UI never sent port 1, so every Apply dropped port 1's tagged
  VLANs (and any port not in the request) and saved that to flash. Apply is now a merge: the
  current configuration is read first and ports not in the request keep their port-VLAN and
  tagged entries. Flat ports are written explicitly, the reset happens before the writes, a
  failure puts the previous tables back, a slow flash save is reported instead of failing,
  and two Applies cannot interleave.
- **Tagged VLANs now join their VLAN's bridge** (`brName` = VLAN ID for VLANs 1-63, as the
  working community clients do) instead of bridge 0, so tagged traffic reaches that VLAN's
  access ports. A trunk's native VLAN no longer gets a tagged entry. **Please verify on real
  hardware** before relying on it (see the upgrade guide).
- VLAN Apply rewrote PVID/native VLAN 0 as 1 on ports it touched; 0 (default bridge) is kept.
- The tag-entry limit rejected exactly 111 entries (the hardware maximum).
- `GET /vlans/assignments` wrote to the database (deleted VLANs reappeared with a generic
  name); VLAN discovery is now computed on `GET /vlans` with `in_use`/`defined` flags.
- Switch problems (offline, bad credentials, HTTP error, unexpected body) surfaced as bare
  `500 Internal Server Error`; they are `502` with a message naming the cause.
- Disabling the management port (port 1) needs `force: true` (the UI asks for confirmation).
- Changing the switch's static IP from SwitchPilot left SwitchPilot pointed at the old address;
  the stored address and live connection now follow, settings are validated, and DHCP comes
  with an explicit note. The stored address only follows when the switch accepted the change
  and SwitchPilot was talking to the switch's own address (not a hostname or NAT address); a
  refusal is reported as `502` and nothing is changed.
- A write answered with the login page even after re-logging in was reported as success (the
  change was silently dropped); it is an error now, and so is a read in that state. Endpoints
  answering `404` on newer firmware count as unsupported like an empty body does.
- After a session expired, every concurrent request re-logged in separately; one re-login is
  shared. Live stats back off to 15 s between attempts while the switch is unreachable or
  refuses the credentials (instead of a login attempt every 3 s). A read timeout is no longer
  retried (it doubled the wait).
- Tagged VLAN entries carried over on Apply are written with their VLAN's bridge even when an
  earlier version had put them in bridge 0, so one VLAN is never split across two bridges.
  VLANs above 63 (tagged-only) get a free bridge of their own, kept across Applies; double-tag
  (QinQ) entries are carried over intact instead of being rewritten as single-tag.
- `POST /vlans/apply` refused the `"unknown"` mode that `GET /vlans/assignments` itself reports
  (a port enabled with neither untag nor tag), so one such port blocked the whole VLAN page;
  it is accepted and left as is. `access_vlan` 0 is accepted like `native_vlan` 0.
- Port mirroring: the clearing request now lists every non-source port including the
  destination, exactly as the native UI's captured sequence does.
- A slow flash save after adding or deleting a static MAC entry was reported as a failure
  although the entry was applied; it is a warning.
- Flipping the SFP+ numbering waits for an in-flight VLAN apply; the last-admin guards run in
  one transaction; `GET /snapshots` returns 404 for an unknown switch; the "cannot connect"
  message no longer echoes the transport error.
- The old interface requested the stream token with GET (the route is POST-only), so live
  stats always fell back to polling.
- Deleting a static MAC entry forwarded the UI's `{mac, port, fid}` body to the firmware as is
  (only `port` was translated), while the add form uses `mac-input`/`port-input`/`fid-input`.
  The body is now validated and the firmware payload built exactly like the add path (the
  firmware's delete form was never captured: this mirrors the add form, to be confirmed on
  hardware).
- Renaming a VLAN was a DELETE followed by a POST, so a failure in between lost the name:
  `PUT /api/switches/{id}/vlans/{vid}` renames it in place.
- Ports page: changing the speed or flow control of port 1 while it was already disabled asked
  the "disable the management port?" question (and reverted the change on Cancel); the question
  is only asked when the change itself disables the port. Live stats go back to the stream
  after a failed stream-token request instead of polling for good.
- Rebuilt interface, after an adversarial review of the new code: Arabic layout no longer
  reorders numeric tokens ("+37/s", "41 °C", "3 / 10", "SFP+"); the Users and static MAC tables
  scroll on phones instead of hiding their action columns; System section headers wrap on
  phones; dialogs focus their first field (not the close button), trap Tab, restore focus on
  close and only the topmost one reacts to Escape; every form label is tied to its field; the
  remaining hard-coded English strings (placeholders, API errors, login footer, imported
  snapshot name) are translated; plural forms ("1 port", "1 switch"); port descriptions no
  longer vanish from the Overview when live stats arrive; a slow ping of the previous switch
  can no longer mark the current one unreachable; the Overview and the static MAC card show a
  load error (with Retry) instead of zeros or "no entries"; VLAN page: creating, renaming or
  deleting a VLAN keeps unsaved port edits, Discard is instant and local, leaving or reloading
  with unsaved changes asks, ports in the switch's "unknown" mode are shown as such and can be
  changed, the trunk native VLAN defaults to a value the select can show, chips show keyboard
  focus; LAG and VLAN load failures offer Retry; a deleted switch id goes back to the dashboard
  instead of polling forever; the live indicator says "Switch unreachable" rather than
  "Connecting…" when the stream is fine but the switch is not, and packet rates survive the
  polling fallback; "Update SNTP" no longer rewrites a timezone the user did not touch (an
  offset outside the list is kept as is); logging out with unsaved VLAN changes asks first;
  the tab title follows the page; language menus and toggle-style buttons carry ARIA state;
  localStorage being blocked (private mode) no longer breaks the app; text/background contrast
  of muted text, buttons and the front-panel labels meets WCAG AA in both themes.
- An admin could demote themselves or the last admin and lock everyone out; roles are
  validated, passwords need 6 characters, duplicate usernames return 409.
- SNTP hostname resolution blocked the whole server; "synced" was reported with SNTP off;
  the daylight-saving flag was reset by every time/timezone change.
- LAG: creating a second group silently merged it into the first one (stale group id);
  `portPriorityId` is now sent as the native UI does; group renames no longer re-send the
  whole trunk configuration (`PUT /lag/names`).
- Ports page: the header row had 9 cells for 10 columns, so "Negotiated" was unlabelled and
  the following headers were shifted (issue #1).
- Login with a wrong password reloaded the page instead of showing the error; validation errors
  displayed as `[object Object]`; 403s were silent.
- Live stats: the SSE composable leaked connections after leaving a page, scheduled two
  reconnects per failure, and treated the backend's `error` event as a dropped connection;
  the switch dashboard never went live when the status call failed.
- Arabic RTL layout and `<html lang>` were lost on reload; `{param}` interpolation replaced
  only the first occurrence.
- `/users` is admin-only in the router; the stored role is refreshed from the server.
- Reboot returned 500 when the switch dropped the connection while rebooting.
- **SFP+ ports 9 and 10 shown and configured the wrong way round on some units** (#3). The 9↔10
  swap between the firmware's indexes and the front-panel labels is unit-dependent and was
  hardcoded for everyone, so on affected switches every read was inverted and every write (port
  enable/speed, VLAN, LAG, loop detection, STP, mirror, static MAC) hit the other SFP+ cage.
  It is now a per-switch setting (System → SFP+ Port Numbering). Existing switches keep the
  previous behaviour after upgrade; new switches default to the firmware's own numbering.
- Port mirroring could not be applied from the UI: two routes were registered on
  `POST /api/switches/{id}/mirror` and the first one rejected the UI's payload with HTTP 422.
  Applying now also clears previously selected sources (second request, as the native UI does),
  and mirroring can be disabled from the UI.
- Login succeeded only when the switch answered with `setup.html`; 2.0.0.x firmware redirects to
  `index.html` and was reported as "cannot connect".
- MAC tables streamed as `data:` lines (newer firmware) crashed the JSON parser; a dropped
  connection right after login made the next request fail instead of being retried once.
- The model name was read from `modle` only; `des` (newer firmware) is used as fallback.
- The static MAC table on the System page was always empty (the API returned the raw payload).
- Adding a static MAC with an invalid or string port silently bound it to port 1 (management).
  Invalid port numbers now return HTTP 400 everywhere instead of 500 or a silent fallback.
- MAC search was sent to the switch without URL encoding.
- The live packets-per-second counters were per 3 s polling tick, not per second.
- Deleting a switch left its descriptions, LAG names, VLAN names and snapshots behind and kept a
  stale connection in memory.

### Added
- `PUT /api/switches/{id}` to edit a switch's name, IP and credentials (connection re-tested).
- `PUT /api/switches/{id}/port-mapping` and the matching System card, "Add Switch" checkbox and
  Ports tooltip; `swap_sfp_9_10` on `GET /api/switches` and `/info`.
- Snapshots record `meta.port_numbering` and `meta.swap_sfp_9_10`, and use user-facing port
  numbers in every section.
- `GET /api/switches/{id}/changes`: an audit log of configuration changes (who, what, when).
- `PUT /api/switches/{id}/lag/names` to rename LAG groups without touching the switch.
- `POST /api/auth/stream-token` (used by the UI for live stats).
- Docker `HEALTHCHECK`, `.dockerignore`, nginx logs to the container output, a `LICENSE`
  file (MIT, as the README always said).
- Backend test suite (`backend/tests`, pytest) with a mock Xikestor switch.
- This changelog and the upgrade guide.

### Changed
- **The web interface was rebuilt.** Sidebar with a switch picker and per-switch navigation,
  top bar with live status, dark mode (follows the system by default), a front-panel view with
  per-port LEDs and negotiated speeds, consistent cards/tables/forms, translated confirmation
  dialogs instead of browser pop-ups, proper empty/loading/error states, and a phone layout.
  Static MAC entries moved from System to the MAC Table page; the System page shows an audit log
  of changes; viewers no longer see controls they cannot use.
- All port translation lives in `SwitchClient` (`to_internal()` / `to_user()`); the module-level
  `PORT_MAP` is gone.
- `POST /api/switches/{id}/lag` and `/mirror` bodies are validated models (see docs/api.md).
- Automatic schema migration at startup (`swap_sfp_9_10` column).
- The API and the frontend report the same version number (2.1.0); the initial release called
  itself 2.0.0 (API) and 1.0.0 (frontend).

## [1.0.0] - 2026-04-09

Initial release: multi-switch dashboard, ports, VLANs, LAG, monitoring (SSE), system settings,
users, snapshots, 12 languages, Docker image.
