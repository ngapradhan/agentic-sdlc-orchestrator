import secrets
from fastapi.testclient import TestClient
from shortener.app import Settings, create_app

def test_approved_security_scope(tmp_path):
    settings = Settings(f"sqlite:///{tmp_path / 'scope.sqlite'}", (secrets.token_urlsafe(32),))
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get('/health')
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['referrer-policy'] == 'no-referrer'
    app.state.engine.dispose()
