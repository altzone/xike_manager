# Changelog

All notable changes to SwitchPilot are listed here. Upgrading an existing install is described in
[docs/upgrade.md](docs/upgrade.md).

## [Unreleased]

### Security
- **Session signing key.** Earlier versions signed every login token with a key that was
  committed to the repository (`docker-compose.yml`) or hard-coded as a fallback, so anyone
  could forge an admin token. The key is now generated on first start and kept in
  `data/secret_key` (`SECRET_KEY` from the environment still wins when it is not one of the
  old defaults). Everyone is logged out once after upgrading.
- The user's role is re-read from the database on every request: a demoted or deleted account
  loses access immediately instead of when its 24 h token expires.
- Login attempts are throttled per client address (10 failures per 10 minutes), the password
  check no longer blocks the server, and an unknown username costs the same time as a wrong
  password.
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
  with an explicit note.
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

## [1.0.0] - 2026-04-09

Initial release: multi-switch dashboard, ports, VLANs, LAG, monitoring (SSE), system settings,
users, snapshots, 12 languages, Docker image.
