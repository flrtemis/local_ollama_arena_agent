from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8765,
    "ollama_chat_url": "http://127.0.0.1:11434/api/chat",
    "model": "gemma4:26b",
    "workspace": "./workspace",
    "outputs": "./outputs",
    "max_agent_steps": 10,
    "auto_approve": False,
    "send_uploaded_images_to_ollama": True,
    "sandbox": {
        "backend": "python",
        "timeout_seconds": 20,
        "output_limit_chars": 16000,
        "max_command_chars": 5000,
        "allow_network_in_python_backend": True,
        "docker_image": "python:3.12-slim",
        "docker_network": "none",
        "docker_memory": "768m",
        "docker_cpus": "1.0",
    },
    "web": {
        "timeout_seconds": 15,
        "max_bytes": 2_000_000,
        "searxng_url": "",
    },
    "image_generation": {
        "backend": "none",
        "auto1111_url": "http://127.0.0.1:7860",
        "command_template": "",
    },
    "video_generation": {
        "backend": "none",
        "command_template": "",
    },
    "speech_generation": {
        "backend": "none",
        "command_template": "",
        "piper_executable": "piper",
        "piper_voice": "",
    },
    "transcription": {
        "backend": "none",
        "command_template": "",
    },
}


def load_config(project_root: Path | None = None) -> dict[str, Any]:
    if project_root is None:
        project_root = Path.cwd()

    config = dict(DEFAULT_CONFIG)

    candidates = []
    env_path = os.getenv("LOCAL_ARENA_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(project_root / "config.json")

    for p in candidates:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                config = deep_merge(config, json.load(f))
            break

    # Environment overrides for common knobs.
    if os.getenv("OLLAMA_MODEL"):
        config["model"] = os.getenv("OLLAMA_MODEL")
    if os.getenv("OLLAMA_CHAT_URL"):
        config["ollama_chat_url"] = os.getenv("OLLAMA_CHAT_URL")
    if os.getenv("AGENT_WORKSPACE"):
        config["workspace"] = os.getenv("AGENT_WORKSPACE")
    if os.getenv("AGENT_OUTPUTS"):
        config["outputs"] = os.getenv("AGENT_OUTPUTS")
    if os.getenv("AGENT_PORT"):
        config["port"] = int(os.getenv("AGENT_PORT", "8765"))
    if os.getenv("AUTO_APPROVE"):
        config["auto_approve"] = os.getenv("AUTO_APPROVE", "0").lower() in {"1", "true", "yes", "on"}
    if os.getenv("SANDBOX_BACKEND"):
        config.setdefault("sandbox", {})["backend"] = os.getenv("SANDBOX_BACKEND")

    # Resolve relative directories against project root.
    for key in ["workspace", "outputs"]:
        p = Path(str(config[key]))
        if not p.is_absolute():
            p = (project_root / p).resolve()
        config[key] = str(p)
        p.mkdir(parents=True, exist_ok=True)

    return config
