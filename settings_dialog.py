"""Settings Dialog for SpellCheck Assistant — supports 2 LLM config slots."""
import tkinter as tk
from tkinter import ttk, messagebox
import os
import yaml


class SettingsDialog:
    """Modal dialog for configuring application settings with LLM slot management."""
    
    def __init__(self, parent, current_config):
        self.parent = parent
        self.current_config = current_config.copy()
        self._loaded_slot_num = None
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("540x580")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.resizable(False, False)
        
        # Center dialog on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # Handle window manager X button — close cleanly without saving
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        
        self._build_ui()
        self._load_values()
    
    def _get_llm_slots(self):
        """Get LLM slots config, migrating from old format if needed."""
        return self.current_config.get("llm_slots", {
            "active_slot": 1,
            "slots": {
                "slot1": {"name": "Slot 1", "provider": "openai", "base_url": "", "api_key": "", "model": "", "temperature": 0.3, "max_tokens": 4096, "verify_ssl": True},
                "slot2": {"name": "Slot 2", "provider": "openai", "base_url": "", "api_key": "", "model": "", "temperature": 0.3, "max_tokens": 4096, "verify_ssl": True}
            }
        })
    
    def _build_ui(self):
        """Build the settings UI layout."""
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ── App Settings Tab ────────────────────────────────
        app_frame = ttk.Frame(notebook)
        notebook.add(app_frame, text="App")
        
        ttk.Label(app_frame, text="Hotkey (format: ctrl+shift+a):").grid(row=0, column=0, sticky=tk.W, padx=10, pady=(10, 2))
        self.hotkey_var = tk.StringVar()
        ttk.Entry(app_frame, textvariable=self.hotkey_var).grid(row=0, column=1, padx=10, pady=(10, 2), sticky=tk.EW)
        
        ttk.Label(app_frame, text="Copy Wait (milliseconds):").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.copy_wait_var = tk.IntVar()
        ttk.Spinbox(app_frame, from_=50, to=1000, increment=50, textvariable=self.copy_wait_var).grid(row=1, column=1, sticky=tk.EW, padx=10, pady=5)
        
        ttk.Label(app_frame, text="Paste Delay (seconds):").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.paste_delay_var = tk.DoubleVar()
        scale_paste = ttk.Scale(app_frame, from_=0.0, to=2.0, variable=self.paste_delay_var)
        scale_paste.grid(row=2, column=1, sticky=tk.EW, padx=10, pady=5)
        self.paste_delay_label = ttk.Label(app_frame, textvariable=self.paste_delay_var)
        self.paste_delay_label.grid(row=2, column=2, padx=5, pady=5)
        
        self.auto_paste_var = tk.BooleanVar()
        ttk.Checkbutton(app_frame, text="Auto-paste corrected text", variable=self.auto_paste_var).grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=10, pady=5)
        
        self.start_minimized_var = tk.BooleanVar()
        ttk.Checkbutton(app_frame, text="Start minimized to tray", variable=self.start_minimized_var).grid(row=4, column=0, columnspan=3, sticky=tk.W, padx=10, pady=5)
        
        self.show_on_tray_click_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(app_frame, text="Show window when tray icon is clicked", variable=self.show_on_tray_click_var).grid(row=5, column=0, columnspan=3, sticky=tk.W, padx=10, pady=5)

        ttk.Label(app_frame, text="Maximum LLM attempts:").grid(row=6, column=0, sticky=tk.W, padx=10, pady=5)
        self.max_retries_var = tk.IntVar(value=3)
        ttk.Spinbox(app_frame, from_=1, to=10, textvariable=self.max_retries_var, width=8).grid(row=6, column=1, sticky=tk.W, padx=10, pady=5)

        ttk.Label(app_frame, text="Request timeout (seconds):").grid(row=7, column=0, sticky=tk.W, padx=10, pady=5)
        self.request_timeout_var = tk.IntVar(value=120)
        ttk.Spinbox(app_frame, from_=1, to=600, increment=5, textvariable=self.request_timeout_var, width=8).grid(row=7, column=1, sticky=tk.W, padx=10, pady=5)
        
        # ── LLM Slots Tab ───────────────────────────────────
        llm_frame = ttk.Frame(notebook)
        notebook.add(llm_frame, text="LLM Slots")
        
        # Slot selector at top
        slot_header = ttk.LabelFrame(llm_frame, text="Select Active Slot", padding=5)
        slot_header.grid(row=0, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=(10, 5))
        
        self.active_slot_var = tk.IntVar(value=1)
        ttk.Radiobutton(slot_header, text="Slot 1", variable=self.active_slot_var, value=1, command=self._switch_slot).grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Radiobutton(slot_header, text="Slot 2", variable=self.active_slot_var, value=2, command=self._switch_slot).grid(row=0, column=1, sticky=tk.W, padx=5)
        
        self.slot_active_label = ttk.Label(slot_header, text="(active)", foreground="green", font=("TkDefaultFont", 9, "bold"))
        self.slot_active_label.grid(row=0, column=2, padx=(0, 5))
        
        # Slot name
        slot_cfg_frame = ttk.LabelFrame(llm_frame, text="Slot Configuration", padding=5)
        slot_cfg_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=5)
        
        ttk.Label(slot_cfg_frame, text="Slot Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=(5, 2))
        self.slot_name_var = tk.StringVar()
        ttk.Entry(slot_cfg_frame, textvariable=self.slot_name_var).grid(row=0, column=1, sticky=tk.EW, padx=5, pady=(5, 2))
        
        # Provider
        ttk.Label(slot_cfg_frame, text="Provider:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.provider_var = tk.StringVar()
        self.provider_combo = ttk.Combobox(slot_cfg_frame, textvariable=self.provider_var, values=["openai", "local"], state="readonly")
        self.provider_combo.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        self.provider_combo.bind("<<ComboboxSelected>>", lambda e: self._on_provider_change())
        
        # Base URL / Endpoint
        ttk.Label(slot_cfg_frame, text="Base URL (endpoint):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.base_url_var = tk.StringVar()
        ttk.Entry(slot_cfg_frame, textvariable=self.base_url_var).grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # Model name
        ttk.Label(slot_cfg_frame, text="Model Name:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.model_var = tk.StringVar()
        ttk.Entry(slot_cfg_frame, textvariable=self.model_var).grid(row=3, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # API Key (only shown for openai provider)
        api_key_row = ttk.Frame(slot_cfg_frame)
        api_key_row.grid(row=4, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=(5, 0))
        self.api_key_label = ttk.Label(api_key_row, text="API Key:")
        self.api_key_label.pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(api_key_row, textvariable=self.api_key_var, show="*")
        self.api_key_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Max Tokens
        ttk.Label(slot_cfg_frame, text="Max Tokens:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.max_tokens_var = tk.IntVar()
        ttk.Spinbox(slot_cfg_frame, from_=256, to=16384, increment=256, textvariable=self.max_tokens_var).grid(row=5, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # Temperature
        ttk.Label(slot_cfg_frame, text="Temperature (0.0-1.0):").grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
        self.temp_var = tk.DoubleVar()
        scale_temp = ttk.Scale(slot_cfg_frame, from_=0.0, to=1.0, variable=self.temp_var, orient=tk.HORIZONTAL)
        scale_temp.grid(row=6, column=1, sticky=tk.EW, padx=5, pady=5)
        self.temp_label = ttk.Label(slot_cfg_frame, textvariable=self.temp_var)
        self.temp_label.grid(row=6, column=2, padx=(0, 5), pady=5)

        self.verify_ssl_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            slot_cfg_frame,
            text="Verify HTTPS certificates (disable only for inspected networks)",
            variable=self.verify_ssl_var,
        ).grid(row=7, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)

        self.thinking_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            slot_cfg_frame,
            text="Use Thinking Mode (extended reasoning — slower but more thorough)",
            variable=self.thinking_mode_var,
        ).grid(row=8, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        
        # Bind scale updates
        self.paste_delay_var.trace_add("write", lambda *args: self.paste_delay_label.config(text=f"{self.paste_delay_var.get():.1f}s"))
        self.temp_var.trace_add("write", lambda *args: self.temp_label.config(text=f"{self.temp_var.get():.2f}"))
        
        # ── Buttons ────────────────────────────────────────
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        ttk.Button(btn_frame, text="Save & Close", command=self.save_and_close).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=(0, 10))
        
        # Configure grid weights for resizing
        app_frame.columnconfigure(1, weight=1)
        llm_frame.columnconfigure(1, weight=1)
        slot_cfg_frame.columnconfigure(1, weight=1)
    
    def _on_provider_change(self):
        """Show/hide API key field based on provider selection."""
        if self.provider_var.get() == "openai":
            self.api_key_label.pack(side=tk.LEFT)
            self.api_key_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        else:
            self.api_key_label.pack_forget()
            self.api_key_entry.pack_forget()
    
    def _switch_slot(self):
        """Switch between slot configurations in the UI."""
        # Radiobutton updates active_slot_var before invoking this callback, so
        # save the slot whose values are actually displayed, not the new slot.
        self._save_current_slot_to_temp(self._loaded_slot_num)
        self._load_selected_slot()
    
    def _build_slot_key(self, slot_num):
        return f"slot{slot_num}"
    
    def _get_slot_config(self, slot_num):
        slots_cfg = self._get_llm_slots()
        slot_key = self._build_slot_key(slot_num)
        return slots_cfg.get("slots", {}).get(slot_key, {})
    
    def _save_current_slot_to_temp(self, slot_num=None):
        """Save displayed UI values to the slot they were loaded from."""
        if slot_num is None:
            slot_num = self._loaded_slot_num or self.active_slot_var.get()
        slot_key = self._build_slot_key(slot_num)
        slots_cfg = self.current_config.setdefault("llm_slots", {
            "active_slot": 1,
            "slots": {"slot1": {}, "slot2": {}}
        })
        slots = slots_cfg.setdefault("slots", {})
        
        # Build slot config from current UI values
        provider = self.provider_var.get() or "openai"
        slot_data = {
            "name": self.slot_name_var.get() or f"Slot {slot_num}",
            "provider": provider,
            "base_url": self.base_url_var.get(),
            "api_key": self.api_key_var.get(),
            "model": self.model_var.get(),
            "temperature": float(self.temp_var.get()),
            "max_tokens": int(self.max_tokens_var.get()),
            "verify_ssl": bool(self.verify_ssl_var.get()),
            "use_thinking_mode": bool(self.thinking_mode_var.get()),
        }
        
        # Preserve existing data and merge with current values
        existing = slots.get(slot_key, {})
        slots[slot_key] = {**existing, **slot_data}
    
    def _load_selected_slot(self):
        """Load selected slot config into UI fields."""
        slot_num = self.active_slot_var.get()
        slot_cfg = self._get_slot_config(slot_num)
        self._loaded_slot_num = slot_num
        
        # Use defaults if slot is empty
        provider = slot_cfg.get("provider", "openai")
        
        self.slot_name_var.set(slot_cfg.get("name", f"Slot {slot_num}"))
        self.provider_var.set(provider)
        self.base_url_var.set(slot_cfg.get("base_url", ""))
        self.model_var.set(slot_cfg.get("model", ""))
        self.api_key_var.set(slot_cfg.get("api_key", ""))
        self.verify_ssl_var.set(bool(slot_cfg.get("verify_ssl", True)))
        self.thinking_mode_var.set(bool(slot_cfg.get("use_thinking_mode", False)))
        
        try:
            self.max_tokens_var.set(int(slot_cfg.get("max_tokens", 4096)))
        except ValueError:
            self.max_tokens_var.set(4096)
        
        try:
            self.temp_var.set(float(slot_cfg.get("temperature", 0.3)))
        except ValueError:
            self.temp_var.set(0.3)
        
        # Update API key visibility based on provider
        self._on_provider_change()
    
    def _load_values(self):
        """Populate UI with current config values."""
        app_cfg = self.current_config.get("app", {})
        
        self.hotkey_var.set(app_cfg.get("hotkey", "ctrl+shift+a"))
        self.copy_wait_var.set(int(app_cfg.get("copy_wait_ms", 150)))
        self.paste_delay_var.set(float(app_cfg.get("paste_delay_s", 0.2)))
        self.auto_paste_var.set(bool(app_cfg.get("auto_paste", True)))
        self.start_minimized_var.set(bool(app_cfg.get("start_minimized", False)))
        self.show_on_tray_click_var.set(bool(app_cfg.get("show_on_tray_click", True)))
        self.max_retries_var.set(int(app_cfg.get("max_retries", 3)))
        self.request_timeout_var.set(int(app_cfg.get("request_timeout_s", 120)))
        
        # Load LLM slots
        slots_cfg = self._get_llm_slots()
        active_slot = int(slots_cfg.get("active_slot", 1))
        self.active_slot_var.set(active_slot)
        
        # Load the active slot into UI
        self._load_selected_slot()
    
    def save_and_close(self):
        """Save settings and close dialog."""
        try:
            # Save current slot values first (in case user switched away from it)
            self._save_current_slot_to_temp()
            self.current_config["llm_slots"]["active_slot"] = int(
                self.active_slot_var.get()
            )
            
            # Build new config structure preserving existing keys
            new_config = dict(self.current_config)  # shallow copy of top-level
            
            # Update app settings while preserving existing app values
            app_cfg = dict(self.current_config.get("app", {}))
            app_cfg.update({
                "hotkey": self.hotkey_var.get(),
                "copy_wait_ms": int(self.copy_wait_var.get()),
                "paste_delay_s": float(self.paste_delay_var.get()),
                "auto_paste": bool(self.auto_paste_var.get()),
                "start_minimized": bool(self.start_minimized_var.get()),
                "show_on_tray_click": bool(self.show_on_tray_click_var.get()),
                "max_retries": max(1, int(self.max_retries_var.get())),
                "request_timeout_s": max(1, int(self.request_timeout_var.get())),
            })
            new_config["app"] = app_cfg
            
            # LLM slots are already updated in current_config via _save_current_slot_to_temp
            
            # Preserve prompt from original config or use default
            new_config["prompt"] = self.current_config.get("prompt",
                "Please fix any spelling and grammar errors in the following text. Return only the corrected text, nothing else:\n\n{text}")
            
            # Write to config.yaml
            import main as _main_module
            _main_module.save_config(new_config)
            
            self.dialog.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
    
    def cancel(self):
        """Close dialog without saving."""
        self.dialog.destroy()
