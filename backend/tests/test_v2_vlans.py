"""VLANs on 2.0.0.x: one 802.1Q table on the switch (names included) and a PVID per port."""
import json

import pytest

from test_v2_safety import make_v2


@pytest.fixture
def v2(api):
    make_v2(api.mock)
    r = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2", "username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ports_of(api, sid):
    return {r["port"]: r for r in api.get(f"/api/switches/{sid}/vlans/assignments").json()}


def tag_posts(m):
    return m.posted("tag_vlan.json")


def test_factory_state_reads_as_flat_ports(api, v2):
    rows = ports_of(api, v2)
    assert all(r["mode"] == "flat" and r["pvid"] == 1 and r["trunk_vlans"] == [] for r in rows.values())
    lim = api.get(f"/api/switches/{v2}/vlans/limits").json()
    assert lim == {"model": "8021q", "max_vlans": 100, "used_vlans": 1, "max_vlan_id": 4094, "max_pvid": 4094}


def test_creating_a_vlan_creates_it_on_the_switch_with_its_name(api, v2):
    m = api.mock
    r = api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 60, "name": "Test"})
    assert r.status_code == 200, r.text
    assert tag_posts(m) == [{"deletedVlans": [], "updatedVlans": [
        {"port_states": [0] * 11, "vlan_id": "60", "vlan_name": "Test"}]}]
    assert m.v2.table[60]["name"] == "Test"
    assert "save_all_configs.json" in [ep for ep, _ in m.posts]
    v = {x["vlan_id"]: x for x in api.get(f"/api/switches/{v2}/vlans").json()}[60]
    assert v["on_switch"] and v["defined"] and not v["in_use"]
    assert api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 60, "name": "Test"}).status_code == 409


def test_a_vlan_defined_only_in_switchpilot_is_pushed_to_the_switch(api, v2):
    """tavalin's VLAN 60, created before SwitchPilot spoke 2.0.0.x: creating it again works."""
    import sqlite3
    import db as dbmod
    con = sqlite3.connect(dbmod.DB_PATH)
    con.execute("INSERT INTO vlans (switch_id, vlan_id, name) VALUES (?, 60, 'test')", (v2,))
    con.commit()
    con.close()
    assert api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 60, "name": "test"}).status_code == 200
    assert 60 in api.mock.v2.table


def test_access_port_moves_untagged_membership_and_pvid_in_a_safe_order(api, v2):
    m = api.mock
    api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 10, "name": "Office"})
    m.posts.clear()
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    assert r.status_code == 200, r.text
    assert [ep for ep, _ in m.posts] == ["tag_vlan.json", "port_vlan.json", "tag_vlan.json", "save_all_configs.json"]
    gain, lose = tag_posts(m)
    by_vid = {int(e["vlan_id"]): e["port_states"] for e in gain["updatedVlans"]}
    assert by_vid[10][5] == 1 and by_vid[1][5] == 1  # still in VLAN 1 until its PVID has moved
    assert m.posted("port_vlan.json") == [{"port_based_vlan_frame_type": "0", "port_based_vlan_pvid_input": "10",
                                           "port_based_vlan_selection": ["5"]}]
    assert [(e["vlan_id"], e["port_states"][5]) for e in lose["updatedVlans"]] == [("1", 0)]
    assert m.v2.table[1]["states"][5] == 0 and m.v2.table[10]["states"][5] == 1 and m.v2.pvids[5] == 10
    assert m.v2.table[1]["states"][4] == 1  # untouched ports keep their membership
    row = ports_of(api, v2)[5]
    assert (row["mode"], row["pvid"]) == ("access", 10)


def test_trunk_port_gets_tagged_vlans_and_missing_vlans_are_created(api, v2):
    m = api.mock
    api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 10, "name": "Office"})
    r = api.post(f"/api/switches/{v2}/vlans/apply",
                 json=[{"port": 9, "mode": "trunk", "native_vlan": 1, "trunk_vlans": [10, 200]}])
    assert r.status_code == 200, r.text
    assert r.json()["created"] == [200]
    assert m.v2.table[10]["states"][9] == 2 and m.v2.table[200]["states"][9] == 2 and m.v2.table[1]["states"][9] == 1
    row = ports_of(api, v2)[9]
    assert (row["mode"], row["pvid"], row["trunk_vlans"]) == ("trunk", 1, [10, 200])
    # back to flat: tagged memberships removed, VLANs kept
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 9, "mode": "flat"}])
    assert r.status_code == 200, r.text
    assert m.v2.table[10]["states"][9] == 0 and m.v2.table[200]["states"][9] == 0 and m.v2.table[1]["states"][9] == 1
    assert ports_of(api, v2)[9]["mode"] == "flat"


def test_vlan_ids_above_63_are_valid_access_vlans_on_2_0_0_x(api, v2):
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 3, "mode": "access", "access_vlan": 300}])
    assert r.status_code == 200, r.text
    assert api.mock.v2.pvids[3] == 300


def test_a_write_the_switch_ignores_is_detected_and_rolled_back(api, v2):
    m = api.mock
    api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 10, "name": "Office"})
    m.v2.refuse.add(10)  # answers 200 but keeps VLAN 10 as it was
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    assert r.status_code == 502 and "port 5 in VLAN 10" in r.json()["detail"] and "put back" in r.json()["detail"]
    assert m.v2.pvids[5] == 1 and m.v2.table[1]["states"][5] == 1  # previous configuration restored
    assert "save_all_configs.json" not in [ep for ep, _ in m.posts[-4:]]


def test_large_changes_are_split_into_bodies_the_switch_can_read(api, v2):
    m = api.mock
    raw = []
    original = m.responders["tag_vlan.json"]
    m.responders["tag_vlan.json"] = lambda request: (raw.append(len(request.content)) if request.method == "POST" else None) or original(request)
    vids = list(range(100, 130))
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 9, "mode": "trunk", "native_vlan": 1, "trunk_vlans": vids}])
    assert r.status_code == 200, r.text
    assert len(raw) > 1 and max(raw) <= 1023
    assert all(m.v2.table[v]["states"][9] == 2 for v in vids)


def test_the_100_vlan_table_limit_is_checked_before_writing(api, v2):
    m = api.mock
    m.v2.table.update({v: {"name": "", "states": {p: 0 for p in range(1, 11)}} for v in range(2, 100)})
    m.posts.clear()
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 2, "mode": "trunk", "native_vlan": 1, "trunk_vlans": [500, 501]}])
    assert r.status_code == 400 and "at most 100" in r.json()["detail"]
    assert m.posts == []


def test_deleting_a_vlan_still_used_as_a_pvid_is_refused_clearly(api, v2):
    m = api.mock
    api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 10, "name": "Office"})
    api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    r = api.delete(f"/api/switches/{v2}/vlans/10")
    assert r.status_code == 409 and "port(s) 5" in r.json()["detail"]
    assert 10 in m.v2.table
    api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "flat"}])
    m.posts.clear()
    assert api.delete(f"/api/switches/{v2}/vlans/10").status_code == 200
    assert m.posted("tag_vlan.json") == [{"deletedVlans": [10], "updatedVlans": []}]
    assert 10 not in m.v2.table
    assert api.delete(f"/api/switches/{v2}/vlans/1").status_code == 400


def test_rename_updates_the_name_on_the_switch_and_keeps_members(api, v2):
    m = api.mock
    api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 10, "name": "Office"})
    api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    r = api.put(f"/api/switches/{v2}/vlans/10", json={"name": "Office 2nd floor"})
    assert r.status_code == 200, r.text
    assert m.v2.table[10]["name"] == "Office 2nd floor"  # 16 characters: what the switch keeps
    assert m.v2.table[10]["states"][5] == 1
    names = {v["vlan_id"]: v["name"] for v in api.get(f"/api/switches/{v2}/vlans").json()}
    assert names[10] == "Office 2nd floor"  # SwitchPilot keeps the full name


def test_vlan_names_from_the_switch_are_shown(api, v2):
    api.mock.v2.table[30] = {"name": "VoIP", "states": {p: (2 if p == 9 else 0) for p in range(1, 11)}}
    v = {x["vlan_id"]: x for x in api.get(f"/api/switches/{v2}/vlans").json()}[30]
    assert v["name"] == "VoIP" and v["in_use"] and v["on_switch"]


def test_1_0_0_x_still_limits_access_vlans_to_its_bridges(api):
    from conftest import add_switch
    sid = add_switch(api)
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 2, "mode": "access", "access_vlan": 64}])
    assert r.status_code == 422


# ── 2.0.0.3: the table reads back with PortNum entries (entry 0 = port 1) ──
def layout_posts(m):
    return [b for b in tag_posts(m) if any(e.get("vlan_name") == "SwitchPilot test" for e in b["updatedVlans"])
            or b["deletedVlans"] == [4094]]


def test_2_0_0_3_writes_are_checked_once_with_a_temporary_vlan(api, v2):
    m = api.mock
    m.v2.read_layout = "plain"  # what tavalin's 2.0.0.3 answers; its web page still writes 11 entries
    rows = ports_of(api, v2)
    assert all(r["mode"] == "flat" and r["pvid"] == 1 for r in rows.values())
    r = api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 10, "name": "Office"})
    assert r.status_code == 200, r.text
    probe, cleanup = layout_posts(m)
    assert probe["updatedVlans"][0]["vlan_id"] == "4094" and probe["updatedVlans"][0]["port_states"][5] == 2
    assert cleanup == {"deletedVlans": [4094], "updatedVlans": []}
    assert 4094 not in m.v2.table and m.v2.table[10]["name"] == "Office"
    assert tag_posts(m)[-1]["updatedVlans"][0]["port_states"] == [0] * 11  # the web page's own layout
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    assert r.status_code == 200, r.text
    assert len(layout_posts(m)) == 2  # checked once per switch
    assert m.v2.table[10]["states"][5] == 1 and m.v2.table[1]["states"][5] == 0 and m.v2.table[1]["states"][1] == 1


def test_a_firmware_that_writes_entry_0_as_port_1_gets_its_own_layout(api, v2):
    m = api.mock
    m.v2.read_layout = m.v2.write_layout = "plain"
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    assert r.status_code == 200, r.text
    assert all(len(e["port_states"]) == 10 for b in tag_posts(m)[2:] for e in b["updatedVlans"])
    assert m.v2.table[10]["states"][5] == 1 and m.v2.pvids[5] == 10
    assert m.v2.table[1]["states"][1] == 1 and m.v2.table[1]["states"][5] == 0  # port 1 never left VLAN 1


def test_no_vlan_is_changed_when_the_check_is_inconclusive(api, v2):
    m = api.mock
    m.v2.read_layout = "plain"
    m.v2.refuse.add(4094)  # the temporary VLAN never shows up
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    assert r.status_code == 502 and "does not change VLANs" in r.json()["detail"], r.text
    assert [b for b in tag_posts(m) if b not in layout_posts(m)] == []  # only the check was sent
    assert m.posted("port_vlan.json") == [] and 10 not in m.v2.table and m.v2.pvids[5] == 1
