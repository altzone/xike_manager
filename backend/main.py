from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiosqlite

from db import init_db, get_db, DB_PATH
from auth import hash_password, verify_password, create_token, get_current_user, require_admin
from switch_client import SwitchClient, MAX_FID, MAX_TAG_ENTRIES
from sse import get_switch_client, sse_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="SwitchPilot", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


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

class PortVlanConfig(BaseModel):
    port: int
    mode: str  # "access", "trunk", "flat"
    pvid: int = 0

class TagVlanEntry(BaseModel):
    entry: int
    port: int
    vlan_id: int


# ── Setup (first run) ──
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
@app.get("/api/switches")
async def list_switches(user=Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, name, ip, username, model, firmware, mac_address, created_at FROM switches")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

@app.post("/api/switches")
async def add_switch(req: SwitchAdd, user=Depends(require_admin)):
    # Test connection
    client = SwitchClient(req.ip, req.username, req.password)
    try:
        if not await client.login():
            raise HTTPException(400, f"Cannot connect to switch at {req.ip}")
        status = await client.get_status()
    except Exception as e:
        raise HTTPException(400, f"Switch connection failed: {e}")
    finally:
        await client.close()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO switches (name, ip, username, password, model, firmware, mac_address) VALUES (?,?,?,?,?,?,?)",
            (req.name, req.ip, req.username, req.password,
             status.get("modle", ""), status.get("fw_ver", ""), status.get("sys_macaddr", ""))
        )
        await db.commit()
        return {"id": cursor.lastrowid, "model": status.get("modle"), "firmware": status.get("fw_ver")}

@app.delete("/api/switches/{switch_id}")
async def delete_switch(switch_id: int, user=Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM switches WHERE id = ?", (switch_id,))
        await db.commit()
        return {"ok": True}


# ── Helper to get switch client ──
async def _get_client(switch_id: int) -> SwitchClient:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM switches WHERE id = ?", (switch_id,))
        sw = await cursor.fetchone()
        if not sw:
            raise HTTPException(404, "Switch not found")
        return get_switch_client(sw["id"], sw["ip"], sw["username"], sw["password"])


# ── SSE ──
@app.get("/api/switches/{switch_id}/sse")
async def switch_sse(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await sse_endpoint(client)


# ── Switch System ──
@app.get("/api/switches/{switch_id}/status")
async def switch_status(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    status = await client.get_status()
    network = await client.get_network()
    return {**status, **network}

@app.get("/api/switches/{switch_id}/time")
async def switch_time(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_time()


# ── Ports ──
@app.get("/api/switches/{switch_id}/ports")
async def switch_ports(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_ports()

@app.get("/api/switches/{switch_id}/ports/stats")
async def switch_port_stats(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_port_stats()


# ── VLANs ──
@app.get("/api/switches/{switch_id}/vlans/port")
async def get_port_vlans(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_port_vlans()

@app.post("/api/switches/{switch_id}/vlans/port")
async def set_port_vlans(switch_id: int, configs: list[PortVlanConfig], user=Depends(require_admin)):
    client = await _get_client(switch_id)
    result = await client.set_port_vlans([c.model_dump() for c in configs])
    await client.save_port_vlans()
    return {"result": result}

@app.get("/api/switches/{switch_id}/vlans/tag")
async def get_tag_vlans(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_tag_vlans()

@app.post("/api/switches/{switch_id}/vlans/tag")
async def set_tag_vlans(switch_id: int, entries: list[TagVlanEntry], user=Depends(require_admin)):
    client = await _get_client(switch_id)
    result = await client.set_tag_vlans([e.model_dump() for e in entries])
    await client.save_tag_vlans()
    return {"result": result}

@app.get("/api/switches/{switch_id}/vlans/limits")
async def vlan_limits(switch_id: int, user=Depends(get_current_user)):
    return {"max_fid": MAX_FID, "max_tag_entries": MAX_TAG_ENTRIES, "max_vlan_id": 4095}


# ── STP ──
@app.get("/api/switches/{switch_id}/stp")
async def get_stp(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_stp()


# ── LAG ──
@app.get("/api/switches/{switch_id}/lag")
async def get_lag(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_lag()


# ── Monitoring ──
@app.get("/api/switches/{switch_id}/mac/dynamic")
async def get_dynamic_macs(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_dynamic_macs()

@app.get("/api/switches/{switch_id}/loop")
async def get_loop(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    status = await client.get_loop_status()
    config = await client.get_loop_config()
    return {"status": status, "config": config}

@app.get("/api/switches/{switch_id}/igmp")
async def get_igmp(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    config = await client.get_igmp_config()
    entries = await client.get_igmp_entries()
    return {"config": config, "entries": entries}

@app.get("/api/switches/{switch_id}/storm")
async def get_storm(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_storm_control()

@app.get("/api/switches/{switch_id}/mirror")
async def get_mirror(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_mirror()

@app.get("/api/switches/{switch_id}/eee")
async def get_eee(switch_id: int, user=Depends(get_current_user)):
    client = await _get_client(switch_id)
    return await client.get_eee()
