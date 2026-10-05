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

### Hardware Limits (MaxLinear MxL86282S)
- PVID/FID (native VLAN): 0-63 max
- Tag VLAN entries: 111 max
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
- 12 languages, ~345 keys each; every key must exist in all 12 files (fallback to English is only for safety)
- Composable useI18n() with t('key', {params}) function; `{param}` placeholders, every occurrence replaced
- Technical terms (VLAN, LACP, STP, etc.) stay in English in all languages
- Arabic has RTL support: use logical utilities (ps-/pe-/ms-/me-/start/end), never left/right; the Faceplate keeps physical order (dir="ltr")
- Language stored in localStorage; `<html dir lang>` set at startup

### UI conventions
- Semantic colour utilities only (bg-surface, text-muted, border-line, text-ok…), never raw gray-*/indigo-* classes, so dark mode works
- Confirmations through useConfirm() (translated dialog), never window.confirm; feedback through useToast()
- Admin-only controls are hidden or disabled for viewers (auth.isAdmin); the backend enforces roles anyway
- Every user-facing string goes through t(); add new keys to all 12 i18n files

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
