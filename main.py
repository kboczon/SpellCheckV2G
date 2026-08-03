"""SpellCheck Tray App — Global hotkey -> LLM grammar fix -> clipboard paste."""

from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import threading
import time
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pywintypes

# ── Logging setup ──────────────────────────────────────────────
def _choose_log_path() -> Path:
    preferred_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    try:
        probe = preferred_dir / "spellcheck.log"
        with probe.open("a", encoding="utf-8"):
            pass
        return probe
    except OSError:
        fallback = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SpellCheck"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback / "spellcheck.log"


LOG_PATH = _choose_log_path()
_log_handlers = [
    RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
]
if sys.stdout is not None:
    _log_handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_log_handlers,
)
log = logging.getLogger("spellcheck")
log.info("SpellCheck started. Log file: %s", LOG_PATH)

# ── Config loader ──────────────────────────────────────────────
import win32clipboard
import win32con
import yaml


def get_config_path() -> str:
    """Return the editable config beside the script or packaged executable."""
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    return str(base_dir / "config.yaml")


def get_log_path() -> str:
    return str(LOG_PATH)


def _default_llm_slots() -> dict:
    """Return default LLM slots configuration."""
    return {
        "active_slot": 1,
        "slots": {
            "slot1": {
                "name": "Slot 1",
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-4o-mini",
                "temperature": 0.3,
                "max_tokens": 4096,
                "verify_ssl": True,
                "use_thinking_mode": False,
            },
            "slot2": {
                "name": "Slot 2",
                "provider": "openai",
                "base_url": "",
                "api_key": "",
                "model": "",
                "temperature": 0.3,
                "max_tokens": 4096,
                "verify_ssl": True,
                "use_thinking_mode": False,
            },
        },
    }


def _ensure_llm_slots(cfg: dict) -> dict:
    """Migrate legacy config or ensure LLM slots structure exists."""
    if "llm_slots" in cfg and "active_slot" in cfg.get("llm_slots", {}):
        return cfg  # Already has new format

    # Migrate from old flat llm config to slots
    old_llm = cfg.get("llm", {})
    if old_llm:
        provider = old_llm.get("provider", "openai")
        slot_cfg = old_llm.get(provider, {})
        base_url = slot_cfg.get("base_url", "")
        api_key = slot_cfg.get("api_key", "")
        model = slot_cfg.get("model", "")
        temperature = slot_cfg.get("temperature", 0.3)
        max_tokens = slot_cfg.get("max_tokens", old_llm.get("max_tokens", 4096))
        verify_ssl = slot_cfg.get("verify_ssl", True)

        cfg["llm_slots"] = {
            "active_slot": 1,
            "slots": {
                "slot1": {
                    "name": "Default (migrated)",
                    "provider": provider,
                    "base_url": base_url,
                    "api_key": api_key,
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "verify_ssl": verify_ssl,
                    "use_thinking_mode": False,
                },
                "slot2": {
                    "name": "Slot 2",
                    "provider": "openai",
                    "base_url": "",
                    "api_key": "",
                    "model": "",
                    "temperature": 0.3,
                    "max_tokens": 4096,
                    "verify_ssl": True,
                    "use_thinking_mode": False,
                },
            },
        }
    else:
        cfg["llm_slots"] = _default_llm_slots()

    return cfg


def get_active_llm_config(cfg: dict) -> dict:
    """Get the active LLM slot config as a flat dict for use by call_llm."""
    slots_cfg = cfg.get("llm_slots", {})
    active_id = slots_cfg.get("active_slot", 1)
    slot_key = f"slot{active_id}"
    slot = slots_cfg.get("slots", {}).get(slot_key, {})

    # Build flat config matching what call_llm expects
    provider = slot.get("provider", "openai")
    use_thinking_mode = bool(slot.get("use_thinking_mode", False))
    return {
        "app": dict(cfg.get("app", {})),
        "llm": {
            "provider": provider,
            "max_tokens": slot.get("max_tokens", 4096),
            "temperature": slot.get("temperature", 0.3),
            "use_thinking_mode": use_thinking_mode,
            provider: {
                "base_url": slot.get("base_url", ""),
                "api_key": slot.get("api_key", ""),
                "model": slot.get("model", ""),
                "temperature": slot.get("temperature", 0.3),
                "max_tokens": slot.get("max_tokens", 4096),
                "verify_ssl": bool(slot.get("verify_ssl", True)),
            },
        },
        "prompt": cfg.get(
            "prompt",
            "Please fix any spelling and grammar errors in the following text. Return only the corrected text, nothing else:\n\n{text}",
        ),
    }


def save_config(cfg: dict, path: str = None):
    """Save config to YAML file."""
    if path is None:
        path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
        log.info(f"Config saved to {path}")
    except Exception as e:
        log.error(f"Failed to save config to {path}: {e}")


def load_config(path: str | None = None) -> dict:
    """Load config from YAML file. Returns empty dict on any error."""
    if path is None:
        path = get_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            cfg = {}
        return _ensure_llm_slots(cfg)
    except FileNotFoundError:
        log.warning(f"Config file not found: {path}. Using defaults.")
        return _ensure_llm_slots({})
    except Exception as e:
        log.error(f"Failed to load config from {path}: {e}")
        return _ensure_llm_slots({})


# ── Clipboard helpers (Windows-only) ───────────────────────────
win32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# CRITICAL: Set explicit restype/argtypes for 64-bit Windows.
# Without these, ctypes defaults to c_int (32-bit) which truncates pointers → access violations.
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_ulong, ctypes.c_size_t]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
win32.GetClipboardData.restype = ctypes.c_void_p
win32.GetClipboardData.argtypes = [ctypes.c_uint]

_clipboard_lock = threading.Lock()  # Thread-safe clipboard access


def get_clipboard_text() -> str | None:
    """Read Unicode text from clipboard using pywin32 (safe — no access violations)."""
    with _clipboard_lock:
        for attempt in range(5):
            opened = False
            try:
                win32clipboard.OpenClipboard()
                opened = True
                # Check if clipboard actually contains UNICODE text before reading
                if not win32clipboard.IsClipboardFormatAvailable(
                    win32con.CF_UNICODETEXT
                ):
                    log.debug("Clipboard does not contain Unicode text")
                    return None
                data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                if data and isinstance(data, str) and data.strip():
                    return data
                return None
            except pywintypes.error as e:
                log.warning(f"Clipboard unavailable (attempt {attempt + 1}/5): {e}")
                time.sleep(0.2)
            except TypeError:
                log.debug("Clipboard contains non-text format")
                return None
            except Exception as e:
                log.error(f"get_clipboard_text failed: {e}")
                return None
            finally:
                if opened:
                    try:
                        win32clipboard.CloseClipboard()
                    except Exception:
                        pass
    return None


def set_clipboard_text(text: str) -> bool:
    """Place Unicode text on clipboard using pywin32 (safe — no access violations)."""
    with _clipboard_lock:
        for attempt in range(5):
            opened = False
            try:
                win32clipboard.OpenClipboard()
                opened = True
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
                return True
            except pywintypes.error as e:
                log.warning(f"set_clipboard failed (attempt {attempt + 1}/5): {e}")
                time.sleep(0.1)
            except Exception as e:
                log.error(f"set_clipboard_text failed: {e}")
                return False
            finally:
                if opened:
                    try:
                        win32clipboard.CloseClipboard()
                    except Exception:
                        pass
    return False


# ── Window Management Constants (from original) ────────────────
IGNORED_WINDOW_CLASSES = {
    "ConsoleWindowClass",
    "CASCADIA_HOSTING_WINDOW_CLASS",
}
ASFW_ANY = -1
GA_ROOT = 2

try:
    SwitchToThisWindow = win32.SwitchToThisWindow
except AttributeError:
    SwitchToThisWindow = None

if hasattr(win32, "GetWindowLongPtrW"):
    GetWindowLongPtr = win32.GetWindowLongPtrW
    GetWindowLongPtr.restype = ctypes.c_longlong
    GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
else:
    GetWindowLongPtr = win32.GetWindowLongW
    GetWindowLongPtr.restype = ctypes.c_long
    GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def get_root_window(hwnd):
    if not hwnd:
        return None
    root = win32.GetAncestor(hwnd, GA_ROOT)
    return root or hwnd


def hwnd_to_hex(hwnd):
    try:
        return f"0x{int(hwnd):08X}"
    except (TypeError, ValueError):
        return "<null>"


def get_class_name(hwnd):
    if not hwnd:
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    if win32.GetClassNameW(hwnd, buffer, 256):
        return buffer.value
    return ""


def describe_hwnd(hwnd):
    if not hwnd:
        return "<none>"
    title = get_window_text(hwnd)
    class_name = get_class_name(hwnd)
    return f"{hwnd_to_hex(hwnd)} [{class_name}] '{title}'"


def get_thread_focus_window(base_hwnd=None):
    hwnd = base_hwnd or win32.GetForegroundWindow()
    if not hwnd:
        return None
    thread_id = win32.GetWindowThreadProcessId(hwnd, None)
    gui_info = GUITHREADINFO()
    gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if win32.GetGUIThreadInfo(thread_id, ctypes.byref(gui_info)):
        return gui_info.hwndFocus or gui_info.hwndActive or hwnd
    return hwnd


def get_console_window():
    return kernel32.GetConsoleWindow()


def is_console_window(hwnd):
    if not hwnd:
        return False
    if hwnd == get_console_window():
        return True
    class_name = get_class_name(hwnd)
    return class_name in IGNORED_WINDOW_CLASSES


def is_interactable_window(hwnd):
    if not hwnd:
        return False
    if not win32.IsWindow(hwnd) or not win32.IsWindowVisible(hwnd):
        return False
    if is_console_window(hwnd):
        return False
    style = GetWindowLongPtr(hwnd, -16)  # GWL_STYLE
    if style & 0x8000000:  # WS_DISABLED
        return False
    return True


def enumerate_top_windows():
    windows = []

    @EnumWindowsProc
    def _enum_proc(hwnd, _):
        windows.append(hwnd)
        return True

    win32.EnumWindows(_enum_proc, 0)
    return windows


def find_previous_top_window(reference):
    windows = enumerate_top_windows()
    if not windows:
        return None
    if reference in windows:
        start_index = windows.index(reference) + 1
    else:
        start_index = 0
    for hwnd in windows[start_index:]:
        if is_interactable_window(hwnd):
            return hwnd
    return None


def focus_window(hwnd):
    """Switch focus to a window with thread attachment and verification."""
    if not hwnd:
        return False
    root_hwnd = get_root_window(hwnd)
    if not root_hwnd or not win32.IsWindow(root_hwnd):
        log.debug(f"focus_window called with invalid handle {hwnd_to_hex(hwnd)}")
        return False
    target_hwnd = root_hwnd
    if win32.IsIconic(target_hwnd):
        win32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
    try:
        win32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass
    foreground = win32.GetForegroundWindow()
    attached = False
    if foreground != target_hwnd:
        thread_fore = (
            win32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )
        thread_target = win32.GetWindowThreadProcessId(target_hwnd, None)
        if thread_fore and thread_fore != thread_target:
            try:
                attached = (
                    win32.AttachThreadInput(thread_fore, thread_target, True) != 0
                )
            except Exception as e:
                log.debug(f"AttachThreadInput failed: {e}")
    win32.BringWindowToTop(target_hwnd)
    win32.SetActiveWindow(target_hwnd)
    win32.SetForegroundWindow(target_hwnd)
    time.sleep(0.1)
    success = win32.GetForegroundWindow() == target_hwnd
    if not success and SwitchToThisWindow:
        try:
            SwitchToThisWindow(target_hwnd, True)
            time.sleep(0.1)
            success = win32.GetForegroundWindow() == target_hwnd
        except Exception as exc:
            log.debug(f"SwitchToThisWindow raised {exc}")
    if attached:
        try:
            win32.AttachThreadInput(thread_fore, thread_target, False)
        except Exception:
            pass
    log.debug(
        f"[{'+' if success else '-'}] Foreground verification for {describe_hwnd(root_hwnd)}"
    )
    return success


def resolve_target_control():
    """Smart target window resolution."""
    global last_interactable_hwnd
    foreground = win32.GetForegroundWindow()
    if (
        foreground
        and not is_console_window(foreground)
        and is_interactable_window(foreground)
    ):
        last_interactable_hwnd = foreground
        focused = get_thread_focus_window(foreground)
        if focused and not is_console_window(focused):
            log.debug(
                f"[+] Using foreground window with child focus {describe_hwnd(focused)}"
            )
            return focused
        else:
            log.debug(
                f"[+] Using foreground window without child focus {describe_hwnd(foreground)}"
            )
            return foreground
    if foreground and foreground == get_console_window():
        candidate = win32.GetWindow(foreground, 2)  # GW_HWNDNEXT
        visited = {foreground}
        while candidate and candidate not in visited:
            if is_interactable_window(candidate):
                focused_candidate = get_thread_focus_window(candidate)
                if focused_candidate and not is_console_window(focused_candidate):
                    last_interactable_hwnd = focused_candidate
                    log.debug(
                        f"[+] Using next window with child focus {describe_hwnd(focused_candidate)}"
                    )
                    return focused_candidate
                elif candidate:
                    last_interactable_hwnd = candidate
                    log.debug(
                        f"[+] Using next window without child focus {describe_hwnd(candidate)}"
                    )
                    return candidate
            visited.add(candidate)
            candidate = win32.GetWindow(candidate, 2)
    if last_interactable_hwnd and is_interactable_window(last_interactable_hwnd):
        log.debug(
            f"[+] Using cached last interactable window {describe_hwnd(last_interactable_hwnd)}"
        )
        focus_window(last_interactable_hwnd)
        return last_interactable_hwnd
    candidate_top = find_previous_top_window(foreground or 0)
    if candidate_top and is_interactable_window(candidate_top):
        log.debug(
            f"[+] Using first available interactable window {describe_hwnd(candidate_top)}"
        )
        return candidate_top
    log.warning("[!] Failed to resolve a target control - no suitable window found")
    return None


def get_active_window_title() -> str | None:
    hwnd = win32.GetForegroundWindow()
    if not hwnd:
        return None
    buf = ctypes.create_unicode_buffer(512)
    win32.GetWindowTextW(hwnd, buf, 512)
    title = buf.value.strip()
    return title or f"HWND:{hwnd}"


def get_window_text(hwnd):
    if not hwnd:
        return ""
    length = win32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    win32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


# ── Keyboard / Hotkey (requires `keyboard` package) ───────────
try:
    import keyboard
except ImportError:
    log.warning("keyboard module not found. Install via: pip install keyboard")
    keyboard = None  # type: ignore[assignment]


def _simulate_key_combo(target_hwnd, ctrl_code):
    """Simulate Ctrl+<key> by sending keyboard input to the foreground window."""
    if target_hwnd and not focus_window(target_hwnd):
        log.warning("Keyboard shortcut skipped because the target window was not activated.")
        return False

    time.sleep(0.05)
    win32.keybd_event(0x11, 0, 0, 0)  # Ctrl down
    time.sleep(0.02)
    win32.keybd_event(ctrl_code, 0, 0, 0)  # Key down
    time.sleep(0.02)
    win32.keybd_event(ctrl_code, 0, 0x0002, 0)  # Key up
    win32.keybd_event(0x11, 0, 0x0002, 0)  # Ctrl up
    return True


def _simulate_ctrl_c(target_hwnd=None):
    """Simulate Ctrl+C to copy selection."""
    return _simulate_key_combo(target_hwnd or wintypes.HWND(0), 0x43)


def _simulate_ctrl_v(target_hwnd=None):
    """Simulate Ctrl+V to paste."""
    return _simulate_key_combo(target_hwnd or wintypes.HWND(0), 0x56)


# ── LLM client with retry logic ───────────────────────────────
import requests


_CHANNEL_HEADER_RE = re.compile(
    r"<\|?channel\|?>\s*(thought|analysis|final)\b", re.IGNORECASE
)


def clean_llm_content(content: str) -> str:
    """Remove model reasoning blocks and return only user-facing content."""
    if not isinstance(content, str):
        return ""

    # Standard reasoning tags. Also discard an unterminated trailing block so
    # hidden reasoning is never pasted when a model forgets </think>.
    content = re.sub(
        r"<think\b[^>]*>.*?</think\s*>", "", content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content = re.sub(
        r"<think\b[^>]*>.*$", "", content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    headers = list(_CHANNEL_HEADER_RE.finditer(content))
    final_headers = [m for m in headers if m.group(1).lower() == "final"]
    if final_headers:
        # A final channel is authoritative; ignore everything before the last one.
        content = content[final_headers[-1].end():]
    else:
        # Handle `<|channel>thought ... <channel|>` as well as thought/analysis
        # followed by another labeled channel.
        content = re.sub(
            r"<\|?channel\|?>\s*(?:thought|analysis)\b.*?(?:<channel\|>|(?=<\|?channel\|?>\s*\w+))",
            "",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        content = re.sub(
            r"<\|?channel\|?>\s*(?:thought|analysis)\b.*$", "", content,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Remove protocol framing that can accompany channel-formatted responses.
    content = re.sub(
        r"<\|(?:message|end|start)\|>(?:assistant)?", "", content,
        flags=re.IGNORECASE,
    )
    content = re.sub(r"<\|?channel\|?>\s*final\b", "", content, flags=re.IGNORECASE)
    return content.strip()


def call_llm(config: dict, text: str) -> str | None:
    llm_section = config.get("llm", {})
    provider = llm_section.get("provider", "local")
    section = llm_section.get(provider, {})
    use_thinking_mode = bool(llm_section.get("use_thinking_mode", False))
    app_section = config.get("app", {})
    try:
        max_retries = max(1, int(app_section.get("max_retries", 3)))
    except (TypeError, ValueError):
        log.warning("Invalid max_retries value; using 3.")
        max_retries = 3
    try:
        request_timeout_s = max(1.0, float(app_section.get("request_timeout_s", 120)))
    except (TypeError, ValueError):
        log.warning("Invalid request_timeout_s value; using 120 seconds.")
        request_timeout_s = 120.0

    prompt_template = config.get("prompt", "")
    if not prompt_template or "{text}" not in prompt_template:
        log.warning("Missing {text} placeholder in prompt template.")
        prompt = f"Fix typos and grammar in this text while preserving meaning:\n{text}"
    else:
        prompt = prompt_template.format(text=text)

    payload = {
        "model": section.get("model", ""),
        "messages": [
            {
                "role": "system",
                "content": "You are a spell checker and grammar corrector. Return ONLY the corrected text with no explanation, no markdown, no quotes, no commentary.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": section.get("max_tokens", 1024),
        "temperature": section.get("temperature", 0.3),
    }

    # Control thinking/reasoning for models that support it (Qwen via llama.cpp)
    if not use_thinking_mode:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        log.info("LLM call: thinking DISABLED (chat_template_kwargs.enable_thinking=false)")
    else:
        log.info("LLM call: thinking ENABLED")

    # Resolve endpoint BEFORE auth check (fix UnboundLocalError)
    endpoint = section.get("base_url", "") or section.get("endpoint", "")
    verify_ssl = bool(section.get("verify_ssl", True))
    if not endpoint:
        log.error("LLM endpoint/base URL is empty for provider '%s'.", provider)
        return None
    log.info(
        "LLM request: provider=%s model=%s endpoint=%s attempts=%s timeout=%ss verify_ssl=%s",
        provider,
        section.get("model", ""),
        endpoint,
        max_retries,
        request_timeout_s,
        verify_ssl,
    )
    if not verify_ssl:
        log.warning(
            "TLS certificate verification is DISABLED for this LLM slot. "
            "HTTPS connections are vulnerable to interception."
        )

    headers = {"Content-Type": "application/json"}
    if provider == "openai":
        key = section.get("api_key", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        elif endpoint and not any(
            endpoint.startswith(p)
            for p in (
                "http://localhost:",
                "http://10.",
                "http://192.168.",
                "http://172.",
            )
        ):
            # Only require API key for remote endpoints (not local/private IPs)
            log.error("API key is missing and endpoint appears to be remote.")
            return None
        else:
            log.info("Using local/private endpoint without API key.")

    for attempt in range(max_retries):
        try:
            # Ensure endpoint includes /chat/completions path
            url = endpoint.rstrip("/")
            if not url.endswith("/chat/completions"):
                url += "/chat/completions"
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=request_timeout_s,
                verify=verify_ssl,
            )

            if resp.status_code == 429:
                wait_time = (2**attempt) * 1.5
                log.warning(f"Rate limited (HTTP 429). Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                continue

            resp.raise_for_status()
            data = resp.json()

            # DEBUG: Log raw response to diagnose format issues
            import json as _json

            raw_preview = (
                _json.dumps(data, ensure_ascii=False)[:500]
                if isinstance(data, dict)
                else str(data)[:500]
            )
            log.warning(f"*** RAW LLM RESPONSE (first 500 chars): {raw_preview}")
            log.info(
                f"LLM response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}"
            )

            try:
                content = clean_llm_content(
                    data["choices"][0]["message"]["content"]
                )
            except (KeyError, IndexError, TypeError) as e:
                log.error(
                    f"Malformed LLM response (missing choices/message/content): {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep((2**attempt) * 2)
                    continue
                return None

            # Clean up surrounding markdown fences properly
            for marker in ("```", '"""'):
                if content.startswith(marker):
                    lines = content.split("\n")
                    clean_lines = []
                    found_end = False
                    for i, line in enumerate(lines[1:], 1):
                        stripped = line.strip()
                        if not found_end and stripped == marker:
                            found_end = True
                            break
                        clean_lines.append(line)
                    content = "\n".join(clean_lines).strip()

            if not content:
                log.error("LLM response contained reasoning but no final answer.")
                return None
            return content

        except requests.exceptions.HTTPError as e:
            response_preview = (
                (e.response.text or "")[:2000] if e.response is not None else ""
            )
            if e.response.status_code >= 500 and attempt < max_retries - 1:
                wait_time = (2**attempt) * 2
                log.warning(
                    f"Server error {e.response.status_code}. Retrying in {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
            else:
                log.error(
                    "LLM HTTP call failed: %s; response body: %s",
                    e,
                    response_preview,
                )
                return None
        except requests.exceptions.Timeout as e:
            if attempt < max_retries - 1:
                wait_time = (2**attempt) * 2
                log.warning(f"Request timed out. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                log.error(f"LLM call failed after retries: {e}")
                return None
        except Exception as e:
            log.error("LLM call failed: %s", e, exc_info=True)
            return None

    log.error("LLM call failed after all retry attempts.")
    return None


# ── Main App Logic ────────────────────────────────────────────
last_interactable_hwnd = None


class SpellCheckApp:
    def _get_effective_config(self):
        """Get config with active LLM slot resolved."""
        return get_active_llm_config(self.config)

    def __init__(self):
        self.config = load_config()
        self.running = True
        self._trigger_lock = threading.Lock()
        self._hotkey_handle = None

        if keyboard:
            try:
                hk = self.config.get("app", {}).get("hotkey", "ctrl+alt+a")
                self._hotkey_handle = keyboard.add_hotkey(
                    hk, self._on_trigger, suppress=True
                )
                log.info(f"Hotkey '{hk}' registered.")
            except Exception as e:
                log.warning(
                    f"Failed to register hotkey '{hk}': {e}. You may need to run as Administrator on Windows."
                )
        else:
            log.warning(
                "No keyboard module — hotkeys disabled. Use manually via CLI or IDE."
            )

    def reload_config(self):
        """Reload settings and apply a changed global hotkey immediately."""
        if keyboard and self._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handle)
            except Exception as exc:
                log.warning(f"Could not remove previous hotkey: {exc}")
            self._hotkey_handle = None
        self.config = load_config()
        if keyboard:
            try:
                hk = self.config.get("app", {}).get("hotkey", "ctrl+alt+a")
                self._hotkey_handle = keyboard.add_hotkey(
                    hk, self._on_trigger, suppress=True
                )
                log.info(f"Hotkey '{hk}' registered.")
            except Exception as exc:
                log.warning(f"Failed to register hotkey '{hk}': {exc}")

    def _on_trigger(self):
        """Called when hotkey is pressed."""
        if not self._trigger_lock.acquire(blocking=False):
            log.info("A correction is already in progress; ignoring duplicate hotkey.")
            return
        try:
            # 1. Resolve target control (smart window selection)
            target_hwnd = resolve_target_control()

            # Focus it immediately so Ctrl+C hits the right place
            if target_hwnd:
                focus_window(target_hwnd)

            # 2. Save current clipboard state BEFORE we overwrite it
            saved_clipboard = get_clipboard_text()
            sequence_before = win32.GetClipboardSequenceNumber()

            # 3. Try to capture selection via Ctrl+C cycle (targeted to resolved window)
            _simulate_ctrl_c(target_hwnd)
            copy_wait_ms = int(self.config.get("app", {}).get("copy_wait_ms", 150))
            if copy_wait_ms < 50:
                copy_wait_ms = 50
            copy_deadline = time.monotonic() + (copy_wait_ms / 1000.0)
            while time.monotonic() < copy_deadline:
                if win32.GetClipboardSequenceNumber() != sequence_before:
                    break
                time.sleep(0.01)

            new_clipboard = get_clipboard_text()

            # If clipboard changed, use it (selection was copied). Otherwise fallback to original.
            copy_succeeded = win32.GetClipboardSequenceNumber() != sequence_before
            if copy_succeeded and new_clipboard is not None:
                text_to_fix = new_clipboard
            else:
                text_to_fix = saved_clipboard

            if not text_to_fix or len(text_to_fix.strip()) < 2:
                log.info("No text to process. Skipping.")
                self._trigger_lock.release()
                return

            # Capture target_hwnd and saved clipboard in local closure for worker thread
            paste_target = target_hwnd
            original_clipboard_for_restore = saved_clipboard

            # 4. Send to LLM (background thread so hotkey doesn't block)
            def llm_worker_inner():
                effective_cfg = self._get_effective_config()  # Resolve active LLM slot
                result = call_llm(effective_cfg, text_to_fix)

                if not result:
                    log.warning("LLM returned nothing — restoring original clipboard.")
                    set_clipboard_text(original_clipboard_for_restore or "")
                    return

                # Only overwrite clipboard RIGHT BEFORE pasting (not immediately after LLM returns)
                # This preserves user's clipboard until we're sure we have corrected text to paste

                # Place corrected text on clipboard RIGHT BEFORE pasting (preserves original until now)
                if not set_clipboard_text(result):
                    log.error("Could not place corrected text on the clipboard.")
                    return

                # 6. Optional: paste into resolved target window
                paste_delay = self.config.get("app", {}).get("paste_delay_s", 0.2)
                auto_paste = self.config.get("app", {}).get("auto_paste", True)
                if auto_paste and paste_target:
                    # Focus the target window before pasting - verify success!
                    if focus_window(paste_target):
                        if paste_delay > 0:
                            time.sleep(paste_delay)
                        _simulate_ctrl_v(paste_target)
                    else:
                        log.warning(
                            "Failed to focus target window — text is on clipboard but auto-paste skipped."
                        )

                log.info(
                    f"Corrected text placed on clipboard. Length: {len(result)} chars"
                )

            def llm_worker():
                try:
                    llm_worker_inner()
                finally:
                    self._trigger_lock.release()

            threading.Thread(target=llm_worker, daemon=True).start()

        except Exception as e:
            log.error(f"Hotkey handler error: {e}", exc_info=True)
            self._trigger_lock.release()


# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SpellCheck Assistant")
    parser.add_argument(
        "--gui",
        action="store_true",
        dest="gui",
        help="Launch with the GUI window (default behavior)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Launch in headless tray mode without opening the GUI window",
    )
    args, _ = parser.parse_known_args()

    if args.gui or not args.headless:
        try:
            from gui_app import SpellCheckGUI

            cfg = load_config()
            # Create a single shared app instance for hotkey handling
            bg_app = SpellCheckApp()
            # Pass the live config ref and reload hook to GUI so settings propagate
            app = SpellCheckGUI(
                config=cfg,
                reload_callback=bg_app.reload_config,
            )
            app.run()
        except ImportError as e:
            print(f"GUI mode failed to load dependencies: {e}")
            sys.exit(1)
    else:
        print("SpellCheck app started (headless). Press Ctrl+Win+A to activate.")
        app = SpellCheckApp()

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Shutting down...")
