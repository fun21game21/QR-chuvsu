"""Browser capability, CSRF, fingerprint and geographic checks; no user accounts."""

import hashlib
import hmac
import json
import math
import os
import secrets
from uuid import UUID

from fastapi import Header, HTTPException, Request

from app.config import Settings

COOKIE = "qr_device"


def get_secret(settings: Settings) -> str:
    if settings.app_secret:
        return settings.app_secret
    path = settings.secret_file
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    secret = path.read_text().strip()
    if len(secret) < 32:
        raise RuntimeError("Secret file is empty or invalid")
    return secret


def signature(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def sign_device(secret: str, device: UUID) -> str:
    return f"{device}.{signature(secret, 'device:' + str(device))}"


def read_device(secret: str, value: str) -> UUID | None:
    try:
        device, mac = value.split(".", 1)
        uid = UUID(device)
        if hmac.compare_digest(mac.encode(), signature(secret, "device:" + str(uid)).encode()):
            return uid
    except (ValueError, AttributeError):
        pass
    return None


def owner_hash(request: Request) -> str:
    return hashlib.sha256(f"teacher:{request.state.device}".encode()).hexdigest()


def csrf_token(request: Request) -> str:
    return signature(request.app.state.secret, "csrf:" + str(request.state.device))


def require_csrf(request: Request, x_csrf_token: str | None = Header(default=None)):
    token = x_csrf_token or ""
    if not request.state.existing_device or not hmac.compare_digest(
        token.encode(), csrf_token(request).encode()
    ):
        raise HTTPException(403, "Обновите страницу и повторите действие")
    origin = request.headers.get("origin")
    if origin and origin != request.app.state.settings.public_base_url:
        raise HTTPException(403, "Недопустимый источник запроса")


def fingerprint_hash(fingerprint) -> str | None:
    if fingerprint is None:
        return None
    payload = fingerprint.model_dump()
    # Orientation must not change a device's fingerprint.
    payload["screen_width"], payload["screen_height"] = sorted(
        (payload["screen_width"], payload["screen_height"])
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def client_ip(request: Request) -> str:
    # Uvicorn only trusts the dedicated Nginx address. Never read arbitrary XFF here.
    return request.client.host


async def allow_ip(conn, request: Request) -> bool:
    settings = request.app.state.settings
    hits = await conn.fetchval(
        """
        INSERT INTO ip_rate_limits(ip_address, window_start, hits)
        VALUES($1::inet, clock_timestamp(), 1)
        ON CONFLICT(ip_address) DO UPDATE SET
            hits = CASE WHEN ip_rate_limits.window_start <
                clock_timestamp() - $2 * interval '1 second' THEN 1
                ELSE LEAST(ip_rate_limits.hits, 2147483646) + 1 END,
            window_start = CASE WHEN ip_rate_limits.window_start <
                clock_timestamp() - $2 * interval '1 second' THEN clock_timestamp()
                ELSE ip_rate_limits.window_start END
        RETURNING hits
    """,
        client_ip(request),
        settings.rate_window_seconds,
    )
    # Bound stale IP history without keeping a background scheduler.
    await conn.execute("DELETE FROM ip_rate_limits WHERE window_start < now() - interval '1 day'")
    return hits <= settings.ip_rate_limit


async def owned_session(request: Request, session_id: UUID, conn=None):
    db = conn or request.app.state.pool
    row = await db.fetchrow(
        "SELECT * FROM sessions WHERE id=$1 AND owner_hash=$2", session_id, owner_hash(request)
    )
    if row is None:
        raise HTTPException(404, "Сессия не найдена в этом браузере преподавателя")
    return row
