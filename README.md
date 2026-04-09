# SwitchPilot - Modern Web Management for Xikestor Switches

**SwitchPilot** is a clean, modern web management interface designed to replace the chaotic, poorly translated, and unintuitive factory firmware UI shipped with Xikestor network switches.

## Why SwitchPilot?

The Xikestor SKS3200-8E2X (and similar models) ships with a web interface that is:

- Written primarily in Chinese with broken English translations
- Confusing VLAN configuration with undocumented limitations
- No real-time monitoring or live port status
- No multi-switch management
- No proper authentication or user management
- No visual port overview or intuitive network topology

**SwitchPilot fixes all of this** by providing a professional-grade management interface inspired by Aruba InstantON, with:

- **Visual switch dashboard** with real-time port status (up/down, speed, traffic counters via SSE)
- **Intuitive VLAN editor** with clear hardware limitation warnings (native VLAN max 63, 111 tag entries max)
- **Multi-switch support** - manage multiple Xikestor switches from a single interface
- **Proper authentication** with JWT tokens and role-based access (admin/viewer)
- **Live monitoring** - MAC table, loop detection, IGMP snooping, storm control, all in one place
- **Full feature coverage** - ports, VLANs, LAG/LACP, STP, port mirroring, EEE, and more

## Supported Hardware

- **Xikestor SKS3200-8E2X** (8x 2.5G RJ45 + 2x 10G SFP+)
- Other Xikestor models using the same MaxLinear MxL86282S-based web API

## Quick Start

```bash
git clone https://github.com/YOUR_ORG/xike_manager.git
cd xike_manager
docker compose up -d
```

Open `http://localhost:8880` in your browser.

1. Create your admin account (first-run wizard)
2. Add your first switch (IP, username, password)
3. Start managing

## Architecture

```
┌─────────────────────────────────┐
│  Docker Container               │
│  ┌──────────┐  ┌─────────────┐ │
│  │ Vue 3    │  │ FastAPI     │ │
│  │ Tailwind │──│ Python      │ │
│  │ (nginx)  │  │ SSE + Auth  │ │
│  └──────────┘  └──────┬──────┘ │
│                 ┌──────┴──────┐ │
│                 │   SQLite    │ │
│                 └─────────────┘ │
└────────────────────┬────────────┘
                     │ HTTP
              ┌──────┴──────┐
              │  Xikestor   │
              │  Switch     │
              └─────────────┘
```

## Hardware Limitations (documented in UI)

| Limitation | Value |
|------------|-------|
| Native VLAN (PVID/FID) | 0 - 63 only |
| Tagged VLAN ID | 0 - 4095 |
| Tag VLAN entries | 111 max |
| Management VLAN | Not supported (always untagged) |
| Port mapping | Ports 9/10 swapped internally |

## Tech Stack

- **Frontend**: Vue 3 + Vite + Tailwind CSS + Pinia
- **Backend**: Python FastAPI + httpx + SSE
- **Database**: SQLite (auth, switch profiles, change log)
- **Container**: Single Docker image (nginx + uvicorn + supervisor)

## License

MIT
