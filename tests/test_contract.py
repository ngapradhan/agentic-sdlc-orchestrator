"""OpenAPI schema and documented response contracts against the real application."""

import secrets

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from shortener.app import Settings, create_app


def test_openapi_and_actual_response_contract(tmp_path):
    key = secrets.token_urlsafe(32)
    app = create_app(Settings(f"sqlite:///{tmp_path / 'contract.sqlite'}", (key,)))
    with TestClient(app) as client:
        document = client.get("/openapi.json").json()
        assert document["openapi"].startswith("3.1.")
        for path in [
            "/api/v1/urls",
            "/{short_code}",
            "/api/v1/urls/{short_code}/stats",
            "/api/v1/urls/{short_code}",
            "/health",
        ]:
            assert path in document["paths"]
        assert document["paths"]["/api/v1/urls"]["post"]["security"]
        headers = {"X-API-Key": key}
        response = client.post("/api/v1/urls", headers=headers, json={"url": "https://example.com"})
        schema = {
            **document["components"]["schemas"]["LinkView"],
            "components": document["components"],
        }
        Draft202012Validator(schema).validate(response.json())
        code = response.json()["code"]
        stats = client.get(f"/api/v1/urls/{code}/stats", headers=headers)
        Draft202012Validator(document["components"]["schemas"]["StatsView"]).validate(stats.json())
        assert client.get("/" + code, follow_redirects=False).status_code == 302
    app.state.engine.dispose()
