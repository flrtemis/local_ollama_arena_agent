from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .agent import LocalArenaAgent
from .config import load_config
from .workspace import Workspace


INDEX_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local Arena-style Ollama Agent</title>
  <style>
    :root { color-scheme: dark; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background: #0d1117; color: #e6edf3; }
    main { max-width: 1100px; margin: 0 auto; padding: 26px; }
    h1 { margin: 0 0 6px; }
    a { color: #58a6ff; }
    .subtle { color: #9da7b3; }
    .bar, .card { background: #161b22; border: 1px solid #30363d; border-radius: 14px; padding: 14px; margin: 14px 0; }
    .bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    textarea { width: 100%; min-height: 120px; box-sizing: border-box; border-radius: 12px; border: 1px solid #30363d; background: #0b0f14; color: #e6edf3; padding: 14px; font-size: 15px; line-height: 1.45; }
    button { background: #238636; color: #fff; border: 0; border-radius: 10px; padding: 10px 14px; cursor: pointer; font-size: 14px; }
    button.secondary { background: #30363d; }
    button.danger { background: #da3633; }
    button:disabled { opacity: .55; cursor: wait; }
    input[type=file] { max-width: 100%; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #0b0f14; border: 1px solid #30363d; border-radius: 12px; padding: 12px; line-height: 1.45; }
    code { color: #f2cc60; }
    .assistant { border-left: 4px solid #58a6ff; }
    .user { border-left: 4px solid #a371f7; }
    .tool { border-left: 4px solid #f2cc60; }
    .approval { border-left: 4px solid #ff7b72; }
    .upload { border-left: 4px solid #7ee787; }
    .pill { display: inline-block; padding: 3px 7px; border-radius: 999px; background: #30363d; margin-right: 6px; margin-top: 4px; font-size: 12px; }
    details summary { cursor: pointer; }
  </style>
</head>
<body>
<main>
  <h1>Local Arena-style Ollama Agent</h1>
  <div class="subtle">Ollama model + Python tool host + workspace tools. Runs entirely on localhost except optional web/tool backends you configure.</div>

  <div class="bar">
    <span>Model: <code id="model">loading</code></span>
    <span>Workspace: <code id="workspace">loading</code></span>
    <label><input type="checkbox" id="autoApprove"> Auto-approve tool calls</label>
    <button class="secondary" onclick="resetChat()">Reset chat</button>
    <button class="secondary" onclick="loadStatus()">Refresh status</button>
  </div>

  <div class="card">
    <textarea id="message">List the files in the workspace. If it is empty, create hello.py, run it, and present the result.</textarea>
    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; align-items:center;">
      <button id="sendBtn" onclick="sendMessage()">Send</button>
      <input id="fileInput" type="file" multiple>
      <button class="secondary" onclick="uploadFiles()">Upload selected files</button>
    </div>
    <div id="attachments" class="subtle" style="margin-top:8px;"></div>
  </div>

  <details class="card">
    <summary>Capabilities / tool manifest</summary>
    <div id="toolManifest"></div>
  </details>

  <section id="log"></section>
</main>
<script>
let state = { busy: false, attachments: [] };

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }
function setBusy(b) { state.busy = b; document.getElementById("sendBtn").disabled = b; }
function addCard(kind, title, body) { const el = document.createElement("div"); el.className = `card ${kind}`; el.innerHTML = `<strong>${esc(title)}</strong><div style="margin-top:10px;">${body}</div>`; document.getElementById("log").prepend(el); return el; }
function renderJson(x) { return `<pre>${esc(JSON.stringify(x, null, 2))}</pre>`; }
function fileLink(meta) { if (!meta) return ""; return `<a href="${esc(meta.preview_url)}" target="_blank">${esc(meta.path || meta.name)}</a> <span class="subtle">(${esc(meta.mime || "")}, ${esc(meta.size || 0)} bytes)</span>`; }

async function postJson(url, payload) { const res = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload || {}) }); const data = await res.json(); if (!res.ok) throw new Error(data.error || JSON.stringify(data)); return data; }

async function loadStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();
  document.getElementById("model").textContent = data.model;
  document.getElementById("workspace").textContent = data.workspace;
  document.getElementById("autoApprove").checked = !!data.auto_approve;
  const groups = {};
  for (const t of data.tools || []) { (groups[t.category] ||= []).push(t); }
  document.getElementById("toolManifest").innerHTML = Object.entries(groups).map(([cat, tools]) => `<h3>${esc(cat)}</h3>` + tools.map(t => `<div class="pill">${esc(t.name)}${t.requires_approval ? " ⚠" : ""}</div>`).join("")).join("");
}

function updateAttachments() {
  document.getElementById("attachments").innerHTML = state.attachments.length ? "Attached: " + state.attachments.map(a => `<span class="pill">${esc(a.path)}</span>`).join("") : "No uploaded attachments for next message.";
}

async function uploadFiles() {
  const input = document.getElementById("fileInput");
  if (!input.files.length) return;
  setBusy(true);
  try {
    for (const file of input.files) {
      const dataUrl = await new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = reject; r.readAsDataURL(file); });
      const b64 = String(dataUrl).split(",").pop();
      const data = await postJson("/api/upload", { filename: file.name, data_base64: b64 });
      state.attachments.push(data.meta);
      addCard("upload", "Uploaded", fileLink(data.meta));
    }
    input.value = "";
    updateAttachments();
  } catch (e) { addCard("approval", "Upload error", `<pre>${esc(e.message)}</pre>`); }
  finally { setBusy(false); }
}

async function sendMessage() {
  if (state.busy) return;
  const message = document.getElementById("message").value;
  const autoApprove = document.getElementById("autoApprove").checked;
  const attachments = state.attachments;
  state.attachments = [];
  updateAttachments();
  addCard("user", "You", `<pre>${esc(message)}</pre>` + (attachments.length ? `<p>${attachments.map(fileLink).join("<br>")}</p>` : ""));
  setBusy(true);
  try { handleAgentResponse(await postJson("/api/chat", { message, attachments, autoApprove })); }
  catch (e) { addCard("approval", "Error", `<pre>${esc(e.message)}</pre>`); }
  finally { setBusy(false); }
}

function handleAgentResponse(data) {
  if (data.lastToolResult) {
    let body = renderJson(data.lastToolResult);
    const meta = data.lastToolResult.file || data.lastToolResult.meta || (data.lastToolResult.file && data.lastToolResult.file.meta);
    if (meta && meta.preview_url) body = fileLink(meta) + body;
    addCard("tool", "Tool result", body);
  }
  if (data.type === "final") { addCard("assistant", "Assistant", `<pre>${esc(data.reply || "")}</pre>`); return; }
  if (data.type === "approval_needed") {
    const body = `${data.assistantContent ? `<pre>${esc(data.assistantContent)}</pre>` : ""}<p>The model wants to call <code>${esc(data.tool)}</code> with:</p>${renderJson(data.arguments)}<button onclick="approve('${data.pendingId}', true)">Approve</button> <button class="danger" onclick="approve('${data.pendingId}', false)">Reject</button>`;
    addCard("approval", "Approval needed", body);
    return;
  }
  if (data.type === "error") { addCard("approval", "Error", `<pre>${esc(data.error)}</pre>`); return; }
  addCard("approval", "Unexpected response", renderJson(data));
}

async function approve(id, approved) {
  if (state.busy) return;
  setBusy(true);
  try { handleAgentResponse(await postJson("/api/approve", { pendingId: id, approved })); }
  catch (e) { addCard("approval", "Error", `<pre>${esc(e.message)}</pre>`); }
  finally { setBusy(false); }
}

async function resetChat() {
  setBusy(true);
  try { await postJson("/api/reset", {}); document.getElementById("log").innerHTML = ""; addCard("assistant", "Reset", "Conversation reset."); }
  catch (e) { addCard("approval", "Error", `<pre>${esc(e.message)}</pre>`); }
  finally { setBusy(false); }
}

loadStatus(); updateAttachments();
</script>
</body>
</html>
"""


class AgentHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, agent: LocalArenaAgent, ws: Workspace):
        super().__init__(server_address, RequestHandlerClass)
        self.agent = agent
        self.ws = ws


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalArenaOllamaAgent/0.1"

    @property
    def agent(self) -> LocalArenaAgent:
        return self.server.agent  # type: ignore[attr-defined]

    @property
    def ws(self) -> Workspace:
        return self.server.ws  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_json(self, status: int, obj: dict[str, Any]) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            data = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/api/status":
            self.send_json(200, self.agent.status())
            return
        if parsed.path.startswith("/workspace/"):
            rel = unquote(parsed.path[len("/workspace/"):])
            try:
                p = self.ws.safe_path(rel)
                if not p.exists() and rel.startswith("outputs/"):
                    p = self.ws.safe_path(rel[len("outputs/"):], base="outputs")
                if not p.exists() or not p.is_file():
                    self.send_json(404, {"error": "File not found"})
                    return
                mime, _ = mimetypes.guess_type(p.name)
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f"inline; filename={p.name!r}")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_json(400, {"error": repr(e)})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/chat":
                body = self.read_json()
                msg = str(body.get("message", ""))
                if not msg.strip():
                    self.send_json(400, {"type": "error", "error": "Message is empty."})
                    return
                data = self.agent.chat(msg, attachments=body.get("attachments") or [], auto_approve=bool(body.get("autoApprove", False)))
                self.send_json(200, data)
                return
            if parsed.path == "/api/approve":
                body = self.read_json()
                data = self.agent.approve(str(body.get("pendingId", "")), bool(body.get("approved", False)))
                self.send_json(200 if data.get("type") != "error" else 404, data)
                return
            if parsed.path == "/api/reset":
                self.agent.reset()
                self.send_json(200, {"ok": True})
                return
            if parsed.path == "/api/upload":
                body = self.read_json()
                filename = str(body.get("filename", "upload.bin"))
                data_b64 = str(body.get("data_base64", ""))
                if data_b64.startswith("data:"):
                    data_b64 = data_b64.split(",", 1)[-1]
                meta = self.ws.save_upload(filename, data_b64)
                self.send_json(200, {"ok": True, "meta": meta})
                return
            self.send_json(404, {"type": "error", "error": "Not found"})
        except Exception as e:
            self.send_json(500, {"type": "error", "error": repr(e)})


def main() -> None:
    project_root = Path.cwd()
    config = load_config(project_root)
    ws = Workspace(Path(config["workspace"]), Path(config["outputs"]))
    agent = LocalArenaAgent(config, ws)
    host = str(config.get("host", "127.0.0.1"))
    port = int(config.get("port", 8765))
    print("Local Arena-style Ollama Agent")
    print(f"  URL:       http://{host}:{port}")
    print(f"  Model:     {config['model']}")
    print(f"  Ollama:    {config['ollama_chat_url']}")
    print(f"  Workspace: {ws.root}")
    print(f"  Sandbox:   {config.get('sandbox', {}).get('backend', 'python')}")
    print()
    print("Important: Python-only sandboxing is a soft sandbox. For stronger isolation set sandbox.backend=docker and install Docker/Podman-compatible CLI.")
    print()
    httpd = AgentHTTPServer((host, port), Handler, agent, ws)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()
