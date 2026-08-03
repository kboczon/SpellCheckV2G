# SpellCheck Tray App — Windows Global Hotkey Utility

[![WARN-LLM GENERATED](https://img.shields.io/badge/WARN-LLM%20GENERATED-FF6347)](https://github.com/40ants/ai-badges)

A lightweight background utility that captures selected text (or clipboard fallback), sends it to an LLM for grammar/typo correction, and places the cleaned result back on your clipboard — optionally auto-pasting into the active window.

## Features
- **Global hotkey** (`Ctrl+Win+A` by default) triggers spell check from anywhere
- **Smart selection capture**: Tries to copy highlighted text first; falls back to current clipboard if nothing is selected
- **LLM-powered correction**: Supports local OpenAI-compatible endpoints (LM Studio, Ollama, vLLM, etc.) and OpenAI API
- **Configurable prompt**: Preserve exact meaning while fixing typos/grammar
- **Auto-paste**: Optionally sends corrected text back to the last active window
- **Background mode**: Runs silently waiting for hotkey
- **Distributable `.exe`**: One-file standalone build via PyInstaller

## Quick Start (Windows)

1. Install Python 3.10+ if not already installed
2. Open Command Prompt in this folder: `cd win-spellcheck`
3. Run the build script: `build.bat`
4. Copy `config.yaml` to the same folder as `SpellCheck.exe` (or edit it before building)
5. Launch `SpellCheck.exe` — a tray icon will appear
6. Press `Ctrl+Win+A` anywhere to trigger

> **Note**: On Windows, global hotkeys like `Ctrl+Win+A` may require running the app as Administrator on first use. The app will log a warning if permission is denied.

## Configuration (`config.yaml`)

```yaml
app:
  hotkey: "ctrl+win+a"       # Global trigger key combo
  copy_wait_ms: 150          # Wait time after Ctrl+C for clipboard update
  paste_delay_s: 0.2         # Pause before auto-pasting corrected text

llm:
  provider: "local"          # Options: "local" or "openai"
  
  local:
    endpoint: "http://127.0.0.1:8000/v1/chat/completions"
    model: "your-model-name"
    max_tokens: 1024
    temperature: 0.1
  
  openai:
    api_key: "sk-your-key-here"
    endpoint: "https://api.openai.com/v1/chat/completions"
    model: "gpt-3.5-turbo"
    max_tokens: 1024
    temperature: 0.1

prompt: |
  Fix typos and grammar in this text while preserving the original meaning exactly. 
  Return only the corrected text with no extra commentary, greetings, or formatting.
  
  Text to correct:
  """{text}"""
```

### Local LLM Setup Examples

**Ollama** (runs locally):
```yaml
local:
  endpoint: "http://127.0.0.1:11434/v1/chat/completions"
  model: "mistral"  # or "llama3", etc.
```

**LM Studio / vLLM**:
```yaml
local:
  endpoint: "http://127.0.0.1:8000/v1/chat/completions"
  model: "your-model-here"
```

## How It Works

1. Press hotkey → app tracks current active window title
2. Simulates `Ctrl+C` to copy selected text (if any)
3. If clipboard changed → uses selection; otherwise uses existing clipboard content
4. Sends text to configured LLM with your custom prompt
5. Corrected result is placed on clipboard
6. Optionally auto-pastes into the tracked window after a short delay

## Troubleshooting

- **"Hotkey registration failed"**: Run as Administrator once, or change `hotkey` in config to something like `ctrl+alt+s`
- **No text captured**: Some apps block clipboard access. Try selecting text first, or ensure clipboard has content before pressing hotkey
- **LLM errors**: Verify endpoint URL, model name, and API key (if using OpenAI). Check logs for exact error messages
- **Auto-paste fails**: Some applications don't accept `Ctrl+V` simulation. Set `paste_delay_s: 0` to disable auto-paste

## Dependencies

- Python 3.10+
- `keyboard` — global hotkey hooking (requires admin on Windows for some combos)
- `PyWin32` — Windows clipboard/window APIs
- `requests` — HTTP calls to LLM endpoints
- `pyyaml` — config parsing
- `pyinstaller` — standalone executable packaging

## License

MIT — use freely, modify as needed.
