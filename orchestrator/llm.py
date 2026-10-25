"""Pluggable completion contract; only MockLLM is selected by the S0 CLI."""

import json
import os
from importlib.resources import files
from typing import Protocol

import httpx

from orchestrator.validation import Json, validate


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[Json], schema: Json) -> Json: ...


class MockLLM:
    """Templates, not live reasoning. Request text is never echoed into logs."""

    def complete(self, system: str, messages: list[Json], schema: Json) -> Json:
        role = schema["title"]
        if role not in {"intake", "plan", "summary"}:
            raise ValueError("No fixture for schema")
        if not system or not messages:
            raise ValueError("A system prompt and input context are required")
        result: Json = json.loads(
            files("orchestrator").joinpath(f"fixtures/{role}.json").read_text()
        )
        validate(result, schema)  # Agent self-check; engine checks independently.
        return result


class LiveHTTPClient:
    """Opt-in adapter for a schema-aware HTTP gateway; not a provider SDK.

    Gateway receives {system, messages, schema}, returns a JSON object.
    Instantiate explicitly with an httpx client; default CLI cannot select it.
    No credentials are persisted. HTTPS is required to protect gateway traffic.
    """

    def __init__(self, endpoint: str, client: httpx.Client) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("Live gateway requires HTTPS")
        self.endpoint = endpoint
        self.client = client

    @classmethod
    def from_environment(cls) -> "LiveHTTPClient":
        endpoint = os.environ.get("SDLC_LLM_ENDPOINT", "")
        token = os.environ.get("SDLC_LLM_TOKEN", "")
        if not endpoint or not token:
            raise ValueError("Live gateway endpoint and token must be supplied in environment")
        return cls(
            endpoint, httpx.Client(headers={"Authorization": f"Bearer {token}"}, trust_env=False)
        )

    def complete(self, system: str, messages: list[Json], schema: Json) -> Json:
        response = self.client.post(
            self.endpoint,
            json={"system": system, "messages": messages, "schema": schema},
            timeout=30,
            follow_redirects=False,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Live gateway returned a non-object")
        validate(result, schema)
        return result
