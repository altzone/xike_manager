# Changelog

All notable changes to SwitchPilot are listed here. Upgrading an existing install is described in
[docs/upgrade.md](docs/upgrade.md).

## [Unreleased]

### Fixed
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
- Backend test suite (`backend/tests`, pytest) with a mock Xikestor switch.
- This changelog and the upgrade guide.

### Changed
- All port translation lives in `SwitchClient` (`to_internal()` / `to_user()`); the module-level
  `PORT_MAP` is gone.
- `POST /api/switches/{id}/lag` and `/mirror` bodies are validated models (see docs/api.md).
- Automatic schema migration at startup (`swap_sfp_9_10` column).

## [1.0.0] - 2026-04-09

Initial release: multi-switch dashboard, ports, VLANs, LAG, monitoring (SSE), system settings,
users, snapshots, 12 languages, Docker image.
