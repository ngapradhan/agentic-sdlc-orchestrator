"""API integration tests use real Alembic migrations and isolated file databases."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

import shortener.app as application
from shortener.app import Settings, create_app
from shortener.database import connect, migrate
from shortener.models import Click


@pytest.fixture
def service(tmp_path: Path):
    keys = (secrets.token_urlsafe(32), secrets.token_urlsafe(32))
    now = [1800000000.0]
    settings = Settings(f"sqlite:///{tmp_path / 'service.sqlite'}", keys, rate_limit=1000)
    app = create_app(settings, clock=lambda: now[0])
    with TestClient(app) as client:
        yield client, {"X-API-Key": keys[0]}, settings, now
    app.state.engine.dispose()


def create(client, headers, **kwargs):
    return client.post(
        "/api/v1/urls", headers=headers, json={"url": "https://example.com/path", **kwargs}
    )


def test_create_resolve_stats_delete(service) -> None:
    client, headers, settings, now = service
    response = create(client, headers)
    assert response.status_code == 201, response.text
    code = response.json()["code"]
    assert len(code) == 8 and code.isalnum()
    redirect = client.get("/" + code, follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://example.com/path"
    assert redirect.headers["cache-control"] == "no-store"
    stats = client.get(f"/api/v1/urls/{code}/stats", headers=headers).json()
    assert stats["clicks"] == 1 and stats["last_clicked_at"] == now[0]
    with Session(client.app.state.engine) as session:
        assert len(session.scalars(select(Click)).all()) == 1
    assert client.delete(f"/api/v1/urls/{code}", headers=headers).status_code == 204
    assert client.get("/" + code, follow_redirects=False).status_code == 410
    assert client.get(f"/api/v1/urls/{code}/stats", headers=headers).json()["clicks"] == 1
    assert client.get(f"/api/v1/urls/{code}/stats", headers=headers).json()["deleted"] is True


def test_alias_duplicate_and_missing(service) -> None:
    client, headers, *_ = service
    assert create(client, headers, alias="my-link").status_code == 201
    assert create(client, headers, alias="my-link").status_code == 409
    assert client.get("/missing").status_code == 404
    assert client.get("/api/v1/urls/missing/stats", headers=headers).status_code == 404
    assert client.delete("/api/v1/urls/missing", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "alias",
    [
        "../escape",
        "a/b",
        "health",
        "docs",
        "redoc",
        "api",
        "a",
        "x" * 65,
        "<script>",
        "white space",
    ],
)
def test_alias_validation(service, alias) -> None:
    client, headers, *_ = service
    assert create(client, headers, alias=alias).status_code == 400


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "ftp://example.com",
        "http://127.0.0.1",
        "http://[::1]",
        "http://10.0.0.1",
        "http://169.254.169.254/latest",
        "https://user:password@example.com",
        "https://example.com\r\nX-Injected: true",
        "http://localhost",
        "http://service.internal",
        "http://2130706433",
        "http://127.1",
        "https://example.com:99999",
        "https://example.com/\\evil",
        "https://-invalid.example",
        "https://a..example",
        "",
        "https://example.com/a b",
    ],
)
def test_unsafe_urls_rejected(service, url) -> None:
    client, headers, *_ = service
    assert create(client, headers, url=url).status_code == 400


def test_expiry_and_permanent(service) -> None:
    client, headers, settings, now = service
    expiry = datetime.fromtimestamp(now[0] + 10, UTC).isoformat()
    code = create(client, headers, expires_at=expiry).json()["code"]
    assert client.get("/" + code, follow_redirects=False).status_code == 302
    now[0] += 11
    assert client.get("/" + code, follow_redirects=False).status_code == 410
    expired = datetime.fromtimestamp(now[0] - 10, UTC).isoformat()
    assert create(client, headers, expires_at=expired).status_code == 400
    assert create(client, headers, expires_at="2035-01-01T00:00:00").status_code == 400
    permanent = create(client, headers, permanent=True).json()["code"]
    assert client.get("/" + permanent, follow_redirects=False).status_code == 301


def test_authentication_and_owner_isolation(service) -> None:
    client, headers, settings, _ = service
    assert create(client, {}).status_code == 401
    assert create(client, {"X-API-Key": "invalid"}).status_code == 401
    code = create(client, headers).json()["code"]
    other = {"X-API-Key": settings.api_keys[1]}
    assert client.get(f"/api/v1/urls/{code}/stats").status_code == 401
    assert client.delete(f"/api/v1/urls/{code}").status_code == 401
    assert client.get(f"/api/v1/urls/{code}/stats", headers=other).status_code == 404
    assert client.delete(f"/api/v1/urls/{code}", headers=other).status_code == 404
    assert client.get("/" + code, follow_redirects=False).status_code == 302


def test_rate_limit_per_authenticated_key_persists(tmp_path: Path) -> None:
    keys = (secrets.token_urlsafe(32), secrets.token_urlsafe(32))
    settings = Settings(f"sqlite:///{tmp_path / 'rate.sqlite'}", keys, rate_limit=2)
    now = [1800000000.0]
    first = create_app(settings, lambda: now[0])
    with TestClient(first) as client:
        for _ in range(2):
            assert create(client, {"X-API-Key": keys[0]}).status_code == 201
        limited = create(client, {"X-API-Key": keys[0], "X-Forwarded-For": "8.8.8.8"})
        assert limited.status_code == 429 and "retry-after" in limited.headers
        assert create(client, {"X-API-Key": keys[1]}).status_code == 201
    second = create_app(settings, lambda: now[0])
    with TestClient(second) as client:
        assert create(client, {"X-API-Key": keys[0]}).status_code == 429
        now[0] += 60
        assert create(client, {"X-API-Key": keys[0]}).status_code == 201
    first.state.engine.dispose()
    second.state.engine.dispose()


def test_database_persistence_and_health(service) -> None:
    client, headers, settings, now = service
    code = create(client, headers).json()["code"]
    other = create_app(settings, lambda: now[0])
    with TestClient(other) as restarted:
        assert restarted.get("/health").json() == {"status": "ok"}
        assert restarted.get("/" + code, follow_redirects=False).status_code == 302
        document = restarted.get("/openapi.json").json()
        assert document["openapi"].startswith("3.1.")
        assert document["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
        assert restarted.get("/docs").status_code == 200
    other.state.engine.dispose()


def test_collision_retry_and_exhaustion(service, monkeypatch) -> None:
    client, headers, *_ = service
    assert create(client, headers, alias="samecode").status_code == 201
    codes = iter(["samecode", "unique88"])
    monkeypatch.setattr(application, "new_code", lambda: next(codes))
    assert create(client, headers).json()["code"] == "unique88"
    monkeypatch.setattr(application, "new_code", lambda: "samecode")
    assert create(client, headers).status_code == 503


def test_parallel_clicks_are_atomic(service) -> None:
    client, headers, *_ = service
    code = create(client, headers).json()["code"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(
            pool.map(
                lambda _: client.get("/" + code, follow_redirects=False).status_code, range(12)
            )
        )
    assert statuses == [302] * 12
    assert client.get(f"/api/v1/urls/{code}/stats", headers=headers).json()["clicks"] == 12


def test_migration_rollback_and_reupgrade(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migration.sqlite'}"
    migrate(url)
    engine = connect(url)
    assert {"links", "clicks", "rate_windows"} <= set(inspect(engine).get_table_names())
    migrate(url, "base", downgrade=True)
    assert "links" not in inspect(engine).get_table_names()
    migrate(url)
    assert "links" in inspect(engine).get_table_names()
    engine.dispose()


def test_storage_failure_safe_error(service) -> None:
    client, headers, *_ = service
    with client.app.state.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE links")
    response = create(client, headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "Storage temporarily unavailable"}
    assert "SQL" not in response.text


def test_invalid_settings_and_unknown_fields(tmp_path: Path, service) -> None:
    with pytest.raises(ValueError):
        create_app(Settings(f"sqlite:///{tmp_path / 'bad.sqlite'}", ("short",)))
    client, headers, *_ = service
    assert create(client, headers, unknown="not allowed").status_code == 400
