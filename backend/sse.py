"""SSE endpoint for real-time switch stats"""
import asyncio
import json
import time
from sse_starlette.sse import EventSourceResponse
from switch_client import SwitchClient

# Cache of active switch clients, shared by request handlers and SSE streams
_clients: dict[int, SwitchClient] = {}

POLL_INTERVAL = 3  # seconds between two readings of the port counters
SETTINGS_INTERVAL = 30  # seconds between two readings of the status and the port settings (sooner after a change)
ERROR_INTERVAL = 15  # seconds between attempts while the switch is unreachable or refuses the login
ACCOUNT_CHECK_TICKS = 20  # re-check the viewer's account every N ticks (about a minute)
QUEUED_EVENTS = 4  # events kept for a stream that reads slowly (the oldest are dropped)

# Set when the server is stopping (main.end_streams_on_exit): every stream ends cleanly at its
# next pause, at most half a second later
stopping = False


def stop_streams():
    global stopping
    stopping = True


async def _pause(seconds: float):
    """Wait between two polls of the switch, cut short when the server is stopping."""
    end = time.monotonic() + seconds
    await asyncio.sleep(0)  # even with no wait, let the streams read what was just published
    while not stopping:
        left = end - time.monotonic()
        if left <= 0:
            return
        await asyncio.sleep(min(0.5, left))


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


class _Feed:
    """The live readings of one switch, whatever the number of streams open on it (tabs, users):
    one poll loop, run while at least one stream listens, and every stream gets its events.

    A small switch web server answers one request at a time (2.0.0.x), so each open tab polling on
    its own multiplied the load. The port counters are read every POLL_INTERVAL; the status
    (temperature) and the port settings change rarely: every SETTINGS_INTERVAL, right after
    SwitchPilot sent a change to the switch, and when a link goes up or down."""

    def __init__(self, client: SwitchClient):
        self.client = client
        self.listeners: set[asyncio.Queue] = set()
        self.last = None  # the latest event, given at once to a stream that joins
        self.task = asyncio.ensure_future(self._run())

    def join(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        if self.last is not None:
            queue.put_nowait(self.last)
        self.listeners.add(queue)
        return queue

    def leave(self, queue: asyncio.Queue):
        self.listeners.discard(queue)
        if not self.listeners:  # nobody is watching: stop asking the switch
            self.task.cancel()
            if _feeds.get(self.client) is self:
                del _feeds[self.client]

    def _publish(self, event):
        self.last = event
        for queue in self.listeners:
            if queue.qsize() >= QUEUED_EVENTS:
                queue.get_nowait()
            queue.put_nowait(event)

    async def _run(self):
        client = self.client
        prev = {}  # internal_port -> (tx_good, rx_good): keyed by physical port so a mapping change can't pair the wrong rows
        prev_time = None
        status = port_settings = links = None
        settings_at, settings_writes = 0.0, None
        try:
            while not client.closed and not stopping:
                ok = True
                try:
                    ports = await client.get_port_stats()
                    now = time.monotonic()
                    # a link that went up or down has a new negotiated speed (in the port settings)
                    was, links = links, {p["internal_port"]: p["link"] for p in ports}
                    if (port_settings is None or settings_writes != client.writes or links != was
                            or now - settings_at >= SETTINGS_INTERVAL):
                        settings_writes = client.writes
                        status = await client.get_status()
                        port_settings = await client.get_ports()
                        settings_at = time.monotonic()

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
                    self._publish({"event": "stats", "data": json.dumps(data)})
                except Exception as e:
                    if client.closed:
                        break
                    ok = False
                    port_settings = links = None  # read everything again once the switch answers
                    # not "error": EventSource would treat that as a connection failure and reconnect
                    self._publish({"event": "switch_error", "data": json.dumps({"error": str(e) or e.__class__.__name__})})
                # back off while the switch is down or refuses the login (no /authorize every 3 s)
                await _pause(POLL_INTERVAL if ok else ERROR_INTERVAL)
        finally:
            for queue in self.listeners:  # the streams end too
                queue.put_nowait(None)
            if _feeds.get(client) is self:
                del _feeds[client]


# client -> its running feed
_feeds: dict[SwitchClient, _Feed] = {}


async def stats_generator(client: SwitchClient, check=None):
    """The live events of a switch for one stream. check: optional async callable answering
    whether the viewer may still stream; it is asked at the start and every ACCOUNT_CHECK_TICKS
    ticks, and a 'no' ends the stream."""
    feed = _feeds.get(client)
    if feed is None or feed.task.done():
        feed = _feeds[client] = _Feed(client)
    queue = feed.join()
    ticks = 0
    try:
        while not stopping:
            if check is not None and ticks % ACCOUNT_CHECK_TICKS == 0 and not await check():
                break
            ticks += 1
            event = await queue.get()
            if event is None:  # the feed ended (server stopping, switch removed)
                break
            yield event
    finally:
        feed.leave(queue)


async def sse_endpoint(client: SwitchClient, check=None):
    return EventSourceResponse(stats_generator(client, check))
