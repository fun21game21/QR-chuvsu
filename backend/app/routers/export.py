from uuid import UUID

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.services.excel import make_excel
from app.services.security import owned_session

router = APIRouter()


@router.get("/api/sessions/{session_id}/export")
async def export_excel(session_id: UUID, request: Request):
    await owned_session(request, session_id)
    rows = await request.app.state.pool.fetch("SELECT * FROM attendance WHERE session_id=$1", session_id)
    data = await run_in_threadpool(make_excel, rows, request.app.state.settings.timezone)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="QR-CHUVSU-{session_id}.xlsx"'},
    )
