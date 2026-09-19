from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from app.models import AttendanceCreate, Student
from app.services.attendance import add_manually, check_in
from app.services.security import require_csrf

router = APIRouter(dependencies=[Depends(require_csrf)])


def result_response(result):
    code = 200
    if result["status"] == "rejected":
        code = {
            "invalid_session": 410,
            "duplicate": 409,
            "device_used": 409,
            "fingerprint_used": 409,
            "rate_limit": 429,
        }.get(result["reason"], 422)
    return JSONResponse(result, status_code=code)


@router.post("/api/attendance/{code}")
async def attend(code: Annotated[str, Path(pattern=r"^[0-9]{6}$")], data: AttendanceCreate, request: Request):
    return result_response(await check_in(request, code, data))


@router.post("/api/sessions/{session_id}/manual")
async def manual(session_id: UUID, data: Student, request: Request):
    return result_response(await add_manually(request, session_id, data))
