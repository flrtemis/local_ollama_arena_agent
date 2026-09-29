from __future__ import annotations

import base64
import csv
import io
import os
import shutil
from pathlib import Path
from typing import Any

from .base import Tool, ToolRegistry
from ..workspace import Workspace


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(msg: str, **kwargs: Any) -> dict[str, Any]:
    return {"ok": False, "error": msg, **kwargs}


def _line_normalized(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines]


def replace_text_fuzzy(content: str, old: str, new: str) -> tuple[str, bool, str]:
    if old in content:
        return content.replace(old, new, 1), True, "exact"

    file_lines = content.splitlines(keepends=True)
    old_lines_raw = old.splitlines()
    if not old_lines_raw:
        return content, False, "old_text was empty"

    old_norm = _line_normalized(old_lines_raw)
    file_norm = _line_normalized([line.rstrip("\r\n") for line in file_lines])
    n = len(old_norm)
    for i in range(0, len(file_norm) - n + 1):
        if file_norm[i : i + n] == old_norm:
            replacement = new
            if i + n < len(file_lines) and replacement and not replacement.endswith("\n"):
                replacement += "\n"
            new_lines = file_lines[:i] + [replacement] + file_lines[i + n :]
            return "".join(new_lines), True, "line-whitespace-insensitive"

    return content, False, "not found"


def register_file_tools(reg: ToolRegistry, ws: Workspace) -> None:
    def list_files(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", "."))
        max_depth = int(args.get("max_depth", 2))
        include_hidden = bool(args.get("include_hidden", False))
        if not path.exists():
            return _err("Path does not exist", path=ws.rel(path))
        if path.is_file():
            return _ok(entries=[ws.meta(path)])

        base_parts = len(path.parts)
        entries = []
        for root, dirs, files in os.walk(path):
            root_path = Path(root)
            depth = len(root_path.parts) - base_parts
            if depth >= max_depth:
                dirs[:] = []
            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]
            for d in sorted(dirs):
                p = root_path / d
                entries.append(ws.meta(p))
            for f in sorted(files):
                p = root_path / f
                entries.append(ws.meta(p))
        return _ok(path=ws.rel(path), entries=entries[:2000], truncated=len(entries) > 2000)

    def read_file(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", ""))
        max_bytes = int(args.get("max_bytes", 200_000))
        if not path.exists() or not path.is_file():
            return _err("File does not exist", path=ws.rel(path))
        data = path.read_bytes()
        truncated = len(data) > max_bytes
        data2 = data[:max_bytes]
        if ws.is_text_file(path):
            text = data2.decode("utf-8", errors="replace")
            return _ok(path=ws.rel(path), text=text, truncated=truncated, size=len(data), meta=ws.meta(path))
        return _ok(
            path=ws.rel(path),
            base64=base64.b64encode(data2).decode("ascii"),
            truncated=truncated,
            size=len(data),
            meta=ws.meta(path),
        )

    def write_file(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", ""))
        content = args.get("content", "")
        encoding = args.get("encoding", "utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        if bool(args.get("base64", False)):
            path.write_bytes(base64.b64decode(str(content)))
        else:
            path.write_text(str(content), encoding=encoding)
        return _ok(path=ws.rel(path), meta=ws.meta(path))

    def append_file(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", ""))
        content = str(args.get("content", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(content)
        return _ok(path=ws.rel(path), meta=ws.meta(path))

    def edit_file(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", ""))
        old = str(args.get("old_text", ""))
        new = str(args.get("new_text", ""))
        if not path.exists() or not path.is_file():
            return _err("File does not exist", path=ws.rel(path))
        content = path.read_text(encoding="utf-8", errors="replace")
        updated, changed, mode = replace_text_fuzzy(content, old, new)
        if not changed:
            return _err("old_text not found", mode=mode, path=ws.rel(path))
        path.write_text(updated, encoding="utf-8")
        return _ok(path=ws.rel(path), replacement_mode=mode, meta=ws.meta(path))

    def delete_file(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", ""))
        if not path.exists():
            return _err("Path does not exist", path=ws.rel(path))
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return _ok(path=ws.rel(path), deleted=True)

    def move_file(args: dict[str, Any]) -> dict[str, Any]:
        src = ws.safe_path(args.get("src", ""))
        dst = ws.safe_path(args.get("dst", ""))
        if not src.exists():
            return _err("Source does not exist", src=ws.rel(src))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return _ok(src=ws.rel(src), dst=ws.rel(dst), meta=ws.meta(dst))

    def present_file(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", ""))
        if not path.exists():
            return _err("File does not exist", path=ws.rel(path))
        return _ok(meta=ws.meta(path), url="/workspace/" + ws.rel(path))

    reg.add(Tool(
        "list_files",
        "List files and directories inside the workspace.",
        {"type": "object", "properties": {"path": {"type": "string"}, "max_depth": {"type": "integer"}, "include_hidden": {"type": "boolean"}}},
        list_files,
        category="files",
    ))
    reg.add(Tool(
        "read_file",
        "Read a text or binary file inside the workspace. Binary content is returned as base64.",
        {"type": "object", "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer"}}, "required": ["path"]},
        read_file,
        category="files",
    ))
    reg.add(Tool(
        "write_file",
        "Create or overwrite a file inside the workspace.",
        {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "base64": {"type": "boolean"}, "encoding": {"type": "string"}}, "required": ["path", "content"]},
        write_file,
        requires_approval=True,
        category="files",
    ))
    reg.add(Tool(
        "append_file",
        "Append text to a file inside the workspace.",
        {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        append_file,
        requires_approval=True,
        category="files",
    ))
    reg.add(Tool(
        "edit_file",
        "Replace the first occurrence of old_text with new_text in a workspace file. Uses exact match first, then a whitespace-insensitive line match.",
        {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]},
        edit_file,
        requires_approval=True,
        category="files",
    ))
    reg.add(Tool(
        "delete_file",
        "Delete a file or directory inside the workspace. Approval is strongly recommended.",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        delete_file,
        requires_approval=True,
        category="files",
    ))
    reg.add(Tool(
        "move_file",
        "Move or rename a file/directory inside the workspace.",
        {"type": "object", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]},
        move_file,
        requires_approval=True,
        category="files",
    ))
    reg.add(Tool(
        "present_file",
        "Return a preview/download URL for a workspace file.",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        present_file,
        category="files",
    ))
