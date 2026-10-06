"""Switches on 2.0.0.x firmware: pages that answer in another format fail cleanly, and the
writes SwitchPilot cannot send safely there are refused before anything reaches the switch
(issue #3: a 1.0.0.x IGMP request turned two other options off on a 2.0.0.3 unit)."""
import sqlite3

import httpx
import pytest

import db as dbmod
from conftest import add_switch
from v2_mock import V2L2, V2Vlans


def make_v2(mock, dynamic=None):
    """An SKS3200-8E2X-P on 2.0.0.3: status as captured from that unit, the other pages as its
    firmware's handlers answer and read them (tests/v2_mock.py)."""
    st = mock.state
    st["status.json"] = {"temperature": "49", "sys_ipv4": "10.0.0.2", "sys_macaddr": "8C:A6:82:71:A3:36",
                         "fw_ver": "2.0.0.3", "hw_ver": "A0", "des": "SKS3200-8E2X-P"}
    st["port_vlan_cfg.json"] = {"PortNum": 10, **{f"Port_{i}": {"Port_Id": i, "PVID": 1, "Frame_Type": 0}
                                                  for i in range(1, 11)}}
    st["tag_vlan_cfg.json"] = {"vlans": []}
    mock.v2 = V2Vlans(mock)  # tag_vlan.json / port_vlan.json (and their 1.0.0.x aliases)
    mock.l2 = V2L2(mock, dynamic)  # LAG, STP, loop, storm, IGMP, mirroring, MAC tables, save


@pytest.fixture
def v2(api):
    make_v2(api.mock)
    r = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2", "username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    assert r.json()["swap_sfp_9_10"] is False  # 2.0.0.x numbers the SFP+ cages like the front panel
    return r.json()["id"]


def test_pages_in_another_format_fail_with_a_clear_502(api, v2):
    for path in ("vlans", "vlans/assignments", "vlans/limits", "stp", "loop", "storm", "igmp", "mirror", "lag",
                 "mac/dynamic", "mac/static", "ports", "eee"):  # all read in the 2.0.0.x format
        assert api.get(f"/api/switches/{v2}/{path}").status_code == 200, path
    api.mock.responders["port_trunk_cfg.json"] = lambda request: httpx.Response(200, json={"PortNum": 10})
    r = api.get(f"/api/switches/{v2}/lag")
    assert r.status_code == 502, r.text
    assert "2.0.0.3" in r.json()["detail"] and "port_trunk_cfg.json" in r.json()["detail"]


WRITES = [  # settings the 2.0.0.x web interface no longer offers
    ("eee", {"enabled": True}),
    ("time", {"time": "12:00:00", "date": "01/10/2026", "timezone": "+01:00"}),
    ("sntp", {"enabled": True, "server": "1.2.3.4", "poll": 64}),
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
    assert by_id[v2]["read_only"] == ["eee", "time"]
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
    assert "unavailable" not in cfg["meta"] and cfg["stp"]["mode"] == "rstp" and cfg["loop"]["model"] == "global"
    assert cfg["vlan_table"]["1"]["ports"]["1"] == 1 and cfg["port_vlan_cfg"]["1"]["pvid"] == 1
    assert cfg["meta"]["firmware"] == "2.0.0.3"
    assert cfg["ports"] and cfg["status"]["fw_ver"] == "2.0.0.3"


def test_a_garbled_page_on_1_0_0_x_is_a_502_not_a_500(api):
    sid = add_switch(api)
    del api.mock.state["port_setting_load.json"]["Port_3"]
    r = api.get(f"/api/switches/{sid}/ports")
    assert r.status_code == 502 and "port_setting_load.json" in r.json()["detail"]
