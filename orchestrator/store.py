"""Transactional state plus an append-only, recoverable JSONL event projection.

SQLite is authoritative. Each state transition and its event commit together.
An interrupted projection is reconciled before execution. Corruption fails closed.
S0 intentionally supports one local executor at a time (POSIX flock).
"""

import fcntl
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from orchestrator.validation import Json, canonical, schema_for, validate


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    requirement_hash: Mapped[str] = mapped_column(String)
    dag: Mapped[Json] = mapped_column(JSON)


class Node(Base):
    __tablename__ = "nodes"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    artifact: Mapped[Json | None] = mapped_column(JSON, nullable=True)
    artifact_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    input_hashes: Mapped[Json] = mapped_column(JSON, default=dict)


class AuditEvent(Base):
    __tablename__ = "events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    body: Mapped[Json] = mapped_column(JSON)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.root / 'state.sqlite'}")

        @event.listens_for(self.engine, "connect")
        def configure(connection: Any, _: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")

        Base.metadata.create_all(self.engine)

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        with (self.root / ".executor.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Another executor holds the workspace lock") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)

    def run_dir(self, run_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid run ID")
        return self.root / run_id

    def get_run(self, run_id: str) -> Json:
        self.run_dir(run_id)
        with self.session() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise ValueError("Unknown run")
            nodes = session.scalars(select(Node).where(Node.run_id == run_id)).all()
            return {
                "run_id": run.id,
                "status": run.status,
                "requirement_hash": run.requirement_hash,
                "dag": run.dag,
                "nodes": [
                    {
                        "id": n.id,
                        "status": n.status,
                        "attempts": n.attempts,
                        "artifact_hash": n.artifact_hash,
                        "input_hashes": n.input_hashes,
                    }
                    for n in nodes
                ],
            }

    def events(self, run_id: str) -> list[Json]:
        self.get_run(run_id)
        with self.session() as session:
            return list(
                session.scalars(
                    select(AuditEvent.body)
                    .where(AuditEvent.run_id == run_id)
                    .order_by(AuditEvent.seq)
                )
            )

    def sync_files(self, run_id: str) -> None:
        """Append missing committed events; never rewrite existing event bytes."""
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True, exist_ok=True)
        expected = self.events(run_id)
        path = directory / "events.jsonl"
        actual: list[Json] = []
        if path.exists():
            data = path.read_bytes()
            if data and not data.endswith(b"\n"):
                raise ValueError("Incomplete JSONL tail; manual recovery required (S0)")
            actual = [json.loads(line) for line in data.splitlines()]
        if actual != expected[: len(actual)]:
            raise ValueError("Audit projection differs from committed events")
        with path.open("a") as handle:
            for item in expected[len(actual) :]:
                validate(item, schema_for("event"))
                handle.write(canonical(item) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Artifacts are projections too: replace atomically from committed state.
        with self.session() as session:
            for node in session.scalars(select(Node).where(Node.run_id == run_id)):
                if node.artifact is not None:
                    validate(node.artifact, schema_for(node.id))
                    self.write_json(directory / f"{node.id}.json", node.artifact)
            run = session.get(Run, run_id)
            assert run is not None
            self.write_json(directory / "dag.json", run.dag)

    @staticmethod
    def write_json(path: Path, value: Any) -> None:
        temporary = path.with_suffix(".tmp")
        with temporary.open("w") as handle:
            handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
