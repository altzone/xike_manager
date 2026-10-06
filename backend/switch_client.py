"""Xikestor SKS3200-8E2X API Client"""
import asyncio
import collections
import contextlib
import functools
import hashlib
import json
import re
import time

import httpx

# Sentinel so _get can distinguish "no default supplied" from default=None
_UNSET = object()

# Hardware limits
NUM_PORTS = 10         # 8x 2.5G RJ45 (1-8) + 2x 10G SFP+ (9-10)
SFP_PORTS = (9, 10)
MAX_FID = 63           # PVID/native VLAN max
MAX_TAG_ENTRIES = 111  # Tag VLAN table max entries
MAX_VLAN_ID = 4094     # 802.1Q max usable VID
V2_MAX_VLANS = 100      # 2.0.0.x: slots in the 802.1Q table
V2_VLAN_NAME_MAX = 16   # 2.0.0.x: bytes kept of a VLAN name
V2_BODY_MAX = 1023      # 2.0.0.x: bytes the VLAN handlers read from a request body
V2_MAC_PAGE = 50        # 2.0.0.x: dynamic MAC entries per answer (mac_get_next_... gives the next ones)
V2_MAC_MAX_PAGES = 40   # read at most this many pages of the dynamic table (2000 entries)
V2_STORM_MAX = 1000     # 2.0.0.x: highest storm control rate, Mbps
# 2.0.0.x storm control: traffic type as the switch names it in a request -> its key in the reading
STORM_TYPES = {"broadcast": "sctrl_bcast", "multicast": "sctrl_mcast",
               "unknown_unicast": "sctrl_unucast", "unknown_multicast": "sctrl_unmcast"}
MANAGEMENT_PORT = 1    # the port SwitchPilot usually reaches the switch through


class InvalidPortError(ValueError):
    """A port number outside 1..NUM_PORTS (or not a number) was given."""


class SwitchError(Exception):
    """The switch refused or garbled a request (bad credentials, HTTP error, odd body)."""


class SwitchFormatError(SwitchError):
    """The switch answered, but not in the format this client reads (typically a page that
    works differently on 2.0.0.x firmware)."""


def _parsed(endpoint: str):
    """Report a payload this client cannot read as a SwitchFormatError (HTTP 502 with the
    endpoint and firmware) instead of an unhandled KeyError/TypeError (HTTP 500)."""
    def wrap(fn):
        @functools.wraps(fn)
        async def inner(self, *args, **kwargs):
            try:
                return await fn(self, *args, **kwargs)
            except (SwitchError, json.JSONDecodeError):
                raise
            except (KeyError, IndexError, TypeError, AttributeError, ValueError) as e:
                if self.fw_ver is None:  # name the firmware in the message (one extra read, failures only)
                    try:
                        await self.get_status()
                    except Exception:
                        pass
                fw = f" on firmware {self.fw_ver}" if self.fw_ver else ""
                raise SwitchFormatError(f"{endpoint}: the switch answered in a format SwitchPilot does not "
                                        f"read yet{fw} ({e.__class__.__name__}: {e})") from e
        return inner
    return wrap


def default_bridge(vlan_id: int) -> int:
    """Bridge (FID) a tagged VLAN joins: the same bridge its access ports use (SwitchPilot
    writes FID = VLAN ID for those), or bridge 0 when the VID is above the FID range."""
    return vlan_id if 0 < vlan_id <= MAX_FID else 0


def firmware_line(fw_ver: str | None) -> int | None:
    """Major version of a firmware string ("1.0.0.4" -> 1, "V2.0.0.2" -> 2), None if unreadable."""
    m = re.match(r"\D*(\d+)\.", str(fw_ver or "").strip())
    return int(m.group(1)) if m else None


def default_swap_sfp(fw_ver: str | None) -> bool | None:
    """Whether a switch running this firmware numbers the SFP+ cages the other way round.

    Observed so far: 1.0.0.x (V1) firmware swaps them (SKS3200-8E2X 1.0.0.4 hw A0, and the two
    other V1 tools hardcode it), 2.0.0.x (V2) does not (SKS3200-8E2X-P 2.0.0.x hw A0, issue #3;
    no V2 tool swaps). None when the version is unknown: the caller decides.
    """
    line = firmware_line(fw_ver)
    if line is None:
        return None
    return line == 1


def build_port_map(swap_sfp: bool) -> dict[int, int]:
    """user-facing port -> internal index used in the switch's JSON.

    On some units the two SFP+ cages are wired the other way round from the
    firmware's own numbering (JSON index 9 is the cage labelled 10 on the front
    panel), on others they match (issue #3). It follows the firmware line as far as we
    know (see default_swap_sfp), but is kept as a per-switch setting so a unit that
    differs can be corrected.
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
        for suffix in suffixes:  # in order of preference
            for key, value in entry.items():
                if key.lower().endswith(suffix):
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
            port = port_raw  # 2.0.0.x writes "1, 2" for an entry on several ports
        vlan = field(e, "vlan_id", default=None)
        entries.append({
            "idx": str(field(e, "_idx", default="")),
            "mac": mac,
            "port": port,
            "fid": str(field(e, "_fid", "vlan_id", default="0")),
            # 2.0.0.x keys its entries by VLAN ID (static ones are added and deleted by it)
            "vlan": int(vlan) if str(vlan).isdigit() else None,
            "age": str(field(e, "age_timer", default="")),
        })
    return entries


def _mac_hex(text: str) -> str | None:
    """Lower-case hex digits of a MAC address or fragment, any separators; None if not hex."""
    digits = re.sub(r"[\s:.\-]", "", text.lower())
    return digits if re.fullmatch(r"[0-9a-f]+", digits) else None


def _loop_form_v2(cfg: dict) -> dict:
    """The 2.0.0.x loop settings as its page posts them back: the prevention box (left out when
    off, which the switch reads as off) and the two timers."""
    form = {k: str(cfg[k]) for k in ("time_interval", "recover_time") if str(cfg.get(k, "")) != ""}
    if cfg.get("cPrev") == "on":
        form["cPrev"] = "on"
    return form


def _chunks_within(items: list, wrap, limit: int):
    """Split items into consecutive lists whose wrapped compact JSON stays within limit bytes."""
    chunk = []
    for item in items:
        if chunk and len(json.dumps(wrap(chunk + [item]), separators=(",", ":")).encode()) > limit:
            yield chunk
            chunk = []
        if len(json.dumps(wrap([item]), separators=(",", ":")).encode()) > limit:
            raise ValueError("A VLAN entry does not fit in one request")
        chunk.append(item)
    if chunk:
        yield chunk


def _alert_key(text: str) -> str | None:
    """The {"alert_key": ...} some 2.0.0.x handlers answer with, None for an empty or other body."""
    try:
        data = json.loads(text) if text and text.strip() else None
    except ValueError:
        return None
    return data.get("alert_key") if isinstance(data, dict) else None


class SwitchClient:
    def __init__(self, ip: str, username: str = "admin", password: str = "admin",
                 swap_sfp: bool = False, transport: httpx.AsyncBaseTransport | None = None):
        self.fw_ver: str | None = None  # from status.json; "" when the switch does not report it
        self.configure(ip, username, password)
        self.set_port_mapping(swap_sfp)
        # trust_env=False: a switch on the LAN must never be reached through an HTTP_PROXY
        # inherited from the container's environment
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5), transport=transport, trust_env=False)
        self.closed = False
        self._login_lock = asyncio.Lock()
        self._last_login = 0.0
        # 2.0.0.x keeps one read position for both MAC tables (per switch, not per session), which
        # its save also moves
        self._mac_lock = asyncio.Lock()
        # 2.0.0.x serves one connection at a time and queues only a few (CivetWeb num_threads=1,
        # connection_queue=2, no keep-alive): its requests are sent one after another
        self._v2_gate = asyncio.Semaphore(1)
        self._vlan_layout_lock = asyncio.Lock()

    def _gate(self):
        """The one-request-at-a-time gate on 2.0.0.x (known once status.json was read), else no gate."""
        return self._v2_gate if (firmware_line(self.fw_ver) or 1) >= 2 else contextlib.nullcontext()

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
            self.fw_ver = None  # another switch may answer at the new address
            self._vlan_layout = None  # see vlan_write_layout
            self._vlan_states_len = None

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
        async with self._gate():
            r = await self.client.get(f"{self.base}/authorize", params={
                "loginusr": usr_md5, "loginpwd": pwd_md5
            })
        # Success is a redirect to setup.html (1.0.0.x) or index.html?page= (2.0.0.x);
        # a bad password is a 200 that redirects to login.html.
        self._logged_in = r.status_code == 200 and "login.html" not in r.text
        self._last_login = time.monotonic()
        return self._logged_in

    async def _ensure_login(self):
        # one login at a time: concurrent requests share one cookie jar and would
        # otherwise each log in and invalidate each other's session
        async with self._login_lock:
            if not self._logged_in and not await self.login():
                raise SwitchError(f"Login to switch {self.ip} failed (check its credentials)")

    async def _relogin(self):
        observed = time.monotonic()  # when this request saw the stale session
        async with self._login_lock:
            if self._logged_in and self._last_login > observed:
                return  # another request re-logged in meanwhile: share that session
            self._logged_in = False
            if not await self.login():
                raise SwitchError(f"Login to switch {self.ip} failed (check its credentials)")

    async def _raw_get(self, endpoint: str, params: dict | None = None) -> httpx.Response:
        async with self._gate():
            try:
                return await self.client.get(f"{self.base}/{endpoint}", params=params)
            except httpx.TimeoutException:
                raise
            except httpx.TransportError:
                # the switch drops the pooled connection after /authorize on some firmware;
                # a GET is safe to send again on a fresh connection (a POST never is)
                return await self.client.get(f"{self.base}/{endpoint}", params=params)

    async def _get(self, endpoint: str, params: dict | None = None, default=_UNSET):
        await self._ensure_login()
        r = await self._raw_get(endpoint, params)
        if "login.html" in r.text:
            await self._relogin()
            r = await self._raw_get(endpoint, params)
            if "login.html" in r.text:
                self._logged_in = False
                raise SwitchError(f"{endpoint}: the switch rejected the session right after login")
        if r.status_code == 404 and default is not _UNSET:
            return default  # endpoint removed in this firmware
        if r.status_code != 200:
            raise SwitchError(f"{endpoint}: switch answered HTTP {r.status_code}")
        try:
            return decode_payload(r.text)
        except json.JSONDecodeError:
            # Endpoints removed in newer firmware (time, SNTP and EEE on 1.0.0.5+)
            # answer with an empty body. Callers that can live without the data
            # pass a default; otherwise surface the error as before.
            if default is not _UNSET:
                return default
            raise

    async def _post(self, endpoint: str, data: dict):
        await self._ensure_login()
        # compact JSON, like the native UI's axios: some 2.0.0.x handlers read at most 47 or 255 bytes
        body = json.dumps(data, separators=(",", ":"))
        headers = {"Content-Type": "application/json"}
        async with self._gate():
            r = await self.client.post(f"{self.base}/{endpoint}", content=body, headers=headers)
        if "login.html" in r.text:
            await self._relogin()
            async with self._gate():
                r = await self.client.post(f"{self.base}/{endpoint}", content=body, headers=headers)
            if "login.html" in r.text:
                # the write was dropped: never report it as applied
                self._logged_in = False
                raise SwitchError(f"{endpoint}: the switch rejected the write (session expired)")
        if r.status_code != 200:
            raise SwitchError(f"{endpoint}: switch answered HTTP {r.status_code}")
        return r.text

    # ── System ──
    async def get_status(self):
        status = await self._get("status.json")
        if isinstance(status, dict):
            self.fw_ver = str(status.get("fw_ver") or "")
        return status

    async def firmware_line(self) -> int | None:
        """1 (1.0.0.x) or 2 (2.0.0.x), None when the switch does not say. status.json is read
        once per address; get_status() keeps the cached version current."""
        if self.fw_ver is None:
            await self.get_status()
        return firmware_line(self.fw_ver)

    async def is_v2(self) -> bool:
        return (await self.firmware_line() or 1) >= 2

    async def save_all(self):
        """2.0.0.x: the native UI's single Save button (POST {} -> empty body). Every change made
        on 2.0.0.x lives in the running configuration only until this is called. It walks the MAC
        table to save the static entries, which moves the one read position a MAC table read uses."""
        async with self._mac_lock:
            return await self._post("save_all_configs.json", {})

    async def get_network(self):
        return await self._get("network_settings.json")

    async def set_network_ipv4(self, ip: str, netmask: str, gateway: str, dhcp: bool):
        if await self.is_v2():
            # 2.0.0.x native UI: the address fields are disabled (so left out) when DHCP is on;
            # the switch answers {"alert_key": "alert_success"} or an alert naming the problem
            body = {"dhcp_enable": "1"} if dhcp else {
                "dhcp_enable": "0", "input_ip": ip, "input_netmask": netmask, "input_gateway": gateway or ""}
            text = await self._post("network_settings_ipv4.json", body)
            alert = _alert_key(text)
            if alert and alert != "alert_success":
                raise SwitchError(f"network_settings_ipv4.json: the switch refused the change ({alert})")
            return text
        return await self._post("network_settings_ipv4.json", {
            "input_ip": ip, "input_netmask": netmask,
            "input_gateway": gateway, "dhcp_enable": "1" if dhcp else "0"
        })

    async def set_description(self, desc: str):
        return await self._post("set_des.json", {"input_des": desc})

    # Time/SNTP and EEE (power-saving) config endpoints were removed in switch
    # firmware 1.0.0.5+. On those versions the endpoint no longer exists and the
    # switch answers with an empty body, so `default=None` signals "feature not
    # supported on this firmware" (distinct from a real, empty `{}` payload).
    async def get_time(self):
        return await self._get("systemtime_settings.json", default=None)

    async def set_time(self, time: str, date: str, timezone: str, daylight: str = "0"):
        return await self._post("systemtime_settings.json", {
            "input_time": time, "input_date": date,
            "timezone_offset": timezone, "input_daylight": daylight,
        })

    async def get_sntp(self):
        return await self._get("sntp_setting.json", default=None)

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

    # ── 2.0.0.x VLANs: one 802.1Q table (100 VLANs, a name each), a PVID and frame type per port ──
    async def _get_events(self, endpoint: str) -> list:
        """A 2.0.0.x Server-Sent-Events answer read to its end: one JSON object per `data:` line,
        kept as a list (decode_payload merges objects, which would keep only the last VLAN)."""
        await self._ensure_login()
        r = await self._raw_get(endpoint)
        if "login.html" in r.text:
            await self._relogin()
            r = await self._raw_get(endpoint)
            if "login.html" in r.text:
                self._logged_in = False
                raise SwitchError(f"{endpoint}: the switch rejected the session right after login")
        if r.status_code != 200:
            raise SwitchError(f"{endpoint}: switch answered HTTP {r.status_code}")
        return [json.loads(line[5:].strip()) for line in r.text.splitlines()
                if line.startswith("data:") and line[5:].strip()]

    @_parsed("tag_vlan.json")
    async def get_vlan_table_v2(self) -> dict:
        """{vlan_id: {"name": str, "ports": {user_port: 0|1|2}}}: 0 not a member, 1 untagged, 2 tagged."""
        port_num = NUM_PORTS
        table = {}
        for ev in await self._get_events("tag_vlan.json"):
            if "vlan_id" not in ev:
                port_num = int(ev.get("PortNum", port_num))
                continue
            states = ev.get("port_states") or []
            # PortNum+1 entries, entry p for port p (the image's own page); 2.0.0.3 sends PortNum
            # entries, entry 0 for port 1 (its page puts the unused entry 0 back before reading)
            offset = 0 if len(states) == port_num else 1
            self._vlan_states_len = len(states)
            ports = {}
            for i in range(1, port_num + 1):
                j = i - 1 + offset
                ports[self.to_user(i)] = int(states[j]) if j < len(states) else 0
            table[int(ev["vlan_id"])] = {"name": str(ev.get("vlan_name") or ""), "ports": ports}
        return table

    @_parsed("port_vlan.json")
    async def get_port_vlan_cfg_v2(self) -> dict:
        """{user_port: {"pvid": int, "frame_type": 0 all | 1 tagged only | 2 untagged only}}"""
        raw = await self._get("port_vlan.json")
        return {self.to_user(i): {"pvid": int(raw[f"Port_{i}"]["PVID"]), "frame_type": int(raw[f"Port_{i}"]["Frame_Type"])}
                for i in range(1, int(raw["PortNum"]) + 1)}

    async def vlan_write_layout(self) -> str:
        """How a tag_vlan.json write places the ports in port_states. "padded": PortNum+1 entries,
        entry p for port p, entry 0 unused, which is what the 2.0.0.x web page sends (its code is the
        same on 2.0.0.3). 2.0.0.3 reads its table back with PortNum entries instead, and no write of
        that build was ever captured, so on such a switch SwitchPilot checks it once before touching
        a real VLAN: a VLAN nobody uses gets one tagged port, is read back and deleted ("plain":
        entry p-1 for port p). A wrong guess here would move every port of every VLAN written."""
        async with self._vlan_layout_lock:
            if self._vlan_layout:
                return self._vlan_layout
            table = await self.get_vlan_table_v2()
            if self._vlan_states_len != NUM_PORTS:
                self._vlan_layout = "padded"
                return self._vlan_layout
            free = next((v for v in range(MAX_VLAN_ID, 1, -1) if v not in table), None)
            if free is None or len(table) >= V2_MAX_VLANS:
                raise SwitchError("tag_vlan.json: before its first VLAN change on this firmware SwitchPilot checks "
                                  "how the switch stores VLAN members with a temporary VLAN, and the VLAN table "
                                  "is full: delete one VLAN first")
            probe = 5
            states = [0] * (NUM_PORTS + 1)
            states[probe] = 2
            try:
                await self._post("tag_vlan.json", {"deletedVlans": [], "updatedVlans": [
                    {"port_states": states, "vlan_id": str(free), "vlan_name": "SwitchPilot test"}]})
                seen = (await self.get_vlan_table_v2()).get(free, {}).get("ports", {})
            finally:
                await self._post("tag_vlan.json", {"deletedVlans": [free], "updatedVlans": []})
            if free in await self.get_vlan_table_v2():
                raise SwitchError(f"tag_vlan.json: SwitchPilot could not delete VLAN {free}, created for a moment "
                                  "to check how this firmware stores VLAN members: delete it on the switch")
            tagged = sorted(self.to_internal(p) for p, state in seen.items() if state == 2)
            if tagged == [probe]:
                self._vlan_layout = "padded"
            elif tagged == [probe + 1]:
                self._vlan_layout = "plain"
            else:
                raise SwitchError(f"tag_vlan.json: a test VLAN member written for port {probe} came back as "
                                  f"{tagged or 'no port'}; SwitchPilot does not change VLANs on this firmware")
            return self._vlan_layout

    async def set_vlans_v2(self, entries: list[dict]):
        """entries: [{"vlan_id": 10, "name": "Office", "ports": {user_port: 0|1|2}}]. Each entry
        creates the VLAN or replaces its whole membership and name, as the native VLAN page
        does; sent in as few bodies as the 1023-byte limit allows. The switch answers 200 even
        when it refuses an entry: read the table back to know."""
        plain = await self.vlan_write_layout() == "plain"
        items = []
        for e in entries:
            states = [0] * (NUM_PORTS + 1)  # index 0 unused, like the native UI
            for port, state in e.get("ports", {}).items():
                if state not in (0, 1, 2):
                    raise ValueError(f"Invalid VLAN membership {state!r} for port {port}")
                states[self.to_internal(port)] = int(state)
            if plain:
                states = states[1:]
            name = (e.get("name") or "").encode("utf-8")[:V2_VLAN_NAME_MAX].decode("utf-8", "ignore")
            items.append({"port_states": states, "vlan_id": str(int(e["vlan_id"])), "vlan_name": name})
        for chunk in _chunks_within(items, lambda c: {"deletedVlans": [], "updatedVlans": c}, V2_BODY_MAX):
            await self._post("tag_vlan.json", {"deletedVlans": [], "updatedVlans": chunk})

    async def delete_vlans_v2(self, vlan_ids):
        """Delete VLANs (never VLAN 1, which the switch keeps). Deletes go in their own request:
        the switch ignores updatedVlans when deletedVlans is not empty."""
        ids = sorted({int(v) for v in vlan_ids} - {1})
        if ids:
            await self._post("tag_vlan.json", {"deletedVlans": ids, "updatedVlans": []})

    async def set_pvids_v2(self, pvids: dict, frame_types: dict | None = None):
        """pvids {user_port: vid}. One request per (PVID, frame type), as the native Port VLAN page
        sends one PVID for the selected ports. The switch writes the frame type with every PVID, so
        a port missing from frame_types keeps the one it has (read from the switch)."""
        frame_types = dict(frame_types or {})
        if any(port not in frame_types for port in pvids):
            current = await self.get_port_vlan_cfg_v2()
            frame_types = {port: frame_types.get(port, current.get(port, {}).get("frame_type", 0)) for port in pvids}
        groups: dict[tuple, list] = {}
        for port, vid in pvids.items():
            vid = int(vid)
            if not 1 <= vid <= MAX_VLAN_ID:
                raise ValueError(f"PVID {vid} on port {port} is outside 1-{MAX_VLAN_ID}")
            frame = int(frame_types[port])
            groups.setdefault((vid, frame), []).append(str(self.to_internal(port)))
        for (vid, frame), ports in sorted(groups.items()):
            await self._post("port_vlan.json", {"port_based_vlan_frame_type": str(frame),
                                                "port_based_vlan_pvid_input": str(vid),
                                                "port_based_vlan_selection": sorted(ports, key=int)})

    # ── Ports ──
    @_parsed("port_setting_load.json")
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
        if await self.is_v2():
            return await self.save_all()  # what the 2.0.0.x port page's Save button sends
        return await self._post("save_user_port_setting.json", {})

    @_parsed("port_statistics.json")
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
    @_parsed("port_vlan_cfg.json")
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
        """configs: [{"port": 1, "mode": "access"|"trunk"|"flat"|"unknown", "pvid": 10}, ...]

        Every port in the list is written explicitly: a flat port is sent with its checkbox
        empty, as the native UI's form does, instead of being left out (the firmware treats a
        missing port as unchecked, which used to reset ports the caller did not mention).
        """
        data = {}
        for cfg in configs:
            internal = self.to_internal(cfg["port"])
            mode = cfg.get("mode", "flat")
            pvid = int(cfg.get("pvid", 0))
            if not 0 <= pvid <= MAX_FID:
                raise ValueError(f"PVID {pvid} on port {cfg['port']} is outside 0-{MAX_FID}")
            if mode == "flat":
                data[f"checkbox_{internal}"] = ""
                data[f"fidName_{internal}"] = "0"
                data[f"checkboxUntag_{internal}"] = ""
                data[f"checkboxTag_{internal}"] = ""
                continue
            data[f"checkbox_{internal}"] = "on"
            data[f"fidName_{internal}"] = str(pvid)
            data[f"checkboxUntag_{internal}"] = "on" if mode == "access" else ""
            data[f"checkboxTag_{internal}"] = "on" if mode == "trunk" else ""
        result = await self._post("port_vlan_cfg.json", data)
        if "invalid FID" in result:
            raise ValueError(f"Invalid FID/PVID (max {MAX_FID})")
        return result

    async def save_port_vlans(self):
        return await self._post("save_port_vlan_map.json", {})

    async def reset_vlans(self):
        return await self._post("init_vlan.json", {})

    # ── Tag VLAN (802.1Q) ──
    @_parsed("tag_vlan_cfg.json")
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
                    "bridge": int(e.get(f"bR_{i}", 0) or 0),
                    "tag_type": "single" if e[f"tT_{i}"] == "0" else "double",
                    "inner_vid": int(e.get(f"iVid_{i}", 0) or 0),
                })
        return entries

    async def set_tag_vlans(self, entries: list[dict]):
        """entries: [{"entry": 0, "port": 7, "vlan_id": 10, "bridge": 10}, ...]

        bridge defaults to the VLAN's own bridge (see default_bridge) so tagged frames land
        in the same bridge as the VLAN's access ports.
        """
        data = {}
        for e in entries:
            idx = e["entry"]
            internal = self.to_internal(e["port"])
            vid = int(e["vlan_id"])
            if not 1 <= vid <= MAX_VLAN_ID:
                raise ValueError(f"VLAN ID {vid} is outside 1-{MAX_VLAN_ID}")
            bridge = e.get("bridge")
            if bridge is None:
                bridge = default_bridge(vid)
            data[f"bpCboxName_{idx}"] = "on"
            data[f"vtypeName_{idx}"] = "1" if e.get("tag_type") == "double" else "0"
            data[f"ppName_{idx}"] = str(internal)
            data[f"brName_{idx}"] = str(int(bridge))
            data[f"oVidName_{idx}"] = str(vid)
            data[f"iVidName_{idx}"] = str(int(e.get("inner_vid") or 0))
        return await self._post("tag_vlan_cfg.json", data)

    async def save_tag_vlans(self):
        return await self._post("save_tag_vlan_map.json", {})

    # ── LAG ──
    async def get_lag_raw(self):
        return await self._get("port_trunk_cfg.json")

    @_parsed("port_trunk_cfg.json")
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
    @_parsed("stp.json")
    async def get_stp(self):
        raw = await self._get("stp.json")
        # 2.0.0.x names the mode "STP"/"RSTP" and reads a port's edge flag as its bit (2**i) or "0"
        v2 = "stp_rstp_mode" in raw
        ports = []
        for i in range(1, int(raw["num_ports"]) + 1):
            edge = str(raw[f"Port_{i}"][f"Stp_Edge_{i}"])
            ports.append({
                "port": self.to_user(i),
                "edge": edge not in ("0", "") if v2 else edge == "1",
                "status": raw[f"Port_{i}"][f"Stp_Status_{i}"],
            })
        ports.sort(key=lambda x: x["port"])
        rstp = raw["stp_rstp_mode"] == "RSTP" if v2 else raw["stp_mode"] == "1"
        return {
            "enabled": str(raw["stp_enable"]) == "1",
            "mode": "rstp" if rstp else "stp",
            "ports": ports,
        }

    async def set_stp(self, enabled: bool, mode: str = "stp", edge_ports: list[int] | None = None) -> bool:
        """Returns True when loop detection was turned off to make way for STP (2.0.0.x only)."""
        if await self.is_v2():
            return await self._set_stp_v2(enabled, mode, edge_ports)
        data = {"stp_enable": "1" if enabled else "0", "stp_mode": "1" if mode == "rstp" else "0"}
        if edge_ports is not None:
            edges = {self.to_internal(p) for p in edge_ports}
            for i in range(1, NUM_PORTS + 1):
                data[f"Stp_Edge_{i}"] = "1" if i in edges else "0"
        await self._post("stp.json", data)
        return False

    async def _set_stp_v2(self, enabled: bool, mode: str, edge_ports: list[int] | None) -> bool:
        """2.0.0.x: every stp.json write sets the whole edge-port list (a port left out loses its
        flag), so the current edge ports are sent again unless new ones are given. Its own page
        has loop detection and STP as alternatives: applying STP turns detection off first."""
        if edge_ports is None:
            edge_ports = [p["port"] for p in (await self.get_stp())["ports"] if p["edge"]]
        loop_off = False
        if enabled:
            loop = await self.get_loop_config()
            if str(loop.get("detect_enable")) == "1":
                await self._post("port_lock_cfg.json", {**_loop_form_v2(loop), "detect_enable": "0"})
                loop_off = True
        body = {"stp_enable": "1" if enabled else "0", "stp_rstp_mode": "RSTP" if mode == "rstp" else "STP"}
        for port in sorted({self.to_internal(p) for p in edge_ports}):
            body[f"psel_cbox{port}"] = "on"
        await self._post("stp.json", body)
        return loop_off

    # ── Loop Detection ──
    async def get_loop_status(self):
        return await self._get("port_loop_status.json")

    async def get_loop_config(self):
        return await self._get("port_lock_cfg.json")

    @_parsed("port_lock_cfg.json")
    async def get_loop(self):
        """1.0.0.x: [{port, enabled, violation}] (enabled per port). 2.0.0.x: one setting for the
        whole switch, {"model": "global", enabled, prevention, interval, recovery, ports}."""
        config = await self.get_loop_config()
        status = await self.get_loop_status()
        if "detect_enable" in config:
            return self._loop_v2(config, status)
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

    def _loop_v2(self, cfg: dict, status: dict) -> dict:
        """2.0.0.x: detection on or off for the whole switch (no per-port setting), prevention
        (block the looping port), the check interval (tenths of a second) and the recovery time
        (seconds); the per-port flag only says where a loop was seen."""
        ports = []
        for i in range(1, NUM_PORTS + 1):
            flag = status.get(f"Violdetd_{i}", (cfg.get(f"Port_{i}") or {}).get(f"Violdetd_{i}", "0"))
            ports.append({"port": self.to_user(i), "violation": str(flag) not in ("0", "")})
        ports.sort(key=lambda x: x["port"])
        return {"model": "global", "enabled": str(cfg["detect_enable"]) == "1", "prevention": cfg.get("cPrev") == "on",
                "interval": int(cfg.get("time_interval") or 0), "recovery": int(cfg.get("recover_time") or 0),
                "ports": ports}

    async def set_loop(self, ports: dict):
        """ports: {user_port: enabled, ...}. Ports left out or False are disabled. (1.0.0.x)"""
        data = {}
        for port, enabled in ports.items():
            internal = self.to_internal(port)
            if enabled:
                data[f"checkbox_{internal}"] = "on"
        return await self._post("port_lock_cfg.json", data)

    async def set_loop_v2(self, enabled: bool, prevention: bool, interval: int | None, recovery: int | None) -> bool:
        """2.0.0.x loop detection, as its own page applies it: detection turned on turns STP off
        (the page offers the two as alternatives). A timer given as None is left out, which keeps
        the stored value; detection must be started with both (a missing one would run as 0).
        Returns True when STP was turned off."""
        body = {"detect_enable": "1" if enabled else "0"}
        for key, value in (("time_interval", interval), ("recover_time", recovery)):
            if value is not None:
                body[key] = str(int(value))
            elif enabled:
                raise ValueError(f"{key} is needed to start loop detection")
        if prevention:
            body["cPrev"] = "on"
        await self._post("port_lock_cfg.json", body)
        if enabled:
            stp = await self.get_stp()
            if stp["enabled"]:
                await self._set_stp_v2(False, stp["mode"], [p["port"] for p in stp["ports"] if p["edge"]])
                return True
        return False

    # ── IGMP ──
    async def get_igmp_config(self):
        return await self._get("igmp_config.json")

    async def set_igmp_config(self, data: dict):
        return await self._post("igmp_config.json", data)

    async def set_igmp_v2(self, enabled: bool, fast_leave: bool, report_flood: bool):
        """2.0.0.x reads "fast-leave"/"report-flood" (it answers fast_leave/report_flood) and takes
        a missing key as off, like the unchecked boxes its own form leaves out. It has no global
        querier (queriers are set per VLAN)."""
        body = {key: "on" for key, on in (("igmp", enabled), ("fast-leave", fast_leave),
                                          ("report-flood", report_flood)) if on}
        return await self._post("igmp_config.json", body)

    async def get_igmp_entries(self):
        return await self._get("igmp_get_entries.json")

    # ── Storm Control ──
    @_parsed("storm_ctrl_cfg.json")
    async def get_storm_control(self):
        """1.0.0.x: the switch's own {"sctrl_state", "sctrl_rate"}. 2.0.0.x: a limit per port and
        traffic type, {"model": "per_port", enabled, rate, types, uniform, ports}."""
        raw = await self._get("storm_ctrl_cfg.json")
        if isinstance(raw, dict) and isinstance(raw.get("ports"), list):
            return self._storm_v2(raw)
        return raw

    def _storm_v2(self, raw: dict) -> dict:
        """Rates are in Mbps, 0 = no limit. rate/types summarise them as one setting for every
        port (the most common rate); uniform is False when the ports differ from that summary."""
        ports = sorted(({"port": self.to_user(int(p["port_id"])), **{t: int(p.get(k) or 0) for t, k in STORM_TYPES.items()}}
                        for p in raw["ports"]), key=lambda x: x["port"])
        limits = [p[t] for p in ports for t in STORM_TYPES if p[t]]
        rate = collections.Counter(limits).most_common(1)[0][0] if limits else 0
        types = [t for t in STORM_TYPES if any(p[t] for p in ports)]
        uniform = all(p[t] == (rate if t in types else 0) for p in ports for t in STORM_TYPES)
        return {"model": "per_port", "enabled": bool(limits), "rate": rate, "types": types,
                "uniform": uniform, "ports": ports}

    async def set_storm_control(self, rate: int, enabled: bool):
        return await self._post("storm_ctrl_cfg.json", {
            "sctrl_rate": str(rate), "sctrl_state": "1" if enabled else "0"
        })

    async def set_storm_v2(self, enabled: bool, rate: int, types: list[str]) -> int:
        """2.0.0.x: the same limit on every port for the given traffic types, none for the others.
        One request per port and type (numbers, as the native page sends them), only where the
        setting changes. Returns the number of requests sent."""
        current = await self.get_storm_control()
        sent = 0
        for p in current["ports"]:
            for storm_type in STORM_TYPES:
                want = int(rate) if enabled and storm_type in types else 0
                if p[storm_type] == want:
                    continue
                await self._post("storm_ctrl_cfg.json", {"port": self.to_internal(p["port"]), "rate": want,
                                                         "state": 1 if want else 0, "storm_type": storm_type})
                sent += 1
        return sent

    # ── Port Mirror ──
    async def get_mirror_raw(self):
        return await self._get("port_mirror.json")

    @_parsed("port_mirror.json")
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
        dest = self.to_user(monitoring) if monitoring else 0
        # the firmware keeps the last destination after mirroring is switched off,
        # so "enabled" means at least one source still copies traffic (the destination
        # itself is never one: the switch skips it when it is listed as a source)
        enabled = bool(monitoring) and any(p["ingress"] or p["egress"] for p in ports if p["port"] != dest)
        return {"monitoring_port": dest, "enabled": enabled, "ports": ports}

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
        requested directions, then every other port (the destination included, as the
        captured sequence does) with both directions off, so sources from a previous
        session are cleared. Turning off = all ten ports off on the current destination
        (the firmware keeps the destination itself).
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
        others = [i for i in range(1, NUM_PORTS + 1) if i not in selected]
        result = ""
        if selected:
            result = await self._post_mirror(dest, selected, ingress, egress)
        if others:
            await self._post_mirror(dest, others, False, False)
        return result

    # ── EEE ──
    async def get_eee(self):
        # Removed in firmware 1.0.0.5+ (empty body → None = unsupported).
        data = await self._get("eee_config.json", default=None)
        if isinstance(data, dict):
            if "eee" in data:  # one switch for the whole device
                data["enabled"] = data["eee"] == "on"
            else:  # 2.0.0.x: per port, Idx_0..7 = ports 1-8 (the SFP+ cages, ext_Idx_*, never do EEE)
                data["enabled"] = any(isinstance(v, dict) and v.get("eee_enable") == "on"
                                      for k, v in data.items() if k.startswith("Idx_"))
        return data

    async def set_eee(self, enabled: bool):
        return await self._post("eee_config.json", {"eee": "on" if enabled else "off"})

    # ── MAC Table ──
    @_parsed("mac_get_dynamic_mac_entries.json")
    async def get_dynamic_macs(self, search: str | None = None):
        if await self.is_v2():
            return await self._get_dynamic_macs_v2(search)
        if search:
            raw = await self._get("mac_search_dynamic_mac_entries.json", params={"mac_search_txt": search})
        else:
            raw = await self._get("mac_get_dynamic_mac_entries.json")
        entries = _parse_mac_entries(raw, self.to_user)
        total = raw.get("total_entries", len(entries)) if isinstance(raw, dict) else len(entries)
        return {"entries": entries, "total": total}

    async def _get_dynamic_macs_v2(self, search: str | None) -> dict:
        """2.0.0.x answers 50 entries at a time (mac_get_next_... continues, and starts again from
        the top past the end) and only searches by prefix, so the table is read whole and filtered
        here: any part of the address, with or without separators. truncated: more entries may
        exist than were read."""
        entries, seen, truncated = [], set(), False
        async with self._mac_lock:
            raw = await self._get("mac_get_dynamic_mac_entries.json")
            for page in range(V2_MAC_MAX_PAGES):
                batch = _parse_mac_entries(raw, self.to_user)
                fresh = [e for e in batch if (e["mac"], e["vlan"], e["fid"]) not in seen]
                if page and (not fresh or batch[0]["idx"] == "1"):
                    break  # read past the end: the switch went back to the first entries
                seen.update((e["mac"], e["vlan"], e["fid"]) for e in fresh)
                entries += fresh
                if len(batch) < V2_MAC_PAGE:
                    break
                try:
                    raw = await self._get("mac_get_next_dynamic_mac_entries.json")
                except (SwitchError, json.JSONDecodeError):
                    truncated = True  # this build cannot page: keep the first entries
                    break
            else:
                truncated = True
        if search:
            needle = _mac_hex(search)
            entries = [e for e in entries if needle and needle in (_mac_hex(e["mac"]) or "")]
        return {"entries": entries, "total": len(entries), "truncated": truncated}

    @_parsed("mac_get_static_mac_entries.json")
    async def get_static_macs(self):
        async with self._mac_lock:
            raw = await self._get("mac_get_static_mac_entries.json")
        return _parse_mac_entries(raw, self.to_user)

    async def _static_entries(self, mac: str) -> dict:
        """2.0.0.x: {vlan: port} of the static entries for this address."""
        return {e["vlan"]: e["port"] for e in await self.get_static_macs() if e["mac"].upper() == mac.upper()}

    async def add_static_mac(self, mac: str, port: int, fid: int = 0, vlan: int | None = None):
        internal = self.to_internal(port)
        if await self.is_v2():
            # 2.0.0.x: keyed by VLAN ID (1-4094) instead of FID, every value a string
            vid = int(vlan or 1)
            await self._post("mac_add_static_mac_entries.json", {
                "mac-input": mac, "port-input": str(internal), "vlan-input": str(vid)})
            if (await self._static_entries(mac)).get(vid) != int(port):
                raise SwitchError(f"mac_add_static_mac_entries.json: the switch answered OK but has no "
                                  f"static entry for {mac} on port {port} in VLAN {vid}")
            return await self._save_static_macs()
        await self._post("mac_add_static_mac_entries.json", {
            "mac-input": mac,
            "port-input": str(internal),
            "fid-input": str(fid),
        })
        return await self._save_static_macs()

    async def delete_static_mac(self, mac: str, port: int, fid: int = 0, vlan: int | None = None):
        """Delete one static entry: by MAC + port + FID on 1.0.0.x (the add form's keys, the only
        shape captured there), by MAC + VLAN ID on 2.0.0.x (its own page's request)."""
        internal = self.to_internal(port)
        if await self.is_v2():
            vid = int(vlan or 1)
            await self._post("mac_delete_static_mac_entries.json", {"mac_addr_txt": [mac], "vlan_text": [str(vid)]})
            # answered 200 even when nothing matched: check the entry is gone
            if vid in await self._static_entries(mac):
                raise SwitchError(f"mac_delete_static_mac_entries.json: the switch answered OK but still has "
                                  f"{mac} in VLAN {vid}")
            return await self._save_static_macs()
        await self._post("mac_delete_static_mac_entries.json", {
            "mac-input": mac,
            "port-input": str(internal),
            "fid-input": str(fid),
        })
        return await self._save_static_macs()

    async def _save_static_macs(self) -> list[str]:
        """Returns warnings: the entry change is applied already, a save timeout only delays flash."""
        try:
            if await self.is_v2():
                # never mac_save_static_mac_entries.json on 2.0.0.x: it rewrites the saved entries
                # from the request body, so an empty body erases them
                await self.save_all()
            else:
                await self._post("mac_save_static_mac_entries.json", {})
        except (httpx.TimeoutException, SwitchError) as e:
            return [f"Static MAC table applied but saving to flash did not complete: {e.__class__.__name__}"]
        return []

    async def clear_dynamic_macs(self):
        return await self._post("mac_clear_dynamic_mac_entries.json", {})

    async def close(self):
        self.closed = True
        await self.client.aclose()
