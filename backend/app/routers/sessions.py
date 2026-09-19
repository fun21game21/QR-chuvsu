import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.models import CodeInput, SessionCreate
from app.services.campuses import CAMPUSES
from app.services.qr_generator import make_qr
from app.services.security import allow_ip, owned_session, owner_hash, require_csrf

router = APIRouter()


@router.post("/api/sessions", status_code=201, dependencies=[Depends(require_csrf)])
async def create_session(data: SessionCreate, request: Request):
    campus = CAMPUSES[data.campus_id]
    async with request.app.state.pool.acquire() as conn:
        if not await allow_ip(conn, request):
            raise HTTPException(429, "Слишком много запросов")
        for _ in range(20):
            sid = uuid4()
            code = f"{secrets.randbelow(1_000_000):06d}"
            now = datetime.now(timezone.utc)
            qr_path = f"/api/sessions/{sid}/qr.png"
            try:
                await conn.execute(
                    """
                    INSERT INTO sessions(id,title,group_name,session_code,qr_path,latitude,
                        longitude,radius,teacher_name,location_name,owner_hash,created_at,expires_at,campus_id)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                    sid,
                    data.title,
                    data.group_name,
                    code,
                    qr_path,
                    campus.latitude,
                    campus.longitude,
                    data.radius,
                    data.teacher_name,
                    campus.label,
                    owner_hash(request),
                    now,
                    now + timedelta(minutes=data.duration_minutes),
                    campus.id,
                )
                return {
                    "id": str(sid),
                    "session_code": code,
                    "qr_path": qr_path,
                    "teacher_url": f"/teacher/session/{sid}",
                    "student_url": f"/s/{code}",
                }
            except asyncpg.UniqueViolationError:
                continue
        raise HTTPException(503, "Не удалось выделить код сессии. Повторите позже")


@router.post("/api/sessions/resolve", dependencies=[Depends(require_csrf)])
async def resolve_code(data: CodeInput, request: Request):
    async with request.app.state.pool.acquire() as conn:
        if not await allow_ip(conn, request):
            raise HTTPException(429, "Слишком много запросов")
        exists = await conn.fetchval(
            """
            SELECT 1 FROM sessions WHERE session_code=$1 AND active AND expires_at>now()
        """,
            data.code,
        )
    if not exists:
        raise HTTPException(410, "Сессия недействительна")
    return {"student_url": f"/s/{data.code}"}


@router.get("/api/sessions/{session_id}/qr.png")
async def qr_image(session_id: UUID, request: Request):
    session = await owned_session(request, session_id)
    url = request.app.state.settings.public_base_url + "/s/" + session["session_code"]
    return Response(make_qr(url), media_type="image/png")


@router.get("/api/sessions/{session_id}/attendance")
async def journal(session_id: UUID, request: Request):
    await owned_session(request, session_id)
    # Exclude device tokens, fingerprints and IPs from the public-facing journal API.
    rows = await request.app.state.pool.fetch(
        """
        SELECT id,student_name,group_name,status,reason,created_at,distance_m
        FROM attendance WHERE session_id=$1 ORDER BY group_name,name_key,created_at
    """,
        session_id,
    )
    return [dict(row) for row in rows]


@router.post("/api/sessions/{session_id}/close", dependencies=[Depends(require_csrf)])
async def close_session(session_id: UUID, request: Request):
    await owned_session(request, session_id)
    await request.app.state.pool.execute("UPDATE sessions SET active=false WHERE id=$1", session_id)
    return {"message": "Сессия закрыта"}
