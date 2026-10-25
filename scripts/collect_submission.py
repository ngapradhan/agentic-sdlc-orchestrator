"""Copy verified scenario evidence into Git-tracked portable submission artifacts."""

import hashlib
import json
import shutil
from pathlib import Path


def main() -> None:
    root = Path.cwd()
    index = {"scenarios": {}, "files": {}}
    for scenario in ["greenfield", "brownfield", "ambiguous"]:
        record = json.loads((root / f"runs/evidence/latest-{scenario}.json").read_text())
        if record["status"] != "PASSED":
            raise ValueError("Cannot package an unpassed scenario")
        source = root / "runs" / record["run_id"]
        if not source.is_dir():
            raise ValueError("Run evidence is missing")
        destination = root / "runs/evidence/scenarios" / f"{scenario}-{record['run_id']}"
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.sqlite*"),
        )
        index["scenarios"][scenario] = {
            "run_id": record["run_id"],
            "status": record["status"],
            "path": str(destination.relative_to(root)),
        }
        for path in destination.rglob("*"):
            if path.is_file():
                index["files"][str(path.relative_to(root))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    Path("runs/evidence/submission-index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(
        json.dumps(
            {"packaged_scenarios": index["scenarios"], "verified_file_count": len(index["files"])},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
