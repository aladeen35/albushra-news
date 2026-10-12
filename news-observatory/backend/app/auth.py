"""Admin sign-in.

Editors sign in with ADMIN_USERNAME / ADMIN_PASSWORD and receive a signed
session token that expires after SESSION_HOURS. ADMIN_TOKEN, if set, is still
accepted as a bearer token for scripts and automation.

Repeated failed sign-ins from one address are locked out for a while, so the
password cannot be guessed by brute force through the API.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque

from .config import get_settings

SESSION_HOURS = 12
MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60

# Without SECRET_KEY, sessions are signed with a per-process key: they stop
# working on restart, which is safe, merely inconvenient.
_PROCESS_KEY = secrets.token_bytes(32)
_failures: dict[str, deque] = defaultdict(deque)


def _key() -> bytes:
    configured = os.environ.get("SECRET_KEY", "")
    return hashlib.sha256(configured.encode()).digest() if configured else _PROCESS_KEY


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue(username: str) -> tuple[str, int]:
    expires = int(time.time()) + SESSION_HOURS * 3600
    payload = _b64(json.dumps({"u": username, "exp": expires}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}", expires


def verify(token: str) -> str | None:
    try:
        payload, signature = token.split(".", 1)
        expected = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(data.get("exp", 0)) < time.time():
        return None
    return str(data.get("u") or "") or None


def login_enabled() -> bool:
    return bool(get_settings().admin_password)


def locked_out(ip: str) -> bool:
    q = _failures[ip]
    now = time.monotonic()
    while q and now - q[0] > LOCKOUT_SECONDS:
        q.popleft()
    return len(q) >= MAX_FAILURES


def check_credentials(ip: str, username: str, password: str) -> bool:
    settings = get_settings()
    ok = (hmac.compare_digest(username.strip().lower().encode(), settings.admin_username.lower().encode())
          and hmac.compare_digest(password.encode(), settings.admin_password.encode()))
    if ok:
        _failures.pop(ip, None)
    else:
        _failures[ip].append(time.monotonic())
    return ok
