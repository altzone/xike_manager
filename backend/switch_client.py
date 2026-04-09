"""Xikestor SKS3200-8E2X API Client"""
import hashlib
import httpx

# Port mapping: user-facing port ↔ internal port
# Ports 9 and 10 are swapped internally
PORT_MAP = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 10, 10: 9}
PORT_MAP_REV = {v: k for k, v in PORT_MAP.items()}

# Hardware limits
MAX_FID = 63          # PVID/native VLAN max
MAX_TAG_ENTRIES = 111  # Tag VLAN table max entries
MAX_VLAN_ID = 4095    # 802.1Q max


class SwitchClient:
    def __init__(self, ip: str, username: str = "admin", password: str = "admin"):
        self.base = f"http://{ip}:80"
        self.username = username
        self.password = password
        self.client = httpx.AsyncClient(timeout=10)
        self._logged_in = False

    async def login(self) -> bool:
        usr_md5 = hashlib.md5(self.username.encode()).hexdigest()
        pwd_md5 = hashlib.md5(self.password.encode()).hexdigest()
        r = await self.client.get(f"{self.base}/authorize", params={
            "loginusr": usr_md5, "loginpwd": pwd_md5
        })
        self._logged_in = "setup.html" in r.text
        return self._logged_in

    async def _ensure_login(self):
        if not self._logged_in:
            await self.login()

    async def _get(self, endpoint: str):
        await self._ensure_login()
        r = await self.client.get(f"{self.base}/{endpoint}")
        if "login.html" in r.text:
            await self.login()
            r = await self.client.get(f"{self.base}/{endpoint}")
        return r.json()

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

    # ── Ports ──
    async def get_ports(self):
        raw = await self._get("port_setting_load.json")
        ports = []
        for i in range(1, int(raw["PortNum"]) + 1):
            p = raw[f"Port_{i}"]
            user_port = PORT_MAP_REV.get(i, i)
            ports.append({
                "port": user_port,
                "internal_port": i,
                "type": "SFP+" if user_port >= 9 else "RJ45 2.5G",
                "status": p[f"Port_Status"],
                "speed_config": p[f"Spd_Duplex_Cfg"],
                "speed_actual": p[f"Spd_Duplex_Actual"],
                "flow_ctrl_config": p[f"Flow_Ctrl_Cfg"],
                "flow_ctrl_actual": p[f"Flow_Ctrl_Actual"],
            })
        ports.sort(key=lambda x: x["port"])
        return ports

    async def set_port(self, port: int, enabled: bool = True, speed: str = "Auto", flow_ctrl: str = "On"):
        internal = PORT_MAP[port]
        return await self._post("apply_user_port_setting.json", {
            f"Port_Status_{internal}": "Enabled" if enabled else "Disabled",
            f"Spd_Duplex_Cfg_{internal}": speed,
            f"Flow_Ctrl_Cfg_{internal}": flow_ctrl,
        })

    async def save_ports(self):
        return await self._post("save_user_port_setting.json", {})

    async def get_port_stats(self):
        raw = await self._get("port_statistics.json")
        stats = []
        for i in range(1, int(raw["PortNum"]) + 1):
            p = raw[f"Port_{i}"]
            user_port = PORT_MAP_REV.get(i, i)
            stats.append({
                "port": user_port,
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
            user_port = PORT_MAP_REV.get(i, i)
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
                "port": user_port, "enabled": enabled,
                "pvid": pvid, "mode": mode,
            })
        result.sort(key=lambda x: x["port"])
        return result

    async def set_port_vlans(self, configs: list[dict]):
        """configs: [{"port": 1, "mode": "access"|"trunk"|"flat", "pvid": 10}, ...]"""
        data = {}
        for cfg in configs:
            internal = PORT_MAP[cfg["port"]]
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
                internal_port = int(e[f"pP_{i}"])
                user_port = PORT_MAP_REV.get(internal_port, internal_port)
                entries.append({
                    "entry": i,
                    "port": user_port,
                    "vlan_id": int(e[f"oVid_{i}"]),
                    "tag_type": "single" if e[f"tT_{i}"] == "0" else "double",
                })
        return entries

    async def set_tag_vlans(self, entries: list[dict]):
        """entries: [{"entry": 0, "port": 7, "vlan_id": 10}, ...]"""
        data = {}
        for e in entries:
            idx = e["entry"]
            internal = PORT_MAP[e["port"]]
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
    async def get_lag(self):
        return await self._get("port_trunk_cfg.json")

    async def set_lag(self, data: dict):
        return await self._post("port_trunk_cfg.json", data)

    # ── STP ──
    async def get_stp(self):
        raw = await self._get("stp.json")
        ports = []
        for i in range(1, int(raw["num_ports"]) + 1):
            user_port = PORT_MAP_REV.get(i, i)
            ports.append({
                "port": user_port,
                "edge": raw[f"Port_{i}"][f"Stp_Edge_{i}"] == "1",
                "status": raw[f"Port_{i}"][f"Stp_Status_{i}"],
            })
        ports.sort(key=lambda x: x["port"])
        return {
            "enabled": raw["stp_enable"] == "1",
            "mode": "rstp" if raw["stp_mode"] == "1" else "stp",
            "ports": ports,
        }

    async def set_stp(self, data: dict):
        return await self._post("stp.json", data)

    # ── Loop Detection ──
    async def get_loop_status(self):
        return await self._get("port_loop_status.json")

    async def get_loop_config(self):
        return await self._get("port_lock_cfg.json")

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
    async def get_mirror(self):
        return await self._get("port_mirror.json")

    async def set_mirror(self, data: dict):
        return await self._post("port_mirror.json", data)

    # ── EEE ──
    async def get_eee(self):
        return await self._get("eee_config.json")

    async def set_eee(self, enabled: bool):
        return await self._post("eee_config.json", {"eee": "on" if enabled else "off"})

    # ── MAC Table ──
    async def get_dynamic_macs(self):
        return await self._get("mac_get_dynamic_mac_entries.json")

    async def get_static_macs(self):
        return await self._get("mac_get_static_mac_entries.json")

    async def clear_dynamic_macs(self):
        return await self._post("mac_clear_dynamic_mac_entries.json", {})

    async def close(self):
        await self.client.aclose()
