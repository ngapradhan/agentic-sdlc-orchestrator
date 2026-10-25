"""Human console for both preserved S0 and v3 workflows."""

import argparse
import json
import signal
from collections.abc import Sequence
from pathlib import Path

from orchestrator.engine import Engine
from orchestrator.scenarios import REPO, action_registry, demo, new_scenario
from orchestrator.store import Store
from orchestrator.workflow import Workflow


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Offline controlled SDLC orchestrator")
    result.add_argument("--root", type=Path, default=Path("runs"))
    commands = result.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="Default: S0 bootstrap. --scenario selects real SDLC workflow."
    )
    run.add_argument("--requirement")
    run.add_argument("--scenario", choices=["greenfield", "brownfield", "ambiguous"])
    run.add_argument("--stop-after", type=int)
    demos = commands.add_parser("demo", help="Clearly labeled simulated approval decisions")
    demos.add_argument("scenario", choices=["greenfield", "brownfield", "ambiguous"])
    resume = commands.add_parser("resume")
    resume.add_argument("run_id")
    resume.add_argument("--stop-after", type=int)
    for command in [
        "inspect",
        "trace",
        "lineage",
        "metrics",
        "halt",
        "approve",
        "reject",
        "replan",
    ]:
        item = commands.add_parser(command)
        item.add_argument("run_id")
        if command == "trace":
            item.add_argument("--format", choices=["text", "mermaid"], default="text")
        if command == "lineage":
            item.add_argument("--node", default="summary")
        if command in {"approve", "reject"}:
            item.add_argument("task_id", nargs="?")
            item.add_argument("--reviewer")
            item.add_argument("--reason")
            item.add_argument("--demo", action="store_true")
        if command == "replan":
            item.add_argument("task_id")
            item.add_argument("--artifact", type=Path, required=True)
    pending = commands.add_parser("list-pending")
    pending.add_argument("--run-id")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "demo":
        demo(args.scenario, args.root)
        return 0
    # Retain old unsupported-control behavior for S0 callers and the S0 regression suite.
    if args.command == "list-pending" and not args.run_id:
        print(json.dumps({"error": "Unavailable in S0; supply --run-id for v3 workflow"}))
        return 2
    try:
        store = Store(args.root)
        workflow = Workflow(store, action_registry(), REPO / "policy.yaml")
        legacy = Engine(store)
        if args.command == "run":
            if args.stop_after is not None and args.stop_after < 1:
                raise ValueError("stop-after must be positive")
            if args.scenario:
                run_id = new_scenario(workflow, args.scenario, args.requirement)
                print(
                    json.dumps({"created_run_id": run_id, "mode": "Offline reasoning; real tools"}),
                    flush=True,
                )
                signal.signal(signal.SIGTERM, lambda *_: setattr(workflow, "stop_requested", True))
                signal.signal(signal.SIGINT, lambda *_: setattr(workflow, "stop_requested", True))
                result = workflow.execute(run_id, args.stop_after)
            else:
                run_id = legacy.create(args.requirement or "")
                print(
                    json.dumps(
                        {"created_run_id": run_id, "mode": "MockLLM fixtures; no live reasoning"}
                    ),
                    flush=True,
                )
                result = legacy.execute(run_id, args.stop_after)
        else:
            run_id = args.run_id
            try:
                version = store.get_run(run_id)["dag"].get("version", 1)
            except ValueError:
                if args.command in {"metrics", "halt", "approve", "reject"}:
                    print(json.dumps({"error": "Unavailable in S0; unknown v3 run"}))
                    return 2
                raise
            if (
                args.command in {"metrics", "halt", "approve", "reject", "list-pending", "replan"}
                and version != 2
            ):
                print(
                    json.dumps({"error": "Unavailable in S0; planned controls require v3 workflow"})
                )
                return 2
            if args.command == "resume":
                signal.signal(signal.SIGTERM, lambda *_: setattr(workflow, "stop_requested", True))
                signal.signal(signal.SIGINT, lambda *_: setattr(workflow, "stop_requested", True))
                result = (
                    workflow.execute(run_id, args.stop_after)
                    if version == 2
                    else legacy.execute(run_id, args.stop_after)
                )
            elif args.command == "inspect":
                result = workflow.inspect(run_id) if version == 2 else store.get_run(run_id)
            elif args.command == "metrics":
                result = workflow.metrics(run_id)
            elif args.command == "halt":
                workflow.request_halt(run_id)
                result = {"run_id": run_id, "halt_requested": True}
            elif args.command in {"approve", "reject"}:
                if not args.task_id or not args.reviewer or not args.reason:
                    raise ValueError("task ID, reviewer and reason required")
                workflow.decide(
                    run_id, args.task_id, args.reviewer, args.command, args.reason, args.demo
                )
                result = workflow.inspect(run_id)
            elif args.command == "list-pending":
                result = {
                    "pending": [
                        n for n in workflow.inspect(run_id)["nodes"] if n["status"] != "PASSED"
                    ]
                }
            elif args.command == "replan":
                data = json.loads(args.artifact.read_text())
                result = {"invalidated": workflow.replan(run_id, args.task_id, data)}
            elif args.command == "trace":
                state = store.get_run(run_id)
                if args.format == "mermaid":
                    print("flowchart LR")
                    for source, target in state["dag"]["edges"]:
                        print(f"  {source} --> {target}")
                else:
                    for item in store.events(run_id):
                        print(
                            f"{item['event_id']} {item['event_type']} {json.dumps(item['payload'])}"
                        )
                return 0
            else:
                events = store.events(run_id)
                matches = [
                    e
                    for e in events
                    if e["event_type"] == "GATE_PASSED" and e["payload"]["node"] == args.node
                ]
                if not matches:
                    raise ValueError("Node has no committed artifact")
                indexed = {e["event_id"]: e for e in events}
                chain = []
                current = matches[-1]
                while True:
                    chain.append(current)
                    if current["parent_event_id"] is None:
                        break
                    current = indexed[current["parent_event_id"]]
                result = {"node": args.node, "lineage": list(reversed(chain))}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(
            json.dumps(
                {"error": "Operation failed; inspect local evidence", "type": type(exc).__name__}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
