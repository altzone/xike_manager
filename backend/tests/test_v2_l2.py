"""LAG, STP, loop detection, storm control, IGMP, mirroring and the MAC tables on 2.0.0.x:
the requests its own web pages send, read back (the switch answers OK whatever it did with
them), then saved with save_all_configs.json."""
import pytest

from test_v2_safety import make_v2

BASE = "/api/switches/{}"


@pytest.fixture
def v2(api):
    make_v2(api.mock)
    r = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2", "username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def url(sid, path):
    return f"{BASE.format(sid)}/{path}"


def saves(m):
    return [ep for ep, _ in m.posts].count("save_all_configs.json")


# ── LAG ──
def test_lacp_group_is_written_read_back_and_saved(api, v2):
    m = api.mock
    ports = [{"port": p, "type": 2 if p in (2, 3) else 0, "group": 1 if p in (2, 3) else 0, "timeout": 1, "priority": 100}
             for p in range(1, 11)]
    r = api.post(url(v2, "lag"), json={"system_priority": 4096, "ports": ports})
    assert r.status_code == 200, r.text
    body = m.posted("port_trunk_cfg.json")[-1]
    assert body["portTypeId_2"] == "2" and body["Port_2_grpInd"] == "1" and body["system_priority"] == "4096"
    assert all(isinstance(v, str) for v in body.values())  # the switch reads every value as a string
    assert m.l2.lag[3] == {"type": 2, "priority": 100, "timeout": 1, "group": 1}
    assert saves(m) == 1
    lag = api.get(url(v2, "lag")).json()
    assert [p["port"] for p in lag["ports"] if p["group"] == 1] == [2, 3] and lag["system_priority"] == 4096


def test_a_system_priority_of_0_set_on_the_switch_can_be_sent_back(api, v2):
    api.mock.l2.system_priority = 0  # allowed by the switch's own page (0-65535)
    lag = api.get(url(v2, "lag")).json()
    r = api.post(url(v2, "lag"), json={"system_priority": lag["system_priority"], "ports": lag["ports"]})
    assert r.status_code == 200, r.text


def test_a_lag_change_the_switch_ignores_is_reported_and_not_saved(api, v2):
    m = api.mock
    m.l2.ignore.add("port_trunk_cfg.json")
    r = api.post(url(v2, "lag"), json={"system_priority": 32768, "ports": [{"port": 4, "type": 1, "group": 3}]})
    assert r.status_code == 502 and "did not apply" in r.json()["detail"] and "nothing was saved" in r.json()["detail"]
    assert saves(m) == 0


# ── Mirroring ──
def test_mirroring_is_saved_and_checked(api, v2):
    m = api.mock
    r = api.post(url(v2, "mirror"), json={"monitoring_port": 8, "mirrored_ports": [2, 3], "ingress": True, "egress": False})
    assert r.status_code == 200, r.text
    assert m.l2.mirror["dest"] == 8 and m.l2.mirror["flags"][2] == [True, False] and m.l2.mirror["flags"][5] == [False, False]
    assert saves(m) == 1
    d = api.get(url(v2, "mirror")).json()
    assert d["enabled"] and d["monitoring_port"] == 8
    # moving the destination onto a former source: the switch never clears the destination's own flags
    r = api.post(url(v2, "mirror"), json={"monitoring_port": 2, "mirrored_ports": [4], "ingress": True, "egress": True})
    assert r.status_code == 200, r.text
    r = api.post(url(v2, "mirror"), json={"monitoring_port": 0})
    assert r.status_code == 200, r.text
    assert api.get(url(v2, "mirror")).json()["enabled"] is False


# ── STP ──
def test_stp_mode_is_written_with_its_2_0_0_x_keys_and_edge_ports_are_kept(api, v2):
    m = api.mock
    m.l2.stp.update(enable=1, mode="RSTP", edges={3, 10})
    r = api.post(url(v2, "stp"), json={"enabled": True, "mode": "stp"})
    assert r.status_code == 200, r.text
    body = m.posted("stp.json")[-1]
    assert body == {"stp_enable": "1", "stp_rstp_mode": "STP", "psel_cbox3": "on", "psel_cbox10": "on"}
    assert m.l2.stp == {"enable": 1, "mode": "STP", "edges": {3, 10}}
    assert r.json()["loop_turned_off"] is False and saves(m) == 1
    d = api.get(url(v2, "stp")).json()
    assert d["enabled"] and d["mode"] == "stp" and [p["port"] for p in d["ports"] if p["edge"]] == [3, 10]


def test_turning_stp_off_is_not_mistaken_for_a_failure(api, v2):
    """With STP off the switch reads the mode as RSTP and forgets the edge ports."""
    m = api.mock
    m.l2.stp.update(enable=1, mode="STP", edges={2})
    r = api.post(url(v2, "stp"), json={"enabled": False, "mode": "stp"})
    assert r.status_code == 200, r.text
    assert m.posted("stp.json")[-1] == {"stp_enable": "0", "stp_rstp_mode": "STP", "psel_cbox2": "on"}
    assert m.l2.stp["enable"] == 0 and saves(m) == 1
    assert api.get(url(v2, "stp")).json()["enabled"] is False


def test_edge_ports_can_be_set(api, v2):
    r = api.post(url(v2, "stp"), json={"enabled": True, "mode": "rstp", "edge_ports": [1, 2]})
    assert r.status_code == 200, r.text
    assert api.mock.l2.stp["edges"] == {1, 2}


def test_turning_stp_on_turns_loop_detection_off_like_the_switch_page(api, v2):
    m = api.mock
    m.l2.loop.update(cPrev="on", detect=1, interval=20, recover=30)
    r = api.post(url(v2, "stp"), json={"enabled": True, "mode": "rstp"})
    assert r.status_code == 200, r.text
    assert r.json()["loop_turned_off"] is True
    assert m.posted("port_lock_cfg.json")[-1] == {"cPrev": "on", "time_interval": "20", "recover_time": "30",
                                                  "detect_enable": "0"}
    assert m.l2.loop["detect"] == 0 and m.l2.loop["cPrev"] == "on" and m.l2.loop["interval"] == 20


# ── Loop detection ──
def test_loop_detection_is_one_setting_for_the_switch(api, v2):
    m = api.mock
    m.l2.loop["violations"] = {6}
    d = api.get(url(v2, "loop")).json()
    # with detection off the switch shows both timers as 0, whatever it stores
    assert d["model"] == "global" and d["enabled"] is False and (d["interval"], d["recovery"]) == (0, 0)
    assert [p["port"] for p in d["ports"] if p["violation"]] == [6]
    r = api.post(url(v2, "loop"), json={"enabled": True, "prevention": True, "interval": 15, "recovery": 30})
    assert r.status_code == 200, r.text
    assert m.posted("port_lock_cfg.json")[-1] == {"time_interval": "15", "recover_time": "30", "detect_enable": "1",
                                                  "cPrev": "on"}
    assert r.json()["stp_turned_off"] is False and saves(m) == 1
    d = api.get(url(v2, "loop")).json()
    assert (d["enabled"], d["prevention"], d["interval"], d["recovery"]) == (True, True, 15, 30)
    # one timer changed while detection runs: the other one is sent as read
    assert api.post(url(v2, "loop"), json={"recovery": 40}).status_code == 200
    assert m.posted("port_lock_cfg.json")[-1] == {"time_interval": "15", "recover_time": "40", "detect_enable": "1",
                                                  "cPrev": "on"}


def test_timers_are_kept_while_loop_detection_is_off(api, v2):
    m = api.mock
    m.l2.loop.update(detect=1, interval=20, recover=30)
    r = api.post(url(v2, "loop"), json={"enabled": False})
    assert r.status_code == 200, r.text  # the timers then read 0: not a failed write
    assert m.posted("port_lock_cfg.json")[-1] == {"time_interval": "20", "recover_time": "30", "detect_enable": "0"}
    # changed while off: the timers the switch does not show are left out, so it keeps them
    assert api.post(url(v2, "loop"), json={"prevention": True}).status_code == 200
    assert m.posted("port_lock_cfg.json")[-1] == {"detect_enable": "0", "cPrev": "on"}
    assert (m.l2.loop["interval"], m.l2.loop["recover"]) == (20, 30)
    # started again without timers: both are sent (0, as the switch's own page would send what it shows)
    assert api.post(url(v2, "loop"), json={"enabled": True}).status_code == 200
    assert m.posted("port_lock_cfg.json")[-1] == {"detect_enable": "1", "time_interval": "0", "recover_time": "0",
                                                  "cPrev": "on"}


def test_turning_loop_detection_on_turns_stp_off_and_keeps_its_settings(api, v2):
    m = api.mock
    m.l2.stp.update(enable=1, mode="STP", edges={4})
    r = api.post(url(v2, "loop"), json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["stp_turned_off"] is True
    # sent as the switch's own page does (mode and edge ports kept in the request); the switch itself
    # then forgets the edge ports while STP is off
    assert m.posted("stp.json")[-1] == {"stp_enable": "0", "stp_rstp_mode": "STP", "psel_cbox4": "on"}
    assert m.l2.stp["enable"] == 0


def test_loop_settings_out_of_range_are_refused(api, v2):
    assert api.post(url(v2, "loop"), json={"enabled": True, "interval": 101}).status_code == 422
    assert api.mock.posts == []


# ── Storm control ──
def test_storm_control_sets_the_same_limit_on_every_port_one_request_each(api, v2):
    m = api.mock
    r = api.post(url(v2, "storm"), json={"enabled": True, "rate": 100, "types": ["broadcast", "unknown_unicast"]})
    assert r.status_code == 200, r.text
    bodies = m.posted("storm_ctrl_cfg.json")
    assert len(bodies) == 20 and r.json()["requests"] == 20
    assert {"port": 1, "rate": 100, "state": 1, "storm_type": "broadcast"} in bodies
    assert all(m.l2.storm[p]["sctrl_bcast"] == 100 and m.l2.storm[p]["sctrl_unucast"] == 100
               and m.l2.storm[p]["sctrl_mcast"] == 0 for p in range(1, 11))
    assert saves(m) == 1
    d = api.get(url(v2, "storm")).json()
    assert (d["model"], d["enabled"], d["rate"], d["types"], d["uniform"]) == (
        "per_port", True, 100, ["broadcast", "unknown_unicast"], True)
    # only what changes is sent again
    m.posts.clear()
    assert api.post(url(v2, "storm"), json={"enabled": True, "rate": 100, "types": ["broadcast"]}).status_code == 200
    assert len(m.posted("storm_ctrl_cfg.json")) == 10
    assert all(b == {"port": b["port"], "rate": 0, "state": 0, "storm_type": "unknown_unicast"}
               for b in m.posted("storm_ctrl_cfg.json"))
    assert api.post(url(v2, "storm"), json={"enabled": False}).status_code == 200
    assert api.get(url(v2, "storm")).json()["enabled"] is False


def test_storm_settings_made_on_the_switch_read_as_mixed(api, v2):
    api.mock.l2.storm[3]["sctrl_mcast"] = 50
    d = api.get(url(v2, "storm")).json()
    assert d["enabled"] and d["rate"] == 50 and d["types"] == ["multicast"] and d["uniform"] is False


def test_storm_rate_is_in_mbps_up_to_1000_on_2_0_0_x(api, v2):
    r = api.post(url(v2, "storm"), json={"enabled": True, "rate": 5000})
    assert r.status_code == 400 and "Mbps" in r.json()["detail"]
    assert api.post(url(v2, "storm"), json={"enabled": True, "rate": 10, "types": []}).status_code == 400
    assert api.mock.posts == []


def test_storm_limits_the_switch_ignores_are_reported(api, v2):
    api.mock.l2.ignore.add("storm_ctrl_cfg.json")
    r = api.post(url(v2, "storm"), json={"enabled": True, "rate": 100})
    assert r.status_code == 502 and saves(api.mock) == 0


# ── IGMP ──
def test_igmp_uses_the_keys_2_0_0_x_reads_and_keeps_report_flooding(api, v2):
    m = api.mock
    r = api.post(url(v2, "igmp"), json={"enabled": True, "fast_leave": True, "querier": True})
    assert r.status_code == 200, r.text
    # issue #3: the 1.0.0.x keys turned fast leave and report flooding off on this firmware
    assert m.posted("igmp_config.json")[-1] == {"igmp": "on", "fast-leave": "on", "report-flood": "on"}
    assert m.l2.igmp == {"igmp": "on", "fast_leave": "on", "report_flood": "on"} and saves(m) == 1
    r = api.post(url(v2, "igmp"), json={"enabled": False, "fast_leave": True, "report_flood": False})
    assert r.status_code == 200, r.text
    assert m.posted("igmp_config.json")[-1] == {"fast-leave": "on"}
    assert m.l2.igmp == {"igmp": "off", "fast_leave": "on", "report_flood": "off"}


def test_igmp_change_the_switch_ignores_is_reported(api, v2):
    api.mock.l2.ignore.add("igmp_config.json")
    r = api.post(url(v2, "igmp"), json={"enabled": True, "fast_leave": True})
    assert r.status_code == 502 and "IGMP" in r.json()["detail"] and saves(api.mock) == 0


# ── MAC tables ──
def dynamic(n, vlan=1):
    return [(f"AA:BB:CC:00:{i // 256:02X}:{i % 256:02X}", vlan, 1 + i % 8, False) for i in range(n)]


def test_the_whole_dynamic_table_is_read_50_entries_at_a_time(api):
    make_v2(api.mock, dynamic(120))
    sid = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2"}).json()["id"]
    d = api.get(url(sid, "mac/dynamic")).json()
    assert d["total"] == 120 and len(d["entries"]) == 120 and d["truncated"] is False
    assert len({e["mac"] for e in d["entries"]}) == 120
    assert d["entries"][0]["vlan"] == 1


def test_a_table_of_exactly_50_stops_when_the_switch_starts_again(api):
    make_v2(api.mock, dynamic(50))
    sid = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2"}).json()["id"]
    d = api.get(url(sid, "mac/dynamic")).json()
    assert d["total"] == 50 and d["truncated"] is False


def test_a_build_without_paging_keeps_the_first_page(api):
    make_v2(api.mock, dynamic(80))
    api.mock.l2.has_next = False
    sid = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2"}).json()["id"]
    d = api.get(url(sid, "mac/dynamic")).json()
    assert d["total"] == 50 and d["truncated"] is True


def test_search_matches_any_part_of_the_address(api):
    make_v2(api.mock, dynamic(120))
    sid = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2"}).json()["id"]
    for query in ("00:00:6", "00-00-6", "00006", "0:6"):  # the switch itself only matches "AA:BB..." prefixes
        macs = [e["mac"] for e in api.get(url(sid, f"mac/dynamic?search={query}")).json()["entries"]]
        assert "AA:BB:CC:00:00:6E" in macs, query
    assert api.get(url(sid, "mac/dynamic?search=apple")).json()["entries"] == []


def test_static_entries_are_added_and_deleted_by_vlan_and_saved_without_erasing_flash(api, v2):
    m = api.mock
    r = api.post(url(v2, "mac/static/add"), json={"mac": "aa-bb-cc-dd-ee-01", "port": 4, "vlan_id": 20})
    assert r.status_code == 200, r.text
    assert m.posted("mac_add_static_mac_entries.json")[-1] == {"mac-input": "AA:BB:CC:DD:EE:01", "port-input": "4",
                                                               "vlan-input": "20"}
    statics = api.get(url(v2, "mac/static")).json()
    assert [(e["mac"], e["port"], e["vlan"]) for e in statics] == [("AA:BB:CC:DD:EE:01", 4, 20)]
    r = api.post(url(v2, "mac/static/delete"), json={"mac": "AA:BB:CC:DD:EE:01", "port": 4, "vlan_id": 20})
    assert r.status_code == 200, r.text
    assert m.posted("mac_delete_static_mac_entries.json")[-1] == {"mac_addr_txt": ["AA:BB:CC:DD:EE:01"],
                                                                  "vlan_text": ["20"]}
    assert api.get(url(v2, "mac/static")).json() == []
    assert saves(m) == 2 and m.l2.static_flash_wiped is False


def test_a_static_delete_the_switch_skips_is_reported(api, v2):
    m = api.mock
    api.post(url(v2, "mac/static/add"), json={"mac": "AA:BB:CC:DD:EE:01", "port": 4, "vlan_id": 20})
    m.l2.ignore.add("mac_delete_static_mac_entries.json")  # answers 200, keeps the entry
    r = api.post(url(v2, "mac/static/delete"), json={"mac": "AA:BB:CC:DD:EE:01", "port": 4, "vlan_id": 20})
    assert r.status_code == 502 and "still has" in r.json()["detail"]
    assert len(api.get(url(v2, "mac/static")).json()) == 1
    m.l2.ignore.clear()
    r = api.post(url(v2, "mac/static/delete"), json={"mac": "AA:BB:CC:DD:EE:01", "port": 4, "vlan_id": 30})
    assert r.status_code == 404  # no entry for it in VLAN 30


def test_a_static_add_the_switch_drops_is_reported(api, v2):
    api.mock.l2.ignore.add("mac_add_static_mac_entries.json")
    r = api.post(url(v2, "mac/static/add"), json={"mac": "AA:BB:CC:DD:EE:01", "port": 4, "vlan_id": 20})
    assert r.status_code == 502 and "VLAN 20" in r.json()["detail"] and saves(api.mock) == 0


def test_clearing_the_dynamic_table_keeps_static_entries(api):
    make_v2(api.mock, dynamic(3) + [("AA:BB:CC:DD:EE:09", 1, 2, True)])
    sid = api.post("/api/switches", json={"name": "P", "ip": "10.0.0.2"}).json()["id"]
    assert api.post(url(sid, "mac/clear")).status_code == 200
    assert api.get(url(sid, "mac/dynamic")).json()["total"] == 0
    assert len(api.get(url(sid, "mac/static")).json()) == 1


# ── Talking to a 2.0.0.x switch ──
def test_requests_to_a_2_0_0_x_switch_go_one_at_a_time():
    """The switch serves one connection at a time and queues only a few (CivetWeb num_threads=1)."""
    import asyncio
    import httpx
    from switch_client import SwitchClient

    def run(fw):
        state = {"now": 0, "max": 0}

        async def handler(request):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.01)
            state["now"] -= 1
            if request.url.path == "/authorize":
                return httpx.Response(200, text="setup.html")
            return httpx.Response(200, json={"fw_ver": fw})

        async def scenario():
            c = SwitchClient("10.0.0.9", transport=httpx.MockTransport(handler))
            await c.get_status()
            await asyncio.gather(*(c._get("status.json") for _ in range(6)))
            await c.close()
        asyncio.run(scenario())
        return state["max"]

    assert run("2.0.0.3") == 1
    assert run("1.0.0.6") > 1  # 1.0.0.x keeps its parallel reads


def test_a_save_waits_for_a_mac_table_read():
    """The save walks the MAC table, which moves the read position a paged MAC read relies on."""
    import asyncio
    import httpx
    from switch_client import SwitchClient

    async def scenario():
        c = SwitchClient("10.0.0.9", transport=httpx.MockTransport(lambda r: httpx.Response(200, text="")))
        c.fw_ver, c._logged_in = "2.0.0.3", True
        await c._mac_lock.acquire()  # a MAC read in progress
        save = asyncio.create_task(c.save_all())
        await asyncio.sleep(0.05)
        assert not save.done()
        c._mac_lock.release()
        await asyncio.wait_for(save, 1)
        await c.close()
    asyncio.run(scenario())


def test_a_pvid_write_keeps_the_ports_frame_type(api, v2):
    import asyncio
    m = api.mock
    m.v2.frames[3] = 2  # untagged frames only, set on the switch
    client = __import__("sse").get_switch_client(v2, "10.0.0.2", "admin", "admin", False)
    asyncio.run(client.set_pvids_v2({3: 1}))
    assert m.posted("port_vlan.json")[-1]["port_based_vlan_frame_type"] == "2"


def test_a_static_entry_left_on_another_port_is_reported(api, v2):
    m = api.mock
    m.l2.macs.append(("AA:BB:CC:DD:EE:01", 20, 3, True))
    m.l2.ignore.add("mac_add_static_mac_entries.json")  # answers 200, keeps the entry on port 3
    r = api.post(url(v2, "mac/static/add"), json={"mac": "AA:BB:CC:DD:EE:01", "port": 4, "vlan_id": 20})
    assert r.status_code == 502 and "port 4" in r.json()["detail"]


# ── What the review found: no protection lost, nothing half-done, no silent change ──
def test_stp_that_does_not_start_leaves_loop_detection_running(api, v2):
    m = api.mock
    m.l2.loop.update(cPrev="on", detect=1, interval=20, recover=30)
    m.l2.ignore.add("stp.json")  # answers 200, STP stays off
    r = api.post(url(v2, "stp"), json={"enabled": True, "mode": "rstp"})
    assert r.status_code == 502 and "put back" in r.json()["detail"], r.text
    assert m.posted("port_lock_cfg.json") == [] and m.l2.loop["detect"] == 1 and saves(m) == 0


def test_loop_detection_that_does_not_start_leaves_stp_running(api, v2):
    m = api.mock
    m.l2.stp.update(enable=1, mode="RSTP", edges={2})
    m.l2.ignore.add("port_lock_cfg.json")
    r = api.post(url(v2, "loop"), json={"enabled": True, "interval": 10, "recovery": 10})
    assert r.status_code == 502, r.text
    assert m.posted("stp.json") == [] and m.l2.stp["enable"] == 1 and saves(m) == 0


def test_storm_limits_half_applied_are_put_back(api, v2):
    m = api.mock
    m.l2.storm[2]["sctrl_bcast"] = 30  # set on the switch
    m.l2.storm_refuse.add("multicast")
    r = api.post(url(v2, "storm"), json={"enabled": True, "rate": 100, "types": ["broadcast", "multicast"]})
    assert r.status_code == 502 and "put back" in r.json()["detail"], r.text
    assert m.l2.storm[2]["sctrl_bcast"] == 30 and all(m.l2.storm[p]["sctrl_bcast"] == 0 for p in range(3, 11))
    assert saves(m) == 0


def test_mirroring_the_switch_ignores_is_put_back(api, v2):
    m = api.mock
    m.l2.mirror["dest"] = 7
    m.l2.mirror["flags"][3] = [True, False]
    m.l2.ignore.add("port_mirror.json")
    r = api.post(url(v2, "mirror"), json={"monitoring_port": 8, "mirrored_ports": [2], "ingress": True, "egress": True})
    assert r.status_code == 502 and "put back" in r.json()["detail"], r.text
    assert m.l2.mirror["dest"] == 7 and m.l2.mirror["flags"][3] == [True, False] and saves(m) == 0


def test_lag_groups_up_to_31_are_accepted(api, v2):
    r = api.post(url(v2, "lag"), json={"system_priority": 32768, "ports": [{"port": 4, "type": 1, "group": 20}]})
    assert r.status_code == 200, r.text
    assert api.mock.l2.lag[4]["group"] == 20


def test_a_static_entry_is_deleted_by_its_vlan_whatever_its_ports(api, v2):
    m = api.mock
    m.l2.macs += [("AA:BB:CC:DD:EE:07", 20, "1, 2", True), ("AA:BB:CC:DD:EE:08", 1, 3, True),
                  ("AA:BB:CC:DD:EE:08", 30, 3, True)]
    # an entry on several ports, deleted without a port and without its VLAN (looked up)
    r = api.post(url(v2, "mac/static/delete"), json={"mac": "AA:BB:CC:DD:EE:07"})
    assert r.status_code == 200, r.text
    assert m.posted("mac_delete_static_mac_entries.json")[-1] == {"mac_addr_txt": ["AA:BB:CC:DD:EE:07"], "vlan_text": ["20"]}
    # in two VLANs: the VLAN is needed
    assert api.post(url(v2, "mac/static/delete"), json={"mac": "AA:BB:CC:DD:EE:08"}).status_code == 400
    assert api.post(url(v2, "mac/static/delete"), json={"mac": "AA:BB:CC:DD:EE:08", "vlan_id": 30}).status_code == 200
    assert api.post(url(v2, "mac/static/delete"), json={"mac": "AA:BB:CC:DD:EE:09"}).status_code == 404
