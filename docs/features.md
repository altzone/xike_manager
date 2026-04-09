# Feature Guide

## Dashboard

The dashboard shows an overview of your switch:
- **Temperature** — Current switch temperature in Celsius
- **Ports Up** — Number of active (linked) ports out of 10
- **SSE Status** — Real-time connection status (Online/Offline)
- **Model** — Switch hardware model
- **Port Diagram** — Visual representation of all 10 ports with link status and speed

## Ports

Configure physical port parameters:

| Setting | Description |
|---------|------------|
| **Status** | Enable or disable a port. Click the badge to toggle. |
| **Speed** | Auto-negotiate or force: 10M, 100M, 1G, 2.5G, 10G (SFP+ only) |
| **Flow Control** | 802.3x pause frames. Click to toggle On/Off |
| **Description** | Custom label stored locally. Click to edit. |
| **Link** | Live negotiated speed. Updates every 3 seconds. |
| **TX/RX** | Packet counters with live packets-per-second delta |
| **Errors** | Bad packet count. Red badge if > 0. |

A green/red dot before each port number indicates link status in real-time.

## VLANs

### Workflow
1. **Create VLANs** — Add VLAN IDs with descriptive names (e.g. "LAN", "VoIP", "Guest")
2. **Assign to Ports** — Set each port to:
   - **Flat**: No VLAN tagging (default)
   - **Access**: Single VLAN, untagged traffic
   - **Trunk**: Multiple VLANs with 802.1Q tags

### Hardware Limitations
- **Native VLAN (PVID)**: Maximum ID is **63** (hardware limitation of MaxLinear chip)
- **Tagged VLAN entries**: Maximum **111** across all ports
- **Port 1**: Protected as management port (shown with MGMT badge)

### VLAN Sync
Click "Sync to all switches" to copy VLAN definitions (names + IDs) to all other configured switches.

## LAG (Link Aggregation)

Bond multiple ports into a single logical link:

| Mode | Description |
|------|------------|
| **Static Trunk** | Manual bonding. Both ends must be configured identically. |
| **LACP (802.3ad)** | Dynamic negotiation. Recommended. Detects link failures automatically. |

- Up to **16 LAG groups**
- Name your groups for easy identification
- Visual per-port status (Active/Down) in each group

## MAC Address Table

- **Live table** of all learned MAC addresses
- **Vendor identification** using IEEE OUI database (39,000+ manufacturers)
- **Search** by MAC address fragment
- **Clear** all dynamic entries

## System & Features

### Clock
- **SNTP mode**: Auto-sync from NTP server (hostnames auto-resolved to IP)
- **Manual mode**: Set time, date, and timezone manually
- **Check** button verifies if SNTP sync is working

### STP (Spanning Tree Protocol)
Prevents network loops with redundant links.
- **STP**: Classic spanning tree (slow convergence)
- **RSTP**: Rapid spanning tree (recommended, faster convergence)

### Storm Control
Limits broadcast/multicast flood traffic.
- Rate: 1-1000 packets per second

### IGMP Snooping
Optimizes multicast delivery (IPTV, video streaming).
- **Fast Leave**: Immediately remove port from multicast group
- **Querier**: Send IGMP membership queries

### EEE (Energy Efficient Ethernet)
Reduces power during low traffic. Safe for most environments.

### Port Mirroring
Copy traffic for analysis (Wireshark, packet capture):
1. Select **destination** (monitoring) port
2. Select **source** ports to mirror
3. Choose **direction** (ingress, egress, or both)

### Loop Detection
Per-port loop detection. Simpler than STP — blocks the port when a loop is detected.

### Static MAC Entries
Permanently bind a MAC address to a port. Useful for security.

### Management Interface
Configure the switch's IP: DHCP or static IP/netmask/gateway.

> **Warning**: Changing IP settings may disconnect you from the switch.

### Configuration Snapshots
- **Save**: Capture all switch settings to database
- **Download**: Export as JSON file
- **Import**: Upload a previously saved JSON
- **Compare**: View raw JSON of any snapshot

## User Management

| Role | Permissions |
|------|------------|
| **Admin** | Full access: configure, manage users, reboot, sync |
| **Viewer** | Read-only: view dashboard, ports, VLANs, monitoring |

Access user management from the Dashboard page ("Users" button).

## Languages

SwitchPilot supports 12 languages. Click the flag icon in the top-right corner to switch:

🇬🇧 English · 🇫🇷 Français · 🇩🇪 Deutsch · 🇪🇸 Español · 🇧🇷 Português · 🇮🇹 Italiano · 🇹🇷 Türkçe · 🇷🇺 Русский · 🇸🇦 العربية · 🇨🇳 中文 · 🇯🇵 日本語 · 🇰🇷 한국어

Language preference is saved in your browser.
