"""Admin panel veb-ilovasi (FastAPI, serverda chiziladigan sahifalar)."""

import csv
import io
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from babel.dates import format_date, format_datetime
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from golli.admin import queries
from golli.admin.auth import LoginThrottle, new_csrf_token, verify_password
from golli.config import Settings
from golli.db.models import InviteLink
from golli.services.team_names import TeamNames

logger = logging.getLogger(__name__)

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
LANG_NAMES = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English", None: "Tanlamagan"}
SESSION_MAX_AGE = 7 * 24 * 3600

# Bot username'ini oluvchi: havolalar t.me/<username>?start=<kod> ko'rinishida yasaladi.
BotUsername = Callable[[], Awaitable[str]]


def create_app(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bot_username: BotUsername,
    *,
    secure_cookies: bool = True,
) -> FastAPI:
    tz = settings.tz
    names = TeamNames()
    throttle = LoginThrottle()
    password_hash = settings.admin_password_hash.get_secret_value()
    cached_username: dict[str, str] = {}

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_secret.get_secret_value(),
        session_cookie="golli_admin",
        max_age=SESSION_MAX_AGE,
        same_site="strict",
        https_only=secure_cookies,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        return response

    # --- yordamchilar

    async def get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    Session = Annotated[AsyncSession, Depends(get_session)]

    def require_login(request: Request) -> str:
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        return user

    Admin = Annotated[str, Depends(require_login)]

    def csrf_token(request: Request) -> str:
        token = request.session.get("csrf")
        if not token:
            token = request.session["csrf"] = new_csrf_token()
        return token

    def check_csrf(request: Request, token: str) -> None:
        if not token or token != request.session.get("csrf"):
            raise HTTPException(status_code=400, detail="Sahifa eskirgan, qayta urinib ko'ring.")

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def local(moment: datetime | None, pattern: str = "dd.MM.yyyy HH:mm") -> str:
        if moment is None:
            return "—"
        return format_datetime(moment.astimezone(tz), pattern, locale="uz")

    def ago(moment: datetime | None, now: datetime) -> str:
        if moment is None:
            return "hech qachon"
        seconds = int((now - moment).total_seconds())
        if seconds < 60:
            return "hozirgina"
        if seconds < 3600:
            return f"{seconds // 60} daqiqa oldin"
        if seconds < 86400:
            return f"{seconds // 3600} soat oldin"
        return f"{seconds // 86400} kun oldin"

    async def username() -> str:
        if "value" not in cached_username:
            cached_username["value"] = await bot_username()
        return cached_username["value"]

    def render(request: Request, template: str, **context) -> HTMLResponse:
        context.update(
            request=request,
            csrf=csrf_token(request),
            admin=request.session.get("user"),
            local=local,
            # 1284 -> "1 284": katta sonlar xonalarga ajratiladi.
            num=lambda value: f"{value:,}".replace(",", "\u00a0"),
            local_date=lambda day: format_date(day, "d-MMM", locale="uz"),
            sources=queries.SOURCES,
            lang_names=LANG_NAMES,
            club=lambda name: names.get(name, "uz"),
        )
        return TEMPLATES.TemplateResponse(request, template, context)

    # --- kirish

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if request.session.get("user"):
            return RedirectResponse("/", status_code=303)
        return render(request, "login.html", error=None)

    @app.post("/login", response_class=HTMLResponse)
    async def login(
        request: Request,
        username_: Annotated[str, Form(alias="username")],
        password: Annotated[str, Form()],
        csrf: Annotated[str, Form()] = "",
    ):
        check_csrf(request, csrf)
        ip = client_ip(request)
        if throttle.blocked(ip):
            return render(
                request,
                "login.html",
                error="Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring.",
            )
        valid = (
            bool(password_hash)
            and username_ == settings.admin_username
            and verify_password(password, password_hash)
        )
        if not valid:
            throttle.failed(ip)
            logger.warning("Admin panel: noto'g'ri kirish urinishi (%s)", ip)
            return render(request, "login.html", error="Login yoki parol noto'g'ri.")
        throttle.succeeded(ip)
        request.session.clear()
        request.session["user"] = username_
        request.session["csrf"] = new_csrf_token()
        return RedirectResponse("/", status_code=303)

    @app.post("/logout")
    async def logout(request: Request, csrf: Annotated[str, Form()] = ""):
        check_csrf(request, csrf)
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    # --- bosh sahifa

    def read_filters(request: Request) -> queries.UserFilter:
        params = request.query_params
        sort = params.get("sort", "new")
        status = params.get("status", "all")
        return queries.UserFilter(
            query=params.get("q", "")[:64],
            sort=sort if sort in ("new", "active") else "new",
            status=status if status in ("all", "active", "blocked") else "all",
            source=params.get("source", "")[:20],
        )

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request, _: Admin, session: Session):
        now = datetime.now(UTC)
        filters = read_filters(request)
        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            page = 1
        users, total = await queries.load_users(session, filters, now, page)
        pages = max(1, -(-total // queries.PAGE_SIZE))

        def url(**changes) -> str:
            params = {
                "q": filters.query,
                "sort": filters.sort,
                "status": filters.status,
                "source": filters.source,
                "page": page,
            }
            params.update(changes)
            return "?" + urlencode({k: v for k, v in params.items() if v not in ("", None)})

        days = await queries.new_users_by_day(session, now, tz)
        breakdown = await queries.source_breakdown(session)
        return render(
            request,
            "dashboard.html",
            kpi=await queries.load_kpi(session, now, tz),
            users=users,
            total=total,
            page=page,
            pages=pages,
            filters=filters,
            url=url,
            ago=lambda moment: ago(moment, now),
            now=now,
            days=days,
            days_max=max((count for _, count in days), default=0),
            top_clubs=await queries.top_clubs(session),
            languages=await queries.languages(session),
            breakdown=breakdown,
            links=await queries.load_links(session, now),
        )

    @app.get("/users.csv")
    async def export_users(request: Request, _: Admin, session: Session):
        now = datetime.now(UTC)
        users, _total = await queries.load_users(session, read_filters(request), now, 1, 100_000)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "ID",
                "Ism",
                "Username",
                "Bot tili",
                "Telegram tili",
                "Manba",
                "Havola",
                "Sevimli klublar",
                "Qo'shilgan",
                "Oxirgi faollik",
                "Holat",
            ]
        )
        for user in users:
            writer.writerow(
                [
                    user.id,
                    user.full_name,
                    f"@{user.username}" if user.username else "",
                    user.lang or "",
                    user.language_code or "",
                    queries.SOURCES.get(user.link_source or "", "Havolasiz"),
                    user.link_name or "",
                    ", ".join(names.get(name, "uz") for name in user.favorites),
                    local(user.created_at),
                    local(user.last_seen_at),
                    "faol" if user.is_active else "bloklagan",
                ]
            )
        filename = f"golli-users-{local(now, 'yyyy-MM-dd')}.csv"
        # BOM: Excel o'zbek/rus harflarini to'g'ri ochishi uchun.
        return Response(
            "﻿" + buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # --- ulashish havolalari

    @app.get("/links", response_class=HTMLResponse)
    async def links_page(request: Request, _: Admin, session: Session):
        now = datetime.now(UTC)
        return render(
            request,
            "links.html",
            links=await queries.load_links(session, now),
            bot=await username(),
            created=request.query_params.get("created"),
            error=None,
        )

    @app.post("/links")
    async def create_link(
        request: Request,
        _: Admin,
        session: Session,
        name: Annotated[str, Form()],
        source: Annotated[str, Form()],
        csrf: Annotated[str, Form()] = "",
    ):
        check_csrf(request, csrf)
        name = name.strip()[:128]
        if not name or source not in queries.SOURCES:
            return render(
                request,
                "links.html",
                links=await queries.load_links(session, datetime.now(UTC)),
                bot=await username(),
                created=None,
                error="Havola nomini yozing va manbani tanlang.",
            )
        for _attempt in range(5):
            code = queries.new_link_code(source)
            session.add(InviteLink(code=code, name=name, source=source))
            try:
                await session.commit()
                break
            except IntegrityError:
                await session.rollback()
        return RedirectResponse(f"/links?created={code}", status_code=303)

    @app.post("/links/{link_id}/delete")
    async def delete_link(
        request: Request,
        link_id: int,
        _: Admin,
        session: Session,
        csrf: Annotated[str, Form()] = "",
    ):
        check_csrf(request, csrf)
        await session.execute(delete(InviteLink).where(InviteLink.id == link_id))
        await session.commit()
        return RedirectResponse("/links", status_code=303)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
