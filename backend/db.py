import aiosqlite
import csv
import json
import os

from switch_client import default_swap_sfp

DB_PATH = os.environ.get("DB_PATH", "/opt/switchpilot/data/switchpilot.db")
OUI_CSV = os.path.join(os.path.dirname(__file__), "oui.csv")

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def _columns(db, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in await cursor.fetchall()}


SCHEMA_VERSION = 2  # PRAGMA user_version once every migration below has run


async def _swap_descriptions_9_10(db, switch_id: int):
    """Descriptions describe what is plugged into a cage, so they follow it when the numbering
    changes. UNIQUE(switch_id, port) forbids a direct swap: go through -9."""
    await db.execute("UPDATE port_descriptions SET port = -9 WHERE switch_id = ? AND port = 9", (switch_id,))
    await db.execute("UPDATE port_descriptions SET port = 9 WHERE switch_id = ? AND port = 10", (switch_id,))
    await db.execute("UPDATE port_descriptions SET port = 10 WHERE switch_id = ? AND port = -9", (switch_id,))


async def _migrate(db):
    """Bring a database from any earlier release to SCHEMA_VERSION (CREATE TABLE IF NOT EXISTS
    never adds columns to an existing table)."""
    if "swap_sfp_9_10" not in await _columns(db, "switches"):
        # 1.x: every switch was shown with the 9/10 swap applied; record that, step 2 corrects it
        await db.execute("ALTER TABLE switches ADD COLUMN swap_sfp_9_10 INTEGER NOT NULL DEFAULT 0")
        await db.execute("UPDATE switches SET swap_sfp_9_10 = 1")
        await db.commit()

    version = (await (await db.execute("PRAGMA user_version")).fetchone())[0]
    if version < 2:
        # The 9/10 numbering follows the firmware line (1.0.0.x swapped, 2.0.0.x not; issue #3).
        # 1.x showed every switch swapped and 2.1.0 started every new switch unswapped, so set each
        # switch whose firmware is known to its line once, and move its 9/10 descriptions with
        # the cages. Unknown firmware keeps its setting. Logged in the switch's change log.
        cursor = await db.execute("SELECT id, firmware, swap_sfp_9_10 FROM switches")
        for switch_id, firmware, current in await cursor.fetchall():
            suggested = default_swap_sfp(firmware)
            if suggested is None or bool(current) == suggested:
                continue
            await db.execute("UPDATE switches SET swap_sfp_9_10 = ? WHERE id = ?", (int(suggested), switch_id))
            await _swap_descriptions_9_10(db, switch_id)
            await db.execute(
                "INSERT INTO change_log (switch_id, user_id, action, details) VALUES (?, 0, 'port_mapping', ?)",
                (switch_id, json.dumps({"swap_sfp_9_10": suggested, "moved_descriptions": True,
                                        "reason": f"firmware {firmware}", "automatic": True})))
        await db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await db.commit()


def _restrict_db_permissions():
    """The database holds the switches' admin passwords: keep it readable by this user only."""
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS switches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ip TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                model TEXT DEFAULT '',
                firmware TEXT DEFAULT '',
                mac_address TEXT DEFAULT '',
                swap_sfp_9_10 INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS vlan_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                switch_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (switch_id) REFERENCES switches(id)
            );
            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                switch_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (switch_id) REFERENCES switches(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS vlans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                switch_id INTEGER NOT NULL,
                vlan_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                UNIQUE(switch_id, vlan_id),
                FOREIGN KEY (switch_id) REFERENCES switches(id)
            );
            CREATE TABLE IF NOT EXISTS lag_names (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                switch_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                UNIQUE(switch_id, group_id),
                FOREIGN KEY (switch_id) REFERENCES switches(id)
            );
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                switch_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (switch_id) REFERENCES switches(id)
            );
            CREATE TABLE IF NOT EXISTS oui (
                prefix TEXT PRIMARY KEY,
                vendor TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS port_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                switch_id INTEGER NOT NULL,
                port INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                UNIQUE(switch_id, port),
                FOREIGN KEY (switch_id) REFERENCES switches(id)
            );
        """)
        await db.commit()
        await _migrate(db)
        _restrict_db_permissions()
        # Load OUI database if empty
        cursor = await db.execute("SELECT COUNT(*) FROM oui")
        count = (await cursor.fetchone())[0]
        if count == 0 and os.path.exists(OUI_CSV):
            with open(OUI_CSV, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                batch = []
                for row in reader:
                    if len(row) >= 3:
                        prefix = row[1].strip().upper()
                        vendor = row[2].strip().strip('"')
                        if prefix and vendor:
                            batch.append((prefix, vendor))
                await db.executemany("INSERT OR IGNORE INTO oui (prefix, vendor) VALUES (?, ?)", batch)
                await db.commit()
