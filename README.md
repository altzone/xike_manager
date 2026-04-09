# SwitchPilot

**Modern, professional web management for Xikestor network switches.**

SwitchPilot replaces the chaotic, poorly translated, and unintuitive factory firmware UI shipped with Xikestor switches. It provides a clean, responsive interface inspired by enterprise-grade tools like Aruba InstantON — but open-source and self-hosted.

![License](https://img.shields.io/badge/license-MIT-blue) ![Docker](https://img.shields.io/badge/docker-ready-brightgreen) ![Languages](https://img.shields.io/badge/i18n-12_languages-orange)

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

### Switch Management
- **Visual Dashboard** — Real-time port status (up/down, speed, traffic counters via SSE)
- **Port Configuration** — Speed, duplex, flow control, enable/disable, descriptions, live TX/RX/pps counters with green/red status dots
- **VLAN Editor** — Create named VLANs, then assign to ports as Access or Trunk with allowed VLAN selection. Clear warnings for hardware limits (native VLAN max 63, 111 tag entries)
- **Link Aggregation** — Create LAG groups (Static/LACP), name them, visual port status per group
- **MAC Address Table** — Live table with search, vendor identification (39,000+ IEEE OUI entries), port mapping
- **System Settings** — STP, Storm Control, IGMP Snooping, EEE, Port Mirroring (3-step wizard), Loop Detection (per port), SNTP with DNS resolution

### Platform
- **Multi-switch** — Manage multiple Xikestor switches from a single interface
- **User Management** — Admin and Viewer roles, password management
- **VLAN Sync** — Copy VLAN definitions across all switches with one click
- **Config Snapshots** — Save, download (JSON), import, and compare full switch configurations
- **12 Languages** — English, French, German, Spanish, Portuguese, Italian, Turkish, Russian, Arabic (RTL), Chinese, Japanese, Korean
- **Real-time SSE** — Live port stats with automatic reconnect and fallback polling
- **Toast Notifications** — Visual feedback for every action
- **Unsaved Changes Banner** — Prevents accidental data loss on VLAN page

### Hardware Awareness
- Native VLAN (PVID) limited to 0-63 — clearly indicated in the UI
- Tag VLAN entries limited to 111 — counter displayed
- Port 9/10 internal mapping handled transparently
- Management port (port 1) protected from accidental VLAN lockout
- Management IP configuration (DHCP/Static) with disconnect warning

## Supported Hardware

| Model | Chipset | Ports |
|-------|---------|-------|
| **Xikestor SKS3200-8E2X** | MaxLinear MxL86282S | 8x 2.5G RJ45 + 2x 10G SFP+ |

Other Xikestor models using the same web API should also work.

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

That's it. No SSL certificates, no reverse proxy, no configuration files needed.

### First Run

1. **Create admin account** — Enter your desired username and password
2. **Add your switch** — Click "Add Switch", enter the switch IP, username (`admin`) and password (`admin` by default)
3. **Start managing** — Dashboard, Ports, VLANs, and all features are immediately available

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
        proxy_buffering off;
        proxy_read_timeout 86400s;
    }
}
```

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
| Tagged VLAN ID | 0 - 4095 | Standard 802.1Q |
| Tag VLAN entries | 111 max | Counter in header |
| Management VLAN | Not supported | Info tooltip |
| Port 9/10 mapping | Internally swapped | Handled transparently |
| SNTP hostname | IP only (auto-resolved) | DNS resolution in backend |
| Port descriptions | Not on hardware | Stored locally in SwitchPilot |
| System logs | Not available | — |

## Data Persistence

All data is stored in `./data/switchpilot.db` (SQLite):
- User accounts and sessions
- Switch connection details
- VLAN names
- Port descriptions
- LAG group names
- Configuration snapshots
- OUI vendor database

To backup: just copy the `data/` directory.

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

See all endpoints in `backend/main.py`.

## Contributing

Pull requests welcome. Please:
- Keep the UI clean and consistent
- Maintain i18n coverage when adding new strings
- Test with a real Xikestor switch if possible
- Technical networking terms should stay in English across all translations

## License

MIT

---

**SwitchPilot** — Because your switches deserve a better UI.
