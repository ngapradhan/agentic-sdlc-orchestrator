"""Scoped local tools. This is a trusted-code sandbox, not an OS security boundary."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from orchestrator.validation import Json, digest


class PolicyError(ValueError):
    pass


class Tools:
    def __init__(self, workspace: Path, policy: Json, evidence: Path) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.allowed_writes: set[str] | None = None
        self.policy = policy
        self.evidence = evidence
        evidence.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        parts = Path(relative).parts
        target = (self.workspace / relative).resolve()
        if (
            not relative
            or Path(relative).is_absolute()
            or ".." in parts
            or any(p in {".git", ".env", ".venv"} for p in parts)
            or not target.is_relative_to(self.workspace)
        ):
            raise PolicyError("Path outside allowed workspace")
        return target

    def write(self, relative: str, content: str) -> Json:
        target = self.path(relative)
        if self.allowed_writes is not None and relative not in self.allowed_writes:
            raise PolicyError("Write not declared by task role")
        if re.search(r"(?:sk-[A-Za-z0-9]{16,}|-----BEGIN .*PRIVATE KEY-----)", content):
            raise PolicyError("Secret-like material rejected")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {"path": relative, "sha256": digest(content)}

    def snapshot(self, paths: list[str]) -> dict[str, bytes | None]:
        result: dict[str, bytes | None] = {}
        for relative in paths:
            path = self.path(relative)
            if path.is_dir():
                raise PolicyError("Snapshot requires explicit files")
            result[relative] = path.read_bytes() if path.exists() else None
        return result

    def restore(self, snapshot: dict[str, bytes | None]) -> None:
        for relative, value in snapshot.items():
            path = self.path(relative)
            if value is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
        for relative, value in snapshot.items():
            path = self.path(relative)
            actual = path.read_bytes() if path.exists() else None
            if actual != value:
                raise PolicyError("Rollback verification failed")

    def command(self, arguments: list[str], label: str) -> Json:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", label):
            raise PolicyError("Invalid command label")
        if (
            len(arguments) < 3
            or arguments[0] != sys.executable
            or arguments[1] != "-m"
            or arguments[2] not in self.policy["commands"]["python_modules"]
        ):
            raise PolicyError("Command not allowlisted")
        if any(".." in Path(arg).parts or Path(arg).is_absolute() for arg in arguments[3:]):
            raise PolicyError("Command arguments must remain relative")
        environment = {
            key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TMPDIR") if key in os.environ
        }
        environment.update(
            {
                "PYTHONPATH": str(self.workspace),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "NO_PROXY": "*",
            }
        )
        started = datetime.now(UTC).isoformat()
        label = f"{label}-{time.time_ns()}"
        result = subprocess.run(
            arguments,
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=self.policy["budgets"]["command_seconds"],
        )
        # Commands are trusted local tests; output is never allowed to echo credentials.
        output = re.sub(
            r"(?i)(api[_-]?key|authorization)(\s*[=:]\s*)\S+",
            r"\1\2[REDACTED]",
            result.stdout + result.stderr,
        )
        log = self.evidence / f"{label}.log"
        log.write_text(output)
        record = {
            "started": started,
            "cwd": str(self.workspace),
            "command": arguments,
            "exit_code": result.returncode,
            "output": str(log),
            "output_excerpt": output[-3000:],
        }
        (self.evidence / f"{label}.json").write_text(__import__("json").dumps(record, indent=2))
        if result.returncode:
            raise PolicyError(f"Validation command failed; evidence {label}")
        return record

    def copy_files(self, source: Path, paths: list[str]) -> list[Json]:
        # Source is the fixed, trusted submission checkout; writes are always sandboxed.
        result = []
        for relative in paths:
            original = (source / relative).resolve()
            if not original.is_relative_to(source.resolve()) or original.is_symlink():
                raise PolicyError("Invalid source path")
            result.append(self.write(relative, original.read_text()))
        return result


def load_policy(path: Path) -> Json:
    with path.open() as stream:
        result: dict[str, Any] = yaml.safe_load(stream)
    if result.get("version") != 2 or result["network"]["default"] != "deny":
        raise PolicyError("Unsupported policy")
    return result
