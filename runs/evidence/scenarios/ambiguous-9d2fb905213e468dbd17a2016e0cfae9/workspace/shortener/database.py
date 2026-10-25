from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import Engine, create_engine, event

from alembic import command


def migrate(database_url: str, revision: str = "head", downgrade: bool = False) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    if downgrade:
        command.downgrade(config, revision)
    else:
        command.upgrade(config, revision)


def connect(database_url: str) -> Engine:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Prototype supports file-backed SQLite only")
    engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def configure(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")

    return engine
