"""Xikestor SKS3200-8E2X API Client"""
import hashlib
import json
import httpx

# Hardware limits
NUM_PORTS = 10         # 8x 2.5G RJ45 (1-8) + 2x 10G SFP+ (9-10)
SFP_PORTS = (9, 10)
MAX_FID = 63           # PVID/native VLAN max
MAX_TAG_ENTRIES = 111  # Tag VLAN table max entries
MAX_VLAN_ID = 4095     # 802.1Q max


class InvalidPortError(ValueError):
    """A port number outside 1..NUM_PORTS (or not a number) was given."""


def build_port_map(swap_sfp: bool) -> dict[int, int]:
    """user-facing port -> internal index used in the switch's JSON.

    On some units the two SFP+ cages are wired the other way round from the
    firmware's own numbering (JSON index 9 is the cage labelled 10 on the front
    panel), on others they match (issue #3). The firmware exposes nothing that
    tells which is which, so the swap is a per-switch setting.
    """
    mapping = {p: p for p in range(1, NUM_PORTS + 1)}
    if swap_sfp:
        mapping[9], mapping[10] = 10, 9
    return mapping


def decode_payload(text: str):
    """Parse a switch response body: plain JSON, or the SSE-style `data: ...` lines that
    newer firmware uses for the MAC tables (one JSON list or object per line)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        chunks = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        parts = [json.loads(c) for c in chunks if c]
        if not parts:
            raise
        if all(isinstance(p, list) for p in parts):
            return [item for p in parts for item in p]
        if all(isinstance(p, dict) for p in parts):
            merged = {}
            for p in parts:
                merged.update(p)
            return merged
        return parts


def _parse_mac_entries(raw, port_to_user) -> list[dict]:
    """Normalise a MAC table payload to [{idx, mac, port, fid, age}].

    The dynamic table is {"total_entries": n, "Idx_0": {"Dynamic_idx", "Dynamic_mac_addr",
    "Dynamic_portid", "Dynamic_fid", "Dynamic_age_timer"}, ...}. The static table uses the
    same layout with a different prefix, and newer firmware returns a flat list with
    `*_vlan_id` instead of `*_fid`, so fields are matched by suffix.
    """
    if isinstance(raw, dict) and "batch" in raw:
        items = [v for v in raw["batch"] if isinstance(v, dict)]
    elif isinstance(raw, dict):
        items = [v for k, v in raw.items() if k.startswith("Idx_") and isinstance(v, dict)]
    elif isinstance(raw, list):
        items = [v for v in raw if isinstance(v, dict)]
    else:
        items = []

    def field(entry, *suffixes, default=""):
        for key, value in entry.items():
            lk = key.lower()
            if any(lk.endswith(s) for s in suffixes):
                return value
        return default

    entries = []
    for e in items:
        mac = field(e, "mac_addr", "mac")
        if not mac:
            continue
        port_raw = field(e, "portid", "port", default="0")
        try:
            port = port_to_user(int(port_raw))
        except (TypeError, ValueError):
            port = port_raw
        entries.append({
            "idx": str(field(e, "_idx", default="")),
            "mac": mac,
            "port": port,
            "fid": str(field(e, "_fid", "vlan_id", default="0")),
            "age": str(field(e, "age_timer", default="")),
        })
    return entries


class SwitchClient:
    def __init__(self, ip: str, username: str = "admin", password: str = "admin",
                 swap_sfp: bool = False, transport: httpx.AsyncBaseTransport | None = None):
        self.configure(ip, username, password)
        self.set_port_mapping(swap_sfp)
        self.client = httpx.AsyncClient(timeout=30, transport=transport)
        self.closed = False

    # ── Configuration ──
    def configure(self, ip: str, username: str, password: str):
        """Point the client at (possibly new) address/credentials without replacing it.

        The same instance is shared by request handlers and long-lived SSE streams,
        so a switch edit must update it in place rather than create a new one.
        """
        changed = (getattr(self, "ip", None), getattr(self, "username", None),
                   getattr(self, "password", None)) != (ip, username, password)
        self.ip = ip
        self.base = f"http://{ip}:80"
        self.username = username
        self.password = password
        if changed:
            self._logged_in = False

    def set_port_mapping(self, swap_sfp: bool):
        self.swap_sfp = bool(swap_sfp)
        self.port_map = build_port_map(self.swap_sfp)
        self.port_map_rev = {v: k for k, v in self.port_map.items()}

    def to_internal(self, port) -> int:
        """User-facing port number -> switch JSON index. Raises InvalidPortError."""
        try:
            port = int(port)
        except (TypeError, ValueError):
            raise InvalidPortError(f"Invalid port {port!r}")
        if port not in self.port_map:
            raise InvalidPortError(f"Port {port} is out of range (1-{NUM_PORTS})")
        return self.port_map[port]

    def to_user(self, internal) -> int:
        """Switch JSON index -> user-facing port number."""
        internal = int(internal)
        return self.port_map_rev.get(internal, internal)

    # ── Session ──
    async def login(self) -> bool:
        usr_md5 = hashlib.md5(self.username.encode()).hexdigest()
        pwd_md5 = hashlib.md5(self.password.encode()).hexdigest()
        r = await self.client.get(f"{self.base}/authorize", params={
            "loginusr": usr_md5, "loginpwd": pwd_md5
        })
        # Success is a redirect to setup.html (1.0.0.x) or index.html?page= (2.0.0.x);
        # a bad password is a 200 that redirects to login.html.
        self._logged_in = r.status_code == 200 and "login.html" not in r.text
        return self._logged_in

    async def _ensure_login(self):
        if not self._logged_in:
            await self.login()

    async def _raw_get(self, endpoint: str, params: dict | None = None) -> httpx.Response:
        try:
            return await self.client.get(f"{self.base}/{endpoint}", params=params)
        except httpx.TransportError:
            # the switch drops the pooled connection after /authorize on some firmware;
            # a GET is safe to send again on a fresh connection (a POST never is)
            return await self.client.get(f"{self.base}/{endpoint}", params=params)

    async def _get(self, endpoint: str, params: dict | None = None):
        await self._ensure_login()
        r = await self._raw_get(endpoint, params)
        if "login.html" in r.text:
            await self.login()
            r = await self._raw_get(endpoint, params)
        return decode_payload(r.text)

    async def _post(self, endpoint: str, data: dict):
        await self._ensure_login()
        r = await self.client.post(f"{self.base}/{endpoint}", json=data)
        if "login.html" in r.text:
            await self.login()
            r = await self.client.post(f"{self.base}/{endpoint}", json=data)
        return r.text

    # ── System ──
    async def get_status(self):
        return await self._get("status.json")

    async def get_network(self):
        return await self._get("network_settings.json")

    async def set_network_ipv4(self, ip: str, netmask: str, gateway: str, dhcp: bool):
        return await self._post("network_settings_ipv4.json", {
            "input_ip": ip, "input_netmask": netmask,
            "input_gateway": gateway, "dhcp_enable": "1" if dhcp else "0"
        })

    async def set_description(self, desc: str):
        return await self._post("set_des.json", {"input_des": desc})

    async def get_time(self):
        return await self._get("systemtime_settings.json")

    async def set_time(self, time: str, date: str, timezone: str, daylight: str = "0"):
        return await self._post("systemtime_settings.json", {
            "input_time": time, "input_date": date,
            "timezone_offset": timezone, "input_daylight": daylight,
        })

    async def get_sntp(self):
        return await self._get("sntp_setting.json")

    async def set_sntp(self, enabled: bool, server: str, poll: int = 64):
        return await self._post("sntp_setting.json", {
            "sntp_state": "1" if enabled else "0",
            "sntp_server_ip": server, "sntp_poll": str(poll)
        })

    async def reboot(self):
        return await self._post("system_reboot.json", {})

    async def factory_reset(self):
        return await self._post("factory_reset.json", {})

    # Speed value mapping: switch returns without space, POST expects with space
    SPEED_READ_TO_WRITE = {
        "Auto": "Auto",
        "10MbpsHalf": "10Mbps Half", "10MbpsFull": "10Mbps Full",
        "100MbpsHalf": "100Mbps Half", "100MbpsFull": "100Mbps Full",
        "1000MbpsFull": "1000Mbps Full",
        "2500MbpsFull": "2500Mbps Full",
        "10GbpsFull": "10Gbps Full",
    }

    # ── Ports ──
    async def get_ports(self):
        raw = await self._get("port_setting_load.json")
        ports = []
        for i in range(1, int(raw["PortNum"]) + 1):
            p = raw[f"Port_{i}"]
            user_port = self.to_user(i)
            raw_speed = p["Spd_Duplex_Cfg"]
            ports.append({
                "port": user_port,
                "internal_port": i,
                "type": "SFP+" if user_port in SFP_PORTS else "RJ45 2.5G",
                "status": p["Port_Status"],
                "speed_config": self.SPEED_READ_TO_WRITE.get(raw_speed, raw_speed),
                "speed_actual": p["Spd_Duplex_Actual"],
                "flow_ctrl_config": p["Flow_Ctrl_Cfg"],
                "flow_ctrl_actual": p["Flow_Ctrl_Actual"],
            })
        ports.sort(key=lambda x: x["port"])
        return ports

    async def set_port(self, port: int, enabled: bool = True, speed: str = "Auto", flow_ctrl: str = "On"):
        internal = self.to_internal(port)
        return await self._post("apply_user_port_setting.json", {
            "port_sts": "Enable" if enabled else "Disable",
            "port_spd_duplex": speed,
            "flow_ctrl": flow_ctrl,
            "port_num": 1,
            "port_list": [str(internal)],
        })

    async def save_ports(self):
        return await self._post("save_user_port_setting.json", {})

    async def get_port_stats(self):
        raw = await self._get("port_statistics.json")
        stats = []
        for i in range(1, int(raw["PortNum"]) + 1):
            p = raw[f"Port_{i}"]
            stats.append({
                "port": self.to_user(i),
                "internal_port": i,
                "link": p["Link_Status"],
                "tx_good": int(p["TxGoodPkt"]),
                "tx_bad": int(p["TxBadPkt"]),
                "rx_good": int(p["RxGoodPkt"]),
                "rx_bad": int(p["RxBadPkt"]),
            })
        stats.sort(key=lambda x: x["port"])
        return stats

    async def clear_stats(self):
        return await self._post("clear_statistics.json", {})

    # ── Port VLAN (PVID) ──
    async def get_port_vlans(self):
        raw = await self._get("port_vlan_cfg.json")
        result = []
        for i in range(1, int(raw["totBports"]) + 1):
            p = raw[f"Port_{i}"]
            enabled = p[f"bpEn_{i}"] == "1"
            pvid = int(p[f"bpVid_{i}"])
            untag = p[f"untag_{i}"] == "1"
            tag = p[f"tag_{i}"] == "1"
            if not enabled:
                mode = "flat"
            elif untag:
                mode = "access"
            elif tag:
                mode = "trunk"
            else:
                mode = "unknown"
            result.append({
                "port": self.to_user(i), "enabled": enabled,
                "pvid": pvid, "mode": mode,
            })
        result.sort(key=lambda x: x["port"])
        return result

    async def set_port_vlans(self, configs: list[dict]):
        """configs: [{"port": 1, "mode": "access"|"trunk"|"flat", "pvid": 10}, ...]"""
        data = {}
        for cfg in configs:
            internal = self.to_internal(cfg["port"])
            mode = cfg.get("mode", "flat")
            pvid = cfg.get("pvid", 0)
            if mode == "flat":
                continue  # don't include = untouched
            if mode == "access" and pvid > MAX_FID:
                raise ValueError(f"PVID {pvid} exceeds max {MAX_FID} for access mode")
            if mode == "trunk" and pvid > MAX_FID:
                raise ValueError(f"Native VLAN {pvid} exceeds max {MAX_FID}")
            data[f"checkbox_{internal}"] = "on"
            data[f"fidName_{internal}"] = str(pvid)
            if mode == "access":
                data[f"checkboxUntag_{internal}"] = "on"
            elif mode == "trunk":
                data[f"checkboxTag_{internal}"] = "on"
        result = await self._post("port_vlan_cfg.json", data)
        if "invalid FID" in result:
            raise ValueError(f"Invalid FID/PVID (max {MAX_FID})")
        return result

    async def save_port_vlans(self):
        return await self._post("save_port_vlan_map.json", {})

    async def reset_vlans(self):
        return await self._post("init_vlan.json", {})

    # ── Tag VLAN (802.1Q) ──
    async def get_tag_vlans(self):
        raw = await self._get("tag_vlan_cfg.json")
        entries = []
        for i in range(int(raw["totBps"])):
            e = raw[f"bP_{i}"]
            if e[f"TBVEn_{i}"] == "1":
                entries.append({
                    "entry": i,
                    "port": self.to_user(int(e[f"pP_{i}"])),
                    "vlan_id": int(e[f"oVid_{i}"]),
                    "tag_type": "single" if e[f"tT_{i}"] == "0" else "double",
                })
        return entries

    async def set_tag_vlans(self, entries: list[dict]):
        """entries: [{"entry": 0, "port": 7, "vlan_id": 10}, ...]"""
        data = {}
        for e in entries:
            idx = e["entry"]
            internal = self.to_internal(e["port"])
            data[f"bpCboxName_{idx}"] = "on"
            data[f"vtypeName_{idx}"] = "0"
            data[f"ppName_{idx}"] = str(internal)
            data[f"brName_{idx}"] = "0"
            data[f"oVidName_{idx}"] = str(e["vlan_id"])
            data[f"iVidName_{idx}"] = "0"
        return await self._post("tag_vlan_cfg.json", data)

    async def save_tag_vlans(self):
        return await self._post("save_tag_vlan_map.json", {})

    # ── LAG ──
    async def get_lag_raw(self):
        return await self._get("port_trunk_cfg.json")

    async def get_lag(self):
        raw = await self.get_lag_raw()
        ports = []
        for i in range(1, int(raw["PortNum"]) + 1):
            p = raw[f"Port_{i}"]
            ports.append({
                "port": self.to_user(i),
                "type": int(p[f"portTypeId_{i}"]),
                "timeout": int(p[f"lacpTimeoutId_{i}"]),
                "priority": int(p.get(f"portPriorityId_{i}", 128)),
                "group": int(p[f"Port_{i}_grpInd"]),
                "state": int(p[f"Port_{i}_state"]),
            })
        ports.sort(key=lambda x: x["port"])
        return {"system_priority": raw["system_priority"], "ports": ports}

    async def set_lag(self, system_priority: int, ports: list[dict]):
        """ports: [{"port": 9, "type": 1, "timeout": 0, "priority": 128, "group": 1}, ...] (user-facing ports)"""
        post = {"system_priority": str(system_priority)}
        for p in ports:
            internal = self.to_internal(p["port"])
            post[f"portTypeId_{internal}"] = str(p["type"])
            post[f"portPriorityId_{internal}"] = str(p.get("priority", 128))
            post[f"lacpTimeoutId_{internal}"] = str(p["timeout"])
            post[f"Port_{internal}_grpInd"] = str(p["group"])
        return await self._post("port_trunk_cfg.json", post)

    # ── STP ──
    async def get_stp(self):
        raw = await self._get("stp.json")
        ports = []
        for i in range(1, int(raw["num_ports"]) + 1):
            ports.append({
                "port": self.to_user(i),
                "edge": raw[f"Port_{i}"][f"Stp_Edge_{i}"] == "1",
                "status": raw[f"Port_{i}"][f"Stp_Status_{i}"],
            })
        ports.sort(key=lambda x: x["port"])
        return {
            "enabled": raw["stp_enable"] == "1",
            "mode": "rstp" if raw["stp_mode"] == "1" else "stp",
            "ports": ports,
        }

    async def set_stp(self, enabled: bool, mode: str = "stp", edge_ports: list[int] | None = None):
        data = {"stp_enable": "1" if enabled else "0", "stp_mode": "1" if mode == "rstp" else "0"}
        if edge_ports is not None:
            edges = {self.to_internal(p) for p in edge_ports}
            for i in range(1, NUM_PORTS + 1):
                data[f"Stp_Edge_{i}"] = "1" if i in edges else "0"
        return await self._post("stp.json", data)

    # ── Loop Detection ──
    async def get_loop_status(self):
        return await self._get("port_loop_status.json")

    async def get_loop_config(self):
        return await self._get("port_lock_cfg.json")

    async def get_loop(self):
        config = await self.get_loop_config()
        status = await self.get_loop_status()
        ports = []
        for i in range(1, NUM_PORTS + 1):
            cfg = config.get(f"Port_{i}", {})
            ports.append({
                "port": self.to_user(i),
                "enabled": cfg.get(f"Locken_{i}") == "1",
                "violation": status.get(f"Violdetd_{i}", "0") == "1",
            })
        ports.sort(key=lambda x: x["port"])
        return ports

    async def set_loop(self, ports: dict):
        """ports: {user_port: enabled, ...}. Ports left out or False are disabled."""
        data = {}
        for port, enabled in ports.items():
            internal = self.to_internal(port)
            if enabled:
                data[f"checkbox_{internal}"] = "on"
        return await self._post("port_lock_cfg.json", data)

    # ── IGMP ──
    async def get_igmp_config(self):
        return await self._get("igmp_config.json")

    async def set_igmp_config(self, data: dict):
        return await self._post("igmp_config.json", data)

    async def get_igmp_entries(self):
        return await self._get("igmp_get_entries.json")

    # ── Storm Control ──
    async def get_storm_control(self):
        return await self._get("storm_ctrl_cfg.json")

    async def set_storm_control(self, rate: int, enabled: bool):
        return await self._post("storm_ctrl_cfg.json", {
            "sctrl_rate": str(rate), "sctrl_state": "1" if enabled else "0"
        })

    # ── Port Mirror ──
    async def get_mirror_raw(self):
        return await self._get("port_mirror.json")

    async def get_mirror(self):
        raw = await self.get_mirror_raw()
        monitoring = int(raw.get("MonitoringPortId", 0) or 0)
        ports = []
        for i in range(1, NUM_PORTS + 1):
            p = raw.get(f"Port_{i}", {})
            ports.append({
                "port": self.to_user(i),
                "ingress": p.get("Ingress_Status") == "Enabled",
                "egress": p.get("Egress_Status") == "Enabled",
            })
        ports.sort(key=lambda x: x["port"])
        # the firmware keeps the last destination after mirroring is switched off,
        # so "enabled" means at least one source still copies traffic
        enabled = bool(monitoring) and any(p["ingress"] or p["egress"] for p in ports)
        return {"monitoring_port": self.to_user(monitoring) if monitoring else 0,
                "enabled": enabled, "ports": ports}

    async def _post_mirror(self, dest: int, sources: list[int], ingress: bool, egress: bool):
        return await self._post("port_mirror.json", {
            "mirroring_port_selection": str(dest),
            "mirrored_port_selection": [str(i) for i in sorted(sources)],
            "Ingress_Status": "1" if ingress else "0",
            "Egress_Status": "0" if not egress else "1",
        })

    async def set_mirror(self, monitoring_port: int, mirrored_ports: list[int],
                         ingress: bool = True, egress: bool = True):
        """Ports are user-facing. monitoring_port 0 turns mirroring off.

        Like the native UI, this sends two requests: the selected sources with the
        requested directions, then every other port with both directions off, so
        sources from a previous session are cleared. Turning off = all ports off on
        the current destination (the firmware keeps the destination itself).
        """
        if monitoring_port:
            dest = self.to_internal(monitoring_port)
            selected = {self.to_internal(p) for p in mirrored_ports if int(p) != int(monitoring_port)}
        else:
            raw = await self.get_mirror_raw()
            dest = int(raw.get("MonitoringPortId", 0) or 0)
            selected = set()
            if not dest:
                return ""  # never configured: nothing to clear
        others = [i for i in range(1, NUM_PORTS + 1) if i != dest and i not in selected]
        result = ""
        if selected:
            result = await self._post_mirror(dest, selected, ingress, egress)
        if others:
            await self._post_mirror(dest, others, False, False)
        return result

    # ── EEE ──
    async def get_eee(self):
        return await self._get("eee_config.json")

    async def set_eee(self, enabled: bool):
        return await self._post("eee_config.json", {"eee": "on" if enabled else "off"})

    # ── MAC Table ──
    async def get_dynamic_macs(self, search: str | None = None):
        if search:
            raw = await self._get("mac_search_dynamic_mac_entries.json", params={"mac_search_txt": search})
        else:
            raw = await self._get("mac_get_dynamic_mac_entries.json")
        entries = _parse_mac_entries(raw, self.to_user)
        total = raw.get("total_entries", len(entries)) if isinstance(raw, dict) else len(entries)
        return {"entries": entries, "total": total}

    async def get_static_macs(self):
        raw = await self._get("mac_get_static_mac_entries.json")
        return _parse_mac_entries(raw, self.to_user)

    async def add_static_mac(self, mac: str, port: int, fid: int = 0):
        internal = self.to_internal(port)
        await self._post("mac_add_static_mac_entries.json", {
            "mac-input": mac,
            "port-input": str(internal),
            "fid-input": str(fid),
        })
        return await self._post("mac_save_static_mac_entries.json", {})

    async def delete_static_mac(self, data: dict):
        """Forward the delete request, translating a user-facing 'port' if present."""
        payload = dict(data)
        if "port" in payload:
            payload["port-input"] = str(self.to_internal(payload.pop("port")))
        await self._post("mac_delete_static_mac_entries.json", payload)
        return await self._post("mac_save_static_mac_entries.json", {})

    async def clear_dynamic_macs(self):
        return await self._post("mac_clear_dynamic_mac_entries.json", {})

    async def close(self):
        self.closed = True
        await self.client.aclose()
