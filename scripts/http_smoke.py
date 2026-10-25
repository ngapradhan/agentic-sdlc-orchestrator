"""Actual loopback HTTP smoke test with an isolated server and ephemeral credentials."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main() -> None:
    Path("work").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="http-smoke-", dir="work") as temporary:
        directory = Path(temporary).resolve()
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        environment = {
            **os.environ,
            "SHORTENER_DB": f"sqlite:///{directory / 'service.sqlite'}",
            "SHORTENER_PORT": str(port),
        }
        # Ensure the tested startup path creates its own local credential file.
        environment.pop("SHORTENER_API_KEY", None)
        with (directory / "server.log").open("w") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "shortener"],
                cwd=directory,
                env=environment,
                stdout=log,
                stderr=log,
            )
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            health = client.get("/health")
                            if health.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError("HTTP server failed to start; inspect smoke log")
                        time.sleep(0.05)
                    key_file = directory / "work" / "local-api-key"
                    assert key_file.stat().st_mode & 0o777 == 0o600
                    headers = {"X-API-Key": key_file.read_text()}
                    created = client.post(
                        "/api/v1/urls", headers=headers, json={"url": "https://example.com"}
                    )
                    assert created.status_code == 201, created.text
                    code = created.json()["code"]
                    assert client.get("/" + code, follow_redirects=False).status_code == 302
                    assert (
                        client.get(f"/api/v1/urls/{code}/stats", headers=headers).json()["clicks"]
                        == 1
                    )
                    assert client.delete(f"/api/v1/urls/{code}", headers=headers).status_code == 204
                    assert client.get("/" + code).status_code == 410
                    assert client.get("/docs").status_code == 200
                    print(
                        json.dumps(
                            {
                                "http_smoke": "PASSED",
                                "health": 200,
                                "create": 201,
                                "resolve": 302,
                                "stats_clicks": 1,
                                "delete": 204,
                                "deleted_resolve": 410,
                                "credential_permissions": "0600",
                            }
                        )
                    )
            finally:
                process.terminate()
                process.wait(timeout=5)
                log.flush()
                evidence = Path("runs/evidence")
                evidence.mkdir(parents=True, exist_ok=True)
                (evidence / f"http-server-{time.time_ns()}.log").write_text(
                    (directory / "server.log").read_text()
                )


if __name__ == "__main__":
    main()
