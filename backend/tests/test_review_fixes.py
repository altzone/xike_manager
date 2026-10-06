"""Regression tests for the issues found in the full code review."""
import os
import sqlite3

import httpx
import pytest
from jose import jwt

import auth
import db as dbmod
import sse
from conftest import add_switch, login_as, ADMIN_PASSWORD


# ── Secrets & sessions ──
def test_secret_key_is_generated_and_persisted(tmp_path, monkeypatch):
    path = tmp_path / "secret_key"
    monkeypatch.setenv("SECRET_KEY_FILE", str(path))
    for default in ("", "switchpilot-prod-change-me", "switchpilot-secret-change-me-in-prod"):
        monkeypatch.setenv("SECRET_KEY", default)
        key = auth.load_secret_key()
        assert len(key) >= 32 and key != default
        assert path.read_text().strip() == key
        assert oct(path.stat().st_mode & 0o777) == "0o600"
        assert auth.load_secret_key() == key  # stable across restarts
    monkeypatch.setenv("SECRET_KEY", "my-own-very-long-production-secret")
    assert auth.load_secret_key() == "my-own-very-long-production-secret"


def test_setup_requires_a_real_password_and_runs_once(db_path, mock_switch):
    from fastapi.testclient import TestClient
    import main
    sse._clients.clear()
    with TestClient(main.app) as c:
        assert c.post("/api/setup", json={"username": "admin", "password": "pw"}).status_code == 400
        assert c.post("/api/setup", json={"username": "admin", "password": "secret123"}).status_code == 200
        assert c.post("/api/setup", json={"username": "other", "password": "secret123"}).status_code == 400


def test_login_failures_are_rate_limited(api):
    api.headers.pop("Authorization")
    for _ in range(auth.LOGIN_MAX_FAILURES):
        assert api.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"}).status_code == 401
    assert api.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 429
    auth._failures.clear()
    assert api.post("/api/auth/login", json={"username": "nobody", "password": "whatever"}).status_code == 401
    assert api.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200


def test_demoted_or_deleted_users_lose_access_immediately(api):
    assert api.post("/api/users", json={"username": "bob", "password": "bobpass1", "role": "admin"}).status_code == 200
    bob_id = next(u["id"] for u in api.get("/api/users").json() if u["username"] == "bob")
    bob = login_as(api, "bob", "bobpass1")
    assert api.get("/api/users", headers=bob).status_code == 200
    assert api.put(f"/api/users/{bob_id}", json={"role": "viewer"}).status_code == 200
    assert api.get("/api/users", headers=bob).status_code == 403  # token still says admin, DB says viewer
    assert api.get("/api/auth/me", headers=bob).json()["role"] == "viewer"
    assert api.delete(f"/api/users/{bob_id}").status_code == 200
    assert api.get("/api/switches", headers=bob).status_code == 401


def test_admin_lockout_guards(api):
    me = int(api.get("/api/auth/me").json()["sub"])
    assert api.put(f"/api/users/{me}", json={"role": "viewer"}).status_code == 400   # own role
    assert api.delete(f"/api/users/{me}").status_code == 400                        # yourself
    assert api.post("/api/users", json={"username": "x", "password": "short", "role": "viewer"}).status_code == 400
    assert api.post("/api/users", json={"username": "x", "password": "longenough", "role": "root"}).status_code == 400
    assert api.post("/api/users", json={"username": "x", "password": "longenough", "role": "viewer"}).status_code == 200
    assert api.post("/api/users", json={"username": "x", "password": "longenough", "role": "viewer"}).status_code == 409
    x_id = next(u["id"] for u in api.get("/api/users").json() if u["username"] == "x")
    assert api.put(f"/api/users/{x_id}", json={"role": "admin"}).status_code == 200
    # now two admins: demoting the other one is fine, then nobody can demote/delete the last one
    assert api.put(f"/api/users/{x_id}", json={"role": "viewer"}).status_code == 200
    headers_x = login_as(api, "x", "longenough")
    assert api.put(f"/api/users/{me}", json={"role": "viewer"}, headers=headers_x).status_code == 403
    assert api.put(f"/api/users/{x_id}", json={"role": "admin"}).status_code == 200
    x = login_as(api, "x", "longenough")
    assert api.put(f"/api/users/{me}", json={"role": "viewer"}, headers=x).status_code == 200  # two admins
    assert api.put(f"/api/users/{x_id}", json={"role": "viewer"}, headers=x).status_code == 400  # own role
    assert api.delete(f"/api/users/{x_id}", headers=x).status_code == 400                       # yourself
    assert api.put(f"/api/users/{x_id}", json={"password": "tiny"}, headers=x).status_code == 400
    assert api.put("/api/users/999", json={"role": "viewer"}, headers=x).status_code == 404


def test_sse_needs_a_short_lived_stream_token(api):
    sid = add_switch(api)
    api_token = api.headers["Authorization"].split()[1]
    assert api.get(f"/api/switches/{sid}/sse", params={"token": api_token}).status_code == 401
    token = api.post("/api/auth/stream-token").json()["token"]
    claims = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    assert claims["scope"] == "stream" and claims["exp"] - claims.get("iat", claims["exp"] - 300) <= 300
    assert api.get("/api/switches", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ── Switch errors are 502, never 500 ──
def test_switch_problems_are_reported_as_502(api):
    sid = add_switch(api)
    m = api.mock
    m.responders["status.json"] = lambda r: httpx.Response(500, text="oops")
    r = api.get(f"/api/switches/{sid}/status")
    assert r.status_code == 502 and "HTTP 500" in r.json()["detail"]

    m.responders["status.json"] = lambda r: httpx.Response(200, text="")
    assert api.get(f"/api/switches/{sid}/status").status_code == 502  # non-JSON body

    def unreachable(r):
        raise httpx.ConnectError("No route to host")
    m.responders["status.json"] = unreachable
    r = api.get(f"/api/switches/{sid}/status")
    assert r.status_code == 502 and "unreachable" in r.json()["detail"]
    assert api.get(f"/api/switches/{sid}/ping").json()["online"] is False
    m.responders.clear()

    m.reject_login = True
    sse._clients[sid]._logged_in = False
    r = api.get(f"/api/switches/{sid}/ports")
    assert r.status_code == 502 and "Login" in r.json()["detail"]


def test_switch_address_is_validated(api):
    for bad in ("http://10.0.0.2/", "10.0.0.2:8080", "10.0.0.2/status.json", "", "a b"):
        r = api.post("/api/switches", json={"name": "x", "ip": bad, "username": "a", "password": "b"})
        assert r.status_code == 400, bad
    sid = add_switch(api)
    assert api.put(f"/api/switches/{sid}", json={"ip": "10.0.0.2/../x"}).status_code == 400


# ── VLAN apply: merge, bridge, order, atomicity ──
def endpoints(m):
    return [ep for ep, _ in m.posts]


def test_vlan_apply_keeps_untouched_ports_and_the_uplink(api):
    sid = add_switch(api)  # fixture: port 9 trunk native 20 + tagged 30, everything else flat
    m = api.mock
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == [] and r.json()["tag_entries"] == 1
    assert endpoints(m) == ["init_vlan.json", "port_vlan_cfg.json", "tag_vlan_cfg.json",
                            "save_port_vlan_map.json", "save_tag_vlan_map.json"]
    pv = m.posted("port_vlan_cfg.json")[0]
    assert pv["checkbox_5"] == "on" and pv["fidName_5"] == "10" and pv["checkboxUntag_5"] == "on" and pv["checkboxTag_5"] == ""
    assert pv["checkbox_9"] == "on" and pv["fidName_9"] == "20" and pv["checkboxTag_9"] == "on"  # untouched trunk kept
    assert pv["checkbox_1"] == "" and pv["fidName_1"] == "0"                                     # flat, written explicitly
    assert len([k for k in pv if k.startswith("checkbox_")]) == 10
    tv = m.posted("tag_vlan_cfg.json")[0]
    assert tv["ppName_0"] == "9" and tv["oVidName_0"] == "30"  # carried over
    assert tv["brName_0"] == "30"  # ...and moved from bridge 0 (earlier versions) to its VLAN's bridge


def test_vlan_apply_bridge_native_and_pvid_zero(api):
    sid = add_switch(api)
    m = api.mock
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[
        {"port": 9, "mode": "trunk", "native_vlan": 5, "trunk_vlans": [5, 100, 10, 10]},
        {"port": 2, "mode": "trunk", "native_vlan": 0, "trunk_vlans": [7]},
    ])
    assert r.status_code == 200, r.text
    tv = m.posted("tag_vlan_cfg.json")[-1]
    entries = {(tv[f"ppName_{i}"], tv[f"oVidName_{i}"]): tv[f"brName_{i}"] for i in range(3)}
    assert entries[("2", "7")] == "7" and entries[("9", "10")] == "10"  # native 5 skipped, dup removed
    assert 1 <= int(entries[("9", "100")]) <= 63 and entries[("9", "100")] not in ("5", "7", "10", "20", "30")  # own bridge
    assert "oVidName_3" not in tv
    pv = m.posted("port_vlan_cfg.json")[-1]
    assert pv["fidName_9"] == "5" and pv["fidName_2"] == "0" and pv["checkboxTag_2"] == "on"


def test_vlan_apply_validation(api):
    sid = add_switch(api)
    m = api.mock
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[]).status_code == 400
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[
        {"port": 2, "mode": "access", "access_vlan": 3}, {"port": 2, "mode": "flat"}]).status_code == 400
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 2, "mode": "hybrid"}]).status_code == 422
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 2, "mode": "access", "access_vlan": 64}]).status_code == 422
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[
        {"port": 2, "mode": "trunk", "trunk_vlans": [5000]}]).status_code == 400
    assert not m.posts
    many = [{"port": 9, "mode": "trunk", "native_vlan": 1, "trunk_vlans": list(range(2, 64))},   # 62 entries
            {"port": 8, "mode": "trunk", "native_vlan": 1, "trunk_vlans": list(range(2, 51))}]   # + 49 = 111
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=many).status_code == 200  # exactly the maximum
    many[1]["trunk_vlans"].append(51)
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=many).status_code == 400


def test_vlan_apply_save_timeout_is_reported_not_fatal(api):
    sid = add_switch(api)
    api.mock.fail_once("save_port_vlan_map.json", httpx.ReadTimeout("slow flash"))
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 3, "mode": "access", "access_vlan": 2}])
    assert r.status_code == 200
    assert len(r.json()["warnings"]) == 1 and "port VLANs" in r.json()["warnings"][0]
    assert endpoints(api.mock)[-1] == "save_tag_vlan_map.json"  # the second save was still attempted


def test_vlan_apply_failure_restores_previous_tables(api):
    sid = add_switch(api)
    m = api.mock
    m.fail_once("tag_vlan_cfg.json", httpx.ReadError("gone"))
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 2, "mode": "trunk", "native_vlan": 1, "trunk_vlans": [10]}])
    assert r.status_code == 502 and "restored" in r.json()["detail"]
    eps = endpoints(m)
    assert eps == ["init_vlan.json", "port_vlan_cfg.json", "port_vlan_cfg.json", "tag_vlan_cfg.json"]
    restored_pv, restored_tv = m.posted("port_vlan_cfg.json")[-1], m.posted("tag_vlan_cfg.json")[-1]
    assert restored_pv["fidName_9"] == "20" and restored_pv["checkbox_2"] == ""
    assert restored_tv["ppName_0"] == "9" and restored_tv["oVidName_0"] == "30"
    assert "save_port_vlan_map.json" not in eps


def test_vlan_list_merges_in_use_without_writing(api):
    sid = add_switch(api)
    vlans = api.get(f"/api/switches/{sid}/vlans").json()
    for v in vlans:
        v.pop("deletable")
    assert vlans == [{"vlan_id": 20, "name": "VLAN 20", "defined": False, "in_use": True},
                     {"vlan_id": 30, "name": "VLAN 30", "defined": False, "in_use": True}]
    assert sqlite3.connect(dbmod.DB_PATH).execute("SELECT COUNT(*) FROM vlans").fetchone()[0] == 0
    assert api.post(f"/api/switches/{sid}/vlans", json={"vlan_id": 20, "name": "Office"}).status_code == 200
    assert api.post(f"/api/switches/{sid}/vlans", json={"vlan_id": 20, "name": "Office"}).status_code == 409
    assert api.post(f"/api/switches/{sid}/vlans", json={"vlan_id": 4095, "name": "x"}).status_code == 422
    assert api.post(f"/api/switches/{sid}/vlans", json={"vlan_id": 40, "name": "Lab"}).status_code == 200
    vlans = {v["vlan_id"]: v for v in api.get(f"/api/switches/{sid}/vlans").json()}
    assert vlans[20] == {"vlan_id": 20, "name": "Office", "defined": True, "in_use": True, "deletable": True}
    assert vlans[40] == {"vlan_id": 40, "name": "Lab", "defined": True, "in_use": False, "deletable": True}
    assert api.delete(f"/api/switches/{sid}/vlans/20").status_code == 200
    assert api.get(f"/api/switches/{sid}/vlans").json()[0]["name"] == "VLAN 20"  # still in use, name gone
    api.get(f"/api/switches/{sid}/vlans/assignments")
    assert sqlite3.connect(dbmod.DB_PATH).execute("SELECT COUNT(*) FROM vlans").fetchone()[0] == 1


# ── Ports / network ──
def test_management_port_needs_force_to_be_disabled(api):
    sid = add_switch(api)
    r = api.post(f"/api/switches/{sid}/ports/config", json=[{"port": 1, "enabled": False}])
    assert r.status_code == 400 and "management" in r.json()["detail"]
    assert not api.mock.posts
    assert api.post(f"/api/switches/{sid}/ports/config", json=[{"port": 1, "enabled": False, "force": True}]).status_code == 200
    assert api.post(f"/api/switches/{sid}/ports/config", json=[{"port": 2, "enabled": False}]).status_code == 200
    assert api.post(f"/api/switches/{sid}/ports/config", json=[{"port": 2, "speed": "2500Mbps Full"}]).status_code == 200
    assert api.post(f"/api/switches/{sid}/ports/config", json=[{"port": 2, "speed": "warp"}]).status_code == 400
    assert api.post(f"/api/switches/{sid}/ports/config", json=[]).status_code == 400


def test_network_change_keeps_switchpilot_pointed_at_the_switch(api):
    sid = add_switch(api)
    api.mock.state["network_settings.json"]["ipAddress"] = "10.0.0.2"  # SwitchPilot talks to the switch's own address
    api.get(f"/api/switches/{sid}/ports")
    client = sse._clients[sid]
    bad = {"dhcp": False, "ip": "10.0.0.300", "netmask": "255.255.255.0", "gateway": "10.0.0.1"}
    assert api.post(f"/api/switches/{sid}/network", json=bad).status_code == 400
    bad["ip"], bad["gateway"] = "10.0.0.50", "192.168.9.1"
    assert api.post(f"/api/switches/{sid}/network", json=bad).status_code == 400  # gateway outside subnet
    assert not api.mock.posted("network_settings_ipv4.json")

    good = {"dhcp": False, "ip": "10.0.0.50", "netmask": "255.255.255.0", "gateway": "10.0.0.1"}
    r = api.post(f"/api/switches/{sid}/network", json=good)
    assert r.status_code == 200 and r.json()["ip"] == "10.0.0.50"
    assert api.mock.posted("network_settings_ipv4.json")[-1] == {
        "input_ip": "10.0.0.50", "input_netmask": "255.255.255.0", "input_gateway": "10.0.0.1", "dhcp_enable": "0"}
    assert api.get(f"/api/switches/{sid}/info").json()["ip"] == "10.0.0.50"
    assert sse._clients[sid] is client and client.base == "http://10.0.0.50:80"

    r = api.post(f"/api/switches/{sid}/network", json={"dhcp": True})
    assert r.status_code == 200 and r.json()["dhcp"] is True and "DHCP" in r.json()["note"]


def test_lag_names_and_validation(api):
    sid = add_switch(api)
    r = api.put(f"/api/switches/{sid}/lag/names", json={"group_names": {"1": "Uplink"}})
    assert r.status_code == 200 and r.json()["group_names"] == {1: "Uplink"} or r.json()["group_names"] == {"1": "Uplink"}
    assert not api.mock.posted("port_trunk_cfg.json")
    assert api.post(f"/api/switches/{sid}/lag", json={"ports": [{"port": 2, "type": 5}]}).status_code == 422
    assert api.post(f"/api/switches/{sid}/lag", json={"ports": [{"port": 2, "type": 1}, {"port": 2, "type": 1}]}).status_code == 400
    assert api.post(f"/api/switches/{sid}/lag", json={"ports": [{"port": 2, "type": 2, "group": 1}]}).status_code == 200
    posted = api.mock.posted("port_trunk_cfg.json")[-1]
    assert posted["portTypeId_2"] == "2" and posted["portPriorityId_2"] == "128"


def test_sntp_and_time_inputs(api):
    sid = add_switch(api)
    r = api.post(f"/api/switches/{sid}/sntp", json={"enabled": True, "server": "1.2.3.4", "poll": 64})
    assert r.status_code == 200 and r.json()["resolved_ip"] == "1.2.3.4"
    assert api.post(f"/api/switches/{sid}/sntp", json={"enabled": True, "server": "", "poll": 64}).status_code == 422
    assert api.post(f"/api/switches/{sid}/time", json={"timezone": "Europe/Paris"}).status_code == 422
    assert api.post(f"/api/switches/{sid}/time", json={"timezone": "+09:00"}).status_code == 200
    assert api.mock.posted("systemtime_settings.json")[-1]["timezone_offset"] == "+09:00"
    check = api.get(f"/api/switches/{sid}/sntp/check").json()
    assert check["enabled"] is True and check["synced"] is True
    api.mock.state["sntp_setting.json"]["sntp_state"] = "0"
    assert api.get(f"/api/switches/{sid}/sntp/check").json()["synced"] is False
    api.mock.state.pop("sntp_setting.json"); api.mock.state.pop("systemtime_settings.json")
    assert api.get(f"/api/switches/{sid}/time").json() == {"supported": False}
    assert api.post(f"/api/switches/{sid}/sntp", json={"enabled": True, "server": "1.2.3.4"}).status_code == 400


def test_change_log_records_actions(api):
    sid = add_switch(api)
    api.post(f"/api/switches/{sid}/ports/config", json=[{"port": 2, "enabled": False}])
    api.post(f"/api/switches/{sid}/stp", json={"enabled": True, "mode": "rstp"})
    log = api.get(f"/api/switches/{sid}/changes").json()
    assert [e["action"] for e in log] == ["stp", "ports"]
    assert log[0]["username"] == "admin" and log[0]["details"]["mode"] == "rstp"
    assert api.get("/api/switches/999/changes").status_code == 404


def test_reboot_survives_the_switch_dropping_the_connection(api):
    sid = add_switch(api)

    def drop(r):
        raise httpx.RemoteProtocolError("connection closed")
    api.mock.responders["system_reboot.json"] = drop
    assert api.post(f"/api/switches/{sid}/reboot").status_code == 200
