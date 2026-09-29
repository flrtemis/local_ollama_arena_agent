# Local Arena-style Ollama Agent

This project turns a local Ollama tool-calling model into an Arena-style agent with a localhost web UI and a Python tool host.

It includes tools for:

- Bash execution inside a workspace
- File listing/reading/writing/editing/moving/deleting
- Local file preview/download links
- Web page fetching
- Web search via SearXNG or best-effort DuckDuckGo HTML fallback
- Image search via SearXNG image search
- Image generation adapters: AUTOMATIC1111/Forge API or configurable command
- Video generation adapter: configurable command
- Speech generation adapters: Piper or configurable command
- Audio transcription adapter: configurable command
- Document creation: `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.csv`
- Image upload to vision-capable Ollama models

The core code uses only the Python standard library. No Python packages are required.

## Honest capability note

This zip gives your local Ollama model an extensible tool layer similar in style to Arena.ai Agent Mode. It cannot bundle external engines or large model weights. Some capabilities require you to install/configure local services:

- **Ollama** is required for the language model.
- **Bash/files/documents** work with Python only.
- **Search** works best with a SearXNG instance; a brittle DuckDuckGo HTML fallback is included.
- **Image generation** requires AUTOMATIC1111/Forge with `--api` or your own command template.
- **Video generation** requires your own local video backend/command template.
- **Speech** requires Piper or a command template.
- **Transcription** requires whisper.cpp or another command template.

So the agent can do the same *classes of tasks* as a hosted agent, but final quality/speed depends on your local models and configured backends.

## Quick start

```bash
# 1. Start Ollama
ollama serve

# 2. Pull a tool-calling-capable model
ollama pull qwen2.5-coder:7b

# 3. Unzip this project and enter it
cd local_ollama_arena_agent

# 4. Optional: copy config
cp config.example.json config.json

# 5. Run
python3 run.py
```

Open:

```text
http://127.0.0.1:8765
```

Try:

```text
List the files in the workspace. If it is empty, create hello.py, run it, and present the result.
```

## Model selection

Any Ollama model may answer, but tool-calling-capable models work best. Try:

```bash
OLLAMA_MODEL=qwen2.5-coder:7b python3 run.py
```

Other possibilities depend on your local Ollama library and hardware.

## Configuration

Copy `config.example.json` to `config.json` and edit it.

Important fields:

```json
{
  "model": "qwen2.5-coder:7b",
  "ollama_chat_url": "http://127.0.0.1:11434/api/chat",
  "workspace": "./workspace",
  "auto_approve": false,
  "sandbox": {
    "backend": "python"
  }
}
```

Environment overrides:

```bash
OLLAMA_MODEL=qwen2.5-coder:7b \
AGENT_PORT=8765 \
SANDBOX_BACKEND=python \
python3 run.py
```

## Sandbox modes

### Python soft sandbox, default

The default backend uses Python `subprocess` with:

- workspace working directory
- minimal environment
- no stdin
- timeout
- output truncation
- policy blocks for obviously dangerous commands
- Unix resource limits where available
- manual approval by default

This is useful, but it is **not** a hard security boundary.

### Docker sandbox, optional

Set in `config.json`:

```json
"sandbox": {
  "backend": "docker",
  "docker_image": "python:3.12-slim",
  "docker_network": "none",
  "docker_memory": "768m",
  "docker_cpus": "1.0"
}
```

Python will call the local `docker` CLI and run commands in short-lived containers. This is stronger than a plain subprocess, but still should be treated carefully.

## Tool approval

By default, potentially mutating or expensive tools ask for browser approval:

- `run_bash`
- `write_file`
- `edit_file`
- `delete_file`
- `move_file`
- media generation
- document creation

You can enable the UI checkbox **Auto-approve tool calls**, but use it only with trusted models/tasks.

## File workspace

All files are under:

```text
workspace/
```

Uploaded files go to:

```text
workspace/uploads/
```

Generated files usually go to:

```text
workspace/generated/
```

The UI serves workspace files at:

```text
/workspace/<relative-path>
```

## Web search

For reliable search, run SearXNG and set:

```json
"web": {
  "searxng_url": "http://127.0.0.1:8080"
}
```

Without SearXNG, `web_search` uses a best-effort DuckDuckGo HTML fallback.

## Image generation

### AUTOMATIC1111/Forge

Start WebUI with API enabled, for example:

```bash
./webui.sh --api
```

Then set:

```json
"image_generation": {
  "backend": "auto1111",
  "auto1111_url": "http://127.0.0.1:7860"
}
```

Ask:

```text
Generate a 1024x1024 image of a retro robot reading a book and save it as generated/robot.png.
```

### Command template

```json
"image_generation": {
  "backend": "command",
  "command_template": "python3 my_image_script.py --prompt {prompt} --output {output} --width {width} --height {height}"
}
```

Place your script in the workspace or use an absolute path you trust.

## Video generation

Configure any local video generator as a command:

```json
"video_generation": {
  "backend": "command",
  "command_template": "python3 my_video_script.py --prompt {prompt} --output {output}"
}
```

The tool substitutes:

- `{prompt}`
- `{output}`
- `{input}`

## Speech generation

### Piper

```json
"speech_generation": {
  "backend": "piper",
  "piper_executable": "piper",
  "piper_voice": "/path/to/voice.onnx"
}
```

### Command template

```json
"speech_generation": {
  "backend": "command",
  "command_template": "my_tts --input {input} --output {output}"
}
```

The text is written to `{input}`.

## Transcription

Example with a custom whisper.cpp command:

```json
"transcription": {
  "backend": "command",
  "command_template": "./whisper-cli -m models/ggml-base.en.bin -f {input} -otxt -of {output}"
}
```

Adjust this to your whisper.cpp build.

## Document creation

The document tools use Python standard library OOXML/PDF generation. They are intentionally simple but useful.

Examples:

```text
Create a Word document called generated/plan.docx with a title and five paragraphs explaining this project.
```

```text
Create an Excel workbook called generated/budget.xlsx with a sheet named Budget and rows for item, cost, and notes.
```

```text
Create a PowerPoint deck called generated/demo.pptx with 4 slides summarizing the local agent architecture.
```

## Vision/image input

Use the file picker in the UI to upload images. If your Ollama model supports vision and `send_uploaded_images_to_ollama` is true, uploaded images are sent to Ollama with your next message.

You can also ask the model to inspect uploaded file paths with tools.

## Project layout

```text
local_ollama_arena_agent/
  run.py
  config.example.json
  local_arena_agent/
    server.py
    agent.py
    ollama.py
    workspace.py
    config.py
    tools/
      bash.py
      files.py
      web.py
      media.py
      documents.py
  workspace/
  outputs/
  docs/
  examples/
```

## Security

Read `SECURITY.md`. Do not expose this server to the public internet. Keep it on `127.0.0.1` unless you know exactly what you are doing.
