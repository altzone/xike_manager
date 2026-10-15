"""How often SwitchPilot asks the switch for its live readings (2.3.3): one reading for every
stream open on a switch, the port counters every tick, the status and the port settings only now
and then or right after a change, and nothing once nobody watches. A 2.0.0.x switch serves one
request at a time, and each open tab used to poll it on its own."""
import asyncio

import sse
import switch_client
from conftest import add_switch


def count(mock, endpoint):
    return sum(url.split("?")[0].endswith("/" + endpoint) for url in mock.gets)


def drive(mock_switch, monkeypatch, scenario):
    """Run scenario(client, tick): the feed takes a first reading when the first stream opens, then
    one more at each tick() (tick(release=False) only lets what is running go on)."""
    async def main():
        release = asyncio.Queue()

        async def pause(seconds):
            await release.get()
        monkeypatch.setattr(sse, "_pause", pause)
        client = switch_client.SwitchClient("10.0.0.2", "admin", "admin")

        async def tick(release_one=True):
            if release_one:
                release.put_nowait(None)
            for _ in range(20):  # let the reading and the streams run
                await asyncio.sleep(0)
        try:
            return await scenario(client, tick)
        finally:
            await client.close()
    return asyncio.run(main())


async def read(client, n):
    events = []
    async for event in sse.stats_generator(client):
        events.append(event)
        if len(events) == n:
            break
    return events


def test_streams_open_on_one_switch_share_its_readings(mock_switch, monkeypatch):
    async def scenario(client, tick):
        a = asyncio.ensure_future(read(client, 3))
        b = asyncio.ensure_future(read(client, 3))
        for _ in range(3):
            await tick()
        return await a, await b
    a, b = drive(mock_switch, monkeypatch, scenario)
    assert [e["event"] for e in a] == ["stats"] * 3 and a == b  # the same events for both
    assert count(mock_switch, "port_statistics.json") == 3  # not 6
    assert count(mock_switch, "status.json") == 1 and count(mock_switch, "port_setting_load.json") == 1
    assert sse._feeds == {}  # both left: the reading stopped


def test_status_and_port_settings_are_read_again_after_a_change(mock_switch, monkeypatch):
    async def scenario(client, tick):
        stream = asyncio.ensure_future(read(client, 4))
        await tick()
        await tick()
        await client.set_port(3, enabled=False)  # sent by SwitchPilot: the next reading takes it in
        await tick()
        await tick()
        return await stream
    drive(mock_switch, monkeypatch, scenario)
    assert count(mock_switch, "port_statistics.json") == 4
    assert count(mock_switch, "port_setting_load.json") == 2 and count(mock_switch, "status.json") == 2


def test_port_settings_are_read_again_when_a_link_goes_up_or_down(mock_switch, monkeypatch):
    """The negotiated speed is in the port settings: a cable plugged in shows its speed at once."""
    async def scenario(client, tick):
        stream = asyncio.ensure_future(read(client, 4))
        await tick(release_one=False)
        await tick()  # nothing changed
        port = mock_switch.state["port_statistics.json"]["Port_3"]
        port["Link_Status"] = "Link Down" if port["Link_Status"] == "Link Up" else "Link Up"
        await tick()
        await tick()
        return await stream
    drive(mock_switch, monkeypatch, scenario)
    assert count(mock_switch, "port_statistics.json") == 4
    assert count(mock_switch, "port_setting_load.json") == 2


def test_status_and_port_settings_are_read_again_after_a_while(mock_switch, monkeypatch):
    monkeypatch.setattr(sse, "SETTINGS_INTERVAL", 0)
    async def scenario(client, tick):
        stream = asyncio.ensure_future(read(client, 3))
        for _ in range(3):
            await tick()
        return await stream
    drive(mock_switch, monkeypatch, scenario)
    assert count(mock_switch, "port_setting_load.json") == 3


def test_a_stream_joining_later_gets_the_last_reading_at_once(mock_switch, monkeypatch):
    async def scenario(client, tick):
        first = asyncio.ensure_future(read(client, 3))
        await tick()
        late = await asyncio.wait_for(read(client, 1), 1)  # no new reading needed
        await tick()
        await tick()
        await first
        return late
    late = drive(mock_switch, monkeypatch, scenario)
    assert late[0]["event"] == "stats"
    assert count(mock_switch, "port_statistics.json") == 3


def test_a_switch_that_fails_is_read_in_full_again_once_it_answers(mock_switch, monkeypatch):
    async def scenario(client, tick):
        stream = asyncio.ensure_future(read(client, 3))
        await tick(release_one=False)  # the first reading
        mock_switch.responders["port_statistics.json"] = lambda request: switch_client.httpx.Response(500)
        await tick()
        mock_switch.responders.clear()
        await tick()
        return await stream
    events = drive(mock_switch, monkeypatch, scenario)
    assert [e["event"] for e in events] == ["stats", "switch_error", "stats"]
    assert count(mock_switch, "port_setting_load.json") == 2  # read again after the error


def test_ping_reuses_a_recent_answer_of_the_switch(api):
    sid = add_switch(api)
    m = api.mock
    before = count(m, "status.json")
    assert api.get(f"/api/switches/{sid}/ping").json() == {"online": True, "temperature": "41"}
    reads = count(m, "status.json")
    assert reads == before or reads == before + 1
    for _ in range(3):  # what open tabs ask every 10 s
        assert api.get(f"/api/switches/{sid}/ping").json()["online"] is True
    assert count(m, "status.json") == reads  # answered from the last reading
    client = sse._clients[sid]
    client.answered_at -= 11  # nothing asked of the switch for a while: ask it
    assert api.get(f"/api/switches/{sid}/ping").json()["online"] is True
    assert count(m, "status.json") == reads + 1


def test_ping_still_reports_a_switch_that_stopped_answering(api):
    sid = add_switch(api)
    api.get(f"/api/switches/{sid}/ping")
    client = sse._clients[sid]
    client.answered_at -= 11
    api.mock.responders["status.json"] = lambda request: switch_client.httpx.Response(500)
    r = api.get(f"/api/switches/{sid}/ping").json()
    assert r["online"] is False and "500" in r["error"]
