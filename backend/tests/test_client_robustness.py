"""Firmware variations the client must survive (1.0.0.x vs 2.0.0.x, connection drops)."""
import asyncio
import json

import httpx
import pytest

from switch_client import SwitchClient, decode_payload, _parse_mac_entries
from conftest import add_switch


def test_decode_payload_accepts_json_and_sse_lines():
    assert decode_payload('{"a": 1}') == {"a": 1}
    assert decode_payload('data: [{"x": 1}]\n\ndata: [{"x": 2}]\n') == [{"x": 1}, {"x": 2}]
    assert decode_payload('data: {"PortNum": 10}\ndata: {"vlan_id": "3"}\n') == {"PortNum": 10, "vlan_id": "3"}
    with pytest.raises(json.JSONDecodeError):
        decode_payload("")
    with pytest.raises(json.JSONDecodeError):
        decode_payload("<html>login.html</html>")


def test_parse_mac_entries_handles_both_firmware_shapes():
    ident = lambda p: p
    v1 = {"total_entries": "1", "Idx_0": {"Dynamic_idx": "0", "Dynamic_mac_addr": "AA:00:00:00:00:01",
                                           "Dynamic_portid": "3", "Dynamic_fid": "2", "Dynamic_age_timer": "10"}}
    assert _parse_mac_entries(v1, ident) == [{"idx": "0", "mac": "AA:00:00:00:00:01", "port": 3, "fid": "2", "vlan": None, "age": "10"}]
    v2 = [{"Static_idx": 1, "Static_mac_addr": "AA:00:00:00:00:02", "Static_vlan_id": 7, "Static_portid": 8}]
    assert _parse_mac_entries(v2, ident) == [{"idx": "1", "mac": "AA:00:00:00:00:02", "port": 8, "fid": "7", "vlan": 7, "age": ""}]
    qss = {"batch": [{"mac_addr": "AA:00:00:00:00:03", "vlan_id": 1, "fid": 0, "portid": 2, "age_timer": 5}],
           "has_more": False, "count": 1}
    assert _parse_mac_entries(qss, ident)[0]["port"] == 2
    # 2.0.0.x writes the VLAN ID before the FID: each keeps its own column
    both = {"Idx_0": {"Static_idx": 1, "Static_mac_addr": "AA:00:00:00:00:04", "Static_vlan_id": 20, "Static_fid": 0,
                      "Static_portid": 4}, "total_entries": 1}
    assert _parse_mac_entries(both, ident)[0] == {"idx": "1", "mac": "AA:00:00:00:00:04", "port": 4, "fid": "0",
                                                  "vlan": 20, "age": ""}
    assert _parse_mac_entries({"total_entries": "0"}, ident) == []


def _client_with(handler) -> SwitchClient:
    return SwitchClient("10.0.0.1", "admin", "admin", transport=httpx.MockTransport(handler))


def test_login_accepts_v2_redirect_and_rejects_login_page():
    def ok(request):
        return httpx.Response(200, text='<script>window.location="index.html?page="</script>')

    def bad(request):
        return httpx.Response(200, text='<script>window.location="login.html"</script>')

    assert asyncio.run(_client_with(ok).login()) is True
    assert asyncio.run(_client_with(bad).login()) is False


def test_get_retries_once_when_the_switch_drops_the_connection():
    calls = {"status": 0}

    def handler(request):
        path = request.url.path
        if path == "/authorize":
            return httpx.Response(200, text="setup.html")
        calls["status"] += 1
        if calls["status"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return httpx.Response(200, json={"fw_ver": "1.0.0.6"})

    assert asyncio.run(_client_with(handler).get_status()) == {"fw_ver": "1.0.0.6"}
    assert calls["status"] == 2


def test_get_does_not_retry_twice():
    def handler(request):
        if request.url.path == "/authorize":
            return httpx.Response(200, text="setup.html")
        raise httpx.ConnectError("unreachable")

    with pytest.raises(httpx.ConnectError):
        asyncio.run(_client_with(handler).get_status())


def test_model_falls_back_to_des_on_newer_firmware(api):
    api.mock.state["status.json"] = {"des": "SKS3200-8E2X", "fw_ver": "2.0.0.3", "hw_ver": "A0",
                                     "sys_macaddr": "8C:A6:82:00:00:02", "temperature": "40"}
    sid = add_switch(api)
    assert api.get(f"/api/switches/{sid}/info").json()["model"] == "SKS3200-8E2X"


def test_static_mac_list_from_sse_style_payload(api, monkeypatch):
    sid = add_switch(api)
    real = api.mock.handler

    def handler(request):
        if request.url.path == "/mac_get_static_mac_entries.json" and api.mock.logged_in:
            return httpx.Response(200, text='data: [{"Static_idx":1,"Static_mac_addr":"00:11:22:33:44:55","Static_vlan_id":1,"Static_portid":9}]\n')
        return real(request)

    monkeypatch.setattr(api.mock, "handler", handler)
    assert api.get(f"/api/switches/{sid}/mac/static").json() == [
        {"idx": "1", "mac": "00:11:22:33:44:55", "port": 9, "fid": "1", "vlan": 1, "age": ""}]
