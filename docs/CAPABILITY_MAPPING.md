# Capability Mapping

The Arena-style JSON you referenced lists models and capabilities such as text, file, image, web, search, video, etc. In a local Ollama setup, those capabilities are split between the model and your host tools.

| Capability | Local implementation in this project |
|---|---|
| Text chat | Ollama `/api/chat` |
| Tool/function calling | Ollama tools + Python dispatcher |
| Bash/code execution | `run_bash` tool |
| File input/output | upload, `read_file`, `write_file`, `edit_file`, `present_file` |
| Web fetch | `fetch_page` |
| Search | `web_search` via SearXNG or fallback DuckDuckGo HTML |
| Image input | browser upload + Ollama `images` field for vision-capable models |
| Image search | `image_search` via SearXNG image results |
| Image generation | `generate_image` adapter: AUTOMATIC1111/Forge or command template |
| Video generation | `generate_video` adapter: command template |
| Speech generation | `generate_speech` adapter: Piper or command template |
| Transcription | `transcribe_audio` adapter: command template |
| Office docs | `create_docx`, `create_xlsx`, `create_pptx` |
| PDF/CSV | `create_pdf`, `create_csv` |
| Webdev | file tools + Bash + preview URLs |

## Native vs tool capability

- Native model capability: what the Ollama model can do directly.
- Tool capability: what Python can do for the model.

Most agent capabilities are tool capabilities.
