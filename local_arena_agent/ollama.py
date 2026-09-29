from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaClient:
    def __init__(self, chat_url: str, model: str, timeout: int = 240) -> None:
        self.chat_url = chat_url
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, *, temperature: float = 0.2) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if tools:
            payload["tools"] = tools
        data = json.dumps(payload).encode("utf-8")
        req = Request(self.chat_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP error {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"Could not reach Ollama at {self.chat_url}: {e}") from e
        parsed = json.loads(raw)
        msg = parsed.get("message")
        if not isinstance(msg, dict):
            raise RuntimeError(f"Unexpected Ollama response: {raw[:1000]}")
        return msg
