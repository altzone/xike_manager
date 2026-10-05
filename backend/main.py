import asyncio
import ipaddress
import json
import logging
import os
import re
import socket
from contextlib import asynccontextmanager
from typing import Literal, Optional

import aiosqlite
import httpx
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import init_db, DB_PATH
from auth import (hash_password_async, verify_password_async, validate_password, validate_role,
                  create_token, create_stream_token, decode_token, get_current_user, require_admin,
                  check_login_allowed, record_login_failure, clear_login_failures, DUMMY_HASH,
                  load_user, password_version)
from switch_client import (SwitchClient, SwitchError, InvalidPortError, MAX_FID, MAX_TAG_ENTRIES,
                           default_swap_sfp,
                           MAX_VLAN_ID, NUM_PORTS, MANAGEMENT_PORT)
from sse import get_switch_client, drop_switch_client, sse_endpoint

log = logging.getLogger("switchpilot")

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="SwitchPilot", version="2.1.1", lifespan=lifespan)
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
    access_vlan: Optional[int] = Field(default=None, ge=0, le=MAX_FID)  # 0 = the default bridge
    native_vlan: Optional[int] = Field(default=None, ge=0, le=MAX_FID)  # 0 = the default bridge
    trunk_vlans: Optional[list[int]] = None

class StpConfig(BaseModel):
    enabled: bool
    mode: Literal["stp", "rstp"] = "stp"
    edge_ports: Optional[list[int]] = None

class LoopConfig(BaseModel):
    ports: dict[int, bool]  # port -> enabled

class StormConfig(BaseModel):
    enabled: bool
    rate: int = Field(default=100, ge=1, le=1000000)

class IgmpConfig(BaseModel):
    enabled: bool
    fast_leave: bool = True
    querier: bool = False

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
    fid: int = Field(default=0, ge=0, le=MAX_FID)

class StaticMacDelete(BaseModel):
    mac: str = Field(pattern=r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
    port: int
    fid: int = Field(default=0, ge=0, le=MAX_FID)

class LagPort(BaseModel):
    port: int
    type: int = Field(ge=0, le=2)        # 0 none, 1 static, 2 LACP
    timeout: int = Field(default=0, ge=0, le=1)
    priority: int = Field(default=128, ge=1, le=65535)
    group: int = Field(default=0, ge=0, le=15)

class LagConfig(BaseModel):
    system_priority: int = Field(default=32768, ge=1, le=65535)
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
    return get_switch_client(sw["id"], sw["ip"], sw["username"], sw["password"], bool(sw["swap_sfp_9_10"]))


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
    return d


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
    try:
        await client.set_network_ipv4(cfg.ip, cfg.netmask, cfg.gateway, cfg.dhcp)
    except SwitchError as e:
        raise HTTPException(502, f"The switch refused the network change: {e}")
    except Exception as e:
        # the switch typically drops the connection while it re-addresses itself
        accepted = False
        note = f"The switch did not acknowledge the change ({e.__class__.__name__}); it may have re-addressed itself."
    await _log_change(switch_id, user, "network", cfg.model_dump())
    if cfg.dhcp:
        return {"ok": True, "dhcp": True,
                "note": (note + " " if note else "") + "The switch now takes its address from DHCP: "
                "once you know the new address, update it under the switch settings (PUT /api/switches/{id})."}
    if cfg.ip != sw["ip"]:
        if sw["ip"] == current_ip:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE switches SET ip = ? WHERE id = ?", (cfg.ip, switch_id))
                await db.commit()
            get_switch_client(switch_id, cfg.ip, sw["username"], sw["password"], bool(sw["swap_sfp_9_10"]))
            note = (note + " " if note else "") + f"SwitchPilot now reaches this switch at {cfg.ip}."
        else:
            note = (note + " " if note else "") + (
                f"SwitchPilot keeps reaching this switch at {sw['ip']} (not the switch's own address); "
                "update it under the switch settings if needed.")
    return {"ok": True, "dhcp": False, "ip": cfg.ip, "accepted": accepted, "note": note}

# ── System ──
@app.get("/api/switches/{switch_id}/status")
async def switch_status(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    status = await client.get_status()
    network = await client.get_network()
    status["modle"] = status.get("modle") or status.get("des", "")
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
    try:
        in_use = await _vlans_in_use(await _get_client(switch_id))
    except Exception as e:  # switch offline: still show what we know
        log.info("VLAN discovery skipped for switch %s: %s", switch_id, e)
        in_use = set()
    vlans = [{"vlan_id": vid, "name": named.get(vid, f"VLAN {vid}"), "defined": vid in named, "in_use": vid in in_use}
             for vid in sorted(set(named) | in_use)]
    return vlans

@app.post("/api/switches/{switch_id}/vlans")
async def create_vlan(switch_id: int, req: VlanCreate, user=Depends(require_admin)):
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                             (switch_id, req.vlan_id, req.name.strip()))
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(409, f"VLAN {req.vlan_id} already exists")
    return {"ok": True}

@app.put("/api/switches/{switch_id}/vlans/{vlan_id}")
async def rename_vlan(switch_id: int, vlan_id: int, req: VlanRename, user=Depends(require_admin)):
    """Rename a defined VLAN in place (the ID stays, so port assignments are untouched)."""
    await _switch_row(switch_id)
    name = req.name.strip()
    if not name:
        raise HTTPException(422, "VLAN name must not be blank")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE vlans SET name=? WHERE switch_id=? AND vlan_id=?",
                                  (name, switch_id, vlan_id))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, f"VLAN {vlan_id} is not defined")
    await _log_change(switch_id, user, "vlans", {"vlan_id": vlan_id, "name": name, "renamed": True})
    return {"ok": True}

@app.delete("/api/switches/{switch_id}/vlans/{vlan_id}")
async def delete_vlan(switch_id: int, vlan_id: int, user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM vlans WHERE switch_id=? AND vlan_id=?", (switch_id, vlan_id))
        await db.commit()
    return {"ok": True}

@app.get("/api/switches/{switch_id}/vlans/limits")
async def vlan_limits(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    tag_entries = await client.get_tag_vlans()
    return {"max_fid": MAX_FID, "max_tag_entries": MAX_TAG_ENTRIES, "used_tag_entries": len(tag_entries),
            "max_vlan_id": MAX_VLAN_ID}

@app.get("/api/switches/{switch_id}/vlans/assignments")
async def get_vlan_assignments(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
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
    await client.set_stp(cfg.enabled, cfg.mode, cfg.edge_ports)
    await _log_change(switch_id, user, "stp", cfg.model_dump())
    return {"ok": True}


# ── Loop Detection ──
@app.get("/api/switches/{switch_id}/loop")
async def get_loop(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_loop()

@app.post("/api/switches/{switch_id}/loop")
async def set_loop(switch_id: int, cfg: LoopConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.set_loop(cfg.ports)
    await _log_change(switch_id, user, "loop", cfg.ports)
    return {"ok": True}


# ── Storm Control ──
@app.get("/api/switches/{switch_id}/storm")
async def get_storm(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_storm_control()

@app.post("/api/switches/{switch_id}/storm")
async def set_storm(switch_id: int, cfg: StormConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.set_storm_control(cfg.rate, cfg.enabled)
    await _log_change(switch_id, user, "storm", cfg.model_dump())
    return {"ok": True}


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
    await client.set_igmp_config({
        "igmp": "on" if cfg.enabled else "off",
        "fast_leave": "on" if cfg.fast_leave else "off",
        "snoop_querier": "on" if cfg.querier else "off",
    })
    await _log_change(switch_id, user, "igmp", cfg.model_dump())
    return {"ok": True}


# ── Port Mirror ──
@app.get("/api/switches/{switch_id}/mirror")
async def get_mirror(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_mirror()

@app.post("/api/switches/{switch_id}/mirror")
async def set_mirror(switch_id: int, cfg: MirrorConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.set_mirror(cfg.monitoring_port, cfg.mirrored_ports, cfg.ingress, cfg.egress)
    await _log_change(switch_id, user, "mirror", cfg.model_dump())
    return {"ok": True}


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
    seen = set()
    for p in cfg.ports:
        client.to_internal(p.port)
        if p.port in seen:
            raise HTTPException(400, f"Port {p.port} is listed twice")
        seen.add(p.port)
    await client.set_lag(cfg.system_priority, [p.model_dump() for p in cfg.ports])
    if cfg.group_names:
        await _save_lag_names(switch_id, cfg.group_names)
    await _log_change(switch_id, user, "lag", cfg.model_dump())
    return {"ok": True}

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
    warnings = await client.add_static_mac(req.mac.upper().replace("-", ":"), req.port, req.fid)
    await _log_change(switch_id, user, "static_mac_add", req.model_dump())
    return {"ok": True, "warnings": warnings}

@app.post("/api/switches/{switch_id}/mac/static/delete")
async def delete_static_mac(switch_id: int, req: StaticMacDelete, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    warnings = await client.delete_static_mac(req.mac.upper().replace("-", ":"), req.port, req.fid)
    await _log_change(switch_id, user, "static_mac_delete", req.model_dump())
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
    snapshot = {
        "meta": {"schema": 2, "port_numbering": "user", "swap_sfp_9_10": client.swap_sfp},
        "status": await client.get_status(),
        "network": await client.get_network(),
        "ports": await client.get_ports(),
        "port_vlans": await client.get_port_vlans(),
        "tag_vlans": await client.get_tag_vlans(),
        "stp": await client.get_stp(),
        "storm": await client.get_storm_control(),
        "igmp_config": await client.get_igmp_config(),
        "eee": await client.get_eee(),
        "lag": await client.get_lag(),
        "mirror": await client.get_mirror(),
        "loop": await client.get_loop(),
        "sntp": await client.get_sntp(),
    }
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
