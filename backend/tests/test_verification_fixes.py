"""Fixes from the verification pass over the review branch (login throttle, sessions,
switch session handling, VLAN bridges, network changes, mirror, static MACs)."""
import asyncio
from types import SimpleNamespace

import httpx

import auth
import sse
import switch_client
from conftest import add_switch, login_as


def _req(headers: dict, host: str = "127.0.0.1"):
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def _bad_login(api, username="admin", headers=None):
    return api.post("/api/auth/login", json={"username": username, "password": "wrong"},
                    headers=headers or {}).status_code


# ── Login throttle ──
def test_client_ip_unwinds_only_trusted_proxies(monkeypatch):
    chain = {"x-real-ip": "172.17.0.1", "x-forwarded-for": "203.0.113.5, 172.17.0.1"}
    monkeypatch.setattr(auth, "TRUSTED_PROXIES", [])
    assert auth.client_ip(_req(chain)) == "172.17.0.1"  # nothing trusted: the peer, whatever it claims
    monkeypatch.setattr(auth, "TRUSTED_PROXIES", auth._parse_networks("172.17.0.0/16, bogus"))
    assert auth.client_ip(_req(chain)) == "203.0.113.5"
    forged = {"x-real-ip": "172.17.0.1", "x-forwarded-for": "9.9.9.9, 203.0.113.5, 172.17.0.1"}
    assert auth.client_ip(_req(forged)) == "203.0.113.5"  # stops at the first untrusted hop
    assert auth.client_ip(_req({"x-real-ip": "172.17.0.1"})) == "172.17.0.1"
    assert auth.client_ip(_req({}, host="10.1.1.1")) == "10.1.1.1"


def test_login_throttle_is_per_address_and_username(api):
    assert [_bad_login(api) for _ in range(10)] == [401] * 10
    assert _bad_login(api) == 429
    # same address, other accounts: not locked out (behind one proxy everybody shares the address)
    assert _bad_login(api, "someone") == 401
    api.post("/api/users", json={"username": "bob", "password": "bobpass1", "role": "viewer"})
    assert login_as(api, "bob", "bobpass1")
    assert _bad_login(api, "ADMIN") == 429  # case does not open a new bucket


def test_login_throttle_caps_username_spraying_per_address(api, monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_MAX_FAILURES_PER_ADDRESS", 15)
    codes = [_bad_login(api, f"u{i}") for i in range(16)]
    assert codes[:15] == [401] * 15 and codes[15] == 429


def test_login_throttle_forgets_old_failures(api, monkeypatch):
    for _ in range(10):
        _bad_login(api)
    assert _bad_login(api) == 429
    monkeypatch.setattr(auth, "LOGIN_WINDOW", 0)
    assert _bad_login(api) == 401
    auth._prune(auth.time.monotonic() + 1)
    assert not auth._failures  # expired buckets are evicted, the dict does not grow forever


# ── Sessions ──
def test_password_change_revokes_existing_sessions(api):
    api.post("/api/users", json={"username": "bob", "password": "bobpass1", "role": "viewer"})
    bob = login_as(api, "bob", "bobpass1")
    assert api.get("/api/auth/me", headers=bob).status_code == 200
    uid = next(u["id"] for u in api.get("/api/users").json() if u["username"] == "bob")
    assert api.put(f"/api/users/{uid}", json={"password": "newpass1"}).status_code == 200
    assert api.get("/api/auth/me", headers=bob).status_code == 401
    assert api.get("/api/auth/me", headers=login_as(api, "bob", "newpass1")).status_code == 200
    assert api.post("/api/auth/stream-token", headers=bob).status_code == 401


def test_sse_stream_ends_when_the_account_is_no_longer_allowed(mock_switch, monkeypatch):
    monkeypatch.setattr(sse, "POLL_INTERVAL", 0)
    monkeypatch.setattr(sse, "ACCOUNT_CHECK_TICKS", 1)
    client = switch_client.SwitchClient("10.0.0.2", "admin", "admin")
    answers = [True, True, False]

    async def check():
        return answers.pop(0)

    async def run():
        events = [ev["event"] async for ev in sse.stats_generator(client, check)]
        await client.close()
        return events
    assert asyncio.run(run()) == ["stats", "stats"]


def test_sse_backs_off_while_the_switch_refuses_the_login(mock_switch, monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            await client.close()
    monkeypatch.setattr(sse.asyncio, "sleep", fake_sleep)
    mock_switch.reject_login = True
    client = switch_client.SwitchClient("10.0.0.2", "admin", "admin")

    async def run():
        return [ev["event"] async for ev in sse.stats_generator(client)]
    assert asyncio.run(run()) == ["switch_error", "switch_error"]
    assert sleeps == [sse.ERROR_INTERVAL, sse.ERROR_INTERVAL]


# ── Switch session handling ──
def test_write_rejected_after_relogin_is_an_error_not_success(api):
    sid = add_switch(api)
    m = api.mock
    m.responders["storm_ctrl_cfg.json"] = (
        lambda request: httpx.Response(200, text="<html>login.html</html>") if request.method == "POST" else None)
    api.get(f"/api/switches/{sid}/ports")  # the cached client is logged in
    logins = m.logins
    r = api.post(f"/api/switches/{sid}/storm", json={"enabled": True, "rate": 100})
    assert r.status_code == 502 and "session" in r.json()["detail"]
    assert m.logins == logins + 1  # one re-login was tried
    assert not m.posted("storm_ctrl_cfg.json")


def test_read_answered_with_the_login_page_after_relogin_is_an_error(api):
    sid = add_switch(api)
    api.mock.responders["status.json"] = lambda request: httpx.Response(200, text="<html>login.html</html>")
    assert api.get(f"/api/switches/{sid}/status").status_code == 502


def test_removed_endpoint_answering_404_is_unsupported(api):
    sid = add_switch(api)
    api.mock.responders["eee_config.json"] = lambda request: httpx.Response(404, text="Not Found")
    assert api.get(f"/api/switches/{sid}/eee").json() == {"supported": False}
    api.mock.responders["status.json"] = lambda request: httpx.Response(404, text="Not Found")
    assert api.get(f"/api/switches/{sid}/status").status_code == 502  # no default: still an error


def test_concurrent_requests_after_expiry_share_one_relogin(mock_switch):
    client = switch_client.SwitchClient("10.0.0.2", "admin", "admin")

    async def run():
        await client.get_status()
        mock_switch.logged_in = False  # the switch expired the session
        await asyncio.gather(*(client.get_status() for _ in range(5)))
        await client.close()
    asyncio.run(run())
    assert mock_switch.logins == 2


def test_get_timeout_is_not_retried(mock_switch):
    calls = []

    def slow(request):
        calls.append(request.method)
        raise httpx.ReadTimeout("slow")
    mock_switch.responders["status.json"] = slow
    client = switch_client.SwitchClient("10.0.0.2", "admin", "admin")

    async def run():
        try:
            await client.get_status()
        except httpx.ReadTimeout:
            return "timeout"
        finally:
            await client.close()
    assert asyncio.run(run()) == "timeout"
    assert calls == ["GET"]


# ── VLANs ──
def _tag_table(body: dict) -> dict:
    """{vid: {bridge, ...}} from a tag_vlan_cfg.json POST body."""
    table = {}
    for k, v in body.items():
        if k.startswith("oVidName_"):
            i = k.split("_")[1]
            table.setdefault(int(v), set()).add(body[f"brName_{i}"])
    return table


def test_vlan_apply_accepts_the_unknown_mode_the_switch_reports(api):
    sid = add_switch(api)
    m = api.mock
    m.state["port_vlan_cfg.json"]["Port_4"] = {"bpEn_4": "1", "bpVid_4": "5", "untag_4": "0", "tag_4": "0"}
    rows = api.get(f"/api/switches/{sid}/vlans/assignments").json()
    assert next(r for r in rows if r["port"] == 4)["mode"] == "unknown"
    # a client that echoes every row back (the previous UI did) must not be refused
    payload = [{"port": r["port"], "mode": r["mode"],
                "access_vlan": r["pvid"] if r["mode"] == "access" else None,
                "native_vlan": r["pvid"] if r["mode"] == "trunk" else None,
                "trunk_vlans": r["trunk_vlans"]} for r in rows if r["port"] != 1]
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=payload)
    assert r.status_code == 200, r.text
    pv = m.posted("port_vlan_cfg.json")[-1]
    assert (pv["checkbox_4"], pv["fidName_4"], pv["checkboxUntag_4"], pv["checkboxTag_4"]) == ("on", "5", "", "")
    assert pv["checkbox_9"] == "on" and pv["fidName_9"] == "20" and pv["checkboxTag_9"] == "on"
    assert _tag_table(m.posted("tag_vlan_cfg.json")[-1]) == {30: {"30"}}  # port 9's entry kept


def test_tagged_vlans_above_63_get_a_bridge_of_their_own(api):
    sid = add_switch(api)
    m = api.mock
    api.post(f"/api/switches/{sid}/vlans", json={"vlan_id": 40, "name": "defined-only"})
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[
        {"port": 2, "mode": "trunk", "native_vlan": 1, "trunk_vlans": [100, 200]},
        {"port": 3, "mode": "trunk", "native_vlan": 1, "trunk_vlans": [100]},
        {"port": 4, "mode": "access", "access_vlan": 63}])
    assert r.status_code == 200, r.text
    table = _tag_table(m.posted("tag_vlan_cfg.json")[-1])
    assert table[30] == {"30"}  # the fixture's entry had no bridge: normalised to its VLAN
    (b100,), (b200,) = table[100], table[200]
    assert 1 <= int(b100) <= 63 and 1 <= int(b200) <= 63 and b100 != b200
    assert {b100, b200}.isdisjoint({"0", "1", "20", "30", "40", "63"})  # FIDs in use, defined VLANs

    # the switch now reports that allocation: it is kept when another port joins VLAN 100
    m.state["tag_vlan_cfg.json"]["bP_1"] = {"TBVEn_1": "1", "pP_1": "2", "oVid_1": "100", "tT_1": "0", "bR_1": b100}
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 5, "mode": "trunk", "native_vlan": 1, "trunk_vlans": [100]}])
    assert r.status_code == 200, r.text
    assert _tag_table(m.posted("tag_vlan_cfg.json")[-1])[100] == {b100}


def test_no_free_bridge_is_a_clear_error(api):
    sid = add_switch(api)
    for vid in range(1, 64):
        api.post(f"/api/switches/{sid}/vlans", json={"vlan_id": vid, "name": f"v{vid}"})
    r = api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 2, "mode": "trunk", "native_vlan": 1, "trunk_vlans": [100]}])
    assert r.status_code == 400 and "No free bridge" in r.json()["detail"]
    assert not api.mock.posted("init_vlan.json")  # refused before touching the switch


def test_double_tag_entries_are_carried_over_intact(api):
    sid = add_switch(api)
    m = api.mock
    m.state["tag_vlan_cfg.json"]["bP_1"] = {"TBVEn_1": "1", "pP_1": "5", "oVid_1": "40", "iVid_1": "41", "tT_1": "1", "bR_1": "40"}
    assert api.post(f"/api/switches/{sid}/vlans/apply", json=[{"port": 2, "mode": "access", "access_vlan": 20}]).status_code == 200
    body = m.posted("tag_vlan_cfg.json")[-1]
    i = next(k.split("_")[1] for k, v in body.items() if k.startswith("oVidName_") and v == "40")
    assert (body[f"vtypeName_{i}"], body[f"iVidName_{i}"], body[f"ppName_{i}"], body[f"brName_{i}"]) == ("1", "41", "5", "40")


# ── Network ──
def test_network_change_refused_by_the_switch_keeps_the_stored_address(api):
    sid = add_switch(api)
    m = api.mock
    m.state["network_settings.json"]["ipAddress"] = "10.0.0.2"
    m.responders["network_settings_ipv4.json"] = (
        lambda request: httpx.Response(500, text="error") if request.method == "POST" else None)
    body = {"dhcp": False, "ip": "10.0.0.50", "netmask": "255.255.255.0", "gateway": "10.0.0.1"}
    assert api.post(f"/api/switches/{sid}/network", json=body).status_code == 502
    assert api.get(f"/api/switches/{sid}/info").json()["ip"] == "10.0.0.2"


def test_network_change_through_a_nat_or_hostname_does_not_repoint(api):
    sid = add_switch(api)  # stored as 10.0.0.2; the switch believes it is 192.168.1.2 (fixture)
    body = {"dhcp": False, "ip": "192.168.1.50", "netmask": "255.255.255.0", "gateway": "192.168.1.1"}
    r = api.post(f"/api/switches/{sid}/network", json=body)
    assert r.status_code == 200 and r.json()["accepted"] is True
    assert api.get(f"/api/switches/{sid}/info").json()["ip"] == "10.0.0.2"
    assert "keeps reaching" in r.json()["note"]


# ── Misc routes ──
def test_static_mac_save_timeout_is_reported_not_fatal(api):
    sid = add_switch(api)
    api.mock.fail_once("mac_save_static_mac_entries.json", httpx.ReadTimeout("slow flash"))
    r = api.post(f"/api/switches/{sid}/mac/static/add", json={"mac": "aa:bb:cc:dd:ee:01", "port": 2, "fid": 0})
    assert r.status_code == 200 and r.json()["warnings"]
    assert api.mock.posted("mac_add_static_mac_entries.json")[-1]["mac-input"] == "AA:BB:CC:DD:EE:01"


def test_snapshots_of_an_unknown_switch_are_404(api):
    assert api.get("/api/switches/999/snapshots").status_code == 404


def test_probe_error_does_not_echo_the_transport_error(api):
    api.mock.responders["status.json"] = lambda request: (_ for _ in ()).throw(httpx.ConnectError("connection refused to 10.0.0.9:80"))
    r = api.post("/api/switches", json={"name": "x", "ip": "10.0.0.9", "username": "a", "password": "b"})
    assert r.status_code == 400 and "10.0.0.9:80" not in r.json()["detail"] and "ConnectError" in r.json()["detail"]
