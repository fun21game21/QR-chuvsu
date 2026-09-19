import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.database import connect
from app.routers import attendance, export, sessions
from app.services.campuses import CATALOGUE
from app.services.security import (
    COOKIE,
    csrf_token,
    get_secret,
    owned_session,
    owner_hash,
    read_device,
    sign_device,
)

BASE = Path(__file__).parent


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        if settings.public_base_url.startswith("https://") and not settings.cookie_secure:
            raise RuntimeError("Set COOKIE_SECURE=true when using HTTPS")
        app.state.settings = settings
        app.state.secret = get_secret(settings)
        app.state.schedule = json.loads(settings.schedule_file.read_text())
        app.state.pool = await connect(settings.database_url)
        yield
        await app.state.pool.close()

    app = FastAPI(title="QR-CHUVSU v2", version="2.0.0", lifespan=lifespan)
    templates = Jinja2Templates(directory=BASE / "templates")
    templates.env.filters["localtime"] = lambda value: value.astimezone(ZoneInfo(settings.timezone)).strftime(
        "%d.%m.%Y %H:%M:%S"
    )

    @app.middleware("http")
    async def browser_identity(request: Request, call_next):
        device = read_device(app.state.secret, request.cookies.get(COOKIE, ""))
        request.state.existing_device = device is not None
        request.state.device = device or uuid4()
        response = await call_next(request)
        if device is None:
            response.set_cookie(
                COOKIE,
                sign_device(app.state.secret, request.state.device),
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                secure=settings.cookie_secure,
                samesite="lax",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self)"
        if request.url.path not in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            )
        return response

    def render(request, name, **context):
        return templates.TemplateResponse(
            request=request, name=name, context={"csrf": csrf_token(request), **context}
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code)
        response = render(request, "error.html", message=str(exc.detail))
        response.status_code = exc.status_code
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "message": "Проверьте заполнение полей",
                "errors": [
                    {"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()
                ],
            },
            status_code=422,
        )

    @app.get("/health")
    async def health():
        await app.state.pool.fetchval("SELECT 1")
        return {"status": "ok", "database": "ok"}

    @app.get("/")
    async def home(request: Request):
        active = await app.state.pool.fetch(
            """
            SELECT id,title,group_name,expires_at FROM sessions
            WHERE owner_hash=$1 AND active AND expires_at>now() ORDER BY created_at DESC
        """,
            owner_hash(request),
        )
        return render(request, "index.html", active_sessions=active, schedule=app.state.schedule)

    @app.get("/teacher/new")
    async def new_session(request: Request):
        return render(request, "create.html", campuses=CATALOGUE)

    @app.get("/teacher/session/{session_id}")
    async def teacher(request: Request, session_id: UUID):
        session = await owned_session(request, session_id)
        rows = await app.state.pool.fetch(
            """
            SELECT * FROM attendance WHERE session_id=$1 ORDER BY group_name,name_key,created_at
        """,
            session_id,
        )
        accepted = [row for row in rows if row["status"] != "rejected"]
        rejected = [row for row in rows if row["status"] == "rejected"]
        live = session["active"] and session["expires_at"] > datetime.now(timezone.utc)
        return render(
            request,
            "teacher.html",
            session=session,
            accepted=accepted,
            rejected=rejected,
            live=live,
            student_url=settings.public_base_url + "/s/" + session["session_code"],
        )

    @app.get("/s/{code}")
    async def student(request: Request, code: str):
        if len(code) != 6 or not code.isascii() or not code.isdigit():
            raise HTTPException(410, "Сессия недействительна")
        session = await app.state.pool.fetchrow(
            """
            SELECT title,group_name,teacher_name,location_name,session_code,expires_at,radius
            FROM sessions WHERE session_code=$1 AND active AND expires_at>now()
        """,
            code,
        )
        if session is None:
            raise HTTPException(410, "Сессия недействительна")
        return render(request, "student.html", session=session)

    @app.get("/privacy")
    async def privacy(request: Request):
        return render(request, "privacy.html")

    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    app.include_router(sessions.router, tags=["Сессии"])
    app.include_router(attendance.router, tags=["Отметка"])
    app.include_router(export.router, tags=["Excel"])
    return app


app = create_app()
