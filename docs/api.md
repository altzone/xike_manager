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

## Firmware lines

Xikestor switches run one of two firmware lines with different web APIs: **1.0.0.x** and
**2.0.0.x**. SwitchPilot speaks both. `firmware_line` in the switch details tells which one a
switch runs; where an endpoint answers differently on 2.0.0.x, its row says so. On 2.0.0.x:

- **Read-back:** every write is read back from the switch (the firmware answers OK even when it
  ignores a request).
  - A difference is a `502` ("... did not apply ... Nothing was saved").
  - Otherwise the change is saved on the switch (`save_all_configs.json`), and the answer's
    `warnings` lists a save that did not complete.
- **Read-only:** settings in `read_only` (EEE and `time` on 2.0.0.x) answer `501` and nothing is
  sent to the switch.
- **One request at a time:** SwitchPilot sends one request at a time to the switch.
- **VLAN layout check (2.0.0.3):** that firmware reads its VLAN table back with 10 port entries
  instead of 11. Before its first VLAN write on such a switch, SwitchPilot creates a temporary
  VLAN 4094 "SwitchPilot test" with one tagged port, reads it back and deletes it. If the result is
  unclear, VLAN writes answer `502` and nothing else is written.

## Switches

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches` | List all switches |
| POST | `/api/switches` | Add switch `{"name","ip","username","password","swap_sfp_9_10"?}`; `swap_sfp_9_10` omitted or `null` = chosen from the firmware line (1.0.0.x swapped, 2.0.0.x not; unreadable version = not swapped). Returns `{"id","model","firmware","swap_sfp_9_10","swap_auto"}` |
| PUT | `/api/switches/{id}` | Edit switch `{"name"?,"ip"?,"username"?,"password"?}` (connection re-tested when address/credentials change) |
| DELETE | `/api/switches/{id}` | Remove switch and its local data (descriptions, LAG names, VLAN names, snapshots) |
| PUT | `/api/switches/{id}/port-mapping` | `{"swap_sfp_9_10": bool, "move_descriptions"?: true}` — whether this unit's SFP+ cages 9/10 are numbered the other way round from the firmware's indexes. Changes labels only; nothing is written to the switch |
| GET | `/api/switches/{id}/info` | Switch name, IP, model, firmware, `swap_sfp_9_10`, `firmware_line` (1 = 1.0.0.x, 2 = 2.0.0.x, null = unknown) and `read_only` (settings SwitchPilot does not change on this firmware: `["eee", "time"]` on 2.0.0.x; writing one of them answers `501` and nothing is sent to the switch) |
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
| GET | `/api/switches/{id}/vlans` | VLANs `[{"vlan_id","name","defined","in_use","on_switch","deletable"}]`. On 2.0.0.x they come from the switch's 802.1Q table (names stored on the switch) plus the ones defined in SwitchPilot |
| POST | `/api/switches/{id}/vlans` | Create VLAN `{"vlan_id","name"}`. On 2.0.0.x the VLAN is also created on the switch (name cut to 16 bytes there) |
| PUT | `/api/switches/{id}/vlans/{vid}` | Rename VLAN `{"name"}` (1-64 chars, trimmed) → `{"ok"}`; the ID and port assignments are untouched; `404` when that VLAN is not defined for this switch (a VLAN that is only in use on the switch must be created first); logged as a `vlans` change |
| DELETE | `/api/switches/{id}/vlans/{vid}` | Delete VLAN. On 2.0.0.x also from the switch: `400` for VLAN 1, `409` while it is a port's access/native VLAN |
| GET | `/api/switches/{id}/vlans/assignments` | Port VLAN assignments |
| POST | `/api/switches/{id}/vlans/apply` | Apply assignments `[{"port","mode","access_vlan","native_vlan","trunk_vlans"}]`; `mode` is `access`, `trunk`, `flat` or `unknown` (= leave as is); ports not listed keep their configuration. 1.0.0.x: tagged entries are written to their VLAN's bridge (VLANs above 63 get a free bridge), answers `{"ok","port_vlans","tag_entries","warnings"}`. 2.0.0.x: memberships and PVIDs (any VLAN 1-4094, missing VLANs are created), read back, the previous configuration put back on a refusal (`502`), then saved; answers `{"ok","port_vlans","vlans","created","warnings"}` |
| GET | `/api/switches/{id}/vlans/limits` | Limits: 1.0.0.x `{"model":"bridge","max_fid":63,"max_tag_entries":111,"used_tag_entries","max_vlan_id":4094,"max_pvid":63}`; 2.0.0.x `{"model":"8021q","max_vlans":100,"used_vlans","max_vlan_id":4094,"max_pvid":4094}` |
| POST | `/api/switches/{id}/vlans/sync` | Sync VLANs to all switches |

## LAG

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/lag` | LAG config + group names |
| POST | `/api/switches/{id}/lag` | Apply LAG `{"system_priority","ports":[{"port","type","timeout","priority","group"}],"group_names"}` → `{"ok","warnings"}` |

## System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/time` | System time + SNTP config |
| POST | `/api/switches/{id}/time` | Set time `{"time","date","timezone"}` |
| POST | `/api/switches/{id}/sntp` | Set SNTP `{"enabled","server","poll"}` |
| GET | `/api/switches/{id}/sntp/check` | Check SNTP sync status |
| POST | `/api/switches/{id}/network` | Set IP `{"dhcp","ip","netmask","gateway"}` → `{"ok","dhcp","ip","accepted","note"}`; `502` when the switch refuses. SwitchPilot follows the new address only when it was talking to the switch's own address |
| GET | `/api/switches/{id}/stp` | STP config |
| POST | `/api/switches/{id}/stp` | Set STP `{"enabled","mode","edge_ports"?}` (`mode` `stp`/`rstp`; `edge_ports` omitted = kept) → `{"ok","warnings"}`. 2.0.0.x adds `loop_turned_off`: turning STP on turns loop detection off, as the switch's own page does |
| GET | `/api/switches/{id}/storm` | Storm control. 1.0.0.x: the switch's `{"sctrl_state","sctrl_rate"}`. 2.0.0.x: `{"model":"per_port","enabled","rate","types","uniform","ports":[{"port","broadcast","multicast","unknown_unicast","unknown_multicast"}]}` (Mbps, 0 = no limit; `rate`/`types` summarise the ports, `uniform` is false when they differ) |
| POST | `/api/switches/{id}/storm` | Set storm `{"enabled","rate"}` (1.0.0.x: packets/s). 2.0.0.x: `rate` in Mbps (1-1000) and `types` (`broadcast`, `multicast`, `unknown_unicast`, `unknown_multicast`; default `["broadcast"]`), the same limit on every port → `{"ok","warnings","requests"}` |
| GET | `/api/switches/{id}/igmp` | IGMP config `{"config","entries"}`; `config` has `snoop_querier` on 1.0.0.x, `report_flood` on 2.0.0.x |
| POST | `/api/switches/{id}/igmp` | Set IGMP `{"enabled","fast_leave","querier"}`; on 2.0.0.x `{"enabled","fast_leave","report_flood"?}` (omitted = kept; there is no global querier) |
| GET | `/api/switches/{id}/eee` | EEE status |
| POST | `/api/switches/{id}/eee` | Set EEE `{"enabled"}` |
| GET | `/api/switches/{id}/mirror` | Port mirror config `{"monitoring_port","enabled","ports":[{"port","ingress","egress"}]}` |
| POST | `/api/switches/{id}/mirror` | Set mirror `{"monitoring_port","ingress","egress","mirrored_ports"}`; `monitoring_port: 0` turns mirroring off. Two requests reach the switch, as the native UI does: the sources, then every other port (destination included) with both directions off |
| GET | `/api/switches/{id}/loop` | Loop detection. 1.0.0.x: `[{"port","enabled","violation"}]`. 2.0.0.x: one setting for the switch, `{"model":"global","enabled","prevention","interval","recovery","ports":[{"port","violation"}]}` (`interval` in tenths of a second, `recovery` in seconds; both read 0 while detection is off) |
| POST | `/api/switches/{id}/loop` | 1.0.0.x: `{"ports": {1: true, 2: false}}`. 2.0.0.x: `{"enabled"?,"prevention"?,"interval"?,"recovery"?}` (0-100, omitted = kept) → `{"ok","warnings","stp_turned_off"}`: turning detection on turns STP off, as the switch's own page does |
| POST | `/api/switches/{id}/reboot` | Reboot switch |

## MAC Table

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/switches/{id}/mac/dynamic` | Dynamic MAC table `{"entries":[{"idx","mac","port","fid","vlan","age","vendor"}],"total","truncated"?}`. Port 0 is the switch itself. 2.0.0.x: the whole table is read (50 entries per answer), `truncated` when not all of it could be |
| GET | `/api/switches/{id}/mac/dynamic?search=AA:BB` | Search MAC (2.0.0.x: any part of the address, with or without separators) |
| POST | `/api/switches/{id}/mac/clear` | Clear dynamic MACs |
| GET | `/api/switches/{id}/mac/static` | Static MAC entries |
| POST | `/api/switches/{id}/mac/static/add` | Add static `{"mac","port","fid"}` (1.0.0.x) or `{"mac","port","vlan_id"}` (2.0.0.x, VLAN 1-4094, default 1) → `{"ok","warnings"}` (a flash-save timeout is a warning, the entry is applied) |
| POST | `/api/switches/{id}/mac/static/delete` | Delete static, same body as add (`port` is the user-facing number) → `{"ok","warnings"}`. 1.0.0.x: the backend builds the firmware payload with the add form's field names (`mac-input`, `port-input`, `fid-input`), the only shape captured on that firmware. 2.0.0.x: by MAC and VLAN, checked on the switch afterwards |

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
