"""Executable abuse/authorization regressions. No claim of a full penetration test."""

import secrets

import pytest
from fastapi.testclient import TestClient

from shortener.app import Settings, create_app


@pytest.fixture
def api(tmp_path):
    key = secrets.token_urlsafe(32)
    app = create_app(Settings(f"sqlite:///{tmp_path / 'security.sqlite'}", (key,)))
    with TestClient(app) as client:
        yield client, {"X-API-Key": key}
    app.state.engine.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]",
        "https://user:password@example.com",
        "https://example.com\r\nLocation:evil",
    ],
)
def test_redirect_input_abuse(api, url):
    client, headers = api
    assert client.post("/api/v1/urls", headers=headers, json={"url": url}).status_code == 400


def test_management_requires_auth_and_errors_do_not_echo_tokens(api):
    client, headers = api
    assert client.post("/api/v1/urls", json={"url": "https://example.com"}).status_code == 401
    assert client.delete("/api/v1/urls/anything").status_code == 401
    response = client.post(
        "/api/v1/urls",
        headers=headers,
        json={"url": "https://example.com", "unexpected": "sensitive-input"},
    )
    assert response.status_code == 400
    assert "sensitive-input" not in response.text
    assert headers["X-API-Key"] not in response.text


def test_alias_path_traversal_and_header_injection(api):
    client, headers = api
    for alias in ["../../etc/passwd", "bad\r\nheader", "<script>"]:
        assert (
            client.post(
                "/api/v1/urls", headers=headers, json={"url": "https://example.com", "alias": alias}
            ).status_code
            == 400
        )
