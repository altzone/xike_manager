# Changelog

All notable changes to SwitchPilot are listed here. Upgrading an existing install is described in
[docs/upgrade.md](docs/upgrade.md).

## [2.1.0] - Unreleased

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
