import aiosqlite
import contextlib
import csv
import glob
import json
import logging
import os
import re
import sqlite3
import time

from switch_client import default_swap_sfp
from version import VERSION

log = logging.getLogger("switchpilot")

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


SCHEMA_VERSION = 3  # PRAGMA user_version once every migration below has run
BACKUPS_KEPT = 5
NEW_COLUMNS = {"swap_sfp_9_10", "vlan_layout"}  # switches columns added after the first release


def backup_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")


def _backup_before_upgrade():
    """Copy the database to data/backups before a start that migrates it or runs another
    SwitchPilot version than the last start (an update, or a return to an earlier version).
    A migration never runs without its copy: if the copy fails, the start fails. A start that
    keeps failing after its copy reuses that first copy (the database records it as pending until
    a start completes), so retries never push the clean copy out of the 5 kept; a database
    restored from a copy carries no such record and is copied again."""
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        return None
    con = sqlite3.connect(DB_PATH)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "switches" not in tables:
            return None  # nothing to keep yet
        last = pending = None
        if "meta" in tables:
            meta = dict(con.execute("SELECT key, value FROM meta WHERE key IN ('last_version', 'backup_pending')"))
            last, pending = meta.get("last_version"), meta.get("backup_pending")
        schema = con.execute("PRAGMA user_version").fetchone()[0]
        columns = {r[1] for r in con.execute("PRAGMA table_info(switches)")}
    finally:
        con.close()
    if schema > SCHEMA_VERSION:
        log.warning("The database was last used by a newer SwitchPilot (schema %d, this version knows %d). "
                    "If something misbehaves, go back to that version or restore a copy from %s",
                    schema, SCHEMA_VERSION, backup_dir())
    migrating = schema < SCHEMA_VERSION or not NEW_COLUMNS <= columns
    if not migrating and last == VERSION:
        return None
    origin = re.sub(r"[^0-9A-Za-z.-]", "", last or "") or "earlier"
    folder = backup_dir()
    update = f"{origin}-to-{VERSION}"
    if pending:
        pending_update, _, pending_copy = pending.partition(":")
        if pending_update == update and pending_copy and os.path.exists(os.path.join(folder, pending_copy)):
            return None  # a retry of a start that failed after its copy: that copy is the clean one
    for stale in glob.glob(os.path.join(folder, "switchpilot-*.db.part")):
        with contextlib.suppress(OSError):
            os.remove(stale)  # left by a copy that was interrupted
    tmp = None
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(folder, 0o700)  # best effort, like the database itself (some mounts refuse it)
        path = os.path.join(folder, f"switchpilot-{update}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.db")
        tmp = path + ".part"
        os.close(os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600))  # holds switch passwords
        src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        os.replace(tmp, path)
        tmp = None
    except (OSError, sqlite3.Error) as e:
        if tmp:
            with contextlib.suppress(OSError):
                os.remove(tmp)
        if migrating:
            raise RuntimeError(f"SwitchPilot {VERSION} must update the database and could not copy it first "
                               f"to {folder} ({e}): nothing was changed. Free some disk space or fix the "
                               f"permissions of that folder, then start again.") from e
        log.warning("Could not copy the database to %s before this start: %s", folder, e)
        return None
    try:  # recorded in the database itself, cleared once this start completes (init_db)
        con = sqlite3.connect(DB_PATH)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('backup_pending', ?)",
                        (f"{update}:{os.path.basename(path)}",))
            con.commit()
        finally:
            con.close()
    except sqlite3.Error as e:
        log.warning("Could not record the copy in the database (a failed start would copy it again): %s", e)
    copies = sorted(glob.glob(os.path.join(folder, "switchpilot-*.db")), key=os.path.getmtime, reverse=True)
    for old in [c for c in copies if c != path][BACKUPS_KEPT - 1:]:
        with contextlib.suppress(OSError):
            os.remove(old)
    log.info("Database copied to %s before starting SwitchPilot %s", path, VERSION)
    return path


async def _swap_descriptions_9_10(db, switch_id: int):
    """Descriptions describe what is plugged into a cage, so they follow it when the numbering
    changes. UNIQUE(switch_id, port) forbids a direct swap: go through -9."""
    await db.execute("UPDATE port_descriptions SET port = -9 WHERE switch_id = ? AND port = 9", (switch_id,))
    await db.execute("UPDATE port_descriptions SET port = 9 WHERE switch_id = ? AND port = 10", (switch_id,))
    await db.execute("UPDATE port_descriptions SET port = 10 WHERE switch_id = ? AND port = -9", (switch_id,))


async def _migrate(db):
    """Bring a database from any earlier release to SCHEMA_VERSION (CREATE TABLE IF NOT EXISTS
    never adds columns to an existing table)."""
    columns = await _columns(db, "switches")
    if not NEW_COLUMNS <= columns:
        await db.execute("BEGIN")  # one step: a column without its values must never be committed
        if "swap_sfp_9_10" not in columns:
            # 1.x: every switch was shown with the 9/10 swap applied; record that, step 2 corrects it
            await db.execute("ALTER TABLE switches ADD COLUMN swap_sfp_9_10 INTEGER NOT NULL DEFAULT 0")
            await db.execute("UPDATE switches SET swap_sfp_9_10 = 1")
        if "vlan_layout" not in columns:
            # 2.3.0: how the switch's firmware stores VLAN members, once confirmed ("<fw_ver>:<layout>")
            await db.execute("ALTER TABLE switches ADD COLUMN vlan_layout TEXT NOT NULL DEFAULT ''")
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
    if version < SCHEMA_VERSION:
        await db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")  # same transaction as step 2
        await db.commit()


def _restrict_db_permissions():
    """The database holds the switches' admin passwords: keep it readable by this user only."""
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass


async def init_db():
    _backup_before_upgrade()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
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
                vlan_layout TEXT NOT NULL DEFAULT '',
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
        # the version this database was last started with: the next update copies it first
        await db.execute("INSERT INTO meta (key, value) VALUES ('last_version', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (VERSION,))
        await db.execute("DELETE FROM meta WHERE key = 'backup_pending'")  # this start completed
        await db.commit()
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
