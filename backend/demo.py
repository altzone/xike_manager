"""Demo mode: simulated switch data, all logins accepted, POST ignored"""
import random
import time
import json
import asyncio
from sse_starlette.sse import EventSourceResponse

# Simulated switch state
_demo_ports = []
_demo_vlans = [
    {"vlan_id": 10, "name": "LAN"},
    {"vlan_id": 20, "name": "VoIP"},
    {"vlan_id": 30, "name": "Guest WiFi"},
    {"vlan_id": 100, "name": "Management"},
    {"vlan_id": 1001, "name": "WiFi-Config"},
]
_demo_snapshots = []
_demo_users = [
    {"id": 1, "username": "admin", "role": "admin", "created_at": "2026-04-01 10:00:00"},
    {"id": 2, "username": "viewer", "role": "viewer", "created_at": "2026-04-05 14:30:00"},
]
_start_time = time.time()

DEMO_SWITCHES = [
    {"id": 1, "name": "SW-Office", "ip": "192.168.10.12", "username": "admin", "model": "SKS3200-8E2X", "firmware": "1.0.0.4", "mac_address": "8C:A6:82:70:D7:3E", "created_at": "2026-04-01"},
    {"id": 2, "name": "SW-Warehouse", "ip": "192.168.10.13", "username": "admin", "model": "SKS3200-8E2X", "firmware": "1.0.0.4", "mac_address": "8C:A6:82:70:D8:4F", "created_at": "2026-04-02"},
    {"id": 3, "name": "SW-Server-Room", "ip": "10.1.10.40", "username": "admin", "model": "SKS3200-8E2X", "firmware": "1.0.0.4", "mac_address": "8C:A6:82:70:D9:5A", "created_at": "2026-04-03"},
    {"id": 4, "name": "SW-Conference", "ip": "172.16.1.10", "username": "admin", "model": "SKS3200-8E2X", "firmware": "1.0.0.4", "mac_address": "8C:A6:82:70:DA:6B", "created_at": "2026-04-05"},
]


def _init_ports():
    global _demo_ports
    up_ports = {1, 3, 5, 7, 9}
    speeds = {1: "1000MbpsFull", 3: "2500MbpsFull", 5: "1000MbpsFull", 7: "2500MbpsFull", 9: "10GbpsFull"}
    _demo_ports = []
    for i in range(1, 11):
        base_tx = random.randint(100000, 5000000) if i in up_ports else 0
        base_rx = random.randint(100000, 5000000) if i in up_ports else 0
        _demo_ports.append({
            "port": i,
            "internal_port": i,
            "type": "SFP+ 10G" if i >= 9 else "RJ45 2.5G",
            "status": "Enabled",
            "speed_config": "Auto",
            "speed_actual": speeds.get(i, "Link Down"),
            "flow_ctrl_config": "On",
            "flow_ctrl_actual": "On" if i in up_ports else "Off",
            "description": {1: "Uplink Router", 3: "Server NAS", 5: "AP WiFi", 7: "Workstation", 9: "Core Switch"}.get(i, ""),
            "link": speeds.get(i, "Link Down"),
            "tx_good": base_tx,
            "tx_bad": 0,
            "rx_good": base_rx,
            "rx_bad": random.choice([0, 0, 0, 0, 2]) if i in up_ports else 0,
        })

_init_ports()


def _tick_ports():
    """Simulate live traffic"""
    up_ports = {1, 3, 5, 7, 9}
    for p in _demo_ports:
        if p["port"] in up_ports:
            tx_add = random.randint(5, 200)
            rx_add = random.randint(10, 300)
            p["tx_good"] += tx_add
            p["rx_good"] += rx_add
            p["tx_pps"] = tx_add
            p["rx_pps"] = rx_add
        else:
            p["tx_pps"] = 0
            p["rx_pps"] = 0


DEMO_STATUS = {
    "temperature": "38",
    "sys_ipv4": "192.168.10.12",
    "sys_ipv6": "2001:db8::1",
    "sys_ipv6_ll": "fe80::demo:1234",
    "sys_macaddr": "8C:A6:82:DE:MO:01",
    "fw_ver": "1.0.0.4",
    "hw_ver": "A0",
    "des": "SKS3200-8E2X",
    "modle": "SKS3200-8E2X",
    "ipAddress": "192.168.10.12",
    "netmask": "255.255.255.0",
    "gateway": "192.168.10.1",
    "dhcpEnabled": "0",
}

DEMO_TIME = {
    "timeVal": "14:30:00",
    "dateVal": "09/04/2026",
    "timezoneOffsetVal": "+01:00",
    "daylightSavingVal": "0",
    "sntp_state": "1",
    "sntp_poll": "64",
    "sntp_server_ip": "162.159.200.123",
}

DEMO_STP = {"enabled": False, "mode": "rstp", "ports": [{"port": i, "edge": False, "status": "Forward"} for i in range(1, 11)]}
DEMO_STORM = {"sctrl_rate": "100", "sctrl_state": "0"}
DEMO_IGMP = {"config": {"igmp": "on", "fast_leave": "on", "snoop_querier": "off"}, "entries": {"total_entries": "0"}}
DEMO_EEE = {"eee": "on"}
DEMO_MIRROR = {"monitoring_port": 0, "ports": [{"port": i, "ingress": False, "egress": False} for i in range(1, 11)]}

DEMO_LOOP = [{"port": i, "enabled": i in {1, 3, 5, 7}, "violation": False} for i in range(1, 11)]

DEMO_LAG = {
    "system_priority": 32768,
    "ports": [{"port": i, "type": 0, "timeout": 0, "group": 0, "state": 1 if i in {1, 3, 5, 7, 9} else 0} for i in range(1, 11)],
    "group_names": {},
}

DEMO_MACS = [
    {"idx": "1", "mac": "CC:2D:E0:80:A9:A4", "port": 1, "fid": "0", "age": "281", "vendor": "Routerboard.com"},
    {"idx": "2", "mac": "54:60:09:FF:F7:24", "port": 1, "fid": "0", "age": "300", "vendor": "Google, Inc."},
    {"idx": "3", "mac": "34:7E:5C:D0:2A:42", "port": 3, "fid": "0", "age": "244", "vendor": "Sonos, Inc."},
    {"idx": "4", "mac": "D8:43:AE:21:52:1C", "port": 3, "fid": "0", "age": "206", "vendor": "Micro-Star INTL CO., LTD."},
    {"idx": "5", "mac": "C4:E7:AE:06:C9:A8", "port": 5, "fid": "0", "age": "169", "vendor": "Chengdu Meross Technology"},
    {"idx": "6", "mac": "98:FA:9B:05:A3:1A", "port": 5, "fid": "0", "age": "263", "vendor": "LCFC Electronics"},
    {"idx": "7", "mac": "48:E1:E9:1B:83:B4", "port": 7, "fid": "0", "age": "188", "vendor": "Tesla, Inc."},
    {"idx": "8", "mac": "A8:A1:59:76:02:98", "port": 7, "fid": "0", "age": "300", "vendor": "Intel Corporate"},
    {"idx": "9", "mac": "BC:24:11:93:07:CA", "port": 9, "fid": "0", "age": "131", "vendor": "Ubiquiti Inc."},
    {"idx": "10", "mac": "4C:5E:0C:14:C0:4B", "port": 9, "fid": "0", "age": "300", "vendor": "Routerboard.com"},
]

DEMO_PORT_VLANS = [
    {"port": 1, "enabled": False, "pvid": 0, "mode": "flat", "trunk_vlans": []},
    {"port": 2, "enabled": True, "pvid": 10, "mode": "access", "trunk_vlans": []},
    {"port": 3, "enabled": True, "pvid": 10, "mode": "access", "trunk_vlans": []},
    {"port": 4, "enabled": True, "pvid": 10, "mode": "access", "trunk_vlans": []},
    {"port": 5, "enabled": True, "pvid": 10, "mode": "access", "trunk_vlans": []},
    {"port": 6, "enabled": True, "pvid": 10, "mode": "access", "trunk_vlans": []},
    {"port": 7, "enabled": True, "pvid": 10, "mode": "trunk", "trunk_vlans": [10, 20, 30, 1001]},
    {"port": 8, "enabled": True, "pvid": 10, "mode": "trunk", "trunk_vlans": [10, 20, 30, 1001]},
    {"port": 9, "enabled": True, "pvid": 10, "mode": "trunk", "trunk_vlans": [10, 20, 30, 100, 1001]},
    {"port": 10, "enabled": True, "pvid": 10, "mode": "trunk", "trunk_vlans": [10, 20, 30, 100, 1001]},
]

DEMO_TAG_VLANS = []
_entry = 0
for pv in DEMO_PORT_VLANS:
    for vid in pv.get("trunk_vlans", []):
        DEMO_TAG_VLANS.append({"entry": _entry, "port": pv["port"], "vlan_id": vid, "tag_type": "single"})
        _entry += 1


async def demo_sse_generator():
    while True:
        _tick_ports()
        temp = str(random.randint(36, 42))
        data = {
            "temperature": temp,
            "ports": [dict(p) for p in _demo_ports],
            "port_settings": [dict(p) for p in _demo_ports],
        }
        yield {"event": "stats", "data": json.dumps(data)}
        await asyncio.sleep(3)


def demo_sse():
    return EventSourceResponse(demo_sse_generator())
