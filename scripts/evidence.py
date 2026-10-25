"""Capture an explicit command, its exit status and complete output without a shell.

Use only for non-sensitive development commands. This does not sanitize arbitrary
test output, so never pass credentials or confidential input to the child.
"""

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    name, *command = sys.argv[1:]
    if not re.fullmatch(r"[a-z0-9-]+", name) or not command:
        raise SystemExit("Usage: evidence.py safe-name command [args]")
    directory = Path("runs/evidence")
    directory.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    result = subprocess.run(command, capture_output=True, text=True)
    finished = datetime.now(UTC)
    unique = f"{name}-{started.strftime('%Y%m%dT%H%M%S%fZ')}"
    output = result.stdout + result.stderr
    log = directory / f"{unique}.log"
    log.write_text(output)
    metadata = {
        "command": command,
        "cwd": str(Path.cwd()),
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "exit_code": result.returncode,
        "output_path": str(log),
        "output_excerpt": output[-6000:],
    }
    (directory / f"{unique}.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(output, end="")
    print(f"Evidence: {directory / (unique + '.json')}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
