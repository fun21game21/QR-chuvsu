"""Business decisions and SQL live together inside one transaction.

Locking the session row serializes checks with other check-ins and session closure.
Partial unique indexes are a second line of defence against duplicate acceptance.
"""

from fastapi import Request

from app.models import AttendanceCreate, Student, normalized
from app.services.security import allow_ip, client_ip, fingerprint_hash, haversine, owned_session

REASONS = {
    "accepted": "Отметка подтверждена",
    "manual": "Добавлен преподавателем",
    "invalid_session": "Сессия недействительна",
    "duplicate": "Вы уже отметились",
    "device_used": "С этого устройства уже отметился другой студент",
    "fingerprint_used": "Этот браузер уже использован для отметки другого студента",
    "no_location": "Попытка отклонена: геолокация недоступна",
    "outside_zone": "Попытка отклонена: вы вне допустимой зоны",
    "no_fingerprint": "Попытка отклонена: данные браузера недоступны",
    "wrong_group": "Попытка отклонена: группа не соответствует занятию",
    "rate_limit": "Слишком много запросов. Повторите через минуту",
}


async def record(conn, request, session, code, data, reason, fingerprint=None, distance=None):
    status = reason if reason in {"accepted", "manual"} else "rejected"
    await conn.execute(
        """
        INSERT INTO attendance(session_id, student_name, group_name, name_key, group_key,
            device_token, fingerprint, latitude, longitude, ip_address, status, reason,
            distance_m, attempted_code)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::inet,$11,$12,$13,$14)
    """,
        session["id"] if session else None,
        data.student_name,
        data.group_name,
        normalized(data.student_name),
        normalized(data.group_name),
        request.state.device if status != "manual" else None,
        fingerprint,
        getattr(data, "latitude", None),
        getattr(data, "longitude", None),
        client_ip(request),
        status,
        REASONS[reason],
        distance,
        code,
    )
    return {"status": status, "reason": reason, "message": REASONS[reason]}


async def check_in(request: Request, code: str, data: AttendanceCreate):
    async with request.app.state.pool.acquire() as conn, conn.transaction():
        allowed = await allow_ip(conn, request)
        session = await conn.fetchrow("SELECT * FROM sessions WHERE session_code=$1 FOR UPDATE", code)
        fp = fingerprint_hash(data.fingerprint)
        distance = None
        if not allowed:
            reason = "rate_limit"
        elif (
            session is None
            or not session["active"]
            or await conn.fetchval("SELECT clock_timestamp() >= $1::timestamptz", session["expires_at"])
        ):
            reason = "invalid_session"
        elif await conn.fetchval(
            """
            SELECT 1 FROM attendance WHERE session_id=$1 AND name_key=$2 AND group_key=$3
            AND status IN ('accepted', 'manual')
        """,
            session["id"],
            normalized(data.student_name),
            normalized(data.group_name),
        ):
            reason = "duplicate"
        elif normalized(data.group_name) != normalized(session["group_name"]):
            reason = "wrong_group"
        elif await conn.fetchval(
            """
            SELECT 1 FROM attendance WHERE session_id=$1 AND device_token=$2 AND status='accepted'
        """,
            session["id"],
            request.state.device,
        ):
            reason = "device_used"
        elif fp is None:
            reason = "no_fingerprint"
        elif await conn.fetchval(
            """
            SELECT 1 FROM attendance WHERE session_id=$1 AND fingerprint=$2 AND status='accepted'
        """,
            session["id"],
            fp,
        ):
            reason = "fingerprint_used"
        elif data.latitude is None or data.longitude is None:
            reason = "no_location"
        else:
            distance = haversine(session["latitude"], session["longitude"], data.latitude, data.longitude)
            reason = "accepted" if distance <= session["radius"] else "outside_zone"
        return await record(conn, request, session, code, data, reason, fp, distance)


async def add_manually(request: Request, session_id, data: Student):
    async with request.app.state.pool.acquire() as conn, conn.transaction():
        allowed = await allow_ip(conn, request)
        await owned_session(request, session_id, conn)
        session = await conn.fetchrow("SELECT * FROM sessions WHERE id=$1 FOR UPDATE", session_id)
        if not allowed:
            reason = "rate_limit"
        elif not session["active"] or await conn.fetchval(
            "SELECT clock_timestamp() >= $1::timestamptz", session["expires_at"]
        ):
            reason = "invalid_session"
        elif await conn.fetchval(
            """
            SELECT 1 FROM attendance WHERE session_id=$1 AND name_key=$2 AND group_key=$3
            AND status IN ('accepted','manual')
        """,
            session_id,
            normalized(data.student_name),
            normalized(data.group_name),
        ):
            reason = "duplicate"
        else:
            reason = "manual"
        return await record(conn, request, session, session["session_code"], data, reason)
