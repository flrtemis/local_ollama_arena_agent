from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .base import Tool, ToolRegistry
from ..workspace import Workspace


def _run_template(template: str, substitutions: dict[str, str], cwd: Path, timeout: int = 600) -> dict[str, Any]:
    command = template
    for k, v in substitutions.items():
        command = command.replace("{" + k + "}", shlex.quote(v))
    try:
        start = time.time()
        result = subprocess.run(["/bin/bash", "-lc", command], cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "command": command,
            "seconds": round(time.time() - start, 3),
            "stdout": result.stdout[-8000:],
            "stderr": result.stderr[-8000:],
        }
    except Exception as e:
        return {"ok": False, "command": command, "error": repr(e)}


def _post_json(url: str, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def register_media_tools(reg: ToolRegistry, ws: Workspace, config: dict[str, Any]) -> None:
    image_cfg = config.get("image_generation", {})
    video_cfg = config.get("video_generation", {})
    speech_cfg = config.get("speech_generation", {})
    trans_cfg = config.get("transcription", {})

    def generate_image(args: dict[str, Any]) -> dict[str, Any]:
        prompt = str(args.get("prompt", ""))
        if not prompt.strip():
            return {"ok": False, "error": "prompt is empty"}
        backend = str(args.get("backend") or image_cfg.get("backend", "none")).lower()
        out_rel = str(args.get("output_path") or f"generated/image_{int(time.time())}.png")
        out_path = ws.safe_path(out_rel)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        width = int(args.get("width", 1024))
        height = int(args.get("height", 1024))

        if backend in {"auto1111", "automatic1111", "forge"}:
            url = str(image_cfg.get("auto1111_url", "http://127.0.0.1:7860")).rstrip("/") + "/sdapi/v1/txt2img"
            payload = {
                "prompt": prompt,
                "negative_prompt": str(args.get("negative_prompt", "")),
                "width": width,
                "height": height,
                "steps": int(args.get("steps", 25)),
                "cfg_scale": float(args.get("cfg_scale", 7.0)),
                "sampler_name": str(args.get("sampler_name", "Euler")),
            }
            try:
                data = _post_json(url, payload, timeout=900)
                images = data.get("images") or []
                if not images:
                    return {"ok": False, "backend": backend, "error": "No images returned", "response": data}
                out_path.write_bytes(base64.b64decode(images[0].split(",")[-1]))
                return {"ok": True, "backend": backend, "prompt": prompt, "file": ws.meta(out_path)}
            except Exception as e:
                return {"ok": False, "backend": backend, "error": repr(e), "hint": "Start AUTOMATIC1111/Forge with --api, or choose command backend."}

        if backend == "command":
            template = str(image_cfg.get("command_template", ""))
            if not template:
                return {"ok": False, "backend": "command", "error": "image_generation.command_template is empty in config.json"}
            result = _run_template(template, {"prompt": prompt, "output": str(out_path), "width": str(width), "height": str(height)}, ws.root, timeout=900)
            result["file"] = ws.meta(out_path) if out_path.exists() else None
            return result

        return {
            "ok": False,
            "backend": backend,
            "error": "No image generation backend configured.",
            "how_to_enable": "Set image_generation.backend to auto1111/forge and run SD WebUI with --api, or set backend=command with a command_template.",
        }

    def generate_video(args: dict[str, Any]) -> dict[str, Any]:
        prompt = str(args.get("prompt", ""))
        backend = str(args.get("backend") or video_cfg.get("backend", "none")).lower()
        out_rel = str(args.get("output_path") or f"generated/video_{int(time.time())}.mp4")
        out_path = ws.safe_path(out_rel)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if backend == "command":
            template = str(video_cfg.get("command_template", ""))
            if not template:
                return {"ok": False, "backend": "command", "error": "video_generation.command_template is empty in config.json"}
            result = _run_template(template, {"prompt": prompt, "output": str(out_path), "input": str(args.get("input_path", ""))}, ws.root, timeout=3600)
            result["file"] = ws.meta(out_path) if out_path.exists() else None
            return result
        return {
            "ok": False,
            "backend": backend,
            "error": "No video generation backend configured.",
            "how_to_enable": "Set video_generation.backend=command and provide a command_template for ComfyUI/Wan/LTX/etc.",
        }

    def generate_speech(args: dict[str, Any]) -> dict[str, Any]:
        text = str(args.get("text", ""))
        if not text.strip():
            return {"ok": False, "error": "text is empty"}
        backend = str(args.get("backend") or speech_cfg.get("backend", "none")).lower()
        out_rel = str(args.get("output_path") or f"generated/speech_{int(time.time())}.wav")
        out_path = ws.safe_path(out_rel)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        input_txt = ws.safe_path(f"tmp/tts_{int(time.time())}.txt")
        input_txt.write_text(text, encoding="utf-8")

        if backend == "piper":
            exe = str(speech_cfg.get("piper_executable", "piper"))
            voice = str(args.get("voice") or speech_cfg.get("piper_voice", ""))
            if not voice:
                return {"ok": False, "backend": "piper", "error": "Set speech_generation.piper_voice to a .onnx voice file."}
            try:
                start = time.time()
                with input_txt.open("r", encoding="utf-8") as stdin, out_path.open("wb") as stdout:
                    result = subprocess.run([exe, "--model", voice], stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, text=False, timeout=600)
                return {"ok": result.returncode == 0, "backend": "piper", "returncode": result.returncode, "seconds": round(time.time() - start, 3), "stderr": result.stderr.decode("utf-8", errors="replace")[-8000:], "file": ws.meta(out_path) if out_path.exists() else None}
            except Exception as e:
                return {"ok": False, "backend": "piper", "error": repr(e)}

        if backend == "command":
            template = str(speech_cfg.get("command_template", ""))
            if not template:
                return {"ok": False, "backend": "command", "error": "speech_generation.command_template is empty in config.json"}
            result = _run_template(template, {"text": text, "input": str(input_txt), "output": str(out_path)}, ws.root, timeout=600)
            result["file"] = ws.meta(out_path) if out_path.exists() else None
            return result

        return {"ok": False, "backend": backend, "error": "No speech backend configured. Use backend=piper or backend=command."}

    def transcribe_audio(args: dict[str, Any]) -> dict[str, Any]:
        audio = ws.safe_path(args.get("path", ""))
        if not audio.exists():
            return {"ok": False, "error": "Audio file does not exist", "path": str(args.get("path", ""))}
        backend = str(args.get("backend") or trans_cfg.get("backend", "none")).lower()
        out_rel = str(args.get("output_path") or f"generated/transcript_{int(time.time())}.txt")
        out_path = ws.safe_path(out_rel)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if backend == "command":
            template = str(trans_cfg.get("command_template", ""))
            if not template:
                return {"ok": False, "backend": "command", "error": "transcription.command_template is empty in config.json"}
            result = _run_template(template, {"input": str(audio), "output": str(out_path)}, ws.root, timeout=1800)
            result["file"] = ws.meta(out_path) if out_path.exists() else None
            if out_path.exists():
                result["text"] = out_path.read_text(encoding="utf-8", errors="replace")[:50000]
            return result
        return {"ok": False, "backend": backend, "error": "No transcription backend configured. Use backend=command with whisper.cpp or another CLI."}

    reg.add(Tool(
        "generate_image",
        "Generate an image using a configured local image backend such as AUTOMATIC1111/Forge API or a command template. Saves output into the workspace.",
        {"type": "object", "properties": {"prompt": {"type": "string"}, "negative_prompt": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "steps": {"type": "integer"}, "output_path": {"type": "string"}, "backend": {"type": "string"}}, "required": ["prompt"]},
        generate_image,
        requires_approval=True,
        category="media",
    ))
    reg.add(Tool(
        "generate_video",
        "Generate a video using a configured local command backend. Saves output into the workspace.",
        {"type": "object", "properties": {"prompt": {"type": "string"}, "input_path": {"type": "string"}, "output_path": {"type": "string"}, "backend": {"type": "string"}}, "required": ["prompt"]},
        generate_video,
        requires_approval=True,
        category="media",
    ))
    reg.add(Tool(
        "generate_speech",
        "Generate spoken audio from text using Piper or a configured command backend. Saves output into the workspace.",
        {"type": "object", "properties": {"text": {"type": "string"}, "voice": {"type": "string"}, "output_path": {"type": "string"}, "backend": {"type": "string"}}, "required": ["text"]},
        generate_speech,
        requires_approval=True,
        category="media",
    ))
    reg.add(Tool(
        "transcribe_audio",
        "Transcribe an audio file using a configured local command backend such as whisper.cpp.",
        {"type": "object", "properties": {"path": {"type": "string"}, "output_path": {"type": "string"}, "backend": {"type": "string"}}, "required": ["path"]},
        transcribe_audio,
        requires_approval=True,
        category="media",
    ))
