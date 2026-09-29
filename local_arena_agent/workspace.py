from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".xml", ".svg", ".sh", ".bat",
    ".ps1", ".java", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".php", ".rb",
    ".sql", ".log",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}


@dataclass
class Workspace:
    root: Path
    outputs: Path

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.outputs = self.outputs.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
        (self.root / "uploads").mkdir(exist_ok=True)
        (self.root / "tmp").mkdir(exist_ok=True)

    def safe_path(self, user_path: str | os.PathLike[str], *, base: str = "workspace") -> Path:
        raw = str(user_path or ".").replace("\\", "/")
        while raw.startswith("/"):
            raw = raw[1:]
        base_path = self.outputs if base == "outputs" else self.root
        p = (base_path / raw).resolve()
        try:
            p.relative_to(base_path)
        except ValueError as exc:
            raise ValueError(f"Path escapes {base}: {user_path!r}") from exc
        return p

    def rel(self, path: Path) -> str:
        path = path.resolve()
        try:
            return str(path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            try:
                return "outputs/" + str(path.relative_to(self.outputs)).replace("\\", "/")
            except ValueError:
                return str(path)

    def meta(self, path: Path) -> dict[str, Any]:
        path = path.resolve()
        stat = path.stat()
        mime, _ = mimetypes.guess_type(path.name)
        return {
            "path": self.rel(path),
            "name": path.name,
            "is_dir": path.is_dir(),
            "size": stat.st_size,
            "mime": mime or "application/octet-stream",
            "preview_url": "/workspace/" + self.rel(path),
        }

    def is_text_file(self, path: Path, sample_bytes: int = 4096) -> bool:
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return True
        try:
            data = path.read_bytes()[:sample_bytes]
            if not data:
                return True
            if b"\x00" in data:
                return False
            data.decode("utf-8")
            return True
        except Exception:
            return False

    def save_upload(self, filename: str, data_base64: str) -> dict[str, Any]:
        safe_name = Path(filename).name or "upload.bin"
        target = self.safe_path("uploads/" + safe_name)
        if target.exists():
            stem, suffix = target.stem, target.suffix
            i = 2
            while True:
                candidate = target.with_name(f"{stem}-{i}{suffix}")
                if not candidate.exists():
                    target = candidate
                    break
                i += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(data_base64))
        return self.meta(target)
