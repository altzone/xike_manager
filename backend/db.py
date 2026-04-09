import aiosqlite
import csv
import os

DB_PATH = os.environ.get("DB_PATH", "/opt/switchpilot/data/switchpilot.db")
OUI_CSV = os.path.join(os.path.dirname(__file__), "oui.csv")

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

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
