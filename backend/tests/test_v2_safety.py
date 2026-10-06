"""Switches on 2.0.0.x firmware: pages that answer in another format fail cleanly, and the
1.0.0.x write requests SwitchPilot cannot send safely are refused before anything reaches the
switch (issue #3: an IGMP change turned two other options off on a 2.0.0.3 unit)."""
import sqlite3

import pytest

import db as dbmod
from conftest import add_switch


def make_v2(mock):
    """Answers of an SKS3200-8E2X-P on 2.0.0.3 (status, storm and IGMP as captured from
    SwitchPilot on that unit; the VLAN/STP pages only need to differ from the 1.0.0.x shape)."""
    st = mock.state
    st["status.json"] = {"temperature": "49", "sys_ipv4": "10.0.0.2", "sys_macaddr": "8C:A6:82:71:A3:36",
                         "fw_ver": "2.0.0.3", "hw_ver": "A0", "des": "SKS3200-8E2X-P"}
    st["port_vlan_cfg.json"] = {"PortNum": 10, **{f"Port_{i}": {"Port_Id": i, "PVID": 1, "Frame_Type": 0}
                                                  for i in range(1, 11)}}
    st["tag_vlan_cfg.json"] = {"vlans": []}
    st["stp.json"] = {"stp_enable": "0", "stp_rstp_mode": "RSTP"}
    st["storm_ctrl_cfg.json"] = {"portnum": 10, "ports": [
        {"sctrl_bcast": 0, "sctrl_mcast": 0, "sctrl_unucast": 0, "sctrl_unmcast": 0, "port_id": i} for i in range(1, 11)]}
    st["igmp_config.json"] = {"igmp": "off", "fast_leave": "on", "report_flood": "on"}


@pytest.fixture
def v2(api):
    make_v2(api.mock)
    r = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2", "username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    assert r.json()["swap_sfp_9_10"] is False  # 2.0.0.x numbers the SFP+ cages like the front panel
    return r.json()["id"]


def test_pages_in_another_format_fail_with_a_clear_502(api, v2):
    for path in ("vlans/assignments", "vlans/limits", "stp"):
        r = api.get(f"/api/switches/{v2}/{path}")
        assert r.status_code == 502, (path, r.status_code, r.text)
        assert "2.0.0.3" in r.json()["detail"] and ".json" in r.json()["detail"]
    assert api.get(f"/api/switches/{v2}/vlans").status_code == 200  # local definitions still listed


WRITES = [
    ("network", {"dhcp": False, "ip": "10.0.0.2", "netmask": "255.255.255.0", "gateway": "10.0.0.1"}),
    ("vlans/apply", [{"port": 2, "mode": "access", "access_vlan": 10}]),
    ("stp", {"enabled": True, "mode": "rstp"}),
    ("loop", {"ports": {"2": True}}),
    ("storm", {"enabled": True, "rate": 100}),
    ("igmp", {"enabled": True, "fast_leave": True, "querier": False}),
    ("mirror", {"monitoring_port": 2, "mirrored_ports": [3], "ingress": True, "egress": False}),
    ("eee", {"enabled": True}),
    ("mac/clear", None),
    ("lag", {"system_priority": 32768, "ports": [{"port": 2, "type": 2, "group": 1}, {"port": 3, "type": 2, "group": 1}]}),
    ("time", {"time": "12:00:00", "date": "01/10/2026", "timezone": "+01:00"}),
    ("sntp", {"enabled": True, "server": "1.2.3.4", "poll": 64}),
    ("mac/static/add", {"mac": "AA:BB:CC:DD:EE:01", "port": 2, "fid": 0}),
    ("mac/static/delete", {"mac": "AA:BB:CC:DD:EE:01", "port": 2, "fid": 0}),
    ("reboot", None),
]


@pytest.mark.parametrize("path, body", WRITES, ids=[w[0] for w in WRITES])
def test_unverified_writes_are_refused_before_anything_is_sent(api, v2, path, body):
    r = api.post(f"/api/switches/{v2}/{path}", json=body)
    assert r.status_code == 501, r.text
    assert "2.0.0.3" in r.json()["detail"] and "nothing was sent" in r.json()["detail"]
    assert api.mock.posts == []
    assert api.get(f"/api/switches/{v2}/changes").json() == []  # nothing logged as changed


def test_port_settings_still_work_on_2_0_0_x(api, v2):
    r = api.post(f"/api/switches/{v2}/ports/config",
                 json=[{"port": 4, "enabled": True, "speed": "2500Mbps Full", "flow_ctrl": "On"}])
    assert r.status_code == 200, r.text
    assert api.mock.posted("apply_user_port_setting.json")[-1]["port_list"] == ["4"]


def test_the_same_writes_still_go_through_on_1_0_0_x(api):
    sid = add_switch(api)  # fixture runs 1.0.0.6
    assert api.post(f"/api/switches/{sid}/igmp", json={"enabled": True, "fast_leave": True, "querier": False}).status_code == 200
    assert api.mock.posted("igmp_config.json")


def test_switches_report_their_firmware_line_and_read_only_features(api, v2):
    api.mock.state["status.json"]["fw_ver"] = "1.0.0.6"  # a second, 1.0.0.x switch is added
    v1 = add_switch(api, name="V1")
    api.mock.state["status.json"]["fw_ver"] = "2.0.0.3"
    by_id = {s["id"]: s for s in api.get("/api/switches").json()}
    assert by_id[v1]["firmware_line"] == 1 and by_id[v1]["read_only"] == []
    assert by_id[v2]["firmware_line"] == 2
    assert "vlans" in by_id[v2]["read_only"] and "igmp" in by_id[v2]["read_only"] and "ports" not in by_id[v2]["read_only"]
    assert api.get(f"/api/switches/{v2}/info").json()["read_only"] == by_id[v2]["read_only"]
    status = api.get(f"/api/switches/{v2}/status").json()
    assert status["firmware_line"] == 2 and status["read_only"] == by_id[v2]["read_only"]


def test_status_refreshes_the_stored_model_and_firmware(api, v2):
    con = sqlite3.connect(dbmod.DB_PATH)  # as recorded by the first release, which only read "modle"
    con.execute("UPDATE switches SET model = '', firmware = '2.0.0.2' WHERE id = ?", (v2,))
    con.commit()
    con.close()
    assert api.get(f"/api/switches/{v2}/status").status_code == 200
    info = api.get(f"/api/switches/{v2}/info").json()
    assert (info["model"], info["firmware"]) == ("SKS3200-8E2X-P", "2.0.0.3")


def test_snapshot_keeps_what_the_switch_can_give(api, v2):
    r = api.post(f"/api/switches/{v2}/snapshots", json={"name": "v2"})
    assert r.status_code == 200, r.text
    cfg = api.get(f"/api/switches/{v2}/snapshots/{r.json()['id']}").json()["config"]
    assert {"port_vlans", "tag_vlans", "stp"} <= set(cfg["meta"]["unavailable"])
    assert cfg["meta"]["firmware"] == "2.0.0.3"
    assert cfg["ports"] and cfg["status"]["fw_ver"] == "2.0.0.3"


def test_a_garbled_page_on_1_0_0_x_is_a_502_not_a_500(api):
    sid = add_switch(api)
    del api.mock.state["port_setting_load.json"]["Port_3"]
    r = api.get(f"/api/switches/{sid}/ports")
    assert r.status_code == 502 and "port_setting_load.json" in r.json()["detail"]
