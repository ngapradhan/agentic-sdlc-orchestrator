"""Deterministic offline role reasoning behind the same LLMClient contract."""

import json
from importlib.resources import files

from orchestrator.validation import Json, digest, validate


class OfflineReasoner:
    def complete(self, system: str, messages: list[Json], schema: Json) -> Json:
        fixtures = json.loads(
            files("orchestrator").joinpath("fixtures/agent_roles.json").read_text()
        )
        if system not in fixtures:
            raise ValueError("Unknown reasoning role")
        result: Json = dict(fixtures[system])
        result["mocked_reasoning"] = True
        result["context_hash"] = digest(messages)
        validate(result, schema)
        return result
