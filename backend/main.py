from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import aiosqlite
import json

import socket
from db import init_db, DB_PATH
from auth import hash_password, verify_password, create_token, decode_token, get_current_user, require_admin
from switch_client import SwitchClient, InvalidPortError, MAX_FID, MAX_TAG_ENTRIES, NUM_PORTS
from sse import get_switch_client, drop_switch_client, sse_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="SwitchPilot", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    # InvalidPortError and the VLAN range checks in SwitchClient are input errors, not crashes
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ── Models ──
class SetupRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class SwitchAdd(BaseModel):
    name: str
    ip: str
    username: str = "admin"
    password: str = "admin"
    swap_sfp_9_10: bool = False

class SwitchUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

class PortMappingUpdate(BaseModel):
    swap_sfp_9_10: bool
    move_descriptions: bool = True  # keep descriptions next to the physical port they were written for

class VlanCreate(BaseModel):
    vlan_id: int
    name: str

class PortAssignment(BaseModel):
    port: int
    mode: str  # "access", "trunk", "flat"
    access_vlan: Optional[int] = None
    native_vlan: Optional[int] = None
    trunk_vlans: Optional[list[int]] = None

class StpConfig(BaseModel):
    enabled: bool
    mode: str = "stp"  # "stp" or "rstp"
    edge_ports: Optional[list[int]] = None

class LoopConfig(BaseModel):
    ports: dict[int, bool]  # port -> enabled

class StormConfig(BaseModel):
    enabled: bool
    rate: int = 100

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
    flow_ctrl: str = "On"

class PortDescription(BaseModel):
    port: int = Field(ge=1, le=NUM_PORTS)
    description: str

class StaticMacAdd(BaseModel):
    mac: str
    port: int
    fid: int = Field(default=0, ge=0, le=MAX_FID)

class LagPort(BaseModel):
    port: int
    type: int
    timeout: int = 0
    group: int = 0

class LagConfig(BaseModel):
    system_priority: int = 32768
    ports: list[LagPort] = []
    group_names: dict[str, str] = {}


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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT COUNT(*) as c FROM users")
        row = await cursor.fetchone()
        if row["c"] > 0:
            raise HTTPException(400, "Already setup")
        await db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                         (req.username, hash_password(req.password), "admin"))
        await db.commit()
        return {"ok": True}


# ── Auth ──
@app.post("/api/auth/login")
async def login(req: LoginRequest):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (req.username,))
        user = await cursor.fetchone()
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(401, "Invalid credentials")
        token = create_token(user["id"], user["username"], user["role"])
        return {"token": token, "username": user["username"], "role": user["role"]}

@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return user


# ── Switches CRUD ──
SWITCH_PUBLIC_COLUMNS = "id, name, ip, username, model, firmware, mac_address, swap_sfp_9_10, created_at"

def _public_switch(row) -> dict:
    d = dict(row)
    d["swap_sfp_9_10"] = bool(d.get("swap_sfp_9_10", 0))
    return d

async def _switch_row(switch_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM switches WHERE id = ?", (switch_id,))
        sw = await cursor.fetchone()
        if not sw:
            raise HTTPException(404, "Switch not found")
        return sw

async def _probe_switch(ip: str, username: str, password: str) -> dict:
    """Log in once with throw-away credentials and return status.json, or raise 400."""
    probe = SwitchClient(ip, username, password)
    try:
        if not await probe.login():
            raise HTTPException(400, f"Cannot connect to switch at {ip}")
        return await probe.get_status()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Switch connection failed: {e}")
    finally:
        await probe.close()

@app.get("/api/switches")
async def list_switches(user=Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(f"SELECT {SWITCH_PUBLIC_COLUMNS} FROM switches")
        return [_public_switch(r) for r in await cursor.fetchall()]

@app.post("/api/switches")
async def add_switch(req: SwitchAdd, user=Depends(require_admin)):
    status = await _probe_switch(req.ip, req.username, req.password)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO switches (name, ip, username, password, model, firmware, mac_address, swap_sfp_9_10) VALUES (?,?,?,?,?,?,?,?)",
            (req.name, req.ip, req.username, req.password,
             status.get("modle", ""), status.get("fw_ver", ""), status.get("sys_macaddr", ""),
             int(req.swap_sfp_9_10)))
        await db.commit()
        return {"id": cursor.lastrowid, "model": status.get("modle"), "firmware": status.get("fw_ver"),
                "swap_sfp_9_10": req.swap_sfp_9_10}

@app.put("/api/switches/{switch_id}")
async def update_switch(switch_id: int, req: SwitchUpdate, user=Depends(require_admin)):
    sw = await _switch_row(switch_id)
    name = req.name if req.name is not None else sw["name"]
    ip = req.ip or sw["ip"]
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
            await db.execute(
                "INSERT INTO change_log (switch_id, user_id, action, details) VALUES (?,?,?,?)",
                (switch_id, int(user.get("sub", 0)), "port_mapping",
                 json.dumps({"swap_sfp_9_10": req.swap_sfp_9_10, "moved_descriptions": moved})))
            await db.commit()
        get_switch_client(switch_id, sw["ip"], sw["username"], sw["password"], req.swap_sfp_9_10)
    return {"swap_sfp_9_10": req.swap_sfp_9_10, "moved_descriptions": moved}


# ── Helper ──
async def _get_client(switch_id: int) -> SwitchClient:
    sw = await _switch_row(switch_id)
    return get_switch_client(sw["id"], sw["ip"], sw["username"], sw["password"], bool(sw["swap_sfp_9_10"]))


# ── SSE ──
@app.get("/api/switches/{switch_id}/sse")
async def switch_sse(switch_id: int, token: str = Query(...)):
    decode_token(token)
    client = await _get_client(switch_id)
    return await sse_endpoint(client)


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
    try:
        client = await _get_client(switch_id)
        status = await client.get_status()
        return {"online": True, "temperature": status.get("temperature")}
    except HTTPException:
        raise
    except Exception:
        return {"online": False}

# ── Network config ──
@app.post("/api/switches/{switch_id}/network")
async def set_network(switch_id: int, data: dict, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    try:
        await client.set_network_ipv4(
            data.get("ip", ""), data.get("netmask", ""),
            data.get("gateway", ""), data.get("dhcp", True)
        )
    except Exception:
        pass  # may disconnect if IP changed
    return {"ok": True}

# ── System ──
@app.get("/api/switches/{switch_id}/status")
async def switch_status(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    status = await client.get_status()
    network = await client.get_network()
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
    for cfg in configs:
        client.to_internal(cfg.port)  # validate everything before touching the switch
    for cfg in configs:
        await client.set_port(cfg.port, cfg.enabled, cfg.speed, cfg.flow_ctrl)
    try:
        await client.save_ports()
    except Exception:
        pass  # save may timeout but apply already took effect
    return {"ok": True}

@app.post("/api/switches/{switch_id}/ports/description")
async def set_port_description(switch_id: int, req: PortDescription, user=Depends(require_admin)):
    await _switch_row(switch_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO port_descriptions (switch_id, port, description) VALUES (?,?,?)",
                         (switch_id, req.port, req.description))
        await db.commit()
    return {"ok": True}

@app.get("/api/switches/{switch_id}/ports/stats")
async def get_port_stats(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_port_stats()


# ── VLANs (abstraction layer) ──
@app.get("/api/switches/{switch_id}/vlans")
async def get_vlans(switch_id: int, user=Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT vlan_id, name FROM vlans WHERE switch_id=? ORDER BY vlan_id", (switch_id,))
        return [dict(r) for r in await cursor.fetchall()]

@app.post("/api/switches/{switch_id}/vlans")
async def create_vlan(switch_id: int, req: VlanCreate, user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                             (switch_id, req.vlan_id, req.name))
            await db.commit()
        except Exception:
            raise HTTPException(400, f"VLAN {req.vlan_id} already exists")
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
    return {"max_fid": MAX_FID, "max_tag_entries": MAX_TAG_ENTRIES, "used_tag_entries": len(tag_entries)}

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

    # Auto-discover VLANs from switch config and sync to DB
    all_vids = set()
    for pv in port_vlans:
        if pv["pvid"] > 0:
            all_vids.add(pv["pvid"])
    for tv in tag_vlans:
        all_vids.add(tv["vlan_id"])
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT vlan_id FROM vlans WHERE switch_id=?", (switch_id,))
        known = {r[0] for r in await cursor.fetchall()}
        for vid in all_vids:
            if vid not in known and vid > 0:
                await db.execute("INSERT OR IGNORE INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                                 (switch_id, vid, f"VLAN {vid}"))
        await db.commit()

    return port_vlans

@app.post("/api/switches/{switch_id}/vlans/apply")
async def apply_vlan_assignments(switch_id: int, assignments: list[PortAssignment], user=Depends(require_admin)):
    """Apply VLAN config like a real switch: access VLAN, trunk allowed VLANs, native VLAN"""
    client = await _get_client(switch_id)
    for a in assignments:
        client.to_internal(a.port)  # reject bad ports before any write

    # 1. Build port VLAN config
    port_configs = []
    for a in assignments:
        if a.mode == "flat":
            port_configs.append({"port": a.port, "mode": "flat", "pvid": 0})
        elif a.mode == "access":
            pvid = a.access_vlan or 1
            if pvid > MAX_FID:
                raise HTTPException(400, f"Access VLAN {pvid} exceeds max PVID ({MAX_FID}) on port {a.port}")
            port_configs.append({"port": a.port, "mode": "access", "pvid": pvid})
        elif a.mode == "trunk":
            native = a.native_vlan or 1
            if native > MAX_FID:
                raise HTTPException(400, f"Native VLAN {native} exceeds max PVID ({MAX_FID}) on port {a.port}. Use a VLAN ID <= {MAX_FID}.")
            port_configs.append({"port": a.port, "mode": "trunk", "pvid": native})

    # 2. Build tag VLAN entries from trunk assignments
    tag_entries = []
    entry_idx = 0
    for a in assignments:
        if a.mode == "trunk" and a.trunk_vlans:
            for vid in a.trunk_vlans:
                tag_entries.append({"entry": entry_idx, "port": a.port, "vlan_id": vid})
                entry_idx += 1
                if entry_idx >= MAX_TAG_ENTRIES:
                    raise HTTPException(400, f"Too many tag VLAN entries (max {MAX_TAG_ENTRIES})")

    # 3. Apply port VLANs
    if port_configs:
        await client.set_port_vlans(port_configs)

    # 4. Reset and re-apply tag VLANs
    await client.reset_vlans()
    if tag_entries:
        await client.set_tag_vlans(tag_entries)

    # 5. Save both
    await client.save_port_vlans()
    await client.save_tag_vlans()

    return {"ok": True, "port_vlans": len(port_configs), "tag_entries": len(tag_entries)}


# ── STP ──
@app.get("/api/switches/{switch_id}/stp")
async def get_stp(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_stp()

@app.post("/api/switches/{switch_id}/stp")
async def set_stp(switch_id: int, cfg: StpConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.set_stp(cfg.enabled, cfg.mode, cfg.edge_ports)
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
    return {"ok": True}


# ── EEE ──
@app.get("/api/switches/{switch_id}/eee")
async def get_eee(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_eee()

@app.post("/api/switches/{switch_id}/eee")
async def set_eee(switch_id: int, cfg: EeeConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.set_eee(cfg.enabled)
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
async def get_dynamic_macs(switch_id: int, search: Optional[str] = None, user=Depends(get_current_user)):
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
@app.get("/api/switches/{switch_id}/lag")
async def get_lag(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    lag = await client.get_lag()
    # Enrich with local names
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT group_id, name FROM lag_names WHERE switch_id=?", (switch_id,))
        names = {r["group_id"]: r["name"] for r in await cursor.fetchall()}
    return {**lag, "group_names": names}

@app.post("/api/switches/{switch_id}/lag")
async def set_lag(switch_id: int, cfg: LagConfig, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.set_lag(cfg.system_priority, [p.model_dump() for p in cfg.ports])
    # Save group names if provided
    if cfg.group_names:
        async with aiosqlite.connect(DB_PATH) as db:
            for gid, name in cfg.group_names.items():
                await db.execute("INSERT OR REPLACE INTO lag_names (switch_id, group_id, name) VALUES (?,?,?)",
                                 (switch_id, int(gid), name))
            await db.commit()
    return {"ok": True}


# ── System Time ──
@app.get("/api/switches/{switch_id}/time")
async def get_time(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    time_data = await client.get_time()
    sntp_data = await client.get_sntp()
    return {**time_data, **sntp_data}

@app.post("/api/switches/{switch_id}/time")
async def set_time(switch_id: int, data: dict, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    # Read current time first so we don't reset fields
    current = await client.get_time()
    await client.set_time(
        data.get("time") or current.get("timeVal", ""),
        data.get("date") or current.get("dateVal", ""),
        data.get("timezone", current.get("timezoneOffsetVal", "+00:00")),
        data.get("daylight", "0"),
    )
    return {"ok": True}

@app.post("/api/switches/{switch_id}/sntp")
async def set_sntp(switch_id: int, data: dict, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    server = data.get("server", "pool.ntp.org")
    # Resolve hostname to IP (switch only accepts IPs)
    resolved_ip = server
    try:
        socket.inet_aton(server)  # already an IP
    except socket.error:
        try:
            resolved_ip = socket.gethostbyname(server)
        except socket.gaierror:
            raise HTTPException(400, f"Cannot resolve hostname '{server}'")
    await client.set_sntp(data.get("enabled", False), resolved_ip, data.get("poll", 64))
    return {"ok": True, "resolved_ip": resolved_ip, "hostname": server}

@app.get("/api/switches/{switch_id}/sntp/check")
async def check_sntp(switch_id: int, user=Depends(get_current_user)):
    """Check if SNTP is working by reading time and comparing"""
    client = await _get_client(switch_id)
    sntp_cfg = await client.get_sntp()
    time_data = await client.get_time()
    # If date is still 01/01/1970, SNTP is not synced
    synced = time_data.get("dateVal", "01/01/1970") != "01/01/1970"
    return {"synced": synced, "server_ip": sntp_cfg.get("sntp_server_ip"), "time": time_data.get("timeVal"), "date": time_data.get("dateVal")}


# ── Static MAC ──
@app.get("/api/switches/{switch_id}/mac/static")
async def get_static_macs(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_static_macs()

@app.post("/api/switches/{switch_id}/mac/static/add")
async def add_static_mac(switch_id: int, req: StaticMacAdd, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.add_static_mac(req.mac, req.port, req.fid)
    return {"ok": True}

@app.post("/api/switches/{switch_id}/mac/static/delete")
async def delete_static_mac(switch_id: int, data: dict, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.delete_static_mac(data)
    return {"ok": True}

# ── Config Snapshots ──
@app.get("/api/switches/{switch_id}/snapshots")
async def list_snapshots(switch_id: int, user=Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, created_at FROM config_snapshots WHERE switch_id=? ORDER BY created_at DESC", (switch_id,))
        return [dict(r) for r in await cursor.fetchall()]

@app.post("/api/switches/{switch_id}/snapshots")
async def create_snapshot(switch_id: int, data: dict, user=Depends(require_admin)):
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
    name = data.get("name", "Snapshot")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO config_snapshots (switch_id, name, config_json) VALUES (?,?,?)",
            (switch_id, name, json.dumps(snapshot)))
        await db.commit()
        return {"id": cursor.lastrowid, "name": name}

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
async def import_snapshot(switch_id: int, data: dict, user=Depends(require_admin)):
    """Import a snapshot config (save to DB, not apply to switch)"""
    name = data.get("name", "Imported")
    config = data.get("config", {})
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO config_snapshots (switch_id, name, config_json) VALUES (?,?,?)",
            (switch_id, name, json.dumps(config)))
        await db.commit()
        return {"id": cursor.lastrowid}


# ── Sync VLANs ──
@app.post("/api/switches/{switch_id}/vlans/sync")
async def sync_vlans(switch_id: int, user=Depends(require_admin)):
    """Copy VLAN definitions from this switch to all other switches"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT vlan_id, name FROM vlans WHERE switch_id=?", (switch_id,))
        source_vlans = await cursor.fetchall()
        cursor = await db.execute("SELECT id FROM switches WHERE id != ?", (switch_id,))
        other_switches = [r["id"] for r in await cursor.fetchall()]
        synced = 0
        for sid in other_switches:
            for v in source_vlans:
                await db.execute("INSERT OR IGNORE INTO vlans (switch_id, vlan_id, name) VALUES (?,?,?)",
                                 (sid, v["vlan_id"], v["name"]))
                synced += 1
        await db.commit()
        return {"ok": True, "synced": synced, "targets": len(other_switches)}


# ── User Management ──
@app.get("/api/users")
async def list_users(user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, username, role, created_at FROM users")
        return [dict(r) for r in await cursor.fetchall()]

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"

@app.post("/api/users")
async def create_user(req: UserCreate, user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                             (req.username, hash_password(req.password), req.role))
            await db.commit()
            return {"ok": True}
        except Exception:
            raise HTTPException(400, "Username already exists")

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, user=Depends(require_admin)):
    if str(user_id) == user.get("sub"):
        raise HTTPException(400, "Cannot delete yourself")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE id=?", (user_id,))
        await db.commit()
        return {"ok": True}

class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, req: UserUpdate, user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        if req.role:
            await db.execute("UPDATE users SET role=? WHERE id=?", (req.role, user_id))
        if req.password:
            await db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(req.password), user_id))
        await db.commit()
        return {"ok": True}


# ── Reboot ──
@app.post("/api/switches/{switch_id}/reboot")
async def reboot_switch(switch_id: int, user=Depends(require_admin)):
    client = await _get_client(switch_id)
    await client.reboot()
    return {"ok": True}
