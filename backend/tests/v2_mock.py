"""The VLAN handlers of a 2.0.0.x switch, as decoded from the firmware's web UI and handler code
(see docs: one 802.1Q table of up to 100 VLANs, a PVID and frame type per port)."""
import json

import httpx

PORTS = range(1, 11)


class V2Vlans:
    def __init__(self, mock, table=None, pvids=None, max_vlans=100, read_layout="padded", write_layout="padded"):
        self.mock = mock
        # port_states as read: "padded" = PortNum+1 entries, entry p for port p (the image's
        # firmware); "plain" = PortNum entries, entry 0 for port 1 (2.0.0.3)
        self.read_layout = read_layout
        # where a write's port_states holds port p: entry p ("padded", the web page's layout) or
        # entry p-1 ("plain", never seen; SwitchPilot must detect it rather than move every port)
        self.write_layout = write_layout
        # {vid: {"name": str, "states": {port: 0|1|2}}}: 0 not a member, 1 untagged, 2 tagged
        self.table = table if table is not None else {1: {"name": "", "states": {p: 1 for p in PORTS}}}
        self.pvids = pvids if pvids is not None else {p: 1 for p in PORTS}
        self.frames = {p: 0 for p in PORTS}
        self.max_vlans = max_vlans
        self.refuse = set()  # VLAN IDs the switch silently refuses to write (still answers 200)
        self.refuse_pvid = set()  # ports whose PVID writes it silently ignores (still answers 200)
        for name in ("tag_vlan.json", "tag_vlan_cfg.json"):
            mock.responders[name] = self.tag_vlan
        for name in ("port_vlan.json", "port_vlan_cfg.json"):
            mock.responders[name] = self.port_vlan
        mock.responders["all_port_pvid.json"] = self.all_port_pvid

    # GET tag_vlan.json: a Server-Sent-Events stream, one VLAN per event
    def stream(self) -> str:
        events = [{"PortNum": 10}]
        for vid in sorted(self.table):
            e = self.table[vid]
            states = [e["states"].get(p, 0) for p in PORTS]
            pvids = [self.pvids[p] for p in PORTS]
            if self.read_layout == "padded":
                states, pvids = [0] + states, [12345] + pvids
            events.append({"vlan_id": vid, "vlan_name": e["name"], "port_states": states, "port_pvids": pvids})
        return "".join(f"data: {json.dumps(ev, separators=(',', ':'))}\n\n" for ev in events)

    def tag_vlan(self, request):
        if request.method == "GET":
            return httpx.Response(200, text=self.stream(), headers={"Content-Type": "text/event-stream"})
        if len(request.content) > 1023:
            return httpx.Response(400, text="Bad Request: Invalid request body data")
        body = json.loads(request.content)
        deleted = body.get("deletedVlans") or []
        if deleted:  # updatedVlans is ignored when deletedVlans is not empty
            for vid in deleted:
                if not isinstance(vid, int):
                    continue  # a string ID reads as 0
                if vid == 1 or vid in self.pvids.values() or vid in self.refuse:
                    continue  # "Default PVID %d is not allowed to delete": logged, still 200
                self.table.pop(vid, None)
            return None
        for item in body.get("updatedVlans") or []:
            vid = int(item["vlan_id"]) if isinstance(item.get("vlan_id"), str) else None
            if vid is None or vid in self.refuse or not 1 <= vid <= 4094:
                continue
            if vid not in self.table and len(self.table) >= self.max_vlans:
                continue
            states = item.get("port_states") or []
            shift = 0 if self.write_layout == "padded" else 1

            def entry(p):  # a missing or non-number entry is "not a member"
                i = p - shift
                return states[i] if 0 <= i < len(states) and isinstance(states[i], int) else 0
            new = {p: entry(p) for p in PORTS}
            old = self.table.get(vid, {}).get("states", {})
            for p in PORTS:  # a port is never dropped from the VLAN that is its PVID
                if new[p] == 0 and self.pvids[p] == vid and old.get(p):
                    new[p] = old[p]
            self.table[vid] = {"name": item.get("vlan_name", "")[:16], "states": new}
        return None  # recorded by the mock, answered 200

    def port_vlan(self, request):
        if request.method == "GET":
            return httpx.Response(200, json={"PortNum": 10, **{f"Port_{p}": {"Port_Id": p, "PVID": self.pvids[p],
                                                                             "Frame_Type": self.frames[p]} for p in PORTS}})
        body = json.loads(request.content)
        keys = ("port_based_vlan_frame_type", "port_based_vlan_pvid_input", "port_based_vlan_selection")
        if any(k not in body for k in keys):
            return httpx.Response(400, text="Missing required JSON fields")
        if not isinstance(body[keys[2]], list) or not all(isinstance(body[k], str) for k in keys[:2]):
            return httpx.Response(400, text="Invalid JSON format")
        pvid, frame = int(body[keys[1]]), int(body[keys[0]])
        if not all(isinstance(port, str) for port in body[keys[2]]):  # checked before anything is applied
            return httpx.Response(400, text="Invalid port value")
        for port in body[keys[2]]:
            if int(port) in self.refuse_pvid:
                continue  # "Failed to config for port": logged, still 200
            self.pvids[int(port)] = pvid
            self.frames[int(port)] = frame
        return None

    def all_port_pvid(self, request):
        return httpx.Response(200, json={"port_pvids": [0] + [self.pvids[p] for p in PORTS]})


def _strings(body: dict, *keys) -> bool:
    """The 2.0.0.x handlers read these values as strings (a number reads as nothing)."""
    return all(isinstance(body[k], str) for k in keys if k in body)


class V2L2:
    """LAG, STP, loop detection, storm control, IGMP, mirroring and the MAC tables of a 2.0.0.x
    switch, as its handlers read and answer them (see the firmware notes in docs). Every POST
    is also recorded by the mock; `saved` counts save_all_configs.json calls."""

    STORM_KEYS = {"broadcast": "sctrl_bcast", "multicast": "sctrl_mcast",
                  "unknown_unicast": "sctrl_unucast", "unknown_multicast": "sctrl_unmcast"}

    def __init__(self, mock, dynamic=None):
        self.mock = mock
        self.lag = {p: {"type": 0, "priority": 128, "timeout": 0, "group": 0} for p in PORTS}
        self.system_priority = 32768
        self.stp = {"enable": 0, "mode": "RSTP", "edges": set()}
        self.loop = {"cPrev": "off", "detect": 0, "interval": 10, "recover": 5, "violations": set()}
        self.storm = {p: {k: 0 for k in self.STORM_KEYS.values()} for p in PORTS}
        self.igmp = {"igmp": "off", "fast_leave": "on", "report_flood": "on"}
        self.mirror = {"dest": 1, "flags": {p: [False, False] for p in PORTS}}
        # [(mac, vlan, port, static)], in hardware order
        self.macs = list(dynamic or [])
        self.cursor = 0  # one read position for the whole switch
        self.has_next = True  # mac_get_next_dynamic_mac_entries.json exists on this build
        self.ignore = set()  # endpoints that answer 200 but change nothing
        self.storm_refuse = set()  # storm types the switch answers 200 for but does not apply
        self.saved = 0
        self.static_flash_wiped = False
        for name, fn in (("port_trunk_cfg.json", self.trunk), ("stp.json", self.stp_json),
                         ("port_lock_cfg.json", self.lock), ("port_loop_status.json", self.loop_status),
                         ("storm_ctrl_cfg.json", self.storm_json), ("igmp_config.json", self.igmp_json),
                         ("port_mirror.json", self.mirror_json), ("save_all_configs.json", self.save),
                         ("mac_get_dynamic_mac_entries.json", self.mac_first),
                         ("mac_get_next_dynamic_mac_entries.json", self.mac_next),
                         ("mac_get_static_mac_entries.json", self.mac_static),
                         ("mac_add_static_mac_entries.json", self.mac_add),
                         ("mac_delete_static_mac_entries.json", self.mac_delete),
                         ("mac_save_static_mac_entries.json", self.mac_save),
                         ("mac_clear_dynamic_mac_entries.json", self.mac_clear)):
            mock.responders[name] = fn

    def _body(self, request):
        return json.loads(request.content or b"{}")

    def _skip(self, request):
        return request.url.path.lstrip("/") in self.ignore

    def save(self, request):
        self.saved += 1
        return None

    # LAG: GET numbers; POST flat strings, a port without portTypeId_N is left as it is
    def trunk(self, request):
        if request.method == "GET":
            return httpx.Response(200, json={"PortNum": 10, "system_priority": self.system_priority, **{
                f"Port_{p}": {f"portTypeId_{p}": c["type"], f"portPriorityId_{p}": c["priority"] or 128,
                              f"lacpTimeoutId_{p}": c["timeout"], f"Port_{p}_grpInd": c["group"],
                              f"Port_{p}_state": 1 if p in (1, 9) else 0} for p, c in self.lag.items()}})
        body = self._body(request)
        if not _strings(body, *body):
            return httpx.Response(400, text="Bad Request")
        if self._skip(request):
            return None
        if "system_priority" in body:
            self.system_priority = int(body["system_priority"])
        for p in PORTS:
            if f"portTypeId_{p}" not in body:
                continue
            self.lag[p] = {"type": int(body[f"portTypeId_{p}"]) & 3,
                           "priority": int(body.get(f"portPriorityId_{p}", "128")),
                           "timeout": int(body.get(f"lacpTimeoutId_{p}", "0")),
                           "group": int(body.get(f"Port_{p}_grpInd", "0")) & 31}
        return None

    # STP: the edge flag reads as the port's bit. Every POST starts from a cleared state (a missing
    # stp_enable is off, a missing mode is RSTP) and rewrites the whole edge set. With STP off a
    # read shows RSTP and wipes the edge ports.
    def stp_json(self, request):
        st = self.stp
        if request.method == "GET":
            if not st["enable"]:
                st["edges"] = set()
            mode = "STP" if st["enable"] and st["mode"] == "STP" else "RSTP"
            return httpx.Response(200, json={"stp_enable": str(st["enable"]), "stp_rstp_mode": mode,
                                             "num_ports": "10", **{f"Port_{p}": {
                                                 f"Stp_Edge_{p}": str(2 ** p if p in st["edges"] else 0),
                                                 f"Stp_Status_{p}": "Forward", f"Hw_Port_Id_{p}": f"Port {p}"} for p in PORTS}})
        body = self._body(request)
        if self._skip(request):
            return None
        enable = body.get("stp_enable")
        st["enable"] = 1 if isinstance(enable, str) and enable != "0" else 0
        st["mode"] = "STP" if body.get("stp_rstp_mode") == "STP" else "RSTP"
        st["edges"] = {p for p in PORTS if body.get(f"psel_cbox{p}") == "on"}
        return None

    # Loop: global; cPrev not "on" and a missing detect_enable both read as off; a timer left out
    # keeps its stored value; with detection off both timers read "0"
    def lock(self, request):
        lp = self.loop
        if request.method == "GET":
            on = bool(lp["detect"])
            return httpx.Response(200, json={"PortNum": "10", "cPrev": lp["cPrev"], "detect_enable": "1" if on else "0",
                                             "time_interval": str(lp["interval"] if on else 0),
                                             "recover_time": str(lp["recover"] if on else 0),
                                             **{f"Port_{p}": {f"Violdetd_{p}": "1" if p in lp["violations"] else "0"}
                                                for p in PORTS}})
        body = self._body(request)
        if self._skip(request):
            return None
        for key, field in (("recover_time", "recover"), ("time_interval", "interval")):
            if isinstance(body.get(key), str):
                lp[field] = int(body[key])
        lp["cPrev"] = "on" if body.get("cPrev") == "on" else "off"
        lp["detect"] = 1 if isinstance(body.get("detect_enable"), str) and int(body["detect_enable"]) else 0
        return None

    def loop_status(self, request):
        return httpx.Response(200, json={"PortNum": "10", **{f"Violdetd_{p}": "1" if p in self.loop["violations"] else "0"
                                                             for p in PORTS}})

    # Storm control: one port and one traffic type per POST, numbers, Mbps
    def storm_json(self, request):
        if request.method == "GET":
            return httpx.Response(200, json={"portnum": 10, "ports": [{**self.storm[p], "port_id": p} for p in PORTS]})
        body = self._body(request)
        if any(k not in body for k in ("port", "rate", "state", "storm_type")):
            return httpx.Response(400, text="Missing JSON keys")
        if body["storm_type"] not in self.STORM_KEYS:
            return httpx.Response(400, text="Invalid storm_type")
        if not all(isinstance(body[k], int) for k in ("port", "rate", "state")):
            return httpx.Response(400, text="Bad Request")  # a string reads as 0 on the switch
        if self._skip(request) or body["storm_type"] in self.storm_refuse:
            return None
        self.storm[body["port"]][self.STORM_KEYS[body["storm_type"]]] = body["rate"] if body["state"] else 0
        return None

    # IGMP: answers fast_leave/report_flood, reads fast-leave/report-flood; a missing key is off
    def igmp_json(self, request):
        if request.method == "GET":
            return httpx.Response(200, json=dict(self.igmp))
        body = self._body(request)
        if self._skip(request):
            return None
        self.igmp = {"igmp": "on" if body.get("igmp") == "on" else "off",
                     "fast_leave": "on" if body.get("fast-leave") == "on" else "off",
                     "report_flood": "on" if body.get("report-flood") == "on" else "off"}
        return None

    # Mirroring: the listed sources get the directions, the destination is skipped if listed
    def mirror_json(self, request):
        m = self.mirror
        if request.method == "GET":
            return httpx.Response(200, json={"PortNum": "10", "MonitoringPortId": str(m["dest"]), **{
                f"Port_{p}": {"Port_Id": str(p), "Ingress_Status": "Enabled" if m["flags"][p][0] else "Disabled",
                              "Egress_Status": "Enabled" if m["flags"][p][1] else "Disabled"} for p in PORTS}})
        body = self._body(request)
        if self._skip(request):
            return None
        m["dest"] = int(body["mirroring_port_selection"])
        for src in body["mirrored_port_selection"]:
            if int(src) != m["dest"]:
                m["flags"][int(src)] = [body["Ingress_Status"] == "1", body["Egress_Status"] == "1"]
        return None

    # MAC tables: 50 dynamic entries per answer, 64 static; one read position for the switch
    def _entries(self, static: bool, start: int, size: int):
        rows = [e for e in self.macs if e[3] == static]
        page = rows[start:start + size]
        prefix = "Static" if static else "Dynamic"
        out = {}
        for i, (mac, vlan, port, _) in enumerate(page):
            item = {f"{prefix}_idx": start + i + 1, f"{prefix}_mac_addr": mac, f"{prefix}_vlan_id": vlan,
                    f"{prefix}_fid": 0, f"{prefix}_portid": port}
            if not static:
                item["Dynamic_age_timer"] = 200
            out[f"Idx_{i}"] = item
        out["total_entries"] = len(page)
        return out, len(rows)

    def mac_first(self, request):
        page, _ = self._entries(False, 0, 50)
        self.cursor = page["total_entries"]
        return httpx.Response(200, json=page)

    def mac_next(self, request):
        if not self.has_next:
            return httpx.Response(404, text="Not Found")
        page, count = self._entries(False, self.cursor, 50)
        if not page["total_entries"]:  # past the end: back to the first entries
            page, _ = self._entries(False, 0, 50)
            self.cursor = 0
        self.cursor += page["total_entries"]
        return httpx.Response(200, json=page)

    def mac_static(self, request):
        self.cursor = 0
        page, _ = self._entries(True, 0, 64)
        return httpx.Response(200, json=page)

    def mac_add(self, request):
        body = self._body(request)
        if any(k not in body for k in ("mac-input", "port-input", "vlan-input")):
            return httpx.Response(400, text="Bad Request: Missing required fields")
        if not _strings(body, "mac-input", "port-input", "vlan-input"):
            return httpx.Response(400, text="Bad Request: Invalid MAC address")
        mac = body["mac-input"]
        if len(mac) != 17 or any(mac[i] != ":" for i in (2, 5, 8, 11, 14)):
            return httpx.Response(400, text="Bad Request: Invalid MAC address")
        vlan = int(body["vlan-input"])
        if not 1 <= vlan <= 4094:
            return httpx.Response(400, text="Bad Request: Invalid VLAN ID")
        if self._skip(request):
            return None
        self.macs = [e for e in self.macs if (e[0], e[1]) != (mac.upper(), vlan)]
        self.macs.append((mac.upper(), vlan, int(body["port-input"]), True))
        return None

    def mac_delete(self, request):
        body = self._body(request)
        macs, vlans = body.get("mac_addr_txt"), body.get("vlan_text")
        if macs is None or vlans is None:
            return httpx.Response(400, text="Bad Request: Missing required fields")
        if not isinstance(macs, list) or not isinstance(vlans, list) or len(macs) != len(vlans) or not macs:
            return httpx.Response(400, text="Bad Request: Array lengths do not match or are empty")
        if self._skip(request):
            return None
        for mac, vlan in zip(macs, vlans):  # not found or invalid: logged, still 200
            if isinstance(mac, str) and isinstance(vlan, str):
                self.macs = [e for e in self.macs if not (e[3] and (e[0], e[1]) == (mac.upper(), int(vlan)))]
        return None

    def mac_save(self, request):
        self.static_flash_wiped = True  # rewrites the saved entries from the (empty) body
        return None

    def mac_clear(self, request):
        self.macs = [e for e in self.macs if e[3]]
        return None
