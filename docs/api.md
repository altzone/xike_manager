# API Reference

SwitchPilot exposes a REST API. All endpoints require JWT authentication (except setup and login).

## Authentication

### Login
```
POST /api/auth/login
Body: {"username": "admin", "password": "yourpass"}
Response: {"token": "eyJ...", "username": "admin", "role": "admin"}
```

Use the token as Bearer header:
```
Authorization: Bearer eyJ...
```

### Check Setup Status
```
GET /api/setup/status
Response: {"setup_complete": true}
```

### Initial Setup
```
POST /api/setup
Body: {"username": "admin", "password": "yourpass"}
```

## Switches

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches` | List all switches |
| POST | `/api/switches` | Add switch `{"name","ip","username","password"}` |
| DELETE | `/api/switches/{id}` | Remove switch |
| GET | `/api/switches/{id}/info` | Switch name, IP, model |
| GET | `/api/switches/{id}/ping` | Quick online check |
| GET | `/api/switches/{id}/status` | Full system status |
| GET | `/api/switches/{id}/sse?token=xxx` | SSE stream (live stats) |

## Ports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/ports` | Port config + descriptions |
| POST | `/api/switches/{id}/ports/config` | Set port `[{"port","enabled","speed","flow_ctrl"}]` |
| POST | `/api/switches/{id}/ports/description` | Set description `{"port","description"}` |
| GET | `/api/switches/{id}/ports/stats` | Port counters (TX/RX/errors) |

## VLANs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/vlans` | List VLAN definitions |
| POST | `/api/switches/{id}/vlans` | Create VLAN `{"vlan_id","name"}` |
| DELETE | `/api/switches/{id}/vlans/{vid}` | Delete VLAN |
| GET | `/api/switches/{id}/vlans/assignments` | Port VLAN assignments |
| POST | `/api/switches/{id}/vlans/apply` | Apply assignments `[{"port","mode","access_vlan","native_vlan","trunk_vlans"}]` |
| GET | `/api/switches/{id}/vlans/limits` | Hardware limits |
| POST | `/api/switches/{id}/vlans/sync` | Sync VLANs to all switches |

## LAG

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/lag` | LAG config + group names |
| POST | `/api/switches/{id}/lag` | Apply LAG `{"system_priority","ports","group_names"}` |

## System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/time` | System time + SNTP config |
| POST | `/api/switches/{id}/time` | Set time `{"time","date","timezone"}` |
| POST | `/api/switches/{id}/sntp` | Set SNTP `{"enabled","server","poll"}` |
| GET | `/api/switches/{id}/sntp/check` | Check SNTP sync status |
| POST | `/api/switches/{id}/network` | Set IP `{"dhcp","ip","netmask","gateway"}` |
| GET | `/api/switches/{id}/stp` | STP config |
| POST | `/api/switches/{id}/stp` | Set STP `{"enabled","mode"}` |
| GET | `/api/switches/{id}/storm` | Storm control |
| POST | `/api/switches/{id}/storm` | Set storm `{"enabled","rate"}` |
| GET | `/api/switches/{id}/igmp` | IGMP config |
| POST | `/api/switches/{id}/igmp` | Set IGMP `{"enabled","fast_leave","querier"}` |
| GET | `/api/switches/{id}/eee` | EEE status |
| POST | `/api/switches/{id}/eee` | Set EEE `{"enabled"}` |
| GET | `/api/switches/{id}/mirror` | Port mirror config |
| POST | `/api/switches/{id}/mirror` | Set mirror `{"monitoring_port","ingress","egress","mirrored_ports"}` |
| GET | `/api/switches/{id}/loop` | Loop detection status |
| POST | `/api/switches/{id}/loop` | Set loop `{"ports": {1: true, 2: false}}` |
| POST | `/api/switches/{id}/reboot` | Reboot switch |

## MAC Table

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/mac/dynamic` | Dynamic MAC table (with vendor) |
| GET | `/api/switches/{id}/mac/dynamic?search=AA:BB` | Search MAC |
| POST | `/api/switches/{id}/mac/clear` | Clear dynamic MACs |
| GET | `/api/switches/{id}/mac/static` | Static MAC entries |
| POST | `/api/switches/{id}/mac/static/add` | Add static `{"mac","port","fid"}` |

## Config Snapshots

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/snapshots` | List snapshots |
| POST | `/api/switches/{id}/snapshots` | Save snapshot `{"name"}` |
| GET | `/api/switches/{id}/snapshots/{sid}` | Get snapshot detail |
| DELETE | `/api/switches/{id}/snapshots/{sid}` | Delete snapshot |
| POST | `/api/switches/{id}/snapshots/import` | Import `{"name","config"}` |

## Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users` | List users (admin only) |
| POST | `/api/users` | Create user `{"username","password","role"}` |
| PUT | `/api/users/{uid}` | Update `{"role"}` or `{"password"}` |
| DELETE | `/api/users/{uid}` | Delete user |
