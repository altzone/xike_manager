"""Updating SwitchPilot safely: the database is copied before it changes, a restart does not test
a switch again, and a stop never cuts a change being sent to a switch."""
import asyncio
import glob
import logging
import os
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time

import httpx
import pytest
from sse_starlette.sse import AppStatus

import db as dbmod
import main
import sse
from version import VERSION
from test_v2_vlans import v2, layout_posts  # noqa: F401 (fixture)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_2_2_database(path):
    """A database as 2.2.x leaves it: schema 2, no meta table, no vlan_layout column."""
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE switches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, ip TEXT NOT NULL,
            username TEXT NOT NULL, password TEXT NOT NULL, model TEXT DEFAULT '',
            firmware TEXT DEFAULT '', mac_address TEXT DEFAULT '',
            swap_sfp_9_10 INTEGER NOT NULL DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO switches (name, ip, username, password, firmware) VALUES ('core', '10.0.0.1', 'admin', 'pw', '1.0.0.6');
        PRAGMA user_version = 2;
    """)
    con.commit()
    con.close()


def backups(db_path):
    return sorted(glob.glob(os.path.join(os.path.dirname(db_path), "backups", "switchpilot-*.db")))


# ── Copy of the database before it changes ──
def test_a_new_install_makes_no_copy(db_path):
    asyncio.run(dbmod.init_db())
    assert backups(db_path) == []


def test_the_database_is_copied_before_it_is_migrated(db_path):
    make_2_2_database(db_path)
    asyncio.run(dbmod.init_db())
    [copy] = backups(db_path)
    assert os.path.basename(copy).startswith(f"switchpilot-earlier-to-{VERSION}-")
    con = sqlite3.connect(copy)  # the copy is the database as it was, before the migration
    assert con.execute("PRAGMA user_version").fetchone() == (2,)
    assert "vlan_layout" not in {r[1] for r in con.execute("PRAGMA table_info(switches)")}
    assert con.execute("SELECT name, password FROM switches").fetchall() == [("core", "pw")]
    con.close()
    # it holds the switches' passwords: readable by this user only
    assert stat.S_IMODE(os.stat(copy).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.dirname(copy)).st_mode) == 0o700
    con = sqlite3.connect(db_path)
    assert con.execute("PRAGMA user_version").fetchone() == (dbmod.SCHEMA_VERSION,)
    assert con.execute("SELECT vlan_layout FROM switches").fetchall() == [("",)]
    assert con.execute("SELECT value FROM meta WHERE key = 'last_version'").fetchone() == (VERSION,)
    con.close()
    asyncio.run(dbmod.init_db())  # a plain restart: no new copy
    assert len(backups(db_path)) == 1


def test_an_update_without_migration_is_copied_too(db_path):
    asyncio.run(dbmod.init_db())
    con = sqlite3.connect(db_path)
    con.execute("UPDATE meta SET value = '2.3.0-before' WHERE key = 'last_version'")  # started by another version
    con.commit()
    con.close()
    asyncio.run(dbmod.init_db())
    [copy] = backups(db_path)
    assert os.path.basename(copy).startswith(f"switchpilot-2.3.0-before-to-{VERSION}-")


def test_a_start_that_keeps_failing_keeps_the_first_copy(db_path):
    """A migration that fails is retried at each restart: the copy made before the first attempt is
    the clean one, so no later copy may push it out of the 5 kept."""
    make_2_2_database(db_path)
    folder = os.path.join(os.path.dirname(db_path), "backups")
    for _ in range(3):
        dbmod._backup_before_upgrade()  # the migration then fails, the container restarts
    assert len(backups(db_path)) == 1
    for i in range(6):  # older copies, from earlier updates
        path = os.path.join(folder, f"switchpilot-1.{i}.0-to-1.{i + 1}.0-2025010{i}-000000.db")
        open(path, "w").close()
        os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))
    con = sqlite3.connect(db_path)  # then another update starts (from 2.2.1)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('last_version', '2.2.1')")
    con.commit()
    con.close()
    dbmod._backup_before_upgrade()
    names = [os.path.basename(p) for p in backups(db_path)]
    assert len(names) == dbmod.BACKUPS_KEPT
    assert any(n.startswith("switchpilot-earlier-to-") for n in names)
    assert any(n.startswith("switchpilot-2.2.1-to-") for n in names)
    assert "switchpilot-1.0.0-to-1.1.0-20250100-000000.db" not in names  # the oldest went


def test_a_restored_copy_is_copied_again_before_the_next_update(db_path):
    """Rolling back by restoring a copy, using the old version, then updating again: the database
    changed since the first copy, so the update copies it again."""
    make_2_2_database(db_path)
    asyncio.run(dbmod.init_db())
    [first] = backups(db_path)
    shutil.copy(first, db_path)  # rolled back to 2.2.x with the copy, as the upgrade guide says
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO switches (name, ip, username, password) VALUES ('added later', '10.0.0.9', 'a', 'b')")
    con.commit()
    con.close()
    time.sleep(1.1)  # copies are named to the second
    asyncio.run(dbmod.init_db())
    copies = backups(db_path)
    assert len(copies) == 2
    newest = max(copies, key=os.path.getmtime)
    con = sqlite3.connect(newest)
    assert ("added later",) in con.execute("SELECT name FROM switches").fetchall()
    con.close()


def test_a_failed_copy_leaves_no_partial_file(db_path, monkeypatch):
    make_2_2_database(db_path)
    folder = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(folder)
    open(os.path.join(folder, "switchpilot-x-to-y-20250101-000000.db.part"), "w").close()  # an old leftover
    real_connect = sqlite3.connect

    def full_disk(path, *a, **k):
        if str(path).endswith(".part"):
            raise sqlite3.OperationalError("database or disk is full")
        return real_connect(path, *a, **k)
    monkeypatch.setattr(dbmod.sqlite3, "connect", full_disk)
    with pytest.raises(RuntimeError, match="could not copy it first"):
        dbmod._backup_before_upgrade()
    assert os.listdir(folder) == []  # neither this attempt's nor the old leftover


def test_no_migration_without_its_copy(db_path):
    make_2_2_database(db_path)
    open(os.path.join(os.path.dirname(db_path), "backups"), "w").close()  # the copy cannot be written
    with pytest.raises(RuntimeError, match="could not copy it first"):
        asyncio.run(dbmod.init_db())
    con = sqlite3.connect(db_path)
    assert con.execute("PRAGMA user_version").fetchone() == (2,)  # untouched
    assert "vlan_layout" not in {r[1] for r in con.execute("PRAGMA table_info(switches)")}
    con.close()


def test_a_copy_that_fails_without_migration_does_not_stop_the_start(db_path, caplog):
    asyncio.run(dbmod.init_db())
    con = sqlite3.connect(db_path)
    con.execute("UPDATE meta SET value = '2.3.0-before' WHERE key = 'last_version'")
    con.commit()
    con.close()
    open(os.path.join(os.path.dirname(db_path), "backups"), "w").close()
    with caplog.at_level(logging.WARNING, logger="switchpilot"):
        asyncio.run(dbmod.init_db())
    assert "Could not copy the database" in caplog.text


def test_a_database_from_a_newer_version_is_reported_and_kept(db_path, caplog):
    asyncio.run(dbmod.init_db())
    con = sqlite3.connect(db_path)
    con.execute(f"PRAGMA user_version = {dbmod.SCHEMA_VERSION + 1}")
    con.commit()
    con.close()
    with caplog.at_level(logging.WARNING, logger="switchpilot"):
        asyncio.run(dbmod.init_db())
    assert "newer SwitchPilot" in caplog.text
    con = sqlite3.connect(db_path)
    assert con.execute("PRAGMA user_version").fetchone() == (dbmod.SCHEMA_VERSION + 1,)  # never lowered
    con.close()


# ── The VLAN layout check on 2.0.0.3 is not repeated after a restart ──
def test_the_layout_check_is_remembered_across_restarts(api, v2):  # noqa: F811
    m = api.mock
    m.v2.read_layout = "plain"  # 2.0.0.3: reads back 10 entries, writes 11 like its web page
    assert api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 10, "name": "Office"}).status_code == 200
    assert len(layout_posts(m)) == 2
    con = sqlite3.connect(dbmod.DB_PATH)
    assert con.execute("SELECT vlan_layout FROM switches WHERE id = ?", (v2,)).fetchone() == ("2.0.0.3:padded",)
    con.close()
    sse._clients.clear()  # what a restart does
    r = api.post(f"/api/switches/{v2}/vlans/apply", json=[{"port": 5, "mode": "access", "access_vlan": 10}])
    assert r.status_code == 200, r.text
    assert len(layout_posts(m)) == 2  # no temporary VLAN this time
    assert m.v2.table[10]["states"][5] == 1 and m.v2.table[1]["states"][5] == 0
    # another firmware may store VLAN members differently: checked again
    sse._clients.clear()
    m.state["status.json"]["fw_ver"] = "2.0.0.4"
    assert api.post(f"/api/switches/{v2}/vlans", json={"vlan_id": 20, "name": "Lab"}).status_code == 200
    assert len(layout_posts(m)) == 4


# ── A stop never cuts a change being sent to a switch ──
def run_request(app_call, method, path):
    async def app(scope, receive, send):
        await app_call()
    middleware = main.FinishSwitchChanges(app)
    scope = {"type": "http", "method": method, "path": path}
    return asyncio.ensure_future(middleware(scope, None, None))


def test_a_cancelled_switch_change_still_runs_to_its_end():
    """uvicorn cancels the requests still open when its graceful time is over; a change being sent to
    a switch must still finish (its read-back and restore included), and the shutdown waits for it."""
    async def scenario():
        steps = []
        release = asyncio.Event()

        async def change():
            steps.append("written")
            await release.wait()  # the switch is slow to answer the read-back
            steps.append("checked and saved")

        async def read():
            steps.append("read")
            await release.wait()
            steps.append("read done")

        request = run_request(change, "POST", "/api/switches/1/vlans/apply")
        reading = run_request(read, "GET", "/api/switches/1/vlans")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        request.cancel()  # uvicorn: graceful shutdown time over
        reading.cancel()
        await asyncio.sleep(0)
        assert len(main._switch_changes) == 1  # the GET is not kept
        waiting = asyncio.ensure_future(main.wait_for_switch_changes(timeout=5))  # lifespan shutdown
        await asyncio.sleep(0.05)
        assert not waiting.done()
        release.set()
        await waiting
        return steps

    steps = asyncio.run(scenario())
    assert "checked and saved" in steps  # the change went on to its end
    assert "read done" not in steps  # a read is simply dropped
    assert not main._switch_changes


def test_the_shutdown_does_not_wait_forever_for_a_switch_change(caplog):
    async def scenario():
        request = run_request(lambda: asyncio.sleep(30), "PUT", "/api/switches/1/ports/3")
        await asyncio.sleep(0)
        with caplog.at_level(logging.ERROR, logger="switchpilot"):
            t = time.monotonic()
            await main.wait_for_switch_changes(timeout=0.2)
            assert time.monotonic() - t < 2
        request.cancel()
        for task in list(main._switch_changes):
            task.cancel()
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert "unfinished" in caplog.text


def test_live_streams_are_told_to_end_on_sigterm():
    """uvicorn installs its handler before importing the app, so sse-starlette's own hook never
    runs: the app chains one in front of uvicorn's."""
    called = []
    previous = signal.signal(signal.SIGTERM, lambda signum, frame: called.append(signum))
    previous_int = signal.getsignal(signal.SIGINT)

    async def scenario(monkeypatch_cut):
        main.end_streams_on_exit()
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        assert sse.stopping and called == [signal.SIGTERM]  # streams end at their next pause
        assert not AppStatus.should_exit
        await asyncio.sleep(monkeypatch_cut + 0.2)
        assert AppStatus.should_exit  # what still waits on a switch is cut

    old_cut = main.STREAMS_CUT_AFTER
    try:
        main.STREAMS_CUT_AFTER = 0.1
        AppStatus.should_exit = False
        asyncio.run(scenario(0.1))
    finally:
        main.STREAMS_CUT_AFTER = old_cut
        signal.signal(signal.SIGTERM, previous)
        signal.signal(signal.SIGINT, previous_int)
        AppStatus.should_exit = False
        AppStatus.should_exit_event = None
        sse.stopping = False


def test_a_stream_pause_ends_early_when_the_server_stops(monkeypatch):
    async def scenario():
        t = time.monotonic()
        waiting = asyncio.ensure_future(sse._pause(15))
        await asyncio.sleep(0.2)
        sse.stop_streams()
        await waiting
        return time.monotonic() - t

    try:
        assert asyncio.run(scenario()) < 1.5
    finally:
        sse.stopping = False


def test_a_change_running_past_the_graceful_time_still_gets_its_own_answer(tmp_path):
    """uvicorn cancels the requests still running when its graceful time is over: a switch change
    keeps running, and its own answer (here a 502 asking to restart the switch) is the one sent,
    not uvicorn's 500."""
    (tmp_path / "slowapp.py").write_text(
        "import asyncio\n"
        "from fastapi import HTTPException\n"
        "import main\n"
        "@main.app.post('/api/switches/999/slow')\n"
        "async def slow():\n"
        "    await asyncio.sleep(4)\n"
        "    raise HTTPException(502, 'previous settings not put back: restart the switch')\n"
        "app = main.app\n")
    port = free_port()
    env = {**os.environ, "DB_PATH": str(tmp_path / "sp.db"), "SECRET_KEY_FILE": str(tmp_path / "key"),
           "PYTHONPATH": f"{tmp_path}{os.pathsep}{BACKEND}"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "slowapp:app", "--host", "127.0.0.1", "--port", str(port),
                             "--timeout-graceful-shutdown", "1"], cwd=BACKEND, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(base + "/api/setup/status").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        answer = {}
        def call():
            answer["r"] = httpx.post(base + "/api/switches/999/slow", timeout=30)
        t = threading.Thread(target=call)
        t.start()
        time.sleep(0.5)
        proc.send_signal(signal.SIGTERM)
        t.join(30)
        proc.wait(timeout=30)
        out = proc.stdout.read().decode()
        assert answer["r"].status_code == 502, (answer["r"].status_code, out)
        assert "restart the switch" in answer["r"].json()["detail"]
        assert "Exception in ASGI application" not in out, out
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_live_stream_does_not_hold_the_server_on_sigterm(tmp_path):
    """The real thing: uvicorn with a live stream open stops within seconds of SIGTERM. Before
    2.3.0 it waited for the stream to end, which never happens, until the container was killed."""
    port = free_port()
    env = {**os.environ, "DB_PATH": str(tmp_path / "sp.db"), "SECRET_KEY_FILE": str(tmp_path / "key")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(base + "/api/setup/status").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        assert httpx.post(base + "/api/setup", json={"username": "admin", "password": "secret123"}).status_code == 200
        token = httpx.post(base + "/api/auth/login", json={"username": "admin", "password": "secret123"}).json()["token"]
        con = sqlite3.connect(env["DB_PATH"])  # a switch nobody answers for: the stream keeps reporting errors
        con.execute("INSERT INTO switches (name, ip, username, password) VALUES ('gone', '127.0.0.1', 'a', 'b')")
        con.commit()
        con.close()
        auth = {"Authorization": f"Bearer {token}"}
        stream_token = httpx.post(base + "/api/auth/stream-token", headers=auth).json()["token"]
        opened = threading.Event()

        def listen():
            try:
                with httpx.stream("GET", f"{base}/api/switches/1/sse?token={stream_token}", timeout=60) as r:
                    for _ in r.iter_lines():
                        opened.set()
            except httpx.HTTPError:
                pass
        threading.Thread(target=listen, daemon=True).start()
        assert opened.wait(20), "the stream never sent anything"
        started = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pytest.fail("uvicorn still running 10 s after SIGTERM with a live stream open")
        assert time.monotonic() - started < 5
        out = proc.stdout.read().decode()
        assert "Finished server process" in out
        assert "without completing response" not in out, out  # the stream ended cleanly
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
