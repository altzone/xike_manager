"""Issue #3: the SFP+ 9/10 swap is a per-switch setting applied to every read and write."""
import asyncio
import sqlite3

import pytest

import db as dbmod
import sse
from switch_client import SwitchClient, InvalidPortError, build_port_map, default_swap_sfp
from conftest import add_switch


# ── Pure mapping ──
def test_build_port_map():
    assert build_port_map(False) == {i: i for i in range(1, 11)}
    swapped = build_port_map(True)
    assert swapped[9] == 10 and swapped[10] == 9 and swapped[8] == 8


def test_to_internal_rejects_bad_ports():
    c = SwitchClient("10.0.0.1", swap_sfp=True)
    assert c.to_internal("9") == 10
    for bad in (0, 11, -1, "x", None):
        with pytest.raises(InvalidPortError):
            c.to_internal(bad)
    assert c.to_user(10) == 9
    c.set_port_mapping(False)
    assert c.to_internal(9) == 9 and c.to_user(10) == 10


# ── Reads ──
def by_port(rows):
    return {r["port"]: r for r in rows}


def test_reads_without_swap_match_firmware_indexes(api):
    sid = add_switch(api, swap=False)
    ports = by_port(api.get(f"/api/switches/{sid}/ports").json())
    assert ports[9]["speed_actual"] == "10GbpsFull" and ports[9]["internal_port"] == 9
    assert ports[10]["speed_actual"] == "Link Down" and ports[10]["internal_port"] == 10
    assert ports[9]["type"] == "SFP+" and ports[8]["type"] == "RJ45 2.5G"

    stats = by_port(api.get(f"/api/switches/{sid}/ports/stats").json())
    assert stats[9]["link"] == "Link Up" and stats[10]["link"] == "Link Down"

    vlans = by_port(api.get(f"/api/switches/{sid}/vlans/assignments").json())
    assert vlans[9]["mode"] == "trunk" and vlans[9]["pvid"] == 20 and vlans[9]["trunk_vlans"] == [30]
    assert vlans[10]["mode"] == "flat"

    lag = by_port(api.get(f"/api/switches/{sid}/lag").json()["ports"])
    assert lag[9]["group"] == 1 and lag[10]["group"] == 0

    stp = by_port(api.get(f"/api/switches/{sid}/stp").json()["ports"])
    assert stp[9]["edge"] and not stp[10]["edge"]

    loop = by_port(api.get(f"/api/switches/{sid}/loop").json())
    assert loop[9]["enabled"] and loop[9]["violation"] and not loop[10]["enabled"]

    mirror = api.get(f"/api/switches/{sid}/mirror").json()
    assert mirror["monitoring_port"] == 9

    macs = api.get(f"/api/switches/{sid}/mac/dynamic").json()["entries"]
    assert macs[0]["port"] == 9 and "vendor" in macs[0]

    static = api.get(f"/api/switches/{sid}/mac/static").json()
    assert static == [{"idx": "0", "mac": "AA:BB:CC:00:00:02", "port": 9, "fid": "0", "vlan": None, "age": ""}]


def test_reads_with_swap_relabel_sfp_ports(api):
    sid = add_switch(api, swap=True)
    ports = by_port(api.get(f"/api/switches/{sid}/ports").json())
    assert ports[10]["speed_actual"] == "10GbpsFull" and ports[10]["internal_port"] == 9
    assert ports[9]["speed_actual"] == "Link Down" and ports[9]["internal_port"] == 10
    assert [p["port"] for p in api.get(f"/api/switches/{sid}/ports").json()] == list(range(1, 11))

    assert by_port(api.get(f"/api/switches/{sid}/ports/stats").json())[10]["link"] == "Link Up"
    assert by_port(api.get(f"/api/switches/{sid}/vlans/assignments").json())[10]["trunk_vlans"] == [30]
    assert by_port(api.get(f"/api/switches/{sid}/lag").json()["ports"])[10]["group"] == 1
    assert by_port(api.get(f"/api/switches/{sid}/stp").json()["ports"])[10]["edge"]
    assert by_port(api.get(f"/api/switches/{sid}/loop").json())[10]["violation"]
    assert api.get(f"/api/switches/{sid}/mirror").json()["monitoring_port"] == 10
    assert api.get(f"/api/switches/{sid}/mac/dynamic").json()["entries"][0]["port"] == 10
    assert api.get(f"/api/switches/{sid}/mac/static").json()[0]["port"] == 10


# ── Writes ──
@pytest.mark.parametrize("swap,expected_internal", [(False, "9"), (True, "10")])
def test_every_write_path_translates_port_9(api, swap, expected_internal):
    sid = add_switch(api, swap=swap)
    m = api.mock
    other = "10" if expected_internal == "9" else "9"

    assert api.post(f"/api/switches/{sid}/ports/config",
                    json=[{"port": 9, "enabled": False, "speed": "Auto", "flow_ctrl": "On"}]).status_code == 200
    assert m.posted("apply_user_port_setting.json")[-1]["port_list"] == [expected_internal]

    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[
        {"port": 9, "mode": "trunk", "native_vlan": 5, "trunk_vlans": [10]},
        {"port": 2, "mode": "access", "access_vlan": 7},
    ]).status_code == 200
    pv = m.posted("port_vlan_cfg.json")[-1]
    assert pv[f"checkboxTag_{expected_internal}"] == "on" and pv[f"fidName_{expected_internal}"] == "5"
    assert pv["fidName_2"] == "7" and pv["checkboxUntag_2"] == "on"
    assert len([k for k in pv if k.startswith("checkbox_")]) == 10  # every port written explicitly
    assert m.posted("tag_vlan_cfg.json")[-1]["ppName_0"] == expected_internal

    assert api.post(f"/api/switches/{sid}/lag", json={
        "system_priority": 4096, "ports": [{"port": 9, "type": 1, "timeout": 0, "group": 2}],
        "group_names": {"2": "Uplink"}}).status_code == 200
    lag = m.posted("port_trunk_cfg.json")[-1]
    assert lag[f"Port_{expected_internal}_grpInd"] == "2" and lag["system_priority"] == "4096"
    assert api.get(f"/api/switches/{sid}/lag").json()["group_names"] == {2: "Uplink"} or \
        api.get(f"/api/switches/{sid}/lag").json()["group_names"] == {"2": "Uplink"}

    assert api.post(f"/api/switches/{sid}/loop", json={"ports": {"9": True, "1": False}}).status_code == 200
    assert m.posted("port_lock_cfg.json")[-1] == {f"checkbox_{expected_internal}": "on"}

    assert api.post(f"/api/switches/{sid}/stp", json={"enabled": True, "mode": "rstp", "edge_ports": [9]}).status_code == 200
    stp = m.posted("stp.json")[-1]
    assert stp[f"Stp_Edge_{expected_internal}"] == "1" and stp[f"Stp_Edge_{other}"] == "0" and stp["stp_mode"] == "1"

    assert api.post(f"/api/switches/{sid}/mirror", json={
        "monitoring_port": 9, "ingress": "1", "egress": "0", "mirrored_ports": [1, 9]}).status_code == 200
    select, clear = m.posted("port_mirror.json")[-2:]
    assert select["mirroring_port_selection"] == expected_internal
    assert select["mirrored_port_selection"] == ["1"]  # the monitor port is never also a source
    assert select["Ingress_Status"] == "1" and select["Egress_Status"] == "0"
    # second request, like the native UI: every other port switched off on the same destination
    assert clear["mirroring_port_selection"] == expected_internal
    assert clear["mirrored_port_selection"] == [str(i) for i in range(2, 11)]  # every non-source, destination included
    assert clear["Ingress_Status"] == "0" and clear["Egress_Status"] == "0"

    assert api.post(f"/api/switches/{sid}/mac/static/add",
                    json={"mac": "AA:BB:CC:00:00:03", "port": 9, "fid": 3}).status_code == 200
    assert m.posted("mac_add_static_mac_entries.json")[-1]["port-input"] == expected_internal
    assert m.posted("mac_save_static_mac_entries.json")

    assert api.post(f"/api/switches/{sid}/mac/static/delete",
                    json={"mac": "AA:BB:CC:00:00:03", "port": 9, "fid": 3}).status_code == 200
    assert m.posted("mac_delete_static_mac_entries.json")[-1]["port-input"] == expected_internal


def test_invalid_ports_are_rejected_before_any_write(api):
    sid = add_switch(api)
    m = api.mock
    r = api.post(f"/api/switches/{sid}/ports/config", json=[{"port": 1, "enabled": True}, {"port": 11, "enabled": False}])
    assert r.status_code == 400 and "out of range" in r.text
    assert not m.posted("apply_user_port_setting.json")

    assert api.post(f"/api/switches/{sid}/mac/static/add", json={"mac": "AA:BB:CC:00:00:03", "port": 0}).status_code == 400
    assert api.post(f"/api/switches/{sid}/mac/static/add", json={"mac": "AA:BB:CC:00:00:03", "port": "x"}).status_code in (400, 422)
    assert not m.posted("mac_add_static_mac_entries.json")

    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 12, "mode": "access", "access_vlan": 1}]).status_code == 400
    assert not m.posted("port_vlan_cfg.json") and not m.posted("init_vlan.json")

    assert api.post(f"/api/switches/{sid}/mirror", json={"monitoring_port": 11, "mirrored_ports": [1]}).status_code == 400
    assert api.post(f"/api/switches/{sid}/loop", json={"ports": {"0": True}}).status_code == 400
    assert api.post(f"/api/switches/{sid}/ports/description", json={"port": 11, "description": "x"}).status_code == 422
    assert not m.posted("port_mirror.json") and not m.posted("port_lock_cfg.json")


def test_mirror_can_be_disabled(api):
    sid = add_switch(api)
    assert api.get(f"/api/switches/{sid}/mirror").json()["enabled"] is True  # port 1 -> 9 in the fixture
    assert api.post(f"/api/switches/{sid}/mirror", json={"monitoring_port": 0, "mirrored_ports": []}).status_code == 200
    posts = api.mock.posted("port_mirror.json")
    assert len(posts) == 1  # the firmware keeps the destination: off = all sources cleared on it
    assert posts[0]["mirroring_port_selection"] == "9"
    assert posts[0]["mirrored_port_selection"] == [str(i) for i in range(1, 11)]  # all ten, as the native UI
    assert posts[0]["Ingress_Status"] == "0" and posts[0]["Egress_Status"] == "0"

    api.mock.state["port_mirror.json"]["MonitoringPortId"] = "0"
    assert api.post(f"/api/switches/{sid}/mirror", json={"monitoring_port": 0}).status_code == 200
    assert len(api.mock.posted("port_mirror.json")) == 1  # nothing was ever configured: nothing sent


def test_dynamic_mac_search_is_url_encoded(api):
    sid = add_switch(api)
    assert api.get(f"/api/switches/{sid}/mac/dynamic", params={"search": "AA:BB"}).status_code == 200
    assert any("mac_search_dynamic_mac_entries.json?mac_search_txt=AA%3ABB" in u for u in api.mock.gets)


# ── The setting itself ──
def test_port_mapping_toggle_relabels_live_client_and_moves_descriptions(api):
    sid = add_switch(api, swap=False)
    assert api.get(f"/api/switches/{sid}/info").json()["swap_sfp_9_10"] is False
    assert api.get("/api/switches").json()[0]["swap_sfp_9_10"] is False
    for port, text in ((9, "uplink"), (10, "spare")):
        api.post(f"/api/switches/{sid}/ports/description", json={"port": port, "description": text})
    assert by_port(api.get(f"/api/switches/{sid}/ports").json())[9]["description"] == "uplink"

    client_before = sse._clients[sid]
    r = api.put(f"/api/switches/{sid}/port-mapping", json={"swap_sfp_9_10": True})
    assert r.status_code == 200 and r.json() == {"swap_sfp_9_10": True, "moved_descriptions": True}
    assert sse._clients[sid] is client_before and client_before.swap_sfp is True

    ports = by_port(api.get(f"/api/switches/{sid}/ports").json())
    # the 10G cage is now labelled 10, and its description came with it
    assert ports[10]["speed_actual"] == "10GbpsFull" and ports[10]["description"] == "uplink"
    assert ports[9]["description"] == "spare"
    assert api.get(f"/api/switches/{sid}/info").json()["swap_sfp_9_10"] is True

    # idempotent: same value again changes nothing and moves nothing
    r = api.put(f"/api/switches/{sid}/port-mapping", json={"swap_sfp_9_10": True})
    assert r.json() == {"swap_sfp_9_10": True, "moved_descriptions": False}
    assert by_port(api.get(f"/api/switches/{sid}/ports").json())[10]["description"] == "uplink"

    # flipping back without moving descriptions keeps them on their labels
    r = api.put(f"/api/switches/{sid}/port-mapping", json={"swap_sfp_9_10": False, "move_descriptions": False})
    assert r.json() == {"swap_sfp_9_10": False, "moved_descriptions": False}
    ports = by_port(api.get(f"/api/switches/{sid}/ports").json())
    assert ports[9]["speed_actual"] == "10GbpsFull" and ports[9]["description"] == "spare"
    assert ports[10]["description"] == "uplink"

    log = sqlite3.connect(dbmod.DB_PATH).execute("SELECT action, details FROM change_log").fetchall()
    assert len(log) == 2 and log[0][0] == "port_mapping"


def test_port_mapping_requires_admin_and_existing_switch(api):
    sid = add_switch(api)
    assert api.put("/api/switches/999/port-mapping", json={"swap_sfp_9_10": True}).status_code == 404
    assert api.post("/api/users", json={"username": "ro", "password": "viewer123", "role": "viewer"}).status_code == 200
    token = api.post("/api/auth/login", json={"username": "ro", "password": "viewer123"}).json()["token"]
    r = api.put(f"/api/switches/{sid}/port-mapping", json={"swap_sfp_9_10": True},
                headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_snapshot_records_numbering_and_user_ports(api):
    sid = add_switch(api, swap=True)
    snap_id = api.post(f"/api/switches/{sid}/snapshots", json={"name": "s1"}).json()["id"]
    cfg = api.get(f"/api/switches/{sid}/snapshots/{snap_id}").json()["config"]
    assert cfg["meta"] == {"schema": 2, "port_numbering": "user", "swap_sfp_9_10": True, "firmware": "1.0.0.6"}
    assert cfg["mirror"]["monitoring_port"] == 10
    assert by_port(cfg["lag"]["ports"])[10]["group"] == 1
    assert by_port(cfg["loop"])[10]["enabled"]
    assert by_port(cfg["ports"])[10]["internal_port"] == 9


# ── Switch lifecycle & client cache ──
def test_update_switch_reconfigures_shared_client_in_place(api):
    sid = add_switch(api)
    api.get(f"/api/switches/{sid}/ports")
    client = sse._clients[sid]
    r = api.put(f"/api/switches/{sid}", json={"name": "Core", "ip": "10.0.0.9"})
    assert r.status_code == 200 and r.json()["ip"] == "10.0.0.9" and r.json()["name"] == "Core"
    assert sse._clients[sid] is client and client.base == "http://10.0.0.9:80"
    assert api.get(f"/api/switches/{sid}/info").json()["name"] == "Core"
    # a rename alone must not probe the switch again
    logins = api.mock.logins
    assert api.put(f"/api/switches/{sid}", json={"name": "Core2"}).status_code == 200
    assert api.mock.logins == logins


def test_delete_switch_drops_client_and_related_rows(api):
    sid = add_switch(api)
    api.post(f"/api/switches/{sid}/ports/description", json={"port": 3, "description": "cam"})
    api.get(f"/api/switches/{sid}/ports")
    assert sid in sse._clients
    assert api.delete(f"/api/switches/{sid}").status_code == 200
    assert sid not in sse._clients
    assert api.get(f"/api/switches/{sid}/info").status_code == 404
    assert api.delete(f"/api/switches/{sid}").status_code == 404
    rows = sqlite3.connect(dbmod.DB_PATH).execute("SELECT COUNT(*) FROM port_descriptions").fetchone()[0]
    assert rows == 0


# ── Migration ──
def test_migration_adds_column_and_keeps_legacy_swap(db_path):
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE switches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, ip TEXT NOT NULL,
            username TEXT NOT NULL, password TEXT NOT NULL, model TEXT DEFAULT '',
            firmware TEXT DEFAULT '', mac_address TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO switches (name, ip, username, password) VALUES ('old', '10.0.0.1', 'admin', 'admin');
        INSERT INTO switches (name, ip, username, password, firmware) VALUES ('v1', '10.0.0.3', 'a', 'b', '1.0.0.6');
        INSERT INTO switches (name, ip, username, password, firmware) VALUES ('v2', '10.0.0.4', 'a', 'b', '2.0.0.2');
    """)
    con.commit()
    con.close()

    asyncio.run(dbmod.init_db())
    asyncio.run(dbmod.init_db())  # idempotent

    con = sqlite3.connect(db_path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(switches)")}
    assert "swap_sfp_9_10" in cols
    assert con.execute("SELECT swap_sfp_9_10 FROM switches WHERE name='old'").fetchone() == (1,)  # unknown: as before
    assert con.execute("SELECT swap_sfp_9_10 FROM switches WHERE name='v1'").fetchone() == (1,)
    assert con.execute("SELECT swap_sfp_9_10 FROM switches WHERE name='v2'").fetchone() == (0,)  # issue #3
    assert con.execute("PRAGMA user_version").fetchone() == (dbmod.SCHEMA_VERSION,)
    con.execute("INSERT INTO switches (name, ip, username, password) VALUES ('new', '10.0.0.2', 'a', 'b')")
    assert con.execute("SELECT swap_sfp_9_10 FROM switches WHERE name='new'").fetchone() == (0,)


# ── Default numbering from the firmware line ──
@pytest.mark.parametrize("fw, expected", [
    ("1.0.0.4", True), ("1.0.0.6", True), ("V1.0.0.6", True),
    ("2.0.0.2", False), ("2.0.0.3", False), ("", None), (None, None), ("unknown", None),
])
def test_default_swap_follows_the_firmware_line(fw, expected):
    assert default_swap_sfp(fw) is expected


@pytest.mark.parametrize("fw, expected", [("1.0.0.4", True), ("2.0.0.2", False), ("", False)])
def test_adding_a_switch_picks_the_numbering_from_its_firmware(api, fw, expected):
    api.mock.state["status.json"]["fw_ver"] = fw
    r = api.post("/api/switches", json={"name": "auto", "ip": "10.0.0.2", "username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    assert r.json()["swap_sfp_9_10"] is expected and r.json()["swap_auto"] is True
    assert api.get(f"/api/switches/{r.json()['id']}/info").json()["swap_sfp_9_10"] is expected


def test_an_explicit_choice_wins_over_the_firmware_line(api):
    api.mock.state["status.json"]["fw_ver"] = "1.0.0.4"
    r = api.post("/api/switches", json={"name": "x", "ip": "10.0.0.2", "username": "admin", "password": "admin",
                                        "swap_sfp_9_10": False})
    assert r.json()["swap_sfp_9_10"] is False and r.json()["swap_auto"] is False


def test_status_reports_what_the_firmware_line_suggests(api):
    sid = add_switch(api, swap=False)
    assert api.get(f"/api/switches/{sid}/status").json()["swap_sfp_suggested"] is True  # fixture runs 1.0.0.6
    api.mock.state["status.json"]["fw_ver"] = "2.0.0.2"
    assert api.get(f"/api/switches/{sid}/status").json()["swap_sfp_suggested"] is False


def test_upgrade_from_2_1_0_sets_each_switch_to_its_firmware_line_once(db_path):
    """2.1.0 already had the column: every switch on 2.0.0.x was swapped (legacy) and every
    switch added under 2.1.0 was not. The schema-version step corrects both, once, and moves the
    9/10 descriptions with the cages."""
    asyncio.run(dbmod.init_db())
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA user_version = 0")  # what a 2.1.0 database looks like
    rows = [("v2-legacy", "2.0.0.2", 1), ("v1-added-2.1.0", "1.0.0.4", 0), ("v1-ok", "1.0.0.6", 1),
            ("unknown", "", 0), ("v2-ok", "2.0.0.3", 0)]
    for name, fw, swap in rows:
        con.execute("INSERT INTO switches (name, ip, username, password, firmware, swap_sfp_9_10) VALUES (?,?,?,?,?,?)",
                    (name, "10.0.0.9", "a", "b", fw, swap))
    ids = {n: i for i, n in con.execute("SELECT id, name FROM switches")}
    for name in ("v2-legacy", "v1-added-2.1.0", "v1-ok"):
        con.execute("INSERT INTO port_descriptions (switch_id, port, description) VALUES (?, 9, 'nas'), (?, 10, 'spare')",
                    (ids[name], ids[name]))
    con.commit()
    con.close()

    asyncio.run(dbmod.init_db())
    asyncio.run(dbmod.init_db())  # runs once

    con = sqlite3.connect(db_path)
    swap = dict(con.execute("SELECT name, swap_sfp_9_10 FROM switches"))
    assert swap == {"v2-legacy": 0, "v1-added-2.1.0": 1, "v1-ok": 1, "unknown": 0, "v2-ok": 0}
    desc = lambda n: dict(con.execute("SELECT port, description FROM port_descriptions WHERE switch_id=?", (ids[n],)))
    assert desc("v2-legacy") == {9: "spare", 10: "nas"}       # moved with the cages
    assert desc("v1-added-2.1.0") == {9: "spare", 10: "nas"}
    assert desc("v1-ok") == {9: "nas", 10: "spare"}           # unchanged switch, unchanged labels
    logged = con.execute("SELECT switch_id, user_id, action FROM change_log ORDER BY switch_id").fetchall()
    assert logged == [(ids["v2-legacy"], 0, "port_mapping"), (ids["v1-added-2.1.0"], 0, "port_mapping")]
    assert con.execute("PRAGMA user_version").fetchone() == (dbmod.SCHEMA_VERSION,)


def test_automatic_change_log_entries_are_attributed_to_switchpilot(api):
    sid = add_switch(api)
    con = sqlite3.connect(dbmod.DB_PATH)
    con.execute("INSERT INTO change_log (switch_id, user_id, action, details) VALUES (?, 0, 'port_mapping', '{}')", (sid,))
    con.commit()
    con.close()
    assert api.get(f"/api/switches/{sid}/changes").json()[0]["username"] == "SwitchPilot"
