"""SSE endpoint for real-time switch stats"""
import asyncio
import json
from sse_starlette.sse import EventSourceResponse
from switch_client import SwitchClient

# Cache of active switch clients for SSE
_clients: dict[int, SwitchClient] = {}


def get_switch_client(switch_id: int, ip: str, username: str, password: str) -> SwitchClient:
    if switch_id not in _clients:
        _clients[switch_id] = SwitchClient(ip, username, password)
    return _clients[switch_id]


async def stats_generator(client: SwitchClient):
    prev_stats = None
    while True:
        try:
            status = await client.get_status()
            ports = await client.get_port_stats()
            port_settings = await client.get_ports()

            # Calculate pps delta
            if prev_stats:
                for p, prev in zip(ports, prev_stats):
                    p["tx_pps"] = max(0, p["tx_good"] - prev["tx_good"])
                    p["rx_pps"] = max(0, p["rx_good"] - prev["rx_good"])
            else:
                for p in ports:
                    p["tx_pps"] = 0
                    p["rx_pps"] = 0

            prev_stats = [dict(p) for p in ports]

            data = {
                "temperature": status.get("temperature", "?"),
                "ports": ports,
                "port_settings": port_settings,
            }
            yield {"event": "stats", "data": json.dumps(data)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
        await asyncio.sleep(3)


async def sse_endpoint(client: SwitchClient):
    return EventSourceResponse(stats_generator(client))
