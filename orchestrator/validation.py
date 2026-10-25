"""Local-only JSON Schema validation shared by clients and engine gates."""

import hashlib
import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

Json = dict[str, Any]


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def schema_for(name: str) -> Json:
    if name not in {"intake", "plan", "summary", "event", "dag"}:
        raise ValueError("Unknown schema")
    result: Json = json.loads(files("orchestrator").joinpath(f"schemas/{name}.json").read_text())
    return result


def validate(value: Any, schema: Json) -> None:
    # Never allow an artifact to request a remote schema fetch.
    def check_local(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in {"$ref", "$dynamicRef"} and (
                    not isinstance(child, str) or not child.startswith("#")
                ):
                    raise ValueError("Remote JSON Schema references are forbidden")
                check_local(child)
        elif isinstance(item, list):
            for child in item:
                check_local(child)

    check_local(schema)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
