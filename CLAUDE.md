# CLAUDE.md - SwitchPilot Project Guide

## Project Overview
SwitchPilot is a web management proxy for Xikestor SKS3200-8E2X network switches. It wraps the switch's chaotic HTTP API into a clean Vue 3 + FastAPI interface with real-time monitoring, VLAN management, and multi-switch support.

## Architecture
```
frontend/ (Vue 3 + Vite + Tailwind CSS 4)
├── src/main.css        # Design tokens (light/dark via CSS variables + @theme inline), base styles, .card/.input/.table primitives
├── src/views/          # Layout (shell: sidebar, top bar, toasts), SwitchView (switch context + ping), Dashboard, SwitchDashboard
│                       # (overview), Ports, Vlans, Lag, Monitoring (MAC + static entries), System, Users, Login, Setup
├── src/components/     # Faceplate (front panel), Tip, AuthShell, ui/ (Icon, Btn, Badge, Toggle, Modal, ConfirmDialog, EmptyState, Stat)
├── src/composables/    # useApi (ApiError, 401 redirect), useSSE (stream token, reconnect), useToast, useConfirm, useTheme
├── src/stores/         # Pinia: auth (token/role, refresh), switches (list, current switch, live status)
├── src/i18n/           # 12 language files (en, fr, zh, es, pt, ar, de, ru, ja, ko, tr, it), all keys in every file
└── nginx.conf          # Serves frontend + proxies /api to uvicorn

backend/ (Python 3.12 + FastAPI)
├── main.py             # All API routes + demo mode conditional logic
├── switch_client.py    # Xikestor HTTP API client (all switch communication)
├── auth.py             # JWT + bcrypt
├── db.py               # SQLite schema + OUI import
├── sse.py              # Server-Sent Events for live stats
├── demo.py             # Demo mode simulated data (branch: demo)
├── oui.csv             # IEEE OUI vendor database (39K entries)
└── requirements.txt

Docker: single container (nginx + supervisor + uvicorn)
```

## Key Technical Details

### Switch API
- Switch at http://SWITCH_IP:80, login via GET /authorize with MD5 hashed credentials
- All config via JSON POST endpoints (port_vlan_cfg.json, tag_vlan_cfg.json, etc.)
- Port mapping: on 1.0.0.x firmware the SFP+ ports 9 and 10 are SWAPPED relative to the firmware's JSON indexes, on 2.0.0.x they match (issue #3; `default_swap_sfp(fw_ver)` picks the default when a switch is added and in the migration). It is a per-switch setting (`switches.swap_sfp_9_10`, `PUT /api/switches/{id}/port-mapping`) applied only through `SwitchClient.to_internal()` / `to_user()`; never translate ports anywhere else
- Cookie-based session, auto-relogin on expiry

### Firmware 2.0.0.x (V2)
- A different web API for almost every setting; `SwitchClient.is_v2()` (from status.json `fw_ver`) picks the format. Formats follow the native web UI built into the official 2.0.0.x image (port settings also verified on a 2.0.0.3 unit)
- Writes are allowed per feature by `V2_WRITABLE` / `_require_writable` (501 before anything is sent); EEE and time/SNTP stay read-only
- Every V2 write goes through `_write_v2` (or `_apply_vlans_v2`): the native request, a read-back (the firmware answers 200 even when it ignores a request), on a mismatch or an error the previous state put back and checked (502, nothing saved), else `save_all()` (`save_all_configs.json`, the only persistence on V2). Not read back: port settings, the management address, MAC table clear
- VLANs: one 802.1Q table (`tag_vlan.json`: GET is an SSE stream, POST `updatedVlans`/`deletedVlans`), PVID + frame type via `port_vlan.json`. STP: `stp_rstp_mode` + `psel_cbox<N>`, every POST resets enable/mode/edges. Loop detection is global (timers read 0 while off) and exclusive with STP. Storm control per port and type, JSON numbers, Mbps. IGMP reads `fast-leave`/`report-flood` (missing = off). Static MACs keyed by VLAN; the dynamic table comes 50 entries at a time
- Never on V2: `mac_save_static_mac_entries.json` (erases the saved static MACs), `logout.json` (logs out every session); never probe unknown URLs (`system_reboot.json`, `factory_reset.json` and `/exit` act on any method)
- One request at a time per V2 switch (`_gate`); MAC reads and `save_all()` share `_mac_lock` (one MAC read position per switch)
- 2.0.0.3 reads `port_states` back with 10 entries (entry 0 = port 1) instead of 11; its own page still writes 11 (entry p = port p). `vlan_write_layout()` confirms the write layout once per switch with a temporary VLAN (4094 or the highest free ID) before any real VLAN write
- Tests: `backend/tests/v2_mock.py` simulates the V2 handlers (`V2Vlans`, `V2L2`)

### Hardware Limits (MaxLinear MxL86282S)
- PVID/FID (native VLAN): 0-63 max on 1.0.0.x (2.0.0.x: any VLAN 1-4094)
- Tag VLAN entries: 111 max on 1.0.0.x (2.0.0.x: 100 VLANs, names of 16 bytes on the switch)
- SNTP: IP only (no hostnames - backend resolves DNS)
- No management VLAN support
- No syslog/event log
- Port descriptions not on hardware (stored in SQLite)
- Speed values: switch returns "2500MbpsFull" but POST expects "2500Mbps Full" (with space) - SPEED_READ_TO_WRITE mapping handles this
- Port config POST format: {"port_sts":"Enable","port_spd_duplex":"Auto","flow_ctrl":"On","port_num":1,"port_list":["1"]}

### Branches
- `master` - production, no demo mode
- `demo` - DEMO=true in docker-compose, simulated data, all logins accepted

### Database (SQLite)
Tables: users, switches, vlans, port_descriptions, lag_names, config_snapshots, oui, vlan_profiles, change_log

### i18n
- 12 languages, ~400 keys each; every key must exist in all 12 files (fallback to English is only for safety)
- Composable useI18n() with t('key', {params}) function; `{param}` placeholders, every occurrence replaced
- Technical terms (VLAN, LACP, STP, etc.) stay in English in all languages
- Arabic has RTL support: use logical utilities (ps-/pe-/ms-/me-/start/end), never left/right; the Faceplate keeps physical order (dir="ltr")
- Language stored in localStorage; `<html dir lang>` set at startup

### UI conventions
- Semantic colour utilities only (bg-surface, text-muted, border-line, text-ok…), never raw gray-*/indigo-* classes, so dark mode works
- Confirmations through useConfirm() (translated dialog), never window.confirm; feedback through useToast()
- Admin-only controls are hidden or disabled for viewers (auth.isAdmin); the backend enforces roles anyway
- Every user-facing string goes through t(); add new keys to all 12 i18n files

## Version
- One number, set in `backend/version.py` (served by `GET /api/version`, shown at the bottom of the side menu) and in `frontend/package.json` (built into the page as `__APP_VERSION__`; when the two differ the page offers a reload). Bump both, the README badge and a new CHANGELOG heading together: `tests/test_version.py` checks they agree

## Build & Deploy
```bash
cd frontend && npm run build          # Build Vue app
cd .. && docker compose build --no-cache  # Rebuild Docker image
docker compose up -d                  # Deploy
```

## Common Pitfalls
- Changing port 1 settings may disconnect management (it's the management port)
- Save to flash (save_*.json) can timeout - caught gracefully
- DEMO=true in docker-compose.yml activates demo mode - remove for production
- The OUI CSV is imported on first startup (takes a few seconds)
- FastAPI route order matters - demo mode patches routes inline, not as overrides

## External Services
- Switch API: http://SWITCH_IP:80 (Xikestor native HTTP API)
- IEEE OUI database: downloaded from standards-oui.ieee.org (bundled in oui.csv)
- SNTP: resolves hostnames via Python socket.gethostbyname()

## Deployment
- Production: xike.altzone.net (nginx reverse proxy + Let's Encrypt)
- Docker port: 8880 mapped to container port 80
- GitHub: https://github.com/altzone/xike_manager
- Wiki: https://github.com/altzone/xike_manager/wiki
