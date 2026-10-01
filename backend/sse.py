"""SSE endpoint for real-time switch stats"""
import asyncio
import json
import time
from sse_starlette.sse import EventSourceResponse
from switch_client import SwitchClient

# Cache of active switch clients, shared by request handlers and SSE streams
_clients: dict[int, SwitchClient] = {}

POLL_INTERVAL = 3  # seconds
ERROR_INTERVAL = 15  # seconds between attempts while the switch is unreachable or refuses the login
ACCOUNT_CHECK_TICKS = 20  # re-check the viewer's account every N ticks (about a minute)


def get_switch_client(switch_id: int, ip: str, username: str, password: str,
                      swap_sfp: bool = False) -> SwitchClient:
    """Return the cached client for a switch, kept in sync with the DB row.

    The instance is updated in place (address, credentials, port mapping) so that
    running SSE streams holding a reference pick the change up on their next tick.
    """
    client = _clients.get(switch_id)
    if client is None or client.closed:
        client = SwitchClient(ip, username, password, swap_sfp=swap_sfp)
        _clients[switch_id] = client
    else:
        client.configure(ip, username, password)
        if client.swap_sfp != bool(swap_sfp):
            client.set_port_mapping(swap_sfp)
    return client


async def drop_switch_client(switch_id: int):
    client = _clients.pop(switch_id, None)
    if client is not None:
        await client.close()


async def stats_generator(client: SwitchClient, check=None):
    """check: optional async callable answering whether the viewer may still stream;
    it is asked at the start and every ACCOUNT_CHECK_TICKS ticks, and a 'no' ends the stream."""
    prev = {}  # internal_port -> (tx_good, rx_good): keyed by physical port so a mapping change can't pair the wrong rows
    prev_time = None
    ticks = 0
    while not client.closed:
        if check is not None and ticks % ACCOUNT_CHECK_TICKS == 0 and not await check():
            break
        ticks += 1
        ok = True
        try:
            status = await client.get_status()
            ports = await client.get_port_stats()
            port_settings = await client.get_ports()

            now = time.monotonic()
            elapsed = (now - prev_time) if prev_time else None
            for p in ports:
                last = prev.get(p["internal_port"])
                if last and elapsed and elapsed > 0:
                    p["tx_pps"] = round(max(0, p["tx_good"] - last[0]) / elapsed)
                    p["rx_pps"] = round(max(0, p["rx_good"] - last[1]) / elapsed)
                else:
                    p["tx_pps"] = 0
                    p["rx_pps"] = 0
            prev = {p["internal_port"]: (p["tx_good"], p["rx_good"]) for p in ports}
            prev_time = now

            data = {
                "temperature": status.get("temperature", "?"),
                "ports": ports,
                "port_settings": port_settings,
            }
            yield {"event": "stats", "data": json.dumps(data)}
        except Exception as e:
            if client.closed:
                break
            ok = False
            # not "error": EventSource would treat that as a connection failure and reconnect
            yield {"event": "switch_error", "data": json.dumps({"error": str(e) or e.__class__.__name__})}
        # back off while the switch is down or refuses the login (no /authorize every 3 s)
        await asyncio.sleep(POLL_INTERVAL if ok else ERROR_INTERVAL)


async def sse_endpoint(client: SwitchClient, check=None):
    return EventSourceResponse(stats_generator(client, check))
