from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    import resource
except Exception:  # pragma: no cover
    resource = None

from .base import Tool, ToolRegistry
from ..workspace import Workspace


FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\x00"), "NUL bytes are not allowed."),
    (re.compile(r"(^|[\s;|&])sudo([\s;|&]|$)", re.I), "sudo is not allowed."),
    (re.compile(r"(^|[\s;|&])su([\s;|&]|$)", re.I), "su is not allowed."),
    (re.compile(r"(^|[\s;|&])doas([\s;|&]|$)", re.I), "doas is not allowed."),
    (re.compile(r"(^|[\s;|&])rm\s+-[^\n;]*r[^\n;]*f", re.I), "rm -rf is not allowed."),
    (re.compile(r"(^|[\s;|&])dd([\s;|&]|$)", re.I), "dd is not allowed."),
    (re.compile(r"(^|[\s;|&])mkfs(\.|[\s;|&]|$)", re.I), "mkfs is not allowed."),
    (re.compile(r"(^|[\s;|&])mount([\s;|&]|$)", re.I), "mount is not allowed."),
    (re.compile(r"(^|[\s;|&])umount([\s;|&]|$)", re.I), "umount is not allowed."),
    (re.compile(r"(^|[\s;|&])shutdown([\s;|&]|$)", re.I), "shutdown is not allowed."),
    (re.compile(r"(^|[\s;|&])reboot([\s;|&]|$)", re.I), "reboot is not allowed."),
    (re.compile(r":\s*\(\s*\)\s*{", re.I), "fork-bomb-like syntax is not allowed."),
    (re.compile(r"(^|[\s:'\"])/(etc|dev|proc|sys|boot|root)(/|[\s:'\"]|$)", re.I), "access to sensitive absolute paths is not allowed."),
]


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n\n...[truncated]...\n\n" + text[-half:]


def command_policy(command: str, max_command_chars: int) -> tuple[bool, str]:
    if not isinstance(command, str):
        return False, "Command must be a string."
    if len(command) > max_command_chars:
        return False, f"Command is too long; max is {max_command_chars} characters."
    if not command.strip():
        return False, "Command is empty."
    for pattern, reason in FORBIDDEN_PATTERNS:
        if pattern.search(command):
            return False, reason
    return True, "ok"


def make_preexec(timeout_seconds: int):
    def preexec() -> None:
        try:
            os.setsid()
        except Exception:
            pass
        try:
            os.umask(0o077)
        except Exception:
            pass
        if resource is not None:
            limits = [
                (getattr(resource, "RLIMIT_CORE", None), 0, 0),
                (getattr(resource, "RLIMIT_CPU", None), timeout_seconds, timeout_seconds + 1),
                (getattr(resource, "RLIMIT_AS", None), 768 * 1024 * 1024, 768 * 1024 * 1024),
                (getattr(resource, "RLIMIT_FSIZE", None), 128 * 1024 * 1024, 128 * 1024 * 1024),
                (getattr(resource, "RLIMIT_NOFILE", None), 128, 128),
                (getattr(resource, "RLIMIT_NPROC", None), 128, 128),
            ]
            for res, soft, hard in limits:
                if res is None:
                    continue
                try:
                    resource.setrlimit(res, (soft, hard))
                except Exception:
                    pass
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            try:
                os.setgid(65534)
                os.setuid(65534)
            except Exception:
                pass
    return preexec


def run_python_backend(command: str, ws: Workspace, sandbox_cfg: dict[str, Any]) -> dict[str, Any]:
    timeout = int(sandbox_cfg.get("timeout_seconds", 20))
    output_limit = int(sandbox_cfg.get("output_limit_chars", 16000))
    max_command_chars = int(sandbox_cfg.get("max_command_chars", 5000))
    allowed, reason = command_policy(command, max_command_chars)
    if not allowed:
        return {"ok": False, "blocked": True, "reason": reason, "command": command}

    bash_path = "/bin/bash" if Path("/bin/bash").exists() else "bash"
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(ws.root),
        "PWD": str(ws.root),
        "TMPDIR": str(ws.root / "tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TERM": "dumb",
        "LOCAL_ARENA_AGENT_SANDBOX": "python-soft",
    }
    start = time.time()
    proc: subprocess.Popen[str] | None = None
    try:
        kwargs: dict[str, Any] = {}
        if os.name == "posix":
            kwargs["preexec_fn"] = make_preexec(timeout)
        proc = subprocess.Popen(
            [bash_path, "--noprofile", "--norc", "-lc", command],
            cwd=str(ws.root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
            else:
                proc.kill()
            stdout, stderr = proc.communicate()
            return {
                "ok": False,
                "timed_out": True,
                "backend": "python",
                "command": command,
                "workspace": str(ws.root),
                "seconds": round(time.time() - start, 3),
                "stdout": truncate_text(stdout, output_limit),
                "stderr": truncate_text(stderr, output_limit),
                "error": f"Command exceeded {timeout}s timeout.",
            }
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "backend": "python",
            "command": command,
            "workspace": str(ws.root),
            "seconds": round(time.time() - start, 3),
            "stdout": truncate_text(stdout, output_limit),
            "stderr": truncate_text(stderr, output_limit),
        }
    except Exception as e:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return {"ok": False, "backend": "python", "command": command, "error": repr(e), "workspace": str(ws.root)}


def run_docker_backend(command: str, ws: Workspace, sandbox_cfg: dict[str, Any]) -> dict[str, Any]:
    timeout = int(sandbox_cfg.get("timeout_seconds", 20))
    output_limit = int(sandbox_cfg.get("output_limit_chars", 16000))
    max_command_chars = int(sandbox_cfg.get("max_command_chars", 5000))
    allowed, reason = command_policy(command, max_command_chars)
    if not allowed:
        return {"ok": False, "blocked": True, "reason": reason, "command": command}

    image = str(sandbox_cfg.get("docker_image", "python:3.12-slim"))
    network = str(sandbox_cfg.get("docker_network", "none"))
    memory = str(sandbox_cfg.get("docker_memory", "768m"))
    cpus = str(sandbox_cfg.get("docker_cpus", "1.0"))
    start = time.time()
    docker_cmd = [
        "docker", "run", "--rm",
        "--network", network,
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--cpus", cpus,
        "--memory", memory,
        "--pids-limit", "128",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
        "-v", f"{ws.root}:/workspace:rw",
        "-w", "/workspace",
        "--user", f"{os.getuid() if hasattr(os, 'getuid') else 1000}:{os.getgid() if hasattr(os, 'getgid') else 1000}",
        image,
        "bash", "--noprofile", "--norc", "-lc", command,
    ]
    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "backend": "docker",
            "command": command,
            "workspace": str(ws.root),
            "seconds": round(time.time() - start, 3),
            "stdout": truncate_text(result.stdout, output_limit),
            "stderr": truncate_text(result.stderr, output_limit),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "timed_out": True,
            "backend": "docker",
            "command": command,
            "workspace": str(ws.root),
            "seconds": round(time.time() - start, 3),
            "stdout": truncate_text(e.stdout or "", output_limit) if isinstance(e.stdout, str) else "",
            "stderr": truncate_text(e.stderr or "", output_limit) if isinstance(e.stderr, str) else "",
            "error": f"Command exceeded {timeout}s timeout.",
        }
    except FileNotFoundError:
        return {"ok": False, "backend": "docker", "error": "docker executable not found. Set sandbox.backend to python or install Docker.", "command": command}
    except Exception as e:
        return {"ok": False, "backend": "docker", "command": command, "error": repr(e)}


def register_bash_tools(reg: ToolRegistry, ws: Workspace, config: dict[str, Any]) -> None:
    sandbox_cfg = config.get("sandbox", {})

    def run_bash(args: dict[str, Any]) -> dict[str, Any]:
        command = str(args.get("command", ""))
        backend = str(sandbox_cfg.get("backend", "python")).lower()
        if backend == "docker":
            return run_docker_backend(command, ws, sandbox_cfg)
        return run_python_backend(command, ws, sandbox_cfg)

    reg.add(Tool(
        "run_bash",
        "Run a Bash command in the workspace. Shell state does not persist across calls. Use for code execution, tests, project inspection, and debugging.",
        {"type": "object", "properties": {"command": {"type": "string", "description": "Bash command to run inside the workspace."}}, "required": ["command"]},
        run_bash,
        requires_approval=True,
        category="execution",
    ))
