# Security Notes

This project lets an AI model request local tool execution. Treat it seriously.

## Python soft sandbox is not a hard boundary

The default sandbox uses Python `subprocess` plus:

- working directory set to `workspace/`
- minimal environment
- closed stdin
- timeout
- output truncation
- basic dangerous command policy
- best-effort Unix resource limits
- browser approval by default

This reduces accidents but does **not** make arbitrary hostile code safe.

Python cannot fully prevent malicious code from using OS features available to the process. If you need stronger isolation, use Docker/Podman, a VM, gVisor, Firecracker, or another kernel/hypervisor-backed isolation method.

## Keep it localhost-only

Default host is:

```text
127.0.0.1
```

Do not bind to `0.0.0.0` unless you add authentication and understand the risk.

## Approval is your safety brake

Leave auto-approval off until you trust the workflow. Inspect commands before approving.

Especially scrutinize commands involving:

- `rm`, deletion, overwriting
- package installation
- network downloads
- shell pipes from remote URLs
- long-running scripts
- access to secrets

## Secrets

Do not put API keys, passwords, SSH keys, browser cookies, or private documents into the workspace unless you are comfortable with the selected model seeing them.

## Docker backend

The optional Docker backend is stronger than Python subprocess, but it is still not magic. Keep images updated, use rootless Docker/Podman if possible, and keep network disabled unless needed.

## Web tools

`fetch_page`, `web_search`, and media backends can connect to networks. A malicious page may contain prompt injection text. The model should treat fetched content as untrusted data, not instructions.
