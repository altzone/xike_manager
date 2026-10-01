"""Shared fixtures: a mock Xikestor switch behind httpx.MockTransport and a TestClient app."""
import json
import os
import sys

import httpx
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import switch_client  # noqa: E402
import db as dbmod  # noqa: E402
import auth  # noqa: E402
import sse  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _port_block(i: int, **fields) -> dict:
    return {f"Port_{i}": fields}


def default_state() -> dict:
    """Payloads as the firmware returns them, keyed by internal index.

    Internal index 9 carries a 10G link (the reporter's unit in issue #3);
    internal index 10 is empty. Port 1 is the management port.
    """
    state = {
        "status.json": {"modle": "SKS3200-8E2X", "fw_ver": "1.0.0.6", "hw_ver": "A0",
                        "sys_macaddr": "8C:A6:82:00:00:01", "temperature": "41", "des": "Test"},
        "network_settings.json": {"ipAddress": "192.168.1.2", "netmask": "255.255.255.0",
                                  "gateway": "192.168.1.1", "dhcpEnabled": "0"},
        "systemtime_settings.json": {"timeVal": "12:00:00", "dateVal": "01/10/2026", "timezoneOffsetVal": "+01:00"},
        "sntp_setting.json": {"sntp_state": "1", "sntp_server_ip": "1.2.3.4", "sntp_poll": "64"},
        "eee_config.json": {"eee": "off"},
        "storm_ctrl_cfg.json": {"sctrl_state": "0", "sctrl_rate": "100"},
        "igmp_config.json": {"igmp": "off", "fast_leave": "on", "snoop_querier": "off"},
        "igmp_get_entries.json": {"total_entries": "0"},
        "port_setting_load.json": {"PortNum": "10"},
        "port_statistics.json": {"PortNum": "10"},
        "port_vlan_cfg.json": {"totBports": "10"},
        "tag_vlan_cfg.json": {"totBps": "111"},
        "port_trunk_cfg.json": {"PortNum": "10", "system_priority": "32768"},
        "stp.json": {"num_ports": "10", "stp_enable": "0", "stp_mode": "0"},
        "port_lock_cfg.json": {},
        "port_loop_status.json": {},
        "port_mirror.json": {"MonitoringPortId": "9"},
        "mac_get_dynamic_mac_entries.json": {
            "total_entries": "1",
            "Idx_0": {"Dynamic_idx": "0", "Dynamic_mac_addr": "AA:BB:CC:00:00:01",
                      "Dynamic_portid": "9", "Dynamic_fid": "0", "Dynamic_age_timer": "300"},
        },
        "mac_search_dynamic_mac_entries.json": {"total_entries": "0"},
        "mac_get_static_mac_entries.json": {
            "total_entries": "1",
            "Idx_0": {"Static_idx": "0", "Static_mac_addr": "AA:BB:CC:00:00:02",
                      "Static_portid": "9", "Static_fid": "0"},
        },
    }
    for i in range(1, 11):
        up = i in (1, 9)
        state["port_setting_load.json"].update(_port_block(
            i, Port_Status="Enabled",
            Spd_Duplex_Cfg="Auto",
            Spd_Duplex_Actual=("10GbpsFull" if i == 9 else "2500MbpsFull" if i == 1 else "Link Down"),
            Flow_Ctrl_Cfg="On", Flow_Ctrl_Actual="On" if up else "Off"))
        state["port_statistics.json"].update(_port_block(
            i, Link_Status=("Link Up" if up else "Link Down"),
            TxGoodPkt=str(1000 * i), TxBadPkt="0", RxGoodPkt=str(2000 * i), RxBadPkt="0"))
        state["port_vlan_cfg.json"].update(_port_block(
            i, **{f"bpEn_{i}": "1" if i == 9 else "0", f"bpVid_{i}": "20" if i == 9 else "1",
                  f"untag_{i}": "0", f"tag_{i}": "1" if i == 9 else "0"}))
        state["port_trunk_cfg.json"].update(_port_block(
            i, **{f"portTypeId_{i}": "1" if i == 9 else "0", f"lacpTimeoutId_{i}": "0",
                  f"Port_{i}_grpInd": "1" if i == 9 else "0", f"Port_{i}_state": "0"}))
        state["stp.json"].update(_port_block(i, **{f"Stp_Edge_{i}": "1" if i == 9 else "0", f"Stp_Status_{i}": "Forwarding"}))
        state["port_lock_cfg.json"].update(_port_block(i, **{f"Locken_{i}": "1" if i == 9 else "0"}))
        state["port_loop_status.json"][f"Violdetd_{i}"] = "1" if i == 9 else "0"
        state["port_mirror.json"].update(_port_block(
            i, Ingress_Status="Enabled" if i == 1 else "Disabled", Egress_Status="Disabled"))
    for n in range(111):
        state["tag_vlan_cfg.json"][f"bP_{n}"] = {
            f"TBVEn_{n}": "1" if n == 0 else "0", f"pP_{n}": "9" if n == 0 else "0",
            f"oVid_{n}": "30" if n == 0 else "0", f"tT_{n}": "0",
        }
    return state


class MockSwitch:
    def __init__(self):
        self.state = default_state()
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []
        self.logged_in = False
        self.logins = 0
        self.reject_login = False
        # endpoint -> callable(request) returning a Response, or raising; None = default behaviour
        self.responders: dict = {}

    def posted(self, endpoint: str) -> list[dict]:
        return [body for ep, body in self.posts if ep == endpoint]

    def fail_once(self, endpoint: str, exc: Exception, method: str = "POST"):
        state = {"done": False}

        def responder(request):
            if request.method == method and not state["done"]:
                state["done"] = True
                raise exc
            return None
        self.responders[endpoint] = responder

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.lstrip("/")
        if path == "authorize":
            if self.reject_login:
                return httpx.Response(200, text="<html>login.html</html>")
            self.logged_in = True
            self.logins += 1
            return httpx.Response(200, text="<html>setup.html</html>")
        if not self.logged_in:
            return httpx.Response(200, text="<html>login.html</html>")
        responder = self.responders.get(path)
        if responder is not None:
            forced = responder(request)
            if forced is not None:
                return forced
        if request.method == "POST":
            body = json.loads(request.content or b"{}")
            self.posts.append((path, body))
            return httpx.Response(200, text="OK")
        self.gets.append(str(request.url))
        if path in self.state:
            return httpx.Response(200, json=self.state[path])
        return httpx.Response(200, text="")  # removed endpoint: empty body, like firmware 1.0.0.5+


@pytest.fixture
def mock_switch(monkeypatch):
    sw = MockSwitch()
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(sw.handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(switch_client.httpx, "AsyncClient", factory)
    return sw


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(dbmod, "DB_PATH", path)
    monkeypatch.setattr(main, "DB_PATH", path)
    monkeypatch.setattr(dbmod, "OUI_CSV", str(tmp_path / "missing-oui.csv"))  # skip the 39K-row import
    return path


ADMIN_PASSWORD = "secret123"


@pytest.fixture
def api(db_path, mock_switch):
    sse._clients.clear()
    auth._failures.clear()
    with TestClient(main.app) as client:
        assert client.post("/api/setup", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
        token = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).json()["token"]
        client.headers["Authorization"] = f"Bearer {token}"
        client.mock = mock_switch
        yield client
    sse._clients.clear()
    auth._failures.clear()


def login_as(api, username: str, password: str) -> dict:
    """Headers for another account (the api fixture's default headers stay admin)."""
    r = api.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def add_switch(api, swap: bool = False, name: str = "SW") -> int:
    r = api.post("/api/switches", json={"name": name, "ip": "10.0.0.2", "username": "admin",
                                        "password": "admin", "swap_sfp_9_10": swap})
    assert r.status_code == 200, r.text
    return r.json()["id"]
