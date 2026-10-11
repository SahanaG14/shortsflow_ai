"""Provider abstraction for conversational AI implementations."""

import json
import os
from collections.abc import Sequence
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider cannot answer a request."""


class AIProvider(Protocol):
    """A provider capable of a tool-aware chat completion."""

    def chat(self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]: ...


class OllamaProvider:
    """Local Ollama implementation; no API key or cloud transport is used."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def chat(self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "messages": list(messages), "stream": False, "options": {"temperature": 0.2}}
        if tools:
            payload["tools"] = list(tools)
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise AIProviderError("Ollama is unavailable. Confirm it is running with the configured local model.") from error
