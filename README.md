# SwitchPilot

**Modern, professional web management for Xikestor network switches.**

SwitchPilot replaces the chaotic, poorly translated, and unintuitive factory firmware UI shipped with Xikestor switches. It provides a clean, responsive interface inspired by enterprise-grade tools like Aruba InstantON — but open-source and self-hosted.

![Version](https://img.shields.io/badge/version-2.1.1-blue) ![License](https://img.shields.io/badge/license-MIT-blue) ![Docker](https://img.shields.io/badge/docker-ready-brightgreen) ![Languages](https://img.shields.io/badge/i18n-12_languages-orange)

Already running SwitchPilot? Jump to **[Updating](#updating)**.

---

## Why SwitchPilot?

The stock Xikestor web UI is:
- Written in Chinese with incomplete English translations
- Confusing VLAN configuration with undocumented hardware limitations
- No real-time monitoring or live port status
- No multi-switch management
- No proper authentication or user management

**SwitchPilot fixes all of this.**

## Features

### Switch management
- **Overview** — front-panel view of the switch with per-port LEDs and negotiated speeds, live figures (temperature, ports up, traffic, errors) and the latest configuration changes
- **Ports** — enable/disable, speed/duplex, flow control, descriptions, live TX/RX and packets-per-second counters; disabling the management port asks for confirmation
- **VLANs** — named VLANs assigned to ports as Access, Trunk (native + allowed VLANs) or Flat. Only the ports you change are written, the rest of the switch's VLAN tables is preserved; hardware limits (native VLAN ≤ 63, 111 tag entries) are shown as you go
- **Link aggregation** — static or LACP groups with names, member state and LACP timeout
- **MAC table** — live table with search and vendor lookup (39,000+ IEEE OUI entries), plus static entries
- **System** — management IP (DHCP/static), clock and SNTP (hostnames resolved for you), STP, storm control, IGMP snooping, EEE, port mirroring, loop detection, configuration snapshots (save / download / import), reboot

### Platform
- **Multi-switch** — all your Xikestor switches in one place, each with its own SFP+ 9/10 numbering setting (some units are wired the other way round from the firmware's indexes)
- **Users** — admin and viewer roles, enforced by the backend on every request
- **Change log** — who changed what and when, per switch
- **VLAN sync** — copy VLAN definitions to every switch in one click
- **12 languages** — English, French, German, Spanish, Portuguese, Italian, Turkish, Russian, Arabic (RTL), Chinese, Japanese, Korean; light and dark themes; works on a phone
- **Live updates** — Server-Sent Events with automatic reconnect and polling fallback
- **Secure by default** — generated session key, login throttling, short-lived stream tokens, no CORS unless you ask for it
- **REST API** — everything the UI does, documented in [docs/api.md](docs/api.md); backend test suite against a simulated switch

## Supported Hardware

| Model | Chipset | Ports |
|-------|---------|-------|
| **Xikestor SKS3200-8E2X** | MaxLinear MxL86282S | 8x 2.5G RJ45 + 2x 10G SFP+ |
| **Xikestor SKS3200-8E2X-P** | MaxLinear MxL86282S | 8x 2.5G RJ45 + 2x 10G SFP+ |

Other Xikestor models using the same web API should also work.

**Firmware:** SwitchPilot targets the **1.0.0.x** firmware line (V1). Xikestor also ships a
**2.0.0.x** line (V2) with a different web API for VLANs, STP, loop detection, storm control and
EEE. V2 support is **coming soon**; until then, on a V2 switch the dashboard, ports and port
statistics work but the VLAN and System pages will not.

The two lines are not interchangeable: Xikestor forbids flashing a 2.0.0.x image onto a 1.0.0.x
unit and the reverse (a V1 switch stays on V1), and the -P model has its own images. Check
`fw_ver` on the switch's status page before updating and only install firmware from the same
line and for your exact model.

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed
- Network access to your Xikestor switch

### Installation

```bash
git clone https://github.com/altzone/xike_manager.git
cd xike_manager
docker compose up -d
```

Open **http://localhost:8880** in your browser.

That's it. No SSL certificates, no reverse proxy, no configuration files needed. More options
(ports, NAS, Raspberry Pi, reverse proxy) are in **[docs/installation.md](docs/installation.md)**.

### Xikestor Default Settings

| Setting | Default |
|---------|---------|
| **IP Address** | `192.168.10.12` |
| **Username** | `admin` |
| **Password** | `admin` |

### First Run

1. **Create admin account** — Enter your desired username and password (this is for SwitchPilot, not the switch)
2. **Add your switch** — Click "Add Switch", enter the switch IP (default `192.168.10.12`), username `admin`, password `admin`
3. **Start managing** — Dashboard, Ports, VLANs, and all features are immediately available

### Updating

Your data (`./data/`) is kept across updates; database changes are applied automatically at startup.
Nothing is written to your switches by an update.

```bash
cd xike_manager
docker compose down                          # stop (releases the database file)
cp -r data/ data-backup-$(date +%Y%m%d)/     # backup, takes a second
git pull                                     # fetch the new version
docker compose build --no-cache              # rebuild the image (frontend + backend)
docker compose up -d                         # start
```

Then hard-refresh the browser once (**Ctrl+Shift+R**, **Cmd+Shift+R** on macOS) so it drops the
old cached frontend. Coming from the first release (before October 2026) you are logged out
once, and you should check each switch's SFP+ port numbering under **System** (see the guide).

Full details, what to check after the update, rollback and troubleshooting:
**[docs/upgrade.md](docs/upgrade.md)**. What changed in each version: **[CHANGELOG.md](CHANGELOG.md)**.

### Running on a Specific Port

```bash
# Edit docker-compose.yml to change the port
ports:
  - "3000:80"  # Change 8880 to any port you want
```

### Running with SSL (Optional)

Put a reverse proxy (nginx, Caddy, Traefik) in front of the container:

```nginx
server {
    listen 443 ssl;
    server_name switch.yourdomain.com;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 86400s;
    }
}
```

Then tell SwitchPilot which address the proxy connects from, so that login throttling (10 wrong
passwords per account and client address) counts browsers, not the proxy:

```yaml
# docker-compose.yml
      - TRUSTED_PROXIES=172.17.0.1        # the proxy's address or network, comma-separated
```

Without it every browser behind the proxy shares one address, which is fine for one household
but means ten wrong passwords on one account lock that account for everyone for 10 minutes.
SwitchPilot sends `X-Frame-Options: DENY`: it opens in its own tab, not inside another
dashboard's iframe.

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **Linux** | Fully supported | Docker or Docker Desktop |
| **macOS** | Fully supported | Docker Desktop |
| **Windows** | Fully supported | Docker Desktop |
| **Synology NAS** | Works | Via Container Manager |
| **Raspberry Pi** | Works | ARM64 Docker |

## Architecture

```
┌─────────────────────────────────────┐
│  Docker Container (single image)     │
│                                      │
│  ┌──────────┐   ┌────────────────┐  │
│  │ Vue 3    │   │ Python FastAPI │  │
│  │ Tailwind │──▶│ Switch API     │  │
│  │ (nginx)  │   │ Auth (SQLite)  │  │
│  │          │◀──│ SSE streaming  │  │
│  └──────────┘   └───────┬────────┘  │
│                    ┌─────┴─────┐     │
│                    │  SQLite   │     │
│                    │  - users  │     │
│                    │  - vlans  │     │
│                    │  - OUI db │     │
│                    │  - config │     │
│                    └───────────┘     │
└──────────────┬──────────────────────┘
               │ HTTP (switch API)
        ┌──────┴──────┐
        │  Xikestor   │
        │  Switch     │
        └─────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Vue 3, Vite, Tailwind CSS 4, Pinia |
| Backend | Python 3.12, FastAPI, httpx, uvicorn |
| Database | SQLite (aiosqlite) |
| Auth | JWT (python-jose), bcrypt |
| Realtime | Server-Sent Events (sse-starlette) |
| Container | Docker (nginx + supervisor) |
| OUI Database | IEEE MA-L (39,000+ vendors) |

## Hardware Limitations

These are limitations of the Xikestor hardware, clearly shown in the SwitchPilot UI:

| Limitation | Value | Displayed in UI |
|------------|-------|-----------------|
| Native VLAN (PVID/FID) | 0 - 63 only | Warning badge + form validation |
| Tagged VLAN ID | 1 - 4094 | Standard 802.1Q |
| Tag VLAN entries | 111 max | Counter in header |
| Management VLAN | Not supported | Info tooltip |
| Port 9/10 mapping | Swapped on 1.0.0.x firmware, not on 2.0.0.x | Set automatically from the firmware; per-switch setting (System → SFP+ Port Numbering) |
| SNTP hostname | IP only (auto-resolved) | DNS resolution in backend |
| Port descriptions | Not on hardware | Stored locally in SwitchPilot |
| System logs | Not available | — |

## Data Persistence

Everything lives in `./data/` (ignored by git):

- `switchpilot.db` (SQLite): user accounts, switch connection details (including each switch's
  admin password, which SwitchPilot needs to log in), VLAN names, port descriptions, LAG group
  names, configuration snapshots, the change log and the OUI vendor database
- `secret_key`: the key that signs login sessions, generated on first start

To backup: just copy the `data/` directory (stop the container first for a consistent copy).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DB_PATH` | `/app/data/switchpilot.db` | Where the database lives inside the container |
| `SECRET_KEY` | generated | Session signing key; set your own only to share it between several instances |
| `SECRET_KEY_FILE` | `<DB dir>/secret_key` | Where the generated key is kept |
| `TRUSTED_PROXIES` | none | Reverse proxy addresses/networks whose `X-Forwarded-For` is believed (see *Running with SSL*) |
| `CORS_ORIGINS` | none | Comma-separated origins allowed to call the API from another site (the UI needs none) |

## API

SwitchPilot exposes a REST API (same as the web UI uses):

```bash
# Login
curl -X POST http://localhost:8880/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"yourpass"}'

# Get switch ports (use token from login)
curl -H "Authorization: Bearer <token>" \
  http://localhost:8880/api/switches/1/ports

# Get MAC table with vendor info
curl -H "Authorization: Bearer <token>" \
  http://localhost:8880/api/switches/1/mac/dynamic
```

The full endpoint list is in **[docs/api.md](docs/api.md)**.

## Contributing

Pull requests welcome. Please:
- Keep the UI clean and consistent
- Maintain i18n coverage when adding new strings (every key in all 12 files)
- Run the backend tests (`cd backend && pip install -r requirements.txt pytest && pytest tests`)
- Test with a real Xikestor switch if possible
- Technical networking terms should stay in English across all translations

## License

MIT

---

**SwitchPilot** — Because your switches deserve a better UI.
