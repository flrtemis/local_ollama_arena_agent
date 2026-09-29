# Quickstart

## 1. Install/start Ollama

Download Ollama from https://ollama.com or use your package manager.

Start it:

```bash
ollama serve
```

## 2. Pull a tool-calling model

```bash
ollama pull qwen2.5-coder:7b
```

## 3. Run the agent

```bash
cd local_ollama_arena_agent
python3 run.py
```

Open:

```text
http://127.0.0.1:8765
```

## 4. First test prompt

```text
List the files in the workspace. If it is empty, create hello.py, run it, and present the result.
```

Approve the requested tool calls in the browser.

## 5. Optional config

```bash
cp config.example.json config.json
```

Then edit `config.json`.

## 6. Useful environment variables

```bash
OLLAMA_MODEL=qwen2.5-coder:7b python3 run.py
AGENT_PORT=9999 python3 run.py
SANDBOX_BACKEND=docker python3 run.py
AUTO_APPROVE=1 python3 run.py
```
