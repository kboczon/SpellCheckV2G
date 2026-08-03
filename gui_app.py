"""SpellCheck GUI Application with System Tray Integration."""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import logging
import threading
import os
import sys

log = logging.getLogger("spellcheck.gui")

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    import pystray
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False
    print("Warning: pystray not installed. Tray icon will be unavailable.")


class SpellCheckGUI:
    """Main GUI application for SpellCheck."""
    
    def __init__(self, config=None, reload_callback=None):
        """
        Args:
            config: Pre-loaded config dict (from main.py). Used as live source of truth.
            reload_callback: Optional callable invoked after settings are saved so the parent
                             can re-read config from disk and update its own state.
        """
        self.root = tk.Tk()
        self.root.title("SpellCheck Assistant")
        self.root.geometry("600x500")
        self.root.minsize(400, 300)
        
        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Config — use passed-in dict as source of truth (avoids double-loading)
        self.config = config or self.load_config()
        self.reload_callback = reload_callback
        self.show_on_tray_click = bool(
            self.config.get("app", {}).get("show_on_tray_click", True)
        )
        self.start_minimized = bool(
            self.config.get("app", {}).get("start_minimized", False)
        )
        
        # State variables
        self.is_correcting = False
        self.status_text = tk.StringVar(value="Ready")
        
        # Create UI components
        self._create_menu()
        self._create_toolbar()
        self._create_main_area()
        self._create_status_bar()
        
        # Bind events
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def _default_config_loader(self):
        """Fallback config loader."""
        return {
            "app": {"hotkey": "ctrl+win+a"},
            "llm": {"provider": "local"}
        }
    
    def load_config(self):
        """Load configuration from file, with LLM slot migration."""
        try:
            import main as _main_module  # access shared config functions
            return _main_module.load_config()
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
        return self._default_config_loader()
    
    def _create_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Settings", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Clear Text", command=self.clear_text)
        edit_menu.add_separator()
        edit_menu.add_command(label="Copy to Clipboard", command=self.copy_to_clipboard)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Open Log File", command=self.open_log_file)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def _create_toolbar(self):
        """Create toolbar with action buttons."""
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(fill=tk.X)
        
        ttk.Button(toolbar, text="🔍 Correct Text", command=self.correct_text).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(toolbar, text="📋 Paste & Correct", command=self.paste_and_correct).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Separator(toolbar, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="⚙️ Settings", command=self.open_settings).pack(side=tk.LEFT)
    
    def _create_main_area(self):
        """Create main text editing area."""
        # Text widget with scrollbars
        self.text_frame = ttk.Frame(self.root)
        self.text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create scrolled text widget
        self.text_area = scrolledtext.ScrolledText(
            self.text_frame,
            wrap=tk.WORD,
            font=("Consolas", 11),
            undo=True,
            autoseparators=True
        )
        self.text_area.pack(fill=tk.BOTH, expand=True)
        
        # Add placeholder text
        self.text_area.insert(tk.END, 
            "Paste or type your text here...\n\n"
            "Then click 'Correct Text' to fix spelling and grammar errors."
        )
        self.text_area.tag_add("placeholder", "1.0", tk.END)
        self.text_area.tag_config("placeholder", foreground="gray")
        
        # Bind focus events for placeholder
        self.text_area.bind("<FocusIn>", self._on_focus_in)
        self.text_area.bind("<FocusOut>", self._on_focus_out)
    
    def _create_status_bar(self):
        """Create status bar at bottom."""
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(
            self.status_frame, 
            textvariable=self.status_text,
            padding=5
        )
        self.status_label.pack(side=tk.LEFT)
        
        # Progress indicator (hidden by default)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.status_frame,
            variable=self.progress_var,
            mode='indeterminate',
            length=200
        )
    
    def _on_focus_in(self, event):
        """Remove placeholder text when focused."""
        if self.text_area.get("1.0", tk.END).strip() == "":
            self.text_area.delete("1.0", tk.END)
            self.text_area.tag_remove("placeholder", "1.0", tk.END)
    
    def _on_focus_out(self, event):
        """Add placeholder text when empty and unfocused."""
        if not self.text_area.get("1.0", tk.END).strip():
            self.text_area.insert(tk.END, 
                "Paste or type your text here...\n\n"
                "Then click 'Correct Text' to fix spelling and grammar errors."
            )
            self.text_area.tag_add("placeholder", "1.0", tk.END)
    
    def clear_text(self):
        """Clear the text area."""
        self.text_area.delete("1.0", tk.END)
    
    def copy_to_clipboard(self):
        """Copy current text to clipboard."""
        text = self.get_current_text()
        if text:
            try:
                import main as _main_module
                if not _main_module.set_clipboard_text(text):
                    raise RuntimeError("Windows clipboard is currently unavailable")
                self.status_text.set("Copied to clipboard")
                self.root.after(2000, lambda: self.status_text.set("Ready"))
            except Exception as exc:
                messagebox.showwarning("Clipboard", f"Could not copy text: {exc}")
    
    def get_current_text(self):
        """Get current text from text area."""
        if self.text_area.tag_ranges("placeholder"):
            return ""
        return self.text_area.get("1.0", tk.END).strip()
    
    def paste_and_correct(self):
        """Paste from clipboard and correct."""
        try:
            import main as _main_module
            clipboard_text = _main_module.get_clipboard_text()
            if clipboard_text:
                self.text_area.delete("1.0", tk.END)
                self.text_area.tag_remove("placeholder", "1.0", tk.END)
                self.text_area.insert(tk.END, clipboard_text)
                self.correct_text()
            else:
                messagebox.showwarning("Warning", "Clipboard has no text")
        except (tk.TclError, RuntimeError):
            messagebox.showwarning("Warning", "Clipboard is empty")
    
    def correct_text(self):
        """Correct the text using LLM."""
        if self.is_correcting:
            return
            
        text = self.get_current_text()
        if not text or len(text) < 2:
            messagebox.showinfo("Info", "Please enter some text to correct")
            return
        
        # Disable UI during correction
        self.is_correcting = True
        self.status_text.set("Correcting...")
        self.progress_bar.pack(side=tk.LEFT, padx=10)
        self.progress_bar.start(10)
        
        # Run correction in background thread
        threading.Thread(target=self._correct_in_thread, args=(text,), daemon=True).start()
    
    def _correct_in_thread(self, text):
        """Run LLM correction in background thread."""
        try:
            # Use lazy import to avoid circular imports at module load time
            import sys as _sys
            if 'main' not in _sys.modules:
                import main as _main_module
            else:
                _main_module = _sys.modules['main']
            
            effective_cfg = _main_module.get_active_llm_config(self.config)
            result = _main_module.call_llm(effective_cfg, text)
            
            if result:
                self.root.after(0, lambda r=result: self._update_text(r))
            else:
                log_path = _main_module.get_log_path()
                self.root.after(
                    0,
                    lambda p=log_path: self._show_error(
                        f"LLM returned no correction.\n\nDetailed error log:\n{p}"
                    ),
                )
                
        except Exception as e:
            log.exception("GUI correction failed")
            self.root.after(0, lambda e=e: self._show_error(f"Error: {str(e)}"))
    
    def _update_text(self, corrected_text):
        """Update text area with corrected text."""
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, corrected_text)
        self.status_text.set("Correction complete")
        self._finish_correction()
        self.root.after(2000, lambda: self.status_text.set("Ready"))
    
    def _show_error(self, error_msg):
        """Show error message."""
        if "Detailed error log:" not in error_msg:
            error_msg += f"\n\nDetailed error log:\n{self._get_log_path()}"
        messagebox.showerror("Error", error_msg)
        self.status_text.set("Error occurred")
        self._finish_correction()

    def _finish_correction(self):
        """Restore GUI state after a background correction finishes."""
        self.is_correcting = False
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
    
    def open_settings(self):
        """Open settings dialog. Reloads config after save so changes propagate."""
        try:
            from settings_dialog import SettingsDialog
            # Reload from disk first so settings shows latest values (incl. LLM slots)
            fresh_config = self.load_config()
            dialog = SettingsDialog(self.root, fresh_config)
            # Wait for the dialog to close (grab_set makes it modal anyway)
            self.root.wait_window(dialog.dialog)
            # After closing, reload config from disk and notify parent
            self.config = self.load_config()
            app_cfg = self.config.get("app", {})
            self.show_on_tray_click = bool(app_cfg.get("show_on_tray_click", True))
            self.start_minimized = bool(app_cfg.get("start_minimized", False))
            if self.reload_callback:
                try:
                    self.reload_callback()
                except Exception as e:
                    log.error(f"reload_callback failed: {e}")
        except ImportError:
            messagebox.showwarning("Warning", "Settings dialog not available yet")
    
    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About SpellCheck Assistant",
            "SpellCheck Assistant v1.3\n\n"
            "A lightweight tool for quick text correction using AI.\n"
            "Features:\n"
            "- Global hotkey support (Ctrl+Win+A)\n"
            "- Local or remote LLM support\n"
            "- Auto-paste capability\n\n"
            f"Built with Python and tkinter.\n\nLog file:\n{self._get_log_path()}"
        )

    def _get_log_path(self):
        try:
            import main as _main_module
            return _main_module.get_log_path()
        except Exception:
            return os.path.join(os.path.dirname(__file__), "spellcheck.log")

    def open_log_file(self):
        """Open the persistent diagnostic log in the default text editor."""
        path = self._get_log_path()
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Log File", f"Could not open log file:\n{path}\n\n{exc}")
    
    def on_close(self):
        """Handle window close event."""
        if messagebox.askokcancel("Quit", "Do you want to quit SpellCheck Assistant?"):
            self.root.destroy()
            sys.exit(0)
    
    def run_minimized_to_tray(self):
        """Hide the main window and show the tray icon."""
        self.root.withdraw()
        
        if HAS_PYSTRAY:
            self._create_tray_icon()
        else:
            print("Tray icon unavailable. Running in background.")
            self.root.after(100, lambda: self.root.iconify())
    
    def _create_tray_icon(self):
        """Create system tray icon."""
        from PIL import Image, ImageDraw
        import io
        
        # Create simple icon programmatically
        icon_image = Image.new('RGB', (64, 64), color=(70, 130, 180))
        draw = ImageDraw.Draw(icon_image)
        draw.text((20, 25), "SC", fill=(255, 255, 255))
        
        def show_window(icon, item):
            """Show main window when tray icon is clicked."""
            if not self.show_on_tray_click:
                return
            self.root.after(0, self.show_window)
            
        def quit_app(icon, item):
            """Quit application from tray menu."""
            icon.stop()
            self.root.after(0, self._quit_without_prompt)
        
        # Create tray menu
        menu = pystray.Menu(
            pystray.MenuItem('Show', show_window, default=True),
            pystray.MenuItem(
                'Settings',
                lambda i, m: self.root.after(0, self._show_settings_from_tray),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Exit', quit_app)
        )
        
        # Create and start tray icon
        self.tray_icon = pystray.Icon(
            "spellcheck",
            icon_image,
            "SpellCheck Assistant",
            menu
        )
        
        # Start tray in background thread
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self):
        """Restore and activate the GUI from the tray or taskbar."""
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.after_idle(self.root.focus_force)

    def _show_settings_from_tray(self):
        self.show_window()
        self.open_settings()

    def _quit_without_prompt(self):
        self.root.destroy()
    
    def run(self):
        """Start the GUI application."""
        if HAS_PYSTRAY and not getattr(self, "tray_icon", None):
            self._create_tray_icon()
        if self.start_minimized:
            self.root.withdraw()
        else:
            self.show_window()
        self.root.mainloop()


if __name__ == "__main__":
    app = SpellCheckGUI()
    app.run()
