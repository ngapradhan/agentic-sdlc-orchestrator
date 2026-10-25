"""Local-only server. A generated API key is written to a mode-0600 file, never logged."""

import os
import secrets
from pathlib import Path

import uvicorn

from shortener.app import Settings, create_app


def main() -> None:
    work = Path("work")
    work.mkdir(exist_ok=True)
    key_file = work / "local-api-key"
    supplied = os.environ.get("SHORTENER_API_KEY")
    if not supplied:
        if not key_file.exists():
            descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(secrets.token_urlsafe(32))
        supplied = key_file.read_text().strip()
    app = create_app(
        Settings(
            database_url=os.environ.get("SHORTENER_DB", "sqlite:///work/service.sqlite"),
            api_keys=(supplied,),
        )
    )
    uvicorn.run(
        app, host="127.0.0.1", port=int(os.environ.get("SHORTENER_PORT", "8000")), access_log=False
    )


if __name__ == "__main__":
    main()
