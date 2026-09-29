from __future__ import annotations

import base64
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .ollama import OllamaClient
from .tools import build_registry
from .tools.base import ToolRegistry
from .workspace import IMAGE_EXTENSIONS, Workspace


SYSTEM_PROMPT_TEMPLATE = """
You are a local Arena-style agent running through a Python host and Ollama.

You can call tools to complete tasks. Use tools whenever a task requires inspecting files,
creating files, running code, searching/fetching the web, generating media, or creating documents.

Workspace:
- Your workspace root is: {workspace}
- Treat the workspace as your world. Do not try to access files outside it.
- Files you create or modify in the workspace persist.

Execution:
- Bash commands run in a sandbox/workspace tool. Shell state does not persist between calls.
- Prefer simple, auditable commands.
- Verify important changes by reading files or running tests.

Available tool categories:
- files: list/read/write/edit/move/delete/present workspace files
- execution: run Bash commands
- web: search/fetch web pages and images
- media: image/video/speech/transcription adapters if configured
- documents: create docx/xlsx/pptx/pdf/csv files

Tool calling:
- Prefer native tool calls.
- If native tool calling fails, you may output a single JSON object exactly like:
  {{"tool": "tool_name", "arguments": {{...}}}}
  and the host will try to execute it.

After using tools, provide a concise summary and mention generated files/URLs.
""".strip()


def parse_json_tool_from_content(content: str) -> list[dict[str, Any]]:
    text = (content or "").strip()
    candidates = []
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S | re.I)
        if m:
            candidates.append(m.group(1))
    candidates.append(text)
    for c in candidates:
        try:
            obj = json.loads(c)
        except Exception:
            continue
        if isinstance(obj, dict) and "tool" in obj:
            return [{"function": {"name": obj.get("tool"), "arguments": obj.get("arguments") or {}}}]
        if isinstance(obj, dict) and "tool_calls" in obj and isinstance(obj["tool_calls"], list):
            return obj["tool_calls"]
    return []


def parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    fn = call.get("function") or {}
    name = str(fn.get("name", ""))
    args = fn.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {"command": args}
    if not isinstance(args, dict):
        args = {}
    return name, args


class LocalArenaAgent:
    def __init__(self, config: dict[str, Any], ws: Workspace) -> None:
        self.config = config
        self.ws = ws
        self.registry: ToolRegistry = build_registry(ws, config)
        self.client = OllamaClient(str(config["ollama_chat_url"]), str(config["model"]))
        self.pending: dict[str, dict[str, Any]] = {}
        self.reset()

    def reset(self) -> None:
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(workspace=self.ws.root)}
        ]
        self.pending.clear()

    def status(self) -> dict[str, Any]:
        return {
            "model": self.config["model"],
            "ollama_chat_url": self.config["ollama_chat_url"],
            "workspace": str(self.ws.root),
            "outputs": str(self.ws.outputs),
            "auto_approve": self.config.get("auto_approve", False),
            "sandbox": self.config.get("sandbox", {}),
            "tools": self.registry.manifest(),
        }

    def _make_user_message(self, content: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        attachments = attachments or []
        msg: dict[str, Any] = {"role": "user", "content": content}
        if attachments:
            lines = [content, "", "Attached/uploaded workspace files:"]
            images: list[str] = []
            for a in attachments:
                path = str(a.get("path") or "")
                lines.append(f"- {path}")
                suffix = Path(path).suffix.lower()
                if self.config.get("send_uploaded_images_to_ollama", True) and suffix in IMAGE_EXTENSIONS and suffix != ".svg":
                    try:
                        p = self.ws.safe_path(path)
                        images.append(base64.b64encode(p.read_bytes()).decode("ascii"))
                    except Exception:
                        pass
            msg["content"] = "\n".join(lines)
            if images:
                msg["images"] = images
        return msg

    def _append_tool_result(self, name: str, result: dict[str, Any]) -> None:
        self.messages.append({"role": "tool", "name": name, "content": json.dumps(result, ensure_ascii=False)})

    def _maybe_approval(self, name: str, args: dict[str, Any], auto_approve: bool, assistant_msg: dict[str, Any]) -> dict[str, Any] | None:
        tool = self.registry.get(name)
        if not tool:
            return None
        if tool.requires_approval and not auto_approve:
            pending_id = str(uuid.uuid4())
            self.pending[pending_id] = {
                "name": name,
                "args": args,
                "created": time.time(),
                "auto_approve": auto_approve,
            }
            return {
                "type": "approval_needed",
                "pendingId": pending_id,
                "tool": name,
                "arguments": args,
                "assistantContent": assistant_msg.get("content", ""),
            }
        return None

    def chat(self, user_message: str, *, attachments: list[dict[str, Any]] | None = None, auto_approve: bool | None = None) -> dict[str, Any]:
        if auto_approve is None:
            auto_approve = bool(self.config.get("auto_approve", False))
        self.messages.append(self._make_user_message(user_message, attachments))
        return self._continue(auto_approve=auto_approve)

    def approve(self, pending_id: str, approved: bool) -> dict[str, Any]:
        item = self.pending.pop(pending_id, None)
        if not item:
            return {"type": "error", "error": "Pending tool call not found or already handled."}
        name = item["name"]
        args = item["args"]
        if approved:
            result = self.registry.dispatch(name, args)
        else:
            result = {"ok": False, "blocked": True, "rejected_by_user": True, "tool": name, "arguments": args}
        self._append_tool_result(name, result)
        return self._continue(auto_approve=bool(item.get("auto_approve", False)), last_tool_result=result)

    def _continue(self, *, auto_approve: bool, last_tool_result: dict[str, Any] | None = None) -> dict[str, Any]:
        max_steps = int(self.config.get("max_agent_steps", 10))
        for _ in range(max_steps):
            assistant_msg = self.client.chat(self.messages, self.registry.schemas())
            self.messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                tool_calls = parse_json_tool_from_content(assistant_msg.get("content", ""))

            if not tool_calls:
                return {"type": "final", "reply": assistant_msg.get("content", ""), "lastToolResult": last_tool_result}

            # Process one at a time for predictable approval UX.
            name, args = parse_tool_call(tool_calls[0])
            tool = self.registry.get(name)
            if not tool:
                result = {"ok": False, "blocked": True, "error": f"Unknown tool: {name}", "arguments": args}
                self._append_tool_result(name or "unknown", result)
                last_tool_result = result
                continue

            approval = self._maybe_approval(name, args, auto_approve, assistant_msg)
            if approval:
                approval["lastToolResult"] = last_tool_result
                return approval

            result = self.registry.dispatch(name, args)
            self._append_tool_result(name, result)
            last_tool_result = result

        return {
            "type": "final",
            "reply": f"Stopped because the agent reached max_agent_steps={max_steps}.",
            "lastToolResult": last_tool_result,
        }
