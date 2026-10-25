"""Exercise pause/resume across separate processes; preserve a reviewable trace."""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def cli(*arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "orchestrator.cli", *arguments],
        text=True,
        capture_output=True,
        check=True,
    )
    print(result.stdout, end="")
    return result.stdout


def main() -> None:
    output = cli("run", "--requirement", "Build a URL shortener", "--stop-after", "1")
    run_id = json.loads(output.splitlines()[0])["created_run_id"]
    paused = json.loads(output[output.index("\n") + 1 :])
    assert paused["status"] == "HALTED"
    resumed = json.loads(cli("resume", run_id))
    assert resumed["status"] == "PASSED"
    assert all(node["attempts"] == 1 for node in resumed["nodes"])
    mermaid = cli("trace", run_id, "--format", "mermaid")
    directory = Path("runs") / run_id
    (directory / "dag.mmd").write_text(mermaid)
    (directory / "lineage.json").write_text(cli("lineage", run_id))
    cli("trace", run_id)
    Path("runs/evidence").mkdir(parents=True, exist_ok=True)
    evidence_directory = Path("runs/evidence") / f"bootstrap-{run_id}"
    shutil.copytree(directory, evidence_directory)
    (evidence_directory / "state.json").write_text(json.dumps(resumed, indent=2) + "\n")
    (Path("runs/evidence") / "latest-bootstrap.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": resumed["status"],
                "path": str(directory),
                "evidence_path": str(evidence_directory),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"S0 only: three schema gates passed; run artifacts: {directory}")


if __name__ == "__main__":
    main()
