"""Application factory: no startup secrets or database side effects at import time."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
import string
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, text, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from shortener.database import connect, migrate
from shortener.models import Click, Link, RateWindow


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_keys: tuple[str, ...]
    rate_limit: int = 60
    rate_window_seconds: int = 60
    base_url: str = "http://127.0.0.1:8000"


class CreateLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    alias: str | None = Field(default=None, min_length=3, max_length=64)
    expires_at: datetime | None = None
    permanent: bool = False


class LinkView(BaseModel):
    code: str
    short_url: str
    url: str
    expires_at: float | None
    permanent: bool


class StatsView(BaseModel):
    code: str
    clicks: int
    created_at: float
    last_clicked_at: float | None
    expires_at: float | None
    deleted: bool


def validate_destination(destination: str) -> str:
    try:
        parsed = urlsplit(destination)
        hostname = parsed.hostname or ""
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username
            or parsed.password
            or "\\" in destination
            or any(ord(c) < 33 or ord(c) == 127 for c in destination)
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)
        ):
            raise ValueError("Unsafe URL")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            if (
                not re.fullmatch(r"[A-Za-z0-9.-]+", hostname)
                or "." not in hostname
                or hostname.endswith((".local", ".localhost", ".internal", "."))
                or hostname.startswith(".")
                or ".." in hostname
                or hostname.replace(".", "").isdigit()
                or any(
                    not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                    for label in hostname.split(".")
                )
            ):
                raise ValueError("Unsafe hostname") from None
        else:
            if not address.is_global or address.is_multicast:
                raise ValueError("Non-public destination")
        return destination
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Destination must be a public HTTP(S) URL") from None


def new_code() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))


def create_app(settings: Settings, clock: Callable[[], float] = time.time) -> FastAPI:
    if (
        not settings.api_keys
        or any(len(k) < 24 for k in settings.api_keys)
        or settings.rate_limit < 1
        or settings.rate_window_seconds < 1
    ):
        raise ValueError("Strong API keys and positive rate limits required")
    migrate(settings.database_url)
    engine = connect(settings.database_url)
    app = FastAPI(title="Controlled SDLC URL Shortener", version="1.0.0")
    app.state.engine = engine
    app.state.settings = settings
    configured = [hashlib.sha256(key.encode()).hexdigest() for key in settings.api_keys]
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    def principal(key: str | None = Security(api_key_header)) -> str:
        supplied = hashlib.sha256((key or "").encode()).hexdigest()
        if not key or not any(hmac.compare_digest(supplied, expected) for expected in configured):
            raise HTTPException(401, "Valid API key required")
        now = clock()
        bucket = int(now // settings.rate_window_seconds)
        # Persist rate limiting across processes; increment and cleanup atomically.
        with engine.begin() as connection:
            statement = insert(RateWindow).values(principal=supplied, bucket=bucket, count=1)
            count = connection.scalar(
                statement.on_conflict_do_update(
                    index_elements=["principal", "bucket"], set_={"count": RateWindow.count + 1}
                ).returning(RateWindow.count)
            )
            connection.execute(delete(RateWindow).where(RateWindow.bucket < bucket - 1))
        if count is not None and count > settings.rate_limit:
            raise HTTPException(
                429,
                "Rate limit exceeded",
                headers={"Retry-After": str(settings.rate_window_seconds)},
            )
        return supplied

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": "Invalid request fields"})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Storage temporarily unavailable"})

    @app.get("/health")
    def health() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    def owned(session: Session, code: str, owner: str) -> Link:
        link = session.get(Link, code)
        if link is None or not hmac.compare_digest(link.owner_hash, owner):
            raise HTTPException(404, "Link not found")
        return link

    @app.post(
        "/api/v1/urls",
        status_code=201,
        response_model=LinkView,
        responses={
            400: {"description": "Invalid input"},
            401: {"description": "Unauthorized"},
            409: {"description": "Alias exists"},
            429: {"description": "Rate limited"},
        },
    )
    def create(
        body: CreateLink, session: Session = Depends(db), owner: str = Depends(principal)
    ) -> LinkView:
        destination = validate_destination(body.url)
        expiry = body.expires_at.timestamp() if body.expires_at is not None else None
        if (
            expiry is not None
            and body.expires_at is not None
            and (body.expires_at.tzinfo is None or expiry <= clock())
        ):
            raise HTTPException(400, "Expiry must be a future timezone-aware timestamp")
        if body.alias is not None and (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}", body.alias)
            or body.alias.lower() in {"health", "docs", "redoc", "api", "openapi.json"}
        ):
            raise HTTPException(400, "Invalid or reserved alias")
        for _ in range(5):
            code = body.alias or new_code()
            link = Link(
                code=code,
                destination=destination,
                owner_hash=owner,
                created_at=clock(),
                expires_at=expiry,
                permanent=body.permanent,
            )
            session.add(link)
            try:
                session.commit()
                return LinkView(
                    code=code,
                    short_url=f"{settings.base_url}/{code}",
                    url=destination,
                    expires_at=expiry,
                    permanent=body.permanent,
                )
            except IntegrityError:
                session.rollback()
                if body.alias:
                    raise HTTPException(409, "Alias already exists") from None
        raise HTTPException(503, "Code allocation temporarily unavailable")

    @app.get("/api/v1/urls/{short_code}/stats", response_model=StatsView)
    def stats(
        short_code: str, session: Session = Depends(db), owner: str = Depends(principal)
    ) -> StatsView:
        link = owned(session, short_code, owner)
        return StatsView(
            code=link.code,
            clicks=link.clicks,
            created_at=link.created_at,
            last_clicked_at=link.last_clicked_at,
            expires_at=link.expires_at,
            deleted=link.deleted,
        )

    @app.delete("/api/v1/urls/{short_code}", status_code=204)
    def deactivate(
        short_code: str, session: Session = Depends(db), owner: str = Depends(principal)
    ) -> Response:
        link = owned(session, short_code, owner)
        link.deleted = True
        session.commit()
        return Response(status_code=204)

    @app.get(
        "/{short_code}",
        response_class=RedirectResponse,
        responses={
            302: {"description": "Redirect"},
            404: {"description": "Missing"},
            410: {"description": "Expired or deleted"},
        },
    )
    def resolve(short_code: str, session: Session = Depends(db)) -> RedirectResponse:
        now = clock()
        # One serialized write transaction keeps resolve+delete+analytics consistent in SQLite.
        session.execute(text("BEGIN IMMEDIATE"))
        link = session.get(Link, short_code)
        if link is None:
            raise HTTPException(404, "Link not found")
        if link.deleted or (link.expires_at is not None and link.expires_at <= now):
            raise HTTPException(410, "Link is no longer active")
        session.execute(
            update(Link)
            .where(Link.code == short_code)
            .values(clicks=Link.clicks + 1, last_clicked_at=now)
        )
        session.add(Click(code=short_code, timestamp=now))
        destination, status = link.destination, 301 if link.permanent else 302
        session.commit()
        return RedirectResponse(
            destination,
            status_code=status,
            headers={"Cache-Control": "no-store" if status == 302 else "public, max-age=60"},
        )


    @app.get("/api/v1/urls/{short_code}/report")
    def report(short_code: str, session: Session = Depends(db),
               owner: str = Depends(principal)) -> dict[str, object]:
        from shortener.reporting import daily_report
        owned(session, short_code, owner)
        return daily_report(session, short_code)

    return app
