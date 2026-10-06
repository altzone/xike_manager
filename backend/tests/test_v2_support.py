"""2.0.0.x support: the requests the firmware's own web UI sends (code carved from the vendor
image), saved with save_all_configs.json."""
import json

import httpx
import pytest

from test_v2_safety import make_v2


@pytest.fixture
def v2(api):
    make_v2(api.mock)
    api.mock.state["network_settings.json"]["ipAddress"] = "10.0.0.2"
    r = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2", "username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def paths(m):
    return [ep for ep, _ in m.posts]


def test_port_changes_are_saved_with_the_global_save(api, v2):
    r = api.post(f"/api/switches/{v2}/ports/config", json=[{"port": 4, "enabled": True, "speed": "Auto", "flow_ctrl": "On"}])
    assert r.status_code == 200 and r.json()["warnings"] == []
    assert paths(api.mock) == ["apply_user_port_setting.json", "save_all_configs.json"]
    assert api.mock.posted("save_all_configs.json") == [{}]


def test_requests_are_sent_as_compact_json(api, v2):
    raw = []
    api.mock.responders["apply_user_port_setting.json"] = lambda request: raw.append(request.content) or None
    api.post(f"/api/switches/{v2}/ports/config", json=[{"port": 4, "enabled": True, "speed": "Auto", "flow_ctrl": "On"}])
    assert raw == [b'{"port_sts":"Enable","port_spd_duplex":"Auto","flow_ctrl":"On","port_num":1,"port_list":["4"]}']


def test_static_address_change_uses_the_native_body_and_is_saved_at_the_new_address(api, v2):
    hosts = []
    api.mock.responders["save_all_configs.json"] = lambda request: hosts.append(request.url.host) or None
    r = api.post(f"/api/switches/{v2}/network",
                 json={"dhcp": False, "ip": "10.0.0.50", "netmask": "255.255.255.0", "gateway": "10.0.0.1"})
    assert r.status_code == 200, r.text
    assert api.mock.posted("network_settings_ipv4.json") == [
        {"dhcp_enable": "0", "input_ip": "10.0.0.50", "input_netmask": "255.255.255.0", "input_gateway": "10.0.0.1"}]
    assert hosts == ["10.0.0.50"]  # the save follows the switch to its new address
    assert "kept after a reboot" not in r.json()["note"]
    assert api.get(f"/api/switches/{v2}/info").json()["ip"] == "10.0.0.50"


def test_dhcp_sends_only_the_dhcp_flag_and_says_how_to_keep_it(api, v2):
    r = api.post(f"/api/switches/{v2}/network", json={"dhcp": True})
    assert r.status_code == 200, r.text
    assert api.mock.posted("network_settings_ipv4.json") == [{"dhcp_enable": "1"}]
    assert "save_all_configs.json" not in paths(api.mock)  # the new address is unknown
    assert "press Save" in r.json()["note"]


def test_an_address_the_switch_refuses_is_reported(api, v2):
    api.mock.responders["network_settings_ipv4.json"] = (
        lambda request: httpx.Response(200, json={"alert_key": "alert_invalid_gateway_address"}) if request.method == "POST" else None)
    r = api.post(f"/api/switches/{v2}/network",
                 json={"dhcp": False, "ip": "10.0.0.50", "netmask": "255.255.255.0", "gateway": "10.0.0.1"})
    assert r.status_code == 502 and "alert_invalid_gateway_address" in r.json()["detail"]
    assert api.get(f"/api/switches/{v2}/info").json()["ip"] == "10.0.0.2"  # not repointed


def test_reboot_is_allowed(api, v2):
    assert api.post(f"/api/switches/{v2}/reboot").status_code == 200
    assert "system_reboot.json" in paths(api.mock)


def test_eee_state_is_read_from_the_per_port_format(api, v2):
    api.mock.state["eee_config.json"] = {"int_port_num": "8", "ext_port_num": "2",
                                         **{f"Idx_{i}": {"eee_enable": "on", "eee_active": "off"} for i in range(8)},
                                         "ext_Idx_0": {"eee_enable": "off", "eee_active": "na"},
                                         "ext_Idx_1": {"eee_enable": "off", "eee_active": "na"}}
    d = api.get(f"/api/switches/{v2}/eee").json()
    assert d["supported"] is True and d["enabled"] is True
    api.mock.state["eee_config.json"].update({f"Idx_{i}": {"eee_enable": "off", "eee_active": "off"} for i in range(8)})
    assert api.get(f"/api/switches/{v2}/eee").json()["enabled"] is False
