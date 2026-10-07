import asyncio
import ipaddress
import json
import logging
import os
import re
import signal
import socket
import threading
from contextlib import asynccontextmanager
from typing import Literal, Optional

import aiosqlite
import httpx
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import AppStatus

from db import init_db, DB_PATH
from version import VERSION
from auth import (hash_password_async, verify_password_async, validate_password, validate_role,
                  create_token, create_stream_token, decode_token, get_current_user, require_admin,
                  check_login_allowed, record_login_failure, clear_login_failures, DUMMY_HASH,
                  load_user, password_version)
from switch_client import (SwitchClient, SwitchError, SwitchFormatError, InvalidPortError, MAX_FID, MAX_TAG_ENTRIES,
                           default_swap_sfp, firmware_line, v2_vlan_name, V2_MAX_VLANS, V2_STORM_MAX, STORM_TYPES,
                           MAX_VLAN_ID, NUM_PORTS, MANAGEMENT_PORT)
from sse import get_switch_client, drop_switch_client, sse_endpoint, stop_streams

log = logging.getLogger("switchpilot")
if not log.handlers:
    # shown in `docker compose logs` next to uvicorn's lines (uvicorn only sets up its own loggers)
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)-9s %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]


# ── Stopping cleanly (container stop, update) ──
# How long the shutdown waits for changes still being sent to switches, once uvicorn's own
# graceful time (--timeout-graceful-shutdown in supervisord.conf) is over and it has cancelled them.
# supervisord's stopwaitsecs and compose's stop_grace_period are longer than both together.
SWITCH_CHANGES_GRACE = 20
_switch_changes: set = set()  # requests changing a switch, still running


class FinishSwitchChanges:
    """A request that changes a switch (write, read-back, restore, save) runs to its end even when
    it is cancelled, which uvicorn does to the requests still open when its graceful shutdown time
    is over: the shutdown then waits for it (lifespan). A restart or an update of SwitchPilot
    never leaves a switch half-changed with its previous settings not put back."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS")
                or not scope["path"].startswith("/api/switches")):
            return await self.app(scope, receive, send)
        task = asyncio.ensure_future(self.app(scope, receive, send))
        _switch_changes.add(task)
        task.add_done_callback(_finished_switch_change)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # uvicorn's graceful time is over: stay open, so the change's own answer still goes
            # out (a 502 saying the previous settings could not be put back, for instance)
            await asyncio.wait({task}, timeout=SWITCH_CHANGES_GRACE)
            if not task.done():
                raise
            await task


def _finished_switch_change(task):
    _switch_changes.discard(task)
    if not task.cancelled() and task.exception() is not None:
        log.debug("switch change ended with %r", task.exception())  # already answered or logged


async def wait_for_switch_changes(timeout: float = SWITCH_CHANGES_GRACE):
    pending = set(_switch_changes)
    if pending:
        log.warning("Stopping: waiting for %d change(s) still being sent to switches", len(pending))
        done, pending = await asyncio.wait(pending, timeout=timeout)
        if pending:
            log.error("Stopping with %d switch change(s) unfinished after %ss", len(pending), timeout)


STREAMS_CUT_AFTER = 2  # seconds: a stream still waiting on its switch then is cut


def end_streams_on_exit():
    """Live streams end as soon as SIGTERM/SIGINT arrives, so they never hold the stop open (uvicorn
    waits for open connections, then cancels whatever runs). They end cleanly at their next pause
    (sse.stop_streams); one still waiting on its switch is cut after STREAMS_CUT_AFTER seconds through
    sse-starlette's own exit signal. sse-starlette sets that signal from a hook on uvicorn's
    Server.handle_exit, but uvicorn installs its signal handlers before it imports this app, so that
    hook never runs: this handler is chained in front of uvicorn's instead."""
    if threading.current_thread() is not threading.main_thread():
        return  # signal handlers can only be set from the main thread (not the case under tests)
    loop = asyncio.get_running_loop()

    def cut_streams():
        AppStatus.should_exit = True
        if AppStatus.should_exit_event is not None:
            AppStatus.should_exit_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(sig)
        if not callable(previous):
            continue  # not under uvicorn: leave the default behaviour alone

        def handler(signum, frame, previous=previous):
            stop_streams()
            loop.call_soon_threadsafe(loop.call_later, STREAMS_CUT_AFTER, cut_streams)
            previous(signum, frame)
        signal.signal(sig, handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    end_streams_on_exit()
    yield
    await wait_for_switch_changes()

app = FastAPI(title="SwitchPilot", version=VERSION, lifespan=lifespan)
app.add_middleware(FinishSwitchChanges)
if CORS_ORIGINS:
    # The UI is served from the same origin by nginx; CORS is only for external tooling.
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])


# ── Error mapping: input errors are 400, switch trouble is 502 (never a bare 500) ──
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    # InvalidPortError and the VLAN range checks in SwitchClient are input errors
    return JSONResponse(status_code=400, content={"detail": str(exc)})

@app.exception_handler(SwitchError)
async def switch_error_handler(request: Request, exc: SwitchError):
    return JSONResponse(status_code=502, content={"detail": f"Switch error: {exc}"})

@app.exception_handler(httpx.HTTPError)
async def switch_unreachable_handler(request: Request, exc: httpx.HTTPError):
    return JSONResponse(status_code=502, content={"detail": f"Switch unreachable: {exc.__class__.__name__}: {exc}"})

@app.exception_handler(json.JSONDecodeError)
async def switch_bad_body_handler(request: Request, exc: json.JSONDecodeError):
    return JSONResponse(status_code=502, content={"detail": "Switch returned an unexpected response (not JSON). "
                                                            "The feature may not exist on this firmware."})


# ── Models ──
HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,252}[A-Za-z0-9])?$")

def validate_host(value: str) -> str:
    value = (value or "").strip()
    if not HOST_RE.match(value):
        raise HTTPException(400, "Switch address must be an IP address or hostname (no scheme, port or path)")
    return value

class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class SwitchAdd(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    ip: str
    username: str = "admin"
    password: str = "admin"
    swap_sfp_9_10: Optional[bool] = None  # None = decide from the firmware line (default_swap_sfp)

class SwitchUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    ip: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

class PortMappingUpdate(BaseModel):
    swap_sfp_9_10: bool
    move_descriptions: bool = True  # keep descriptions next to the physical port they were written for

class NetworkConfig(BaseModel):
    dhcp: bool = False
    ip: str = ""
    netmask: str = ""
    gateway: str = ""

class VlanCreate(BaseModel):
    vlan_id: int = Field(ge=1, le=MAX_VLAN_ID)
    name: str = Field(min_length=1, max_length=64)

class VlanRename(BaseModel):
    name: str = Field(min_length=1, max_length=64)

class PortAssignment(BaseModel):
    port: int
    mode: Literal["access", "trunk", "flat", "unknown"]  # unknown = as reported by GET: keep as is
    # 1.0.0.x: 0-63 (a bridge/FID, 0 = the default bridge); 2.0.0.x: an 802.1Q VLAN ID 1-4094
    access_vlan: Optional[int] = Field(default=None, ge=0, le=MAX_VLAN_ID)
    native_vlan: Optional[int] = Field(default=None, ge=0, le=MAX_VLAN_ID)
    trunk_vlans: Optional[list[int]] = None

class StpConfig(BaseModel):
    enabled: bool
    mode: Literal["stp", "rstp"] = "stp"
    edge_ports: Optional[list[int]] = None

class LoopConfig(BaseModel):
    # 1.0.0.x: port -> enabled
    ports: Optional[dict[int, bool]] = None
    # 2.0.0.x: one setting for the whole switch; a field left out keeps its current value
    enabled: Optional[bool] = None
    prevention: Optional[bool] = None  # block the port a loop is seen on
    interval: Optional[int] = Field(default=None, ge=0, le=100)  # tenths of a second
    recovery: Optional[int] = Field(default=None, ge=0, le=100)  # seconds

StormType = Literal["broadcast", "multicast", "unknown_unicast", "unknown_multicast"]

class StormConfig(BaseModel):
    enabled: bool
    rate: int = Field(default=100, ge=1, le=1000000)  # 1.0.0.x: packets/s; 2.0.0.x: Mbps, 1-1000
    types: Optional[list[StormType]] = None  # 2.0.0.x: traffic limited (default: broadcast)

class IgmpConfig(BaseModel):
    enabled: bool
    fast_leave: bool = True
    querier: bool = False  # 1.0.0.x only (2.0.0.x sets queriers per VLAN)
    report_flood: Optional[bool] = None  # 2.0.0.x only; left out = keep the current value

class MirrorConfig(BaseModel):
    monitoring_port: int  # 0 disables mirroring
    mirrored_ports: list[int] = []
    ingress: bool = True
    egress: bool = True

class EeeConfig(BaseModel):
    enabled: bool

class PortConfig(BaseModel):
    port: int
    enabled: bool = True
    speed: str = "Auto"
    flow_ctrl: Literal["On", "Off"] = "On"
    force: bool = False  # required to disable the management port

class PortDescription(BaseModel):
    port: int = Field(ge=1, le=NUM_PORTS)
    description: str = Field(max_length=128)

class StaticMacAdd(BaseModel):
    mac: str = Field(pattern=r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
    port: int
    fid: int = Field(default=0, ge=0, le=MAX_FID)  # 1.0.0.x
    vlan_id: Optional[int] = Field(default=None, ge=1, le=MAX_VLAN_ID)  # 2.0.0.x (default VLAN 1)

class StaticMacDelete(BaseModel):
    mac: str = Field(pattern=r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
    port: Optional[int] = None  # 1.0.0.x (required there); 2.0.0.x deletes by MAC and VLAN
    fid: int = Field(default=0, ge=0, le=MAX_FID)  # 1.0.0.x
    vlan_id: Optional[int] = Field(default=None, ge=1, le=MAX_VLAN_ID)  # 2.0.0.x (default VLAN 1)

class LagPort(BaseModel):
    port: int
    type: int = Field(ge=0, le=2)        # 0 none, 1 static, 2 LACP
    timeout: int = Field(default=0, ge=0, le=1)
    priority: int = Field(default=128, ge=1, le=65535)
    group: int = Field(default=0, ge=0, le=31)  # 2.0.0.x stores 5 bits (its page does not check)

class LagConfig(BaseModel):
    system_priority: int = Field(default=32768, ge=0, le=65535)
    ports: list[LagPort] = []
    group_names: dict[str, str] = {}

class LagNames(BaseModel):
    group_names: dict[str, str]

class TimeConfig(BaseModel):
    time: Optional[str] = None
    date: Optional[str] = None
    timezone: Optional[str] = Field(default=None, pattern=r"^[+-]\d{2}:\d{2}$")
    daylight: Optional[str] = Field(default=None, pattern=r"^[01]$")

class SntpConfig(BaseModel):
    enabled: bool = False
    server: str = Field(default="pool.ntp.org", min_length=1, max_length=253)
    poll: int = Field(default=64, ge=16, le=99999)

class SnapshotCreate(BaseModel):
    name: str = Field(default="Snapshot", min_length=1, max_length=64)

class SnapshotImport(BaseModel):
    name: str = Field(default="Imported", min_length=1, max_length=128)
    config: dict

class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str
    role: str = "viewer"

class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None


# ── Helpers ──
_setup_lock = asyncio.Lock()
_vlan_locks: dict[int, asyncio.Lock] = {}


async def _log_change(switch_id: int, user: dict, action: str, details=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO change_log (switch_id, user_id, action, details) VALUES (?,?,?,?)",
                         (switch_id, int(user.get("sub", 0)), action, json.dumps(details) if details is not None else None))
        await db.commit()


async def _switch_row(switch_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM switches WHERE id = ?", (switch_id,))
        sw = await cursor.fetchone()
        if not sw:
            raise HTTPException(404, "Switch not found")
        return sw


async def _get_client(switch_id: int) -> SwitchClient:
    sw = await _switch_row(switch_id)
    client = get_switch_client(sw["id"], sw["ip"], sw["username"], sw["password"], bool(sw["swap_sfp_9_10"]))
    fw, _, layout = (sw["vlan_layout"] or "").rpartition(":")
    if fw and layout:
        client.vlan_layout_known = (fw, layout)
    client.on_vlan_layout = lambda fw, layout, sid=sw["id"]: _store_vlan_layout(sid, fw, layout)
    return client


async def _store_vlan_layout(switch_id: int, fw_ver: str, layout: str):
    """Keep how this switch's firmware stores VLAN members, once confirmed with a temporary VLAN,
    so a restart of SwitchPilot does not check it again (see SwitchClient.vlan_write_layout)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE switches SET vlan_layout = ? WHERE id = ?", (f"{fw_ver}:{layout}", switch_id))
        await db.commit()


async def _probe_switch(ip: str, username: str, password: str) -> dict:
    """Log in once with throw-away credentials and return status.json, or raise 400."""
    probe = SwitchClient(ip, username, password)
    try:
        if not await probe.login():
            raise HTTPException(400, f"Switch at {ip} rejected the credentials")
        status = await probe.get_status()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Cannot connect to switch at {ip} ({e.__class__.__name__})")
    finally:
        await probe.close()
    # 1.0.0.x firmware spells the model "modle"; 2.0.0.x puts it in "des"
    status["modle"] = status.get("modle") or status.get("des", "")
    return status


SWITCH_PUBLIC_COLUMNS = "id, name, ip, username, model, firmware, mac_address, swap_sfp_9_10, created_at"

def _public_switch(row) -> dict:
    d = dict(row)
    d["swap_sfp_9_10"] = bool(d.get("swap_sfp_9_10", 0))
    d["firmware_line"] = firmware_line(d.get("firmware"))
    d["read_only"] = read_only_features(d.get("firmware"))
    return d


# ── Firmware lines ──
# Settings SwitchPilot writes to a switch, by feature. On 2.0.0.x firmware only the ones in
# V2_WRITABLE are sent: the 1.0.0.x requests for the others are either rejected by that
# firmware or, worse, accepted and misread (an IGMP change turned two other options off on a
# 2.0.0.3 unit, issue #3). Reading works or fails cleanly (SwitchFormatError -> 502).
WRITE_FEATURES = ("network", "ports", "vlans", "lag", "stp", "loop", "storm", "igmp", "mirror",
                  "eee", "time", "static_mac", "mac_table", "reboot")
# Each entry follows the request the 2.0.0.x native UI sends (code carved from the vendor image),
# is read back where the switch answers OK whatever it did, and is saved with save_all_configs.json
# (ports, VLANs, STP and IGMP were also seen working on a 2.0.0.3 unit, issue #3). Left out:
# - EEE and time/SNTP: the 2.0.0.x web interface no longer offers them (format unconfirmed);
# - LAG and storm control (2.3.1): on that 2.0.0.3 unit a LAG change was followed by a network
#   outage, and storm limits were answered OK but not applied, although both requests match what
#   the switch's own pages send. Their code stays (tests), unused until confirmed on a real switch.
V2_WRITABLE = frozenset({"ports", "network", "reboot", "vlans", "stp", "loop", "igmp",
                         "mirror", "static_mac", "mac_table"})


def read_only_features(fw_ver) -> list[str]:
    """Features SwitchPilot cannot change yet on this firmware (empty on 1.0.0.x and unknown)."""
    line = firmware_line(fw_ver)
    if line is None or line < 2:
        return []
    return [f for f in WRITE_FEATURES if f not in V2_WRITABLE]


async def _require_writable(client: SwitchClient, feature: str):
    """Refuse a write this switch's firmware line is not known to accept, before sending anything."""
    line = await client.firmware_line()
    if line is not None and line >= 2 and feature not in V2_WRITABLE:
        raise HTTPException(501, f"Not supported on firmware {client.fw_ver} yet: how this firmware takes this "
                                 "setting is not confirmed on a real switch, so nothing was sent to the switch.")


async def _write_v2(client: SwitchClient, what: str, write, applied, restore):
    """2.0.0.x: write, read back with applied(), and on an error or a difference put the state read
    before the write back with restore() (True when its own read-back matches), then report it.
    Nothing is saved then; without the put-back, the next change saved from SwitchPilot (the save
    is global) would keep a half-done one."""
    error = None
    try:
        result = await write()
        if await applied():
            return result
    except (SwitchError, httpx.HTTPError, json.JSONDecodeError) as e:
        error = e
    try:
        restored = await restore()
    except (SwitchError, httpx.HTTPError, json.JSONDecodeError, ValueError):
        restored = False
    head = (f"Firmware {client.fw_ver} answered OK but did not apply {what}." if error is None
            else f"Changing {what} failed on firmware {client.fw_ver} ({error}).")
    tail = ("The previous setting was put back; nothing was saved." if restored else
            "Putting the previous setting back failed too, so the switch may run part of the change. Nothing was "
            "saved: restart the switch to go back to its saved configuration before changing anything else in "
            "SwitchPilot (the next change would save it).")
    raise HTTPException(502, f"{head} {tail}")


# ── Setup ──
@app.get("/api/setup/status")
async def setup_status():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT COUNT(*) as c FROM users")
        row = await cursor.fetchone()
        return {"setup_complete": row["c"] > 0}

@app.post("/api/setup")
async def setup(req: SetupRequest):
    validate_password(req.password)
    async with _setup_lock:  # two concurrent first-run calls must not both create an admin
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) as c FROM users")
            row = await cursor.fetchone()
            if row["c"] > 0:
                raise HTTPException(400, "Already setup")
            await db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                             (req.username.strip(), await hash_password_async(req.password), "admin"))
            await db.commit()
    return {"ok": True}


# ── Auth ──
@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    check_login_allowed(request, req.username)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (req.username,))
        user = await cursor.fetchone()
    # verify against a dummy hash when the user is unknown so timing does not reveal usernames
    ok = await verify_password_async(req.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not ok:
        record_login_failure(request, req.username)
        raise HTTPException(401, "Invalid credentials")
    clear_login_failures(request, req.username)
    token = create_token(user["id"], user["username"], user["role"], pv=password_version(user["password_hash"]))
    return {"token": token, "username": user["username"], "role": user["role"]}

@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return user

@app.get("/api/version")
async def version(user=Depends(get_current_user)):
    """The SwitchPilot version this server runs (the web page compares it with its own build)."""
    return {"version": VERSION}

@app.post("/api/auth/stream-token")
async def stream_token(user=Depends(get_current_user)):
    """Short-lived token for the SSE stream (EventSource cannot send headers, so the token
    travels in the URL and ends up in access logs; this one is useless after a few minutes)."""
    return {"token": create_stream_token(user)}


# ── Switches CRUD ──
@app.get("/api/switches")
async def list_switches(user=Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(f"SELECT {SWITCH_PUBLIC_COLUMNS} FROM switches")
        return [_public_switch(r) for r in await cursor.fetchall()]

@app.post("/api/switches")
async def add_switch(req: SwitchAdd, user=Depends(require_admin)):
    ip = validate_host(req.ip)
    status = await _probe_switch(ip, req.username, req.password)
    auto = req.swap_sfp_9_10 is None
    # unknown firmware line: the firmware's own numbering (no translation)
    swap = bool(default_swap_sfp(status.get("fw_ver"))) if auto else req.swap_sfp_9_10
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO switches (name, ip, username, password, model, firmware, mac_address, swap_sfp_9_10) VALUES (?,?,?,?,?,?,?,?)",
            (req.name.strip(), ip, req.username, req.password,
             status.get("modle", ""), status.get("fw_ver", ""), status.get("sys_macaddr", ""),
             int(swap)))
        await db.commit()
        return {"id": cursor.lastrowid, "model": status.get("modle"), "firmware": status.get("fw_ver"),
                "swap_sfp_9_10": swap, "swap_auto": auto}

@app.put("/api/switches/{switch_id}")
async def update_switch(switch_id: int, req: SwitchUpdate, user=Depends(require_admin)):
    sw = await _switch_row(switch_id)
    name = req.name.strip() if req.name is not None else sw["name"]
    ip = validate_host(req.ip) if req.ip else sw["ip"]
    username = req.username or sw["username"]
    password = req.password or sw["password"]
    model, firmware, mac = sw["model"], sw["firmware"], sw["mac_address"]
    if (ip, username, password) != (sw["ip"], sw["username"], sw["password"]):
        status = await _probe_switch(ip, username, password)
        model = status.get("modle", model)
        firmware = status.get("fw_ver", firmware)
        mac = status.get("sys_macaddr", mac)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE switches SET name=?, ip=?, username=?, password=?, model=?, firmware=?, mac_address=? WHERE id=?",
            (name, ip, username, password, model, firmware, mac, switch_id))
        await db.commit()
    # keep the shared client (and any open SSE stream) pointed at the new address
    get_switch_client(switch_id, ip, username, password, bool(sw["swap_sfp_9_10"]))
    return {"id": switch_id, "name": name, "ip": ip, "username": username,
            "model": model, "firmware": firmware, "mac_address": mac,
            "swap_sfp_9_10": bool(sw["swap_sfp_9_10"])}

@app.delete("/api/switches/{switch_id}")
async def delete_switch(switch_id: int, user=Depends(require_admin)):
    await _switch_row(switch_id)
    await drop_switch_client(switch_id)
    _vlan_locks.pop(switch_id, None)
    async with aiosqlite.connect(DB_PATH) as db:
        for table in ("port_descriptions", "lag_names", "vlans", "vlan_profiles", "config_snapshots", "change_log"):
            await db.execute(f"DELETE FROM {table} WHERE switch_id = ?", (switch_id,))
        await db.execute("DELETE FROM switches WHERE id = ?", (switch_id,))
        await db.commit()
        return {"ok": True}

@app.put("/api/switches/{switch_id}/port-mapping")
async def set_port_mapping(switch_id: int, req: PortMappingUpdate, user=Depends(require_admin)):
    """Tell SwitchPilot whether this unit's SFP+ cages are numbered the other way round
    from the firmware's own indexes. Nothing is written to the switch: only the labels move."""
    sw = await _switch_row(switch_id)
    moved = False
    if bool(sw["swap_sfp_9_10"]) != req.swap_sfp_9_10:
        # not while a VLAN apply is writing ports 9/10 with the old numbering
        async with _vlan_locks.setdefault(switch_id, asyncio.Lock()):
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE switches SET swap_sfp_9_10 = ? WHERE id = ?",
                                 (int(req.swap_sfp_9_10), switch_id))
                if req.move_descriptions:
                    # Descriptions describe what is plugged into a cage, so they follow it.
                    # UNIQUE(switch_id, port) forbids a direct CASE swap: go through -9.
                    await db.execute("UPDATE port_descriptions SET port = -9 WHERE switch_id = ? AND port = 9", (switch_id,))
                    await db.execute("UPDATE port_descriptions SET port = 9 WHERE switch_id = ? AND port = 10", (switch_id,))
                    await db.execute("UPDATE port_descriptions SET port = 10 WHERE switch_id = ? AND port = -9", (switch_id,))
                    moved = True
                await db.commit()
            get_switch_client(switch_id, sw["ip"], sw["username"], sw["password"], req.swap_sfp_9_10)
        await _log_change(switch_id, user, "port_mapping",
                          {"swap_sfp_9_10": req.swap_sfp_9_10, "moved_descriptions": moved})
    return {"swap_sfp_9_10": req.swap_sfp_9_10, "moved_descriptions": moved}


# ── SSE ──
@app.get("/api/switches/{switch_id}/sse")
async def switch_sse(switch_id: int, token: str = Query(...)):
    payload = decode_token(token, scope="stream")
    await load_user(payload)
    client = await _get_client(switch_id)

    async def still_allowed() -> bool:
        try:
            await load_user(payload)  # deleted account or changed password: stop streaming
            return True
        except HTTPException:
            return False
    return await sse_endpoint(client, still_allowed)


# ── Switch Info (name from DB) ──
@app.get("/api/switches/{switch_id}/info")
async def switch_info(switch_id: int, user=Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, ip, model, firmware, mac_address, swap_sfp_9_10 FROM switches WHERE id=?", (switch_id,))
        sw = await cursor.fetchone()
        if not sw:
            raise HTTPException(404, "Switch not found")
        return _public_switch(sw)

@app.get("/api/switches/{switch_id}/ping")
async def switch_ping(switch_id: int, user=Depends(get_current_user)):
    """Quick check if switch is reachable"""
    client = await _get_client(switch_id)
    try:
        status = await asyncio.wait_for(client.get_status(), timeout=8)
        return {"online": True, "temperature": status.get("temperature")}
    except Exception as e:
        return {"online": False, "error": str(e) or e.__class__.__name__}

# ── Network config ──
@app.post("/api/switches/{switch_id}/network")
async def set_network(switch_id: int, cfg: NetworkConfig, user=Depends(require_admin)):
    sw = await _switch_row(switch_id)
    client = await _get_client(switch_id)
    await _require_writable(client, "network")
    if not cfg.dhcp:
        try:
            ip = ipaddress.IPv4Address(cfg.ip)
            mask = ipaddress.IPv4Address(cfg.netmask)
            gateway = ipaddress.IPv4Address(cfg.gateway) if cfg.gateway else None
            ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)  # validates the netmask
        except ValueError as e:
            raise HTTPException(400, f"Invalid network settings: {e}")
        if gateway and gateway not in ipaddress.IPv4Network(f"{ip}/{mask}", strict=False):
            raise HTTPException(400, "Gateway is not inside the configured subnet")
    # What the switch believes its address is: SwitchPilot only follows a change when it was
    # talking to that address directly (not through a hostname, NAT or a port forward).
    try:
        current_ip = str((await client.get_network()).get("ipAddress", "") or "")
    except Exception:
        current_ip = ""
    note = ""
    accepted = True
    v2 = await client.is_v2()
    try:
        await client.set_network_ipv4(cfg.ip, cfg.netmask, cfg.gateway, cfg.dhcp)
    except SwitchError as e:
        raise HTTPException(502, f"The switch refused the network change: {e}")
    except Exception as e:
        # the switch typically drops the connection while it re-addresses itself
        accepted = False
        note = f"The switch did not acknowledge the change ({e.__class__.__name__}); it may have re-addressed itself."
    await _log_change(switch_id, user, "network", cfg.model_dump())

    def add(text):
        nonlocal note
        note = (note + " " if note else "") + text

    # 2.0.0.x applies the address at once but keeps it only once saved, and the save has to be
    # sent to the switch at its new address
    v2_unsaved = ("On this firmware the new address is kept after a reboot only once saved: open the "
                  "switch's own web interface at its new address and press Save.")
    if cfg.dhcp:
        add("The switch now takes its address from DHCP: once you know the new address, update it under "
            "the switch settings (PUT /api/switches/{id}).")
        if v2:
            add(v2_unsaved)
        return {"ok": True, "dhcp": True, "note": note}
    target = client
    if cfg.ip != sw["ip"]:
        if sw["ip"] == current_ip:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE switches SET ip = ? WHERE id = ?", (cfg.ip, switch_id))
                await db.commit()
            target = get_switch_client(switch_id, cfg.ip, sw["username"], sw["password"], bool(sw["swap_sfp_9_10"]))
            add(f"SwitchPilot now reaches this switch at {cfg.ip}.")
        else:
            target = None
            add(f"SwitchPilot keeps reaching this switch at {sw['ip']} (not the switch's own address); "
                "update it under the switch settings if needed.")
    if v2:
        saved = False
        if target is not None:
            try:
                await target.save_all()
                saved = True
            except Exception:
                pass
        if not saved:
            add(v2_unsaved)
    return {"ok": True, "dhcp": False, "ip": cfg.ip, "accepted": accepted, "note": note}

# ── System ──
@app.get("/api/switches/{switch_id}/status")
async def switch_status(switch_id: int, user=Depends(get_current_user)):
    sw = await _switch_row(switch_id)
    client = await _get_client(switch_id)
    status = await client.get_status()
    network = await client.get_network()
    status["modle"] = status.get("modle") or status.get("des", "")
    # keep the stored identity current (switches added by the first release have no model on
    # 2.0.0.x, which only reports "des"; a firmware update changes fw_ver)
    ident = (status["modle"] or sw["model"] or "", str(status.get("fw_ver") or sw["firmware"] or ""),
             status.get("sys_macaddr") or sw["mac_address"] or "")
    if ident != (sw["model"] or "", sw["firmware"] or "", sw["mac_address"] or ""):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE switches SET model = ?, firmware = ?, mac_address = ? WHERE id = ?",
                             (*ident, switch_id))
            await db.commit()
    status["firmware_line"] = firmware_line(status.get("fw_ver"))
    status["read_only"] = read_only_features(status.get("fw_ver"))
    # what this firmware line usually needs, so the UI can flag a setting that does not match
    # (a choice forced when the switch was added, or a unit that differs); None when unknown
    status["swap_sfp_suggested"] = default_swap_sfp(status.get("fw_ver"))
    return {**status, **network}


# ── Ports ──
@app.get("/api/switches/{switch_id}/ports")
async def get_ports(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    ports = await client.get_ports()
    # Enrich with local descriptions
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT port, description FROM port_descriptions WHERE switch_id=?", (switch_id,))
        descs = {r["port"]: r["description"] for r in await cursor.fetchall()}
    for p in ports:
        p["description"] = descs.get(p["port"], "")
    return ports

@app.post("/api/switches/{switch_id}/ports/config")
async def set_port_config(switch_id: int, configs: list[PortConfig], user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "ports")
    if not configs:
        raise HTTPException(400, "No port configuration given")
    for cfg in configs:
        client.to_internal(cfg.port)  # validate everything before touching the switch
        if cfg.speed not in SwitchClient.SPEED_READ_TO_WRITE.values():
            raise HTTPException(400, f"Unknown speed '{cfg.speed}'")
        if cfg.port == MANAGEMENT_PORT and not cfg.enabled and not cfg.force:
            raise HTTPException(400, f"Port {MANAGEMENT_PORT} is the management port: disabling it can cut "
                                     "SwitchPilot off from the switch. Send force=true to confirm.")
    for cfg in configs:
        await client.set_port(cfg.port, cfg.enabled, cfg.speed, cfg.flow_ctrl)
    warnings = []
    try:
        await client.save_ports()
    except Exception as e:
        warnings.append(f"Applied, but saving to flash did not complete: {e.__class__.__name__}")
    await _log_change(switch_id, user, "ports", [c.model_dump() for c in configs])
    return {"ok": True, "warnings": warnings}

@app.post("/api/switches/{switch_id}/ports/description")
async def set_port_description(switch_id: int, req: PortDescription, user=Depends(require_admin)):
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO port_descriptions (switch_id, port, description) VALUES (?,?,?)",
                         (switch_id, req.port, req.description.strip()))
        await db.commit()
    return {"ok": True}

@app.get("/api/switches/{switch_id}/ports/stats")
async def get_port_stats(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_port_stats()


# ── VLANs (abstraction layer) ──
def _assign_bridges(tag_entries: list[dict], port_configs: list[dict], current_tags: list[dict], defined: set[int]):
    """Give every tagged entry the bridge its VLAN lives in, for the whole table at once.

    VLANs 1-63 use their own ID (the FID of their access ports), so the tagged and untagged
    traffic of one VLAN share a bridge. The hardware only has bridges 0-63, so a VLAN above
    63 (tagged-only, by construction) gets a free bridge: the one it already had on the
    switch when there is one, else the highest ID not used by a port's FID, by another VLAN,
    or by a VLAN defined in SwitchPilot that could become an access VLAN later. Entries are
    normalised on every apply so one VLAN never ends up split over two bridges (entries
    written with bridge 0 by earlier versions included).
    """
    used = {int(p["pvid"]) for p in port_configs if p["mode"] != "flat"}
    reserved = (used | {v for v in defined if 1 <= v <= MAX_FID}
                | {e["vlan_id"] for e in tag_entries if e["vlan_id"] <= MAX_FID})
    assigned: dict[int, int] = {}
    for t in current_tags:  # keep what the switch already holds for a high VLAN
        vid, bridge = t["vlan_id"], int(t.get("bridge") or 0)
        if vid > MAX_FID and 1 <= bridge <= MAX_FID and bridge not in reserved and bridge not in assigned.values():
            assigned.setdefault(vid, bridge)
    for e in tag_entries:
        vid = e["vlan_id"]
        if vid <= MAX_FID:
            e["bridge"] = vid
            continue
        if vid not in assigned:
            taken = reserved | set(assigned.values())
            free = next((b for b in range(MAX_FID, 0, -1) if b not in taken), None)
            if free is None:
                raise HTTPException(400, f"No free bridge for VLAN {vid}: the switch has 64 bridges (0-63) "
                                         "and all are in use")
            assigned[vid] = free
        e["bridge"] = assigned[vid]


# ── 2.0.0.x VLANs: one 802.1Q table, a PVID per port ──
def _v2_port_view(port: int, table: dict, pvid: int) -> tuple[str, list[int]]:
    """SwitchPilot's view of a port from the 802.1Q table: (mode, tagged VLANs).
    flat = untagged in VLAN 1 only (the factory state), access = untagged in its PVID only,
    trunk = untagged in its PVID (the native VLAN) and tagged in others. Anything else, such as a
    port tagged in its own PVID VLAN or outside it (both possible on the switch's own pages), is
    unknown, which SwitchPilot leaves as it is: writing it back as a trunk would change it."""
    untagged = sorted(v for v, e in table.items() if e["ports"].get(port) == 1)
    tagged = sorted(v for v, e in table.items() if e["ports"].get(port) == 2)
    if untagged == [pvid]:
        return ("trunk", tagged) if tagged else (("flat" if pvid == 1 else "access"), [])
    return "unknown", tagged


def _v2_frame_type(mode_now: str, mode: str, frame_type: int) -> int:
    """Accepted frame types (0 all, 1 tagged only, 2 untagged only) a port gets with its new mode.
    Kept while the mode stays (it may be a deliberate setting made on the switch); when the mode
    changes, one that would drop the new mode's traffic goes back to all (untagged only still suits
    a port without tagged VLANs). SwitchPilot does not show this setting."""
    if mode == mode_now:
        return frame_type
    return 2 if mode in ("flat", "access") and frame_type == 2 else 0


def _v2_target(a: "PortAssignment") -> tuple[dict, int]:
    """Membership ({vlan_id: 1 untagged | 2 tagged}) and PVID a requested port mode asks for."""
    if a.mode == "flat":
        return {1: 1}, 1
    if a.mode == "access":
        vid = a.access_vlan or 1
        return {vid: 1}, vid
    native = a.native_vlan or 1  # untagged traffic: the native VLAN, untagged member and PVID
    states = {vid: 2 for vid in (a.trunk_vlans or []) if vid != native}
    states[native] = 1
    return states, native


async def _is_v2(client: SwitchClient, sw) -> bool:
    """Firmware line from the switch, or from the stored version when it cannot be reached (so
    the 1.0.0.x VLAN definitions, kept in SwitchPilot only, can still be edited offline)."""
    try:
        return await client.is_v2()
    except Exception:
        return (firmware_line(sw["firmware"]) or 1) >= 2


async def _defined_vlan_names(switch_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT vlan_id, name FROM vlans WHERE switch_id=?", (switch_id,))
        return {r[0]: r[1] for r in await cursor.fetchall()}


async def _save_v2(client: SwitchClient, warnings: list):
    try:
        await client.save_all()
    except Exception as e:
        warnings.append(f"Applied, but saving the configuration on the switch did not complete: {e.__class__.__name__}")


async def _apply_vlans_v2(switch_id: int, client: SwitchClient, requested: dict) -> dict:
    """2.0.0.x: write the requested port modes as 802.1Q memberships and PVIDs.

    Each VLAN entry the switch takes replaces that VLAN's whole membership, so every affected
    VLAN is sent with all its ports (untouched ports as read). Order: memberships a port gains,
    then PVIDs, then the memberships it loses (the switch keeps a port in the VLAN that is its
    PVID). The switch answers 200 even when it refuses something, so the result is read back;
    on a mismatch the previous configuration is put back.
    """
    table = await client.get_vlan_table_v2()
    cfg = await client.get_port_vlan_cfg_v2()
    names = await _defined_vlan_names(switch_id)
    changes = {p: _v2_target(a) for p, a in requested.items() if a.mode != "unknown"}
    if not changes:
        return {"ok": True, "port_vlans": 0, "vlans": 0, "warnings": []}
    affected = set()
    for port, (states, _) in changes.items():
        affected |= {v for v, e in table.items() if e["ports"].get(port)}
        affected |= set(states)
    created = sorted(affected - set(table))
    if len(table) + len(created) > V2_MAX_VLANS:
        raise HTTPException(400, f"The switch holds at most {V2_MAX_VLANS} VLANs ({len(table)} exist, "
                                 f"{len(created)} more needed)")
    final = {}
    for vid in affected:
        ports = dict(table[vid]["ports"]) if vid in table else {p: 0 for p in range(1, NUM_PORTS + 1)}
        for port, (states, _) in changes.items():
            ports[port] = states.get(vid, 0)
        final[vid] = ports

    def name_of(vid):
        return table[vid]["name"] if vid in table else names.get(vid, "")

    gain = [{"vlan_id": v, "name": name_of(v),
             "ports": {p: (s or (table[v]["ports"].get(p, 0) if v in table else 0)) for p, s in final[v].items()}}
            for v in sorted(affected)]
    lose = [{"vlan_id": v, "name": name_of(v), "ports": final[v]} for v, g in zip(sorted(affected), gain)
            if g["ports"] != final[v]]
    # PVID and accepted frame types each changed port ends up with
    port_targets = {}
    for p, (_, pvid) in changes.items():
        now = cfg.get(p, {"pvid": 1, "frame_type": 0})
        mode_now = _v2_port_view(p, table, now["pvid"])[0]
        port_targets[p] = (pvid, _v2_frame_type(mode_now, requested[p].mode, now["frame_type"]))
    pvid_writes = {p: t for p, t in port_targets.items()
                   if (cfg.get(p, {}).get("pvid"), cfg.get(p, {}).get("frame_type")) != t}

    # settled before any write: a firmware whose layout cannot be confirmed is left untouched
    await client.vlan_write_layout()
    step = "VLAN memberships"
    try:
        await client.set_vlans_v2(gain)
        if pvid_writes:
            step = "PVIDs"
            await client.set_pvids_v2({p: t[0] for p, t in pvid_writes.items()}, {p: t[1] for p, t in pvid_writes.items()})
            got = await client.get_port_vlan_cfg_v2()
            # memberships are only dropped once the PVIDs they depend on are in place
            unset = [p for p, t in sorted(pvid_writes.items())
                     if (got.get(p, {}).get("pvid"), got.get(p, {}).get("frame_type")) != t]
            if unset:
                raise SwitchError("the switch did not set the PVID of port(s) " + ", ".join(map(str, unset)))
        step = "VLAN memberships"
        if lose:
            await client.set_vlans_v2(lose)
        step = "verification"
        after, after_cfg = await client.get_vlan_table_v2(), await client.get_port_vlan_cfg_v2()
        wrong = [f"port {p} in VLAN {v}" for v in sorted(affected) for p in sorted(changes)
                 if after.get(v, {}).get("ports", {}).get(p, 0) != final[v][p]]
        wrong += [f"PVID of port {p}" for p, (pvid, _) in sorted(port_targets.items()) if after_cfg.get(p, {}).get("pvid") != pvid]
        if wrong:
            raise SwitchError("the switch did not apply " + ", ".join(wrong[:6]) + (" ..." if len(wrong) > 6 else ""))
    except Exception as e:
        restored = await _restore_vlans_v2(client, table, cfg, affected, created, sorted(changes))
        raise HTTPException(502, f"VLAN apply failed while writing {step} ({e}). " + (
            "The previous configuration was put back (not saved)." if restored else
            "Putting the previous configuration back did not work either: check the switch's VLANs before changing "
            "anything else in SwitchPilot (the next change would save them)."))
    warnings = []
    await _save_v2(client, warnings)
    return {"ok": True, "port_vlans": len(changes), "vlans": len(affected), "created": created, "warnings": warnings}


async def _restore_vlans_v2(client: SwitchClient, table: dict, cfg: dict, affected: set, created: list,
                            ports: list) -> bool:
    """Put back the VLAN memberships and port settings read before an apply, in the apply's own safe
    order: every port back in the VLANs it was in (without leaving the ones it is in now), then the
    PVIDs and frame types, then the exact previous memberships, then the VLANs the apply created
    deleted. True only when a read-back shows the previous configuration."""
    previous = {v: table[v] for v in sorted(affected) if v in table}
    before = {p: cfg[p] for p in ports if p in cfg}
    try:
        now = await client.get_vlan_table_v2()
        await client.set_vlans_v2([{"vlan_id": v, "name": e["name"], "ports": {
            p: s or now.get(v, {}).get("ports", {}).get(p, 0) for p, s in e["ports"].items()}} for v, e in previous.items()])
        await client.set_pvids_v2({p: c["pvid"] for p, c in before.items()}, {p: c["frame_type"] for p, c in before.items()})
        await client.set_vlans_v2([{"vlan_id": v, "name": e["name"], "ports": e["ports"]} for v, e in previous.items()])
        await client.delete_vlans_v2(created)
        after, after_cfg = await client.get_vlan_table_v2(), await client.get_port_vlan_cfg_v2()
    except Exception:
        return False
    return (all(after.get(v, {}).get("ports") == e["ports"] for v, e in previous.items())
            and not set(created) & set(after)
            and all((after_cfg.get(p, {}).get("pvid"), after_cfg.get(p, {}).get("frame_type")) == (c["pvid"], c["frame_type"])
                    for p, c in before.items()))


async def _vlans_in_use(client: SwitchClient) -> set[int]:
    in_use = set()
    for pv in await client.get_port_vlans():
        if pv["enabled"] and pv["pvid"] > 0:  # a flat port keeps a stale bpVid that means nothing
            in_use.add(pv["pvid"])
    for tv in await client.get_tag_vlans():
        in_use.add(tv["vlan_id"])
    return in_use

@app.get("/api/switches/{switch_id}/vlans")
async def get_vlans(switch_id: int, user=Depends(get_current_user)):
    """Named VLANs from the database merged with the VLAN IDs in use on the switch.
    Nothing is written: a VLAN that is in use but has no name is listed as 'VLAN n'."""
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT vlan_id, name FROM vlans WHERE switch_id=?", (switch_id,))
        named = {r["vlan_id"]: r["name"] for r in await cursor.fetchall()}
    client = await _get_client(switch_id)
    try:
        if await client.is_v2():
            # 2.0.0.x keeps VLANs (and a 16-character name) on the switch itself
            table = await client.get_vlan_table_v2()
            out = []
            for vid in sorted(set(table) | set(named)):
                on = table.get(vid)
                name = named.get(vid) or (on["name"] if on and on["name"] else f"VLAN {vid}")
                out.append({"vlan_id": vid, "name": name, "defined": vid in named or on is not None,
                            "in_use": bool(on and any(on["ports"].values())), "on_switch": on is not None,
                            "deletable": vid != 1})
            return out
        in_use = await _vlans_in_use(client)
    except Exception as e:  # switch offline: still show what we know
        log.info("VLAN discovery skipped for switch %s: %s", switch_id, e)
        in_use = set()
    vlans = [{"vlan_id": vid, "name": named.get(vid, f"VLAN {vid}"), "defined": vid in named, "in_use": vid in in_use,
              "deletable": vid in named}
             for vid in sorted(set(named) | in_use)]
    return vlans

@app.post("/api/switches/{switch_id}/vlans")
async def create_vlan(switch_id: int, req: VlanCreate, user=Depends(require_admin)):
    sw = await _switch_row(switch_id)
    name = req.name.strip()
    named = await _defined_vlan_names(switch_id)
    client = await _get_client(switch_id)
    warnings = []
    if await _is_v2(client, sw):
        # 2.0.0.x: the VLAN is created on the switch (no member port yet), with its name
        async with _vlan_locks.setdefault(switch_id, asyncio.Lock()):
            table = await client.get_vlan_table_v2()
            if req.vlan_id in named and req.vlan_id in table:
                raise HTTPException(409, f"VLAN {req.vlan_id} already exists")
            if req.vlan_id not in table and len(table) >= V2_MAX_VLANS:
                raise HTTPException(400, f"The switch holds at most {V2_MAX_VLANS} VLANs")
            old = table.get(req.vlan_id)
            ports = old["ports"] if old else {}

            async def applied():
                e = (await client.get_vlan_table_v2()).get(req.vlan_id)
                return bool(e) and e["name"] == v2_vlan_name(name) and (not old or e["ports"] == ports)

            async def restore():
                if old:
                    await client.set_vlans_v2([{"vlan_id": req.vlan_id, "name": old["name"], "ports": old["ports"]}])
                else:
                    await client.delete_vlans_v2([req.vlan_id])
                return (await client.get_vlan_table_v2()).get(req.vlan_id) == old

            await _write_v2(client, f"VLAN {req.vlan_id}",
                            lambda: client.set_vlans_v2([{"vlan_id": req.vlan_id, "name": name, "ports": ports}]),
                            applied, restore)
            await _save_v2(client, warnings)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                             (switch_id, req.vlan_id, name))
            await db.commit()
        await _log_change(switch_id, user, "vlans", {"vlan_id": req.vlan_id, "name": name, "created": True})
        return {"ok": True, "warnings": warnings}
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                             (switch_id, req.vlan_id, name))
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(409, f"VLAN {req.vlan_id} already exists")
    return {"ok": True, "warnings": warnings}

@app.put("/api/switches/{switch_id}/vlans/{vlan_id}")
async def rename_vlan(switch_id: int, vlan_id: int, req: VlanRename, user=Depends(require_admin)):
    """Rename a defined VLAN in place (the ID stays, so port assignments are untouched)."""
    sw = await _switch_row(switch_id)
    name = req.name.strip()
    if not name:
        raise HTTPException(422, "VLAN name must not be blank")
    client = await _get_client(switch_id)
    warnings = []
    on_switch = False
    if await _is_v2(client, sw):
        # 2.0.0.x keeps the name on the switch too (16 characters): rename it there, members unchanged
        async with _vlan_locks.setdefault(switch_id, asyncio.Lock()):
            table = await client.get_vlan_table_v2()
            old = table.get(vlan_id)
            if old:
                on_switch = True

                async def applied():
                    e = (await client.get_vlan_table_v2()).get(vlan_id)
                    return bool(e) and e["name"] == v2_vlan_name(name) and e["ports"] == old["ports"]

                async def restore():
                    await client.set_vlans_v2([{"vlan_id": vlan_id, "name": old["name"], "ports": old["ports"]}])
                    return (await client.get_vlan_table_v2()).get(vlan_id) == old

                await _write_v2(client, f"the name of VLAN {vlan_id}",
                                lambda: client.set_vlans_v2([{"vlan_id": vlan_id, "name": name, "ports": old["ports"]}]),
                                applied, restore)
                await _save_v2(client, warnings)
    async with aiosqlite.connect(DB_PATH) as db:
        if on_switch:
            cursor = await db.execute("INSERT OR REPLACE INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                                      (switch_id, vlan_id, name))
        else:
            cursor = await db.execute("UPDATE vlans SET name=? WHERE switch_id=? AND vlan_id=?",
                                      (name, switch_id, vlan_id))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, f"VLAN {vlan_id} is not defined")
    await _log_change(switch_id, user, "vlans", {"vlan_id": vlan_id, "name": name, "renamed": True})
    return {"ok": True, "warnings": warnings}

@app.delete("/api/switches/{switch_id}/vlans/{vlan_id}")
async def delete_vlan(switch_id: int, vlan_id: int, user=Depends(require_admin)):
    sw = await _switch_row(switch_id)
    client = await _get_client(switch_id)
    if await _is_v2(client, sw):
        if vlan_id == 1:
            raise HTTPException(400, "VLAN 1 is the default VLAN: the switch keeps it")
        async with _vlan_locks.setdefault(switch_id, asyncio.Lock()):
            table = await client.get_vlan_table_v2()
            if vlan_id in table:
                cfg = await client.get_port_vlan_cfg_v2()
                pvid_ports = sorted(p for p, c in cfg.items() if c["pvid"] == vlan_id)
                if pvid_ports:  # the switch silently refuses this
                    raise HTTPException(409, f"VLAN {vlan_id} is the access/native VLAN of port(s) "
                                             f"{', '.join(map(str, pvid_ports))}: move them to another VLAN first")
                await client.delete_vlans_v2([vlan_id])
                if vlan_id in await client.get_vlan_table_v2():
                    raise HTTPException(502, f"The switch did not delete VLAN {vlan_id}")
                await _save_v2(client, [])
                await _log_change(switch_id, user, "vlans", {"vlan_id": vlan_id, "deleted": True})
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM vlans WHERE switch_id=? AND vlan_id=?", (switch_id, vlan_id))
        await db.commit()
    return {"ok": True}

@app.get("/api/switches/{switch_id}/vlans/limits")
async def vlan_limits(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    if await client.is_v2():
        table = await client.get_vlan_table_v2()
        return {"model": "8021q", "max_vlans": V2_MAX_VLANS, "used_vlans": len(table),
                "max_vlan_id": MAX_VLAN_ID, "max_pvid": MAX_VLAN_ID}
    tag_entries = await client.get_tag_vlans()
    return {"model": "bridge", "max_fid": MAX_FID, "max_tag_entries": MAX_TAG_ENTRIES, "used_tag_entries": len(tag_entries),
            "max_vlan_id": MAX_VLAN_ID, "max_pvid": MAX_FID}

@app.get("/api/switches/{switch_id}/vlans/assignments")
async def get_vlan_assignments(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    if await client.is_v2():
        table = await client.get_vlan_table_v2()
        cfg = await client.get_port_vlan_cfg_v2()
        rows = []
        for port in sorted(cfg):
            pvid = cfg[port]["pvid"]
            mode, tagged = _v2_port_view(port, table, pvid)
            rows.append({"port": port, "enabled": mode != "flat", "pvid": pvid, "mode": mode,
                         "trunk_vlans": tagged, "frame_type": cfg[port]["frame_type"]})
        return rows
    port_vlans = await client.get_port_vlans()
    tag_vlans = await client.get_tag_vlans()
    # Build per-port view
    trunk_map = {}
    for tv in tag_vlans:
        trunk_map.setdefault(tv["port"], []).append(tv["vlan_id"])
    for pv in port_vlans:
        pv["trunk_vlans"] = sorted(trunk_map.get(pv["port"], []))
    return port_vlans

@app.post("/api/switches/{switch_id}/vlans/apply")
async def apply_vlan_assignments(switch_id: int, assignments: list[PortAssignment], user=Depends(require_admin)):
    """Apply VLAN config like a real switch: access VLAN, trunk allowed VLANs, native VLAN.

    The request only has to list the ports to change. Every other port keeps its current
    port-VLAN and tagged-VLAN configuration (read from the switch first), so a partial
    request can no longer wipe the uplink's tagged VLANs.
    """
    client = await _get_client(switch_id)
    await _require_writable(client, "vlans")
    if not assignments:
        raise HTTPException(400, "No port assignments given")
    requested: dict[int, PortAssignment] = {}
    for a in assignments:
        client.to_internal(a.port)
        if a.port in requested:
            raise HTTPException(400, f"Port {a.port} is listed twice")
        if a.mode == "trunk" and a.trunk_vlans:
            for vid in a.trunk_vlans:
                if not 1 <= vid <= MAX_VLAN_ID:
                    raise HTTPException(400, f"VLAN ID {vid} on port {a.port} is outside 1-{MAX_VLAN_ID}")
        requested[a.port] = a

    lock = _vlan_locks.setdefault(switch_id, asyncio.Lock())
    if await client.is_v2():
        async with lock:
            result = await _apply_vlans_v2(switch_id, client, requested)
        await _log_change(switch_id, user, "vlans", [a.model_dump() for a in assignments])
        return result
    for a in requested.values():  # 1.0.0.x: PVIDs are bridges (FIDs) 0-63
        for vid in (a.access_vlan, a.native_vlan):
            if vid is not None and vid > MAX_FID:
                raise HTTPException(422, f"Port {a.port}: VLAN {vid} cannot be an access/native VLAN on this "
                                         f"firmware (0-{MAX_FID})")
    async with lock:
        current_ports = {p["port"]: p for p in await client.get_port_vlans()}
        current_tags = await client.get_tag_vlans()

        # 1. Full port-VLAN table: requested ports as asked, the others (and ports sent back
        #    with the "unknown" mode GET reported) as they are now
        port_configs = []
        for port in range(1, NUM_PORTS + 1):
            a = requested.get(port)
            if a is None or a.mode == "unknown":
                cur = current_ports.get(port)
                if cur:
                    port_configs.append({"port": port, "mode": cur["mode"], "pvid": cur["pvid"]})
            elif a.mode == "flat":
                port_configs.append({"port": port, "mode": "flat", "pvid": 0})
            elif a.mode == "access":
                port_configs.append({"port": port, "mode": "access",
                                     "pvid": a.access_vlan if a.access_vlan is not None else 1})
            else:
                port_configs.append({"port": port, "mode": "trunk",
                                     "pvid": a.native_vlan if a.native_vlan is not None else 1})

        # 2. Full tag-VLAN table: requested trunks (without their native VLAN) + untouched ports' entries
        tag_entries = []
        for port in range(1, NUM_PORTS + 1):
            a = requested.get(port)
            if a is None or a.mode == "unknown":
                for t in current_tags:
                    if t["port"] == port:
                        tag_entries.append({"port": port, "vlan_id": t["vlan_id"],
                                            "tag_type": t.get("tag_type"), "inner_vid": t.get("inner_vid")})
            elif a.mode == "trunk" and a.trunk_vlans:
                native = a.native_vlan if a.native_vlan is not None else 1
                for vid in sorted(set(a.trunk_vlans)):
                    if vid != native:  # untagged traffic is handled by the port's own bridge
                        tag_entries.append({"port": port, "vlan_id": vid})
        if len(tag_entries) > MAX_TAG_ENTRIES:
            raise HTTPException(400, f"Too many tag VLAN entries: {len(tag_entries)} (max {MAX_TAG_ENTRIES})")
        for i, e in enumerate(tag_entries):
            e["entry"] = i
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT vlan_id FROM vlans WHERE switch_id=?", (switch_id,))
            defined = {r[0] for r in await cursor.fetchall()}
        _assign_bridges(tag_entries, port_configs, current_tags, defined)

        # 3. Write: reset first so the outcome is the same whatever init_vlan clears
        previous_ports = [{"port": p["port"], "mode": p["mode"], "pvid": p["pvid"]} for p in current_ports.values()]
        previous_tags = [{"entry": i, "port": t["port"], "vlan_id": t["vlan_id"], "bridge": t.get("bridge")}
                         for i, t in enumerate(current_tags)]
        step = "reset"
        try:
            await client.reset_vlans()
            step = "port VLANs"
            await client.set_port_vlans(port_configs)
            step = "tag VLANs"
            if tag_entries:
                await client.set_tag_vlans(tag_entries)
        except Exception as e:
            # best effort: put the previous tables back before reporting
            restored = True
            try:
                await client.set_port_vlans(previous_ports)
                if previous_tags:
                    await client.set_tag_vlans(previous_tags)
            except Exception:
                restored = False
            raise HTTPException(502, f"VLAN apply failed while writing {step} ({e}). "
                                     + ("The previous configuration was restored in memory (not saved)."
                                        if restored else "The switch may be left with an incomplete VLAN "
                                        "configuration: check it and apply again."))

        # 4. Save both (a timeout here does not undo the apply, so report instead of failing)
        warnings = []
        for label, save in (("port VLANs", client.save_port_vlans), ("tag VLANs", client.save_tag_vlans)):
            try:
                await save()
            except Exception as e:
                warnings.append(f"{label} applied but saving to flash did not complete: {e.__class__.__name__}")

    await _log_change(switch_id, user, "vlans", [a.model_dump() for a in assignments])
    return {"ok": True, "port_vlans": len(port_configs), "tag_entries": len(tag_entries), "warnings": warnings}


# ── STP ──
@app.get("/api/switches/{switch_id}/stp")
async def get_stp(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_stp()

@app.post("/api/switches/{switch_id}/stp")
async def set_stp(switch_id: int, cfg: StpConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "stp")
    if cfg.edge_ports is not None:
        for p in cfg.edge_ports:
            client.to_internal(p)  # InvalidPortError -> 400 before anything is sent
    result = {"ok": True, "warnings": []}
    if await client.is_v2():
        before = await client.get_stp()

        async def applied():
            now = await client.get_stp()
            # with STP off the switch reads the mode as RSTP and drops every edge port: only "off" is checked
            return now["enabled"] == cfg.enabled and (not cfg.enabled or (now["mode"] == cfg.mode and (
                cfg.edge_ports is None or {p["port"] for p in now["ports"] if p["edge"]} == set(cfg.edge_ports))))

        async def restore():
            await client.set_stp(before["enabled"], before["mode"], [p["port"] for p in before["ports"] if p["edge"]])
            return (await client.get_stp())["enabled"] == before["enabled"]

        await _write_v2(client, "the STP setting", lambda: client.set_stp(cfg.enabled, cfg.mode, cfg.edge_ports),
                        applied, restore)
        # STP and loop detection are alternatives on the switch's own page. Detection goes off only
        # once STP runs, so a failed write never leaves the network with neither.
        result["loop_turned_off"] = False
        if cfg.enabled and await client.loop_detection_off_v2():
            if (await client.get_loop())["enabled"]:
                result["warnings"].append("STP is on, but loop detection could not be turned off: both run.")
            else:
                result["loop_turned_off"] = True
        await _save_v2(client, result["warnings"])
    else:
        await client.set_stp(cfg.enabled, cfg.mode, cfg.edge_ports)
    await _log_change(switch_id, user, "stp", cfg.model_dump())
    return result


# ── Loop Detection ──
@app.get("/api/switches/{switch_id}/loop")
async def get_loop(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_loop()

@app.post("/api/switches/{switch_id}/loop")
async def set_loop(switch_id: int, cfg: LoopConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "loop")
    if not await client.is_v2():
        if cfg.ports is None:
            raise HTTPException(400, "Give the ports to watch: {\"ports\": {\"1\": true, ...}}")
        await client.set_loop(cfg.ports)
        await _log_change(switch_id, user, "loop", cfg.ports)
        return {"ok": True}
    # 2.0.0.x: one setting for the whole switch, fields left out keep their value. The switch only
    # shows the two timers while detection runs (they read 0 otherwise): when they are unknown they
    # are left out, which keeps them, except to start detection, which needs both (0 as its page sends)
    cur = await client.get_loop()
    want = {"enabled": cur["enabled"] if cfg.enabled is None else cfg.enabled,
            "prevention": cur["prevention"] if cfg.prevention is None else cfg.prevention}
    for key, given in (("interval", cfg.interval), ("recovery", cfg.recovery)):
        known = cur[key] if cur["enabled"] else None
        want[key] = given if given is not None else (known if known is not None or not want["enabled"] else 0)
    checked = ("enabled", "prevention", "interval", "recovery") if want["enabled"] else ("enabled", "prevention")

    async def applied():
        now = await client.get_loop()
        return all(now[k] == want[k] for k in checked)

    async def restore():
        await client.set_loop_v2(cur["enabled"], cur["prevention"], cur["interval"] if cur["enabled"] else None,
                                 cur["recovery"] if cur["enabled"] else None)
        back = await client.get_loop()
        return (back["enabled"], back["prevention"]) == (cur["enabled"], cur["prevention"])

    await _write_v2(client, "the loop detection setting", lambda: client.set_loop_v2(**want), applied, restore)
    # STP goes off only once detection runs, so a failed write never leaves the network with neither
    result = {"ok": True, "warnings": [], "stp_turned_off": False}
    if want["enabled"] and await client.stp_off_v2():
        if (await client.get_stp())["enabled"]:
            result["warnings"].append("Loop detection is on, but STP could not be turned off: both run.")
        else:
            result["stp_turned_off"] = True
    await _save_v2(client, result["warnings"])
    await _log_change(switch_id, user, "loop", want)
    return result


# ── Storm Control ──
@app.get("/api/switches/{switch_id}/storm")
async def get_storm(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_storm_control()

@app.post("/api/switches/{switch_id}/storm")
async def set_storm(switch_id: int, cfg: StormConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "storm")
    if not await client.is_v2():
        await client.set_storm_control(cfg.rate, cfg.enabled)
        await _log_change(switch_id, user, "storm", cfg.model_dump())
        return {"ok": True}
    # 2.0.0.x: a limit in Mbps per port and traffic type; SwitchPilot sets the same one on every port
    if cfg.enabled and cfg.rate > V2_STORM_MAX:
        raise HTTPException(400, f"The rate is in Mbps on this firmware: 1-{V2_STORM_MAX}")
    types = list(dict.fromkeys(cfg.types if cfg.types is not None else ["broadcast"]))
    if cfg.enabled and not types:
        raise HTTPException(400, "Choose at least one kind of traffic to limit")
    before = await client.get_storm_control()
    target = {p["port"]: {t: cfg.rate if cfg.enabled and t in types else 0 for t in STORM_TYPES} for p in before["ports"]}
    previous = {p["port"]: {t: p[t] for t in STORM_TYPES} for p in before["ports"]}

    async def matches(want):
        return all(p[t] == want[p["port"]][t] for p in (await client.get_storm_control())["ports"] for t in STORM_TYPES)

    async def restore():
        await client.set_storm_ports_v2(previous)
        return await matches(previous)

    sent = await _write_v2(client, "the storm control limits", lambda: client.set_storm_ports_v2(target, before),
                           lambda: matches(target), restore)
    result = {"ok": True, "warnings": [], "requests": sent}
    await _save_v2(client, result["warnings"])
    await _log_change(switch_id, user, "storm", {**cfg.model_dump(), "types": types})
    return result


# ── IGMP ──
@app.get("/api/switches/{switch_id}/igmp")
async def get_igmp(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    config = await client.get_igmp_config()
    entries = await client.get_igmp_entries()
    return {"config": config, "entries": entries}

@app.post("/api/switches/{switch_id}/igmp")
async def set_igmp(switch_id: int, cfg: IgmpConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "igmp")
    if not await client.is_v2():
        await client.set_igmp_config({
            "igmp": "on" if cfg.enabled else "off",
            "fast_leave": "on" if cfg.fast_leave else "off",
            "snoop_querier": "on" if cfg.querier else "off",
        })
        await _log_change(switch_id, user, "igmp", cfg.model_dump())
        return {"ok": True}
    def state(c):
        return c.get("igmp") == "on", c.get("fast_leave") == "on", c.get("report_flood") == "on"

    before = state(await client.get_igmp_config())
    report_flood = before[2] if cfg.report_flood is None else cfg.report_flood
    want = (cfg.enabled, cfg.fast_leave, report_flood)

    async def restore():
        await client.set_igmp_v2(*before)
        return state(await client.get_igmp_config()) == before

    await _write_v2(client, "the IGMP snooping setting", lambda: client.set_igmp_v2(*want),
                    lambda: _igmp_is(client, state, want), restore)
    result = {"ok": True, "warnings": []}
    await _save_v2(client, result["warnings"])
    await _log_change(switch_id, user, "igmp", {"enabled": cfg.enabled, "fast_leave": cfg.fast_leave,
                                                "report_flood": report_flood})
    return result


async def _igmp_is(client: SwitchClient, state, want) -> bool:
    return state(await client.get_igmp_config()) == want


# ── Port Mirror ──
@app.get("/api/switches/{switch_id}/mirror")
async def get_mirror(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_mirror()

@app.post("/api/switches/{switch_id}/mirror")
async def set_mirror(switch_id: int, cfg: MirrorConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "mirror")
    if cfg.monitoring_port:
        for p in [cfg.monitoring_port, *cfg.mirrored_ports]:
            client.to_internal(p)  # InvalidPortError -> 400 before anything is sent
    result = {"ok": True, "warnings": []}
    if not await client.is_v2():
        await client.set_mirror(cfg.monitoring_port, cfg.mirrored_ports, cfg.ingress, cfg.egress)
    else:
        before = await client.get_mirror()

        def flags(state, dest):  # the switch skips the destination as a source: its own flags do not count
            return {p["port"]: (p["ingress"], p["egress"]) for p in state["ports"] if p["port"] != dest}

        async def applied():
            now = await client.get_mirror()
            dest = cfg.monitoring_port or now["monitoring_port"]
            sources = {int(p) for p in cfg.mirrored_ports} - {dest} if cfg.monitoring_port else set()
            actual = flags(now, dest)
            expected = {port: (port in sources and cfg.ingress, port in sources and cfg.egress) for port in actual}
            return actual == expected and (not cfg.monitoring_port or now["monitoring_port"] == cfg.monitoring_port)

        async def restore():
            if before["monitoring_port"]:
                await client.set_mirror_ports_v2(before["monitoring_port"], flags(before, before["monitoring_port"]))
            now = await client.get_mirror()
            return (now["monitoring_port"] == before["monitoring_port"]
                    and flags(now, now["monitoring_port"]) == flags(before, before["monitoring_port"]))

        await _write_v2(client, "the port mirroring setting",
                        lambda: client.set_mirror(cfg.monitoring_port, cfg.mirrored_ports, cfg.ingress, cfg.egress),
                        applied, restore)
        await _save_v2(client, result["warnings"])
    await _log_change(switch_id, user, "mirror", cfg.model_dump())
    return result


# ── EEE ──
@app.get("/api/switches/{switch_id}/eee")
async def get_eee(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    data = await client.get_eee()
    # EEE (power-saving) was removed in firmware 1.0.0.5+ → empty body → None.
    if data is None:
        return {"supported": False}
    return {"supported": True, **data}

@app.post("/api/switches/{switch_id}/eee")
async def set_eee(switch_id: int, cfg: EeeConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "eee")
    if await client.get_eee() is None:
        raise HTTPException(400, "Power-saving (EEE) is not supported on this firmware")
    await client.set_eee(cfg.enabled)
    await _log_change(switch_id, user, "eee", cfg.model_dump())
    return {"ok": True}


# ── MAC Table ──
async def _lookup_vendors(macs: list) -> list:
    """Enrich MAC entries with vendor name from OUI database"""
    prefixes = set()
    for m in macs:
        mac = m["mac"].upper().replace(":", "").replace("-", "")
        prefixes.add(mac[:6])
    if not prefixes:
        return macs
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" for _ in prefixes)
        cursor = await db.execute(f"SELECT prefix, vendor FROM oui WHERE prefix IN ({placeholders})", list(prefixes))
        vendor_map = {r[0]: r[1] for r in await cursor.fetchall()}
    for m in macs:
        mac = m["mac"].upper().replace(":", "").replace("-", "")
        m["vendor"] = vendor_map.get(mac[:6], "")
    return macs

@app.get("/api/switches/{switch_id}/mac/dynamic")
async def get_dynamic_macs(switch_id: int, search: Optional[str] = Query(default=None, max_length=32),
                           user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    result = await client.get_dynamic_macs(search)
    result["entries"] = await _lookup_vendors(result["entries"])
    return result

@app.post("/api/switches/{switch_id}/mac/clear")
async def clear_macs(switch_id: int, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "mac_table")
    await client.clear_dynamic_macs()
    return {"ok": True}


# ── LAG ──
async def _lag_names(switch_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT group_id, name FROM lag_names WHERE switch_id=?", (switch_id,))
        return {r["group_id"]: r["name"] for r in await cursor.fetchall()}

async def _save_lag_names(switch_id: int, names: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        for gid, name in names.items():
            await db.execute("INSERT OR REPLACE INTO lag_names (switch_id, group_id, name) VALUES (?,?,?)",
                             (switch_id, int(gid), name.strip()[:64]))
        await db.commit()

@app.get("/api/switches/{switch_id}/lag")
async def get_lag(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    lag = await client.get_lag()
    return {**lag, "group_names": await _lag_names(switch_id)}

@app.post("/api/switches/{switch_id}/lag")
async def set_lag(switch_id: int, cfg: LagConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "lag")
    seen = set()
    for p in cfg.ports:
        client.to_internal(p.port)
        if p.port in seen:
            raise HTTPException(400, f"Port {p.port} is listed twice")
        seen.add(p.port)
    result = {"ok": True, "warnings": []}
    if not await client.is_v2():
        if cfg.system_priority < 1:  # 0 is only known to be accepted by 2.0.0.x (its own page allows it)
            raise HTTPException(422, "The LACP system priority must be 1-65535")
        await client.set_lag(cfg.system_priority, [p.model_dump() for p in cfg.ports])
    else:
        before = await client.get_lag()

        def groups(ports):
            return {(p["port"], p["type"], p["group"] if p["type"] else 0) for p in ports}

        async def applied():
            now = await client.get_lag()
            by_port = {p["port"]: p for p in now["ports"]}
            return int(now["system_priority"]) == cfg.system_priority and all(
                (by_port[p.port]["type"], by_port[p.port]["group"] if p.type else 0) == (p.type, p.group if p.type else 0)
                for p in cfg.ports)

        async def restore():
            await client.set_lag(int(before["system_priority"]), before["ports"])
            now = await client.get_lag()
            return groups(now["ports"]) == groups(before["ports"])

        await _write_v2(client, "the link aggregation setting",
                        lambda: client.set_lag(cfg.system_priority, [p.model_dump() for p in cfg.ports]), applied, restore)
        await _save_v2(client, result["warnings"])
    if cfg.group_names:
        await _save_lag_names(switch_id, cfg.group_names)
    await _log_change(switch_id, user, "lag", cfg.model_dump())
    return result

@app.put("/api/switches/{switch_id}/lag/names")
async def set_lag_names(switch_id: int, req: LagNames, user=Depends(require_admin)):
    """Rename LAG groups without re-sending the trunk configuration to the switch."""
    await _switch_row(switch_id)
    await _save_lag_names(switch_id, req.group_names)
    return {"ok": True, "group_names": await _lag_names(switch_id)}


# ── System Time ──
@app.get("/api/switches/{switch_id}/time")
async def get_time(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    time_data = await client.get_time()
    sntp_data = await client.get_sntp()
    # Time/SNTP config was removed in firmware 1.0.0.5+ (endpoints return an
    # empty body → None). Report it as unsupported so the UI can hide the panel.
    if time_data is None and sntp_data is None:
        return {"supported": False}
    return {"supported": True, **(time_data or {}), **(sntp_data or {})}

def _daylight_flag(current: dict) -> str:
    for key, value in current.items():
        if "daylight" in key.lower():
            return "1" if str(value) in ("1", "on", "true") else "0"
    return "0"

@app.post("/api/switches/{switch_id}/time")
async def set_time(switch_id: int, cfg: TimeConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "time")
    # Read current time first so we don't reset fields
    current = await client.get_time()
    if current is None:
        raise HTTPException(400, "Time configuration is not supported on this firmware")
    await client.set_time(
        cfg.time or current.get("timeVal", ""),
        cfg.date or current.get("dateVal", ""),
        cfg.timezone or current.get("timezoneOffsetVal", "+00:00"),
        cfg.daylight if cfg.daylight is not None else _daylight_flag(current),
    )
    await _log_change(switch_id, user, "time", cfg.model_dump(exclude_none=True))
    return {"ok": True}

@app.post("/api/switches/{switch_id}/sntp")
async def set_sntp(switch_id: int, cfg: SntpConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "time")
    if await client.get_sntp() is None:
        raise HTTPException(400, "SNTP is not supported on this firmware")
    server = cfg.server.strip()
    # Resolve hostname to IP (switch only accepts IPs) without blocking the event loop
    try:
        resolved_ip = str(ipaddress.IPv4Address(server))
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(server, None, family=socket.AF_INET)
            resolved_ip = infos[0][4][0]
        except (socket.gaierror, IndexError, OSError):
            raise HTTPException(400, f"Cannot resolve hostname '{server}'")
    await client.set_sntp(cfg.enabled, resolved_ip, cfg.poll)
    await _log_change(switch_id, user, "sntp", {**cfg.model_dump(), "resolved_ip": resolved_ip})
    return {"ok": True, "resolved_ip": resolved_ip, "hostname": server}

@app.get("/api/switches/{switch_id}/sntp/check")
async def check_sntp(switch_id: int, user=Depends(get_current_user)):
    """Check if SNTP is working by reading time and comparing"""
    client = await _get_client(switch_id)
    sntp_cfg = await client.get_sntp()
    time_data = await client.get_time()
    if time_data is None and sntp_cfg is None:
        return {"supported": False}
    sntp_cfg = sntp_cfg or {}
    time_data = time_data or {}
    # Synced only if SNTP is on and the clock left the epoch default
    enabled = str(sntp_cfg.get("sntp_state", "0")) == "1"
    synced = enabled and time_data.get("dateVal", "01/01/1970") != "01/01/1970"
    return {"supported": True, "enabled": enabled, "synced": synced, "server_ip": sntp_cfg.get("sntp_server_ip"),
            "time": time_data.get("timeVal"), "date": time_data.get("dateVal")}


# ── Static MAC ──
@app.get("/api/switches/{switch_id}/mac/static")
async def get_static_macs(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_static_macs()

@app.post("/api/switches/{switch_id}/mac/static/add")
async def add_static_mac(switch_id: int, req: StaticMacAdd, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "static_mac")
    warnings = await client.add_static_mac(req.mac.upper().replace("-", ":"), req.port, req.fid, req.vlan_id)
    await _log_change(switch_id, user, "static_mac_add", req.model_dump(exclude_none=True))
    return {"ok": True, "warnings": warnings}

@app.post("/api/switches/{switch_id}/mac/static/delete")
async def delete_static_mac(switch_id: int, req: StaticMacDelete, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "static_mac")
    mac = req.mac.upper().replace("-", ":")
    if await client.is_v2():
        # keyed by MAC and VLAN: the port does not count (an entry may even be on several ports)
        vlans = sorted(e["vlan"] for e in await client.get_static_macs()
                       if e["mac"].upper() == mac and e["vlan"] is not None)
        vlan = req.vlan_id
        if vlan is None and len(vlans) > 1:
            raise HTTPException(400, f"{mac} has static entries in VLANs {', '.join(map(str, vlans))}: give vlan_id")
        vlan = vlan if vlan is not None else (vlans[0] if vlans else None)
        if vlan is None or vlan not in vlans:
            raise HTTPException(404, f"No static entry for {mac}" + (f" in VLAN {vlan}" if vlan is not None else ""))
        warnings = await client.delete_static_mac(mac, None, vlan=vlan)
    else:
        if req.port is None:
            raise HTTPException(422, "port is required")
        warnings = await client.delete_static_mac(mac, req.port, req.fid)
    await _log_change(switch_id, user, "static_mac_delete", req.model_dump(exclude_none=True))
    return {"ok": True, "warnings": warnings}

# ── Config Snapshots ──
@app.get("/api/switches/{switch_id}/snapshots")
async def list_snapshots(switch_id: int, user=Depends(get_current_user)):
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, created_at FROM config_snapshots WHERE switch_id=? ORDER BY created_at DESC", (switch_id,))
        return [dict(r) for r in await cursor.fetchall()]

@app.post("/api/switches/{switch_id}/snapshots")
async def create_snapshot(switch_id: int, req: SnapshotCreate, user=Depends(require_admin)):
    """Save a full snapshot of all switch settings (port numbers are user-facing)"""
    client = await _get_client(switch_id)
    snapshot = {"meta": {"schema": 2, "port_numbering": "user", "swap_sfp_9_10": client.swap_sfp}}
    unavailable = []
    vlan_reads = ((("vlan_table", client.get_vlan_table_v2), ("port_vlan_cfg", client.get_port_vlan_cfg_v2))
                  if await client.is_v2() else
                  (("port_vlans", client.get_port_vlans), ("tag_vlans", client.get_tag_vlans)))
    for name, read in (("status", client.get_status), ("network", client.get_network), ("ports", client.get_ports),
                       *vlan_reads,
                       ("stp", client.get_stp), ("storm", client.get_storm_control),
                       ("igmp_config", client.get_igmp_config), ("eee", client.get_eee), ("lag", client.get_lag),
                       ("mirror", client.get_mirror), ("loop", client.get_loop), ("sntp", client.get_sntp)):
        try:
            snapshot[name] = await read()
        except (SwitchFormatError, json.JSONDecodeError):
            # a page this firmware formats differently: keep the rest of the snapshot
            snapshot[name] = None
            unavailable.append(name)
    snapshot["meta"]["firmware"] = client.fw_ver
    if unavailable:
        snapshot["meta"]["unavailable"] = unavailable
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO config_snapshots (switch_id, name, config_json) VALUES (?,?,?)",
            (switch_id, req.name.strip(), json.dumps(snapshot)))
        await db.commit()
        return {"id": cursor.lastrowid, "name": req.name.strip()}

@app.get("/api/switches/{switch_id}/snapshots/{snapshot_id}")
async def get_snapshot(switch_id: int, snapshot_id: int, user=Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM config_snapshots WHERE id=? AND switch_id=?", (snapshot_id, switch_id))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Snapshot not found")
        return {"id": row["id"], "name": row["name"], "created_at": row["created_at"],
                "config": json.loads(row["config_json"])}

@app.delete("/api/switches/{switch_id}/snapshots/{snapshot_id}")
async def delete_snapshot(switch_id: int, snapshot_id: int, user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM config_snapshots WHERE id=? AND switch_id=?", (snapshot_id, switch_id))
        await db.commit()
        return {"ok": True}

@app.post("/api/switches/{switch_id}/snapshots/import")
async def import_snapshot(switch_id: int, req: SnapshotImport, user=Depends(require_admin)):
    """Import a snapshot config (save to DB, not apply to switch)"""
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO config_snapshots (switch_id, name, config_json) VALUES (?,?,?)",
            (switch_id, req.name.strip(), json.dumps(req.config)))
        await db.commit()
        return {"id": cursor.lastrowid}


# ── Sync VLANs ──
@app.post("/api/switches/{switch_id}/vlans/sync")
async def sync_vlans(switch_id: int, user=Depends(require_admin)):
    """Copy VLAN names from this switch to all other switches (existing names are kept)"""
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT vlan_id, name FROM vlans WHERE switch_id=?", (switch_id,))
        source_vlans = await cursor.fetchall()
        cursor = await db.execute("SELECT id FROM switches WHERE id != ?", (switch_id,))
        other_switches = [r["id"] for r in await cursor.fetchall()]
        synced = 0
        for sid in other_switches:
            for v in source_vlans:
                cursor = await db.execute("INSERT OR IGNORE INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                                          (sid, v["vlan_id"], v["name"]))
                synced += cursor.rowcount
        await db.commit()
        return {"ok": True, "synced": synced, "targets": len(other_switches)}


# ── User Management ──
async def _admin_count(db) -> int:
    cursor = await db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    return (await cursor.fetchone())[0]

@app.get("/api/users")
async def list_users(user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, username, role, created_at FROM users")
        return [dict(r) for r in await cursor.fetchall()]

@app.post("/api/users")
async def create_user(req: UserCreate, user=Depends(require_admin)):
    validate_role(req.role)
    validate_password(req.password)
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                             (req.username.strip(), await hash_password_async(req.password), req.role))
            await db.commit()
            return {"ok": True}
        except aiosqlite.IntegrityError:
            raise HTTPException(409, "Username already exists")

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, user=Depends(require_admin)):
    if str(user_id) == user.get("sub"):
        raise HTTPException(400, "Cannot delete yourself")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")  # the count and the write happen under one lock
        cursor = await db.execute("SELECT role FROM users WHERE id=?", (user_id,))
        target = await cursor.fetchone()
        if not target:
            raise HTTPException(404, "User not found")
        if target["role"] == "admin" and await _admin_count(db) <= 1:
            raise HTTPException(400, "Cannot delete the last admin")
        await db.execute("DELETE FROM users WHERE id=?", (user_id,))
        await db.commit()
        return {"ok": True}

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, req: UserUpdate, user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("SELECT role FROM users WHERE id=?", (user_id,))
        target = await cursor.fetchone()
        if not target:
            raise HTTPException(404, "User not found")
        if req.role is not None and req.role != target["role"]:
            validate_role(req.role)
            if str(user_id) == user.get("sub"):
                raise HTTPException(400, "Cannot change your own role")
            if target["role"] == "admin" and await _admin_count(db) <= 1:
                raise HTTPException(400, "Cannot demote the last admin")
            await db.execute("UPDATE users SET role=? WHERE id=?", (req.role, user_id))
        if req.password is not None:
            validate_password(req.password)
            await db.execute("UPDATE users SET password_hash=? WHERE id=?",
                             (await hash_password_async(req.password), user_id))
        await db.commit()
        return {"ok": True}


# ── Reboot ──
@app.post("/api/switches/{switch_id}/reboot")
async def reboot_switch(switch_id: int, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await _require_writable(client, "reboot")
    try:
        await client.reboot()
    except httpx.HTTPError:
        pass  # the switch drops the connection while it reboots
    await _log_change(switch_id, user, "reboot")
    return {"ok": True}


# ── Change log ──
@app.get("/api/switches/{switch_id}/changes")
async def list_changes(switch_id: int, limit: int = Query(default=50, ge=1, le=500), user=Depends(get_current_user)):
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            # user_id 0 = done by SwitchPilot itself (startup migration)
            "SELECT c.id, c.action, c.details, c.created_at, "
            "COALESCE(u.username, CASE WHEN c.user_id = 0 THEN 'SwitchPilot' END) AS username FROM change_log c "
            "LEFT JOIN users u ON u.id = c.user_id WHERE c.switch_id = ? ORDER BY c.id DESC LIMIT ?",
            (switch_id, limit))
        rows = []
        for r in await cursor.fetchall():
            d = dict(r)
            try:
                d["details"] = json.loads(d["details"]) if d["details"] else None
            except ValueError:
                pass
            rows.append(d)
        return rows
