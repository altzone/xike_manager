import asyncio
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
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(key)
        os.chmod(path, 0o600)
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
def create_token(user_id: int, username: str, role: str, scope: str = "api",
                 expires: timedelta = timedelta(hours=ACCESS_TOKEN_EXPIRE)) -> str:
    return jwt.encode(
        {"sub": str(user_id), "username": username, "role": role, "scope": scope,
         "exp": datetime.now(timezone.utc) + expires},
        SECRET_KEY, algorithm=ALGORITHM
    )


def create_stream_token(user: dict) -> str:
    return create_token(int(user["sub"]), user["username"], user["role"], scope="stream",
                        expires=timedelta(minutes=STREAM_TOKEN_EXPIRE))


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
        cursor = await db.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account no longer exists")
    return {"sub": str(row["id"]), "username": row["username"], "role": row["role"]}


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return await load_user(decode_token(credentials.credentials))


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user


# ── Login throttling (per client address, failures only) ──
LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW = 600  # seconds
_failures: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def check_login_allowed(request: Request):
    ip = client_ip(request)
    now = time.monotonic()
    q = _failures[ip]
    while q and now - q[0] > LOGIN_WINDOW:
        q.popleft()
    if len(q) >= LOGIN_MAX_FAILURES:
        raise HTTPException(429, "Too many failed logins, try again later")


def record_login_failure(request: Request):
    _failures[client_ip(request)].append(time.monotonic())


def clear_login_failures(request: Request):
    _failures.pop(client_ip(request), None)
