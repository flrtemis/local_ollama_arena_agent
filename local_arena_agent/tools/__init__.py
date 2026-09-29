from __future__ import annotations

from .base import ToolRegistry
from .bash import register_bash_tools
from .documents import register_document_tools
from .files import register_file_tools
from .media import register_media_tools
from .web import register_web_tools
from ..workspace import Workspace


def build_registry(ws: Workspace, config: dict) -> ToolRegistry:
    reg = ToolRegistry()
    register_file_tools(reg, ws)
    register_bash_tools(reg, ws, config)
    register_web_tools(reg, ws, config)
    register_media_tools(reg, ws, config)
    register_document_tools(reg, ws)
    return reg
