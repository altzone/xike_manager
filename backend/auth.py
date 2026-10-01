import asyncio
import hashlib
import ipaddress
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import aiosqlite
import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

import db as dbmod

log = logging.getLogger("switchpilot.auth")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = 24  # hours
STREAM_TOKEN_EXPIRE = 5   # minutes: only ever used to open an SSE stream, so it can leak into access logs harmlessly
MIN_PASSWORD_LENGTH = 6
ROLES = ("admin", "viewer")

# Secrets that shipped in docker-compose.yml / this file in earlier versions. Anyone who read
# the repository could forge an admin token for an install still using them.
KNOWN_DEFAULT_SECRETS = {"", "switchpilot-secret-change-me-in-prod", "switchpilot-prod-change-me", "change-me"}

security = HTTPBearer()


def load_secret_key() -> str:
    """Use SECRET_KEY from the environment, or a random key generated once and kept
    next to the database (so tokens survive restarts) when it is unset or a known default."""
    env = os.environ.get("SECRET_KEY", "")
    if env not in KNOWN_DEFAULT_SECRETS:
        if len(env) < 32:
            log.warning("SECRET_KEY is only %d characters long; use at least 32 random ones", len(env))
        return env
    path = os.environ.get("SECRET_KEY_FILE") or os.path.join(os.path.dirname(dbmod.DB_PATH), "secret_key")
    try:
        with open(path) as f:
            key = f.read().strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(48)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # created 0600 from the start (never world-readable, even for an instant)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        log.warning("SECRET_KEY unset or a known default: generated a new one in %s", path)
    except OSError as e:
        log.warning("SECRET_KEY unset and %s is not writable (%s): sessions will not survive a restart", path, e)
    return key


SECRET_KEY = load_secret_key()


# ── Passwords (bcrypt is CPU-bound: keep it off the event loop) ──
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# Compared against when the username is unknown, so a failed login costs the same either way
DUMMY_HASH = hash_password(secrets.token_hex(16))


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_password, plain, hashed)


def validate_password(password: str):
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def validate_role(role: str):
    if role not in ROLES:
        raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}")


# ── Tokens ──
def password_version(password_hash: str) -> str:
    """Fingerprint of the stored hash, carried in tokens so that changing a password
    revokes every session opened with the old one (the hash itself never leaves the DB)."""
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:16]


def create_token(user_id: int, username: str, role: str, scope: str = "api",
                 expires: timedelta = timedelta(hours=ACCESS_TOKEN_EXPIRE), pv: str = "") -> str:
    return jwt.encode(
        {"sub": str(user_id), "username": username, "role": role, "scope": scope, "pv": pv,
         "exp": datetime.now(timezone.utc) + expires},
        SECRET_KEY, algorithm=ALGORITHM
    )


def create_stream_token(user: dict) -> str:
    return create_token(int(user["sub"]), user["username"], user["role"], scope="stream",
                        expires=timedelta(minutes=STREAM_TOKEN_EXPIRE), pv=user.get("pv", ""))


def decode_token(token: str, scope: str = "api") -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("scope", "api") != scope:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token not valid for this use")
    return payload


async def load_user(payload: dict) -> dict:
    """Re-read the account so a deleted or demoted user loses access immediately,
    not when their 24 h token expires."""
    try:
        user_id = int(payload.get("sub", ""))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, username, role, password_hash FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account no longer exists")
    pv = password_version(row["password_hash"])
    if payload.get("pv") != pv:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Password changed, log in again")
    return {"sub": str(row["id"]), "username": row["username"], "role": row["role"], "pv": pv}


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return await load_user(decode_token(credentials.credentials))


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user


# ── Login throttling (failures only) ──
# Keyed on (client address, username): a wrong password on one account never locks the
# others out, which matters when every browser arrives from the same address (an outer
# reverse proxy, Docker Desktop's NAT). A looser per-address cap still stops one client
# from spraying many usernames.
LOGIN_MAX_FAILURES = 10            # per (address, username)
LOGIN_MAX_FAILURES_PER_ADDRESS = 100
LOGIN_WINDOW = 600  # seconds
_failures: dict[tuple, deque] = defaultdict(deque)


def _parse_networks(spec: str) -> list:
    nets = []
    for item in (spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            log.warning("TRUSTED_PROXIES: ignoring %r (not an IP address or CIDR)", item)
    return nets


# Addresses of reverse proxies in front of the container whose X-Forwarded-For can be believed
TRUSTED_PROXIES = _parse_networks(os.environ.get("TRUSTED_PROXIES", ""))


def _is_trusted_proxy(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in TRUSTED_PROXIES)


def client_ip(request: Request) -> str:
    """The address of whoever is logging in.

    The container's nginx sets X-Real-IP to the peer that connected to it and appends that
    peer to X-Forwarded-For. Hops are only unwound through proxies listed in TRUSTED_PROXIES;
    without it, the peer address is used as-is (a client cannot pick its own bucket).
    """
    addr = request.headers.get("x-real-ip") or (request.client.host if request.client else "?")
    if not TRUSTED_PROXIES:
        return addr
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if hops and hops[-1] == addr:
        hops.pop()  # the entry nginx appended for the peer itself
    while hops and _is_trusted_proxy(addr):
        addr = hops.pop()
    return addr


def _prune(now: float):
    for key in [k for k, q in _failures.items() if not q or now - q[-1] > LOGIN_WINDOW]:
        _failures.pop(key, None)


def _recent(key: tuple, now: float) -> int:
    q = _failures.get(key)
    if not q:
        return 0
    while q and now - q[0] > LOGIN_WINDOW:
        q.popleft()
    return len(q)


def _keys(request: Request, username: str) -> tuple:
    ip = client_ip(request)
    return (ip, (username or "").lower()), (ip,)


def check_login_allowed(request: Request, username: str = ""):
    now = time.monotonic()
    if len(_failures) > 1000:
        _prune(now)
    pair, addr = _keys(request, username)
    if _recent(pair, now) >= LOGIN_MAX_FAILURES or _recent(addr, now) >= LOGIN_MAX_FAILURES_PER_ADDRESS:
        raise HTTPException(429, "Too many failed logins, try again later")


def record_login_failure(request: Request, username: str = ""):
    now = time.monotonic()
    for key in _keys(request, username):
        _failures[key].append(now)


def clear_login_failures(request: Request, username: str = ""):
    pair, _ = _keys(request, username)
    _failures.pop(pair, None)
