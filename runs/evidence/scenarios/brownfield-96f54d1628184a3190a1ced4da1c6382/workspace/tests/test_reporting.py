import secrets
from fastapi.testclient import TestClient
from shortener.app import Settings, create_app

def test_daily_reporting_and_owner_isolation(tmp_path):
    keys = (secrets.token_urlsafe(32), secrets.token_urlsafe(32))
    app = create_app(Settings(f"sqlite:///{tmp_path / 'report.sqlite'}", keys))
    with TestClient(app) as client:
        h = {"X-API-Key": keys[0]}
        created = client.post('/api/v1/urls', headers=h, json={"url":"https://example.com"})
        assert created.status_code == 201
        code = created.json()['code']
        path = f'/api/v1/urls/{code}/report'
        assert client.get(path, headers=h).json()['total'] == 0
        for _ in range(2):
            assert client.get('/'+code, follow_redirects=False).status_code == 302
        response = client.get(path, headers=h)
        assert response.status_code == 200
        assert response.json()['total'] == 2
        assert sum(response.json()['daily'].values()) == 2
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-API-Key":keys[1]}).status_code == 404
    app.state.engine.dispose()
