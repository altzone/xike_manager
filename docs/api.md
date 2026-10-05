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
| POST | `/api/switches` | Add switch `{"name","ip","username","password","swap_sfp_9_10"?}`; `swap_sfp_9_10` omitted or `null` = chosen from the firmware line (1.0.0.x swapped, 2.0.0.x not). Returns `{"id","model","firmware","swap_sfp_9_10","swap_auto"}` |
| PUT | `/api/switches/{id}` | Edit switch `{"name"?,"ip"?,"username"?,"password"?}` (connection re-tested when address/credentials change) |
| DELETE | `/api/switches/{id}` | Remove switch and its local data (descriptions, LAG names, VLAN names, snapshots) |
| PUT | `/api/switches/{id}/port-mapping` | `{"swap_sfp_9_10": bool, "move_descriptions"?: true}` — whether this unit's SFP+ cages 9/10 are numbered the other way round from the firmware's indexes. Changes labels only; nothing is written to the switch |
| GET | `/api/switches/{id}/info` | Switch name, IP, model, `swap_sfp_9_10` |
| GET | `/api/switches/{id}/ping` | Quick online check |
| GET | `/api/switches/{id}/status` | Full system status, plus `swap_sfp_suggested` (what the firmware line usually needs: `true` 1.0.0.x, `false` 2.0.0.x, `null` unknown) |
| GET | `/api/switches/{id}/sse?token=xxx` | SSE stream (live stats); `token` from `POST /api/auth/stream-token` (5 min) |
| GET | `/api/switches/{id}/changes?limit=50` | Audit log of configuration changes |

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
| PUT | `/api/switches/{id}/vlans/{vid}` | Rename VLAN `{"name"}` (1-64 chars, trimmed) → `{"ok"}`; the ID and port assignments are untouched; `404` when that VLAN is not defined for this switch (a VLAN that is only in use on the switch must be created first); logged as a `vlans` change |
| DELETE | `/api/switches/{id}/vlans/{vid}` | Delete VLAN |
| GET | `/api/switches/{id}/vlans/assignments` | Port VLAN assignments |
| POST | `/api/switches/{id}/vlans/apply` | Apply assignments `[{"port","mode","access_vlan","native_vlan","trunk_vlans"}]`; `mode` is `access`, `trunk`, `flat` or `unknown` (= leave as is); ports not listed keep their configuration; tagged entries are written to their VLAN's bridge (VLANs above 63 get a free bridge) |
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
| POST | `/api/switches/{id}/network` | Set IP `{"dhcp","ip","netmask","gateway"}` → `{"ok","dhcp","ip","accepted","note"}`; `502` when the switch refuses. SwitchPilot follows the new address only when it was talking to the switch's own address |
| GET | `/api/switches/{id}/stp` | STP config |
| POST | `/api/switches/{id}/stp` | Set STP `{"enabled","mode"}` |
| GET | `/api/switches/{id}/storm` | Storm control |
| POST | `/api/switches/{id}/storm` | Set storm `{"enabled","rate"}` |
| GET | `/api/switches/{id}/igmp` | IGMP config |
| POST | `/api/switches/{id}/igmp` | Set IGMP `{"enabled","fast_leave","querier"}` |
| GET | `/api/switches/{id}/eee` | EEE status |
| POST | `/api/switches/{id}/eee` | Set EEE `{"enabled"}` |
| GET | `/api/switches/{id}/mirror` | Port mirror config `{"monitoring_port","enabled","ports":[{"port","ingress","egress"}]}` |
| POST | `/api/switches/{id}/mirror` | Set mirror `{"monitoring_port","ingress","egress","mirrored_ports"}`; `monitoring_port: 0` turns mirroring off. Two requests reach the switch, as the native UI does: the sources, then every other port (destination included) with both directions off |
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
| POST | `/api/switches/{id}/mac/static/add` | Add static `{"mac","port","fid"}` → `{"ok","warnings"}` (a flash-save timeout is a warning, the entry is applied) |
| POST | `/api/switches/{id}/mac/static/delete` | Delete static `{"mac","port","fid"}` (same body as add; `fid` defaults to 0, `port` is the user-facing number) → `{"ok","warnings"}`. The backend builds the firmware payload itself with the add form's field names (`mac-input`, `port-input`, `fid-input`); the firmware's own delete form was never captured, so mirroring the add form is the best evidence available |

## Config Snapshots

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/snapshots` | List snapshots (`404` for an unknown switch) |
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
