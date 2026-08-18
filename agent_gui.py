#!/usr/bin/env python3
"""
Computer Use Agent GUI — upgraded layout, live permissions, color logs, history.
Pure Tkinter/ttk. Keeps existing computer_use_agent.py / desktop_control.py interface.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

from computer_use_agent import ModelSelector, MODELS_DIR, ROOT
from desktop_control import DesktopTool

HISTORY_FILE = ROOT / "prompt_history.json"
MAX_HISTORY = 30


class AgentGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Computer Use Agent")
        self.root.geometry("1100x780")
        self.root.minsize(900, 620)

        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self.model_var = tk.StringVar(value="auto")
        self.steps_var = tk.StringVar(value="0")
        self.ctx_var = tk.StringVar(value="8192")
        self.tokens_var = tk.StringVar(value="900")
        self.status_var = tk.StringVar(value="Ready")
        self.perm_access_var = tk.StringVar(value="Accessibility: …")
        self.perm_screen_var = tk.StringVar(value="Screen Recording: …")
        self.advanced_visible = tk.BooleanVar(value=False)
        self.history: list[str] = []

        self._configure_styles()
        self._build_ui()
        self._load_models()
        self._load_history()
        self._refresh_permissions()
        self.root.after(100, self._poll_output)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, lambda: self.prompt_text.focus_set())

    # ------------------------------------------------------------------ styles
    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        # Dark-leaning professional developer palette
        bg = "#1e1e1e"
        panel = "#252526"
        accent = "#0e639c"
        accent_hover = "#1177bb"
        fg = "#d4d4d4"
        muted = "#858585"

        self.root.configure(bg=bg)
        style.configure(".", background=bg, foreground=fg, fieldbackground=panel)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg, font=("System", 11, "bold"))
        style.configure("TButton", padding=(12, 6))
        style.configure("Primary.TButton", background=accent, foreground="#ffffff", font=("System", 11, "bold"))
        style.map("Primary.TButton", background=[("active", accent_hover), ("disabled", "#3c3c3c")])
        style.configure("Danger.TButton", foreground="#f14c4c")
        style.configure("Muted.TLabel", foreground=muted)
        style.configure("StatusOK.TLabel", foreground="#4ec9b0")
        style.configure("StatusBad.TLabel", foreground="#f14c4c")
        style.configure("StatusWarn.TLabel", foreground="#dcdcaa")

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)  # output grows

        # === 1. Prompt card ===
        prompt_frame = ttk.LabelFrame(outer, text="What do you want me to do?", padding=10)
        prompt_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        prompt_frame.columnconfigure(0, weight=1)

        self.prompt_text = tk.Text(
            prompt_frame,
            height=5,
            wrap="word",
            font=("System", 12),
            bg="#252526",
            fg="#d4d4d4",
            insertbackground="#ffffff",
            relief="flat",
            padx=8,
            pady=6,
            highlightthickness=1,
            highlightbackground="#3c3c3c",
            highlightcolor="#0e639c",
        )
        self.prompt_text.grid(row=0, column=0, sticky="nsew")
        self.prompt_text.bind("<Control-Return>", lambda e: self.run_task())
        self.prompt_text.bind("<Command-Return>", lambda e: self.run_task())  # macOS
        self.prompt_text.bind("<Return>", self._on_return)

        hint = ttk.Label(
            prompt_frame,
            text="Examples: Open google.com and search…  ·  Test example.com for SQL injection  ·  List files in current directory",
            style="Muted.TLabel",
            wraplength=1000,
        )
        hint.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # History row
        hist_row = ttk.Frame(prompt_frame)
        hist_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(hist_row, text="History:", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        self.history_box = ttk.Combobox(hist_row, state="readonly", width=70)
        self.history_box.pack(side="left", fill="x", expand=True)
        self.history_box.bind("<<ComboboxSelected>>", self._on_history_select)
        ttk.Button(hist_row, text="Clear History", command=self._clear_history, width=12).pack(side="right", padx=(8, 0))

        # === 2. Controls + permissions ===
        controls = ttk.Frame(outer)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(4, weight=1)

        self.run_button = ttk.Button(controls, text="▶  Run Task", style="Primary.TButton", command=self.run_task, width=14)
        self.run_button.grid(row=0, column=0, padx=(0, 8))

        self.stop_button = ttk.Button(controls, text="⏹  Stop", style="Danger.TButton", command=self.stop_task, width=10, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=(0, 16))

        ttk.Button(controls, text="Check Permissions", command=self._refresh_permissions).grid(row=0, column=2, padx=(0, 8))

        self.status_label = ttk.Label(controls, textvariable=self.status_var)
        self.status_label.grid(row=0, column=5, sticky="e")

        # Permission badges
        perm_frame = ttk.Frame(outer)
        perm_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        self.access_label = ttk.Label(perm_frame, textvariable=self.perm_access_var)
        self.access_label.pack(side="left", padx=(0, 12))
        ttk.Button(perm_frame, text="Open Accessibility", command=lambda: self._open_settings("accessibility"), width=16).pack(side="left", padx=(0, 16))

        self.screen_label = ttk.Label(perm_frame, textvariable=self.perm_screen_var)
        self.screen_label.pack(side="left", padx=(0, 12))
        ttk.Button(perm_frame, text="Open Screen Recording", command=lambda: self._open_settings("screen_recording"), width=18).pack(side="left")

        # === 3. Output card ===
        output_frame = ttk.LabelFrame(outer, text="Output", padding=6)
        output_frame.grid(row=3, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self.output_text = tk.Text(
            output_frame,
            wrap="word",
            state="disabled",
            font=("Menlo", 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            relief="flat",
            padx=6,
            pady=4,
            highlightthickness=0,
        )
        self.output_text.grid(row=0, column=0, sticky="nsew")

        # Color tags for log levels
        self.output_text.tag_configure("info", foreground="#d4d4d4")
        self.output_text.tag_configure("action", foreground="#4fc1ff")
        self.output_text.tag_configure("error", foreground="#f14c4c")
        self.output_text.tag_configure("finish", foreground="#4ec9b0")
        self.output_text.tag_configure("header", foreground="#dcdcaa", font=("Menlo", 11, "bold"))

        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=scrollbar.set)

        # Empty state placeholder
        self._show_empty_state()

        # === 4. Bottom toolbar ===
        bottom = ttk.Frame(outer)
        bottom.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(2, weight=1)

        ttk.Button(bottom, text="Clear Output", command=self.clear_output).pack(side="left")
        ttk.Button(bottom, text="Copy Last", command=self._copy_last).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Open Output Folder", command=self._open_output_folder).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Screenshots…", command=self._manage_screenshots).pack(side="left", padx=(8, 0))

        ttk.Checkbutton(
            bottom,
            text="Advanced options",
            variable=self.advanced_visible,
            command=self._toggle_advanced,
        ).pack(side="right")

        # Advanced drawer (hidden by default)
        self.advanced_frame = ttk.Frame(outer)
        # not packed until toggled

        adv_inner = ttk.Frame(self.advanced_frame)
        adv_inner.pack(fill="x", pady=(8, 0))

        ttk.Label(adv_inner, text="Model:").pack(side="left", padx=(0, 4))
        self.model_box = ttk.Combobox(adv_inner, textvariable=self.model_var, state="readonly", width=42)
        self.model_box.pack(side="left", padx=(0, 16))

        ttk.Label(adv_inner, text="Max steps (0=∞):").pack(side="left", padx=(0, 4))
        ttk.Entry(adv_inner, textvariable=self.steps_var, width=6).pack(side="left", padx=(0, 12))

        ttk.Label(adv_inner, text="Ctx:").pack(side="left", padx=(0, 4))
        ttk.Entry(adv_inner, textvariable=self.ctx_var, width=6).pack(side="left", padx=(0, 12))

        ttk.Label(adv_inner, text="Max tokens:").pack(side="left", padx=(0, 4))
        ttk.Entry(adv_inner, textvariable=self.tokens_var, width=6).pack(side="left")

        ttk.Label(
            bottom,
            text="⌘/Ctrl+Enter run  ·  Shift+Enter newline",
            style="Muted.TLabel",
        ).pack(side="right", padx=(0, 12))

    # ------------------------------------------------------------------ helpers
    def _show_empty_state(self) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("end", "Ready.\n\nPaste a task above and press Run (or ⌘/Ctrl+Enter).\n", "info")
        self.output_text.configure(state="disabled")

    def _on_return(self, event) -> str | None:
        if not (event.state & 0x1):  # Shift not held
            self.run_task()
            return "break"
        return None

    def _toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_frame.grid(row=5, column=0, sticky="ew")
        else:
            self.advanced_frame.grid_remove()

    def _load_models(self) -> None:
        selector = ModelSelector(MODELS_DIR)
        values = ["auto (recommended)"]
        for path in selector.all_models():
            if selector.detect_incomplete_shards(path):
                continue
            values.append(str(path.relative_to(ROOT)))
        self.model_box["values"] = values
        self.model_var.set(values[0] if values else "auto")

    def _load_history(self) -> None:
        try:
            if HISTORY_FILE.exists():
                data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.history = [str(x) for x in data][:MAX_HISTORY]
        except Exception:
            self.history = []
        self._refresh_history_box()

    def _save_history(self) -> None:
        try:
            HISTORY_FILE.write_text(json.dumps(self.history[:MAX_HISTORY], indent=2), encoding="utf-8")
        except Exception:
            pass

    def _refresh_history_box(self) -> None:
        self.history_box["values"] = self.history
        if self.history:
            self.history_box.set("")

    def _on_history_select(self, _event=None) -> None:
        val = self.history_box.get()
        if val:
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.insert("1.0", val)

    def _clear_history(self) -> None:
        self.history = []
        self._save_history()
        self._refresh_history_box()

    def _add_to_history(self, prompt: str) -> None:
        prompt = prompt.strip()
        if not prompt:
            return
        if prompt in self.history:
            self.history.remove(prompt)
        self.history.insert(0, prompt)
        self.history = self.history[:MAX_HISTORY]
        self._save_history()
        self._refresh_history_box()

    def _refresh_permissions(self) -> None:
        # Accessibility
        try:
            ok = DesktopTool.has_accessibility_access()
            if ok:
                self.perm_access_var.set("Accessibility: ✓ granted")
                self.access_label.configure(style="StatusOK.TLabel")
            else:
                self.perm_access_var.set("Accessibility: ✗ missing")
                self.access_label.configure(style="StatusBad.TLabel")
        except Exception:
            self.perm_access_var.set("Accessibility: ?")
            self.access_label.configure(style="StatusWarn.TLabel")

        # Screen Recording — best-effort (no reliable preflight on all macOS versions)
        # We surface the open-settings button and note that a real check happens on first screenshot.
        self.perm_screen_var.set("Screen Recording: check on first screenshot")
        self.screen_label.configure(style="StatusWarn.TLabel")

        self.status_var.set("Permissions refreshed")

    def _open_settings(self, panel: str) -> None:
        try:
            msg = DesktopTool.open_settings_panel(panel)
            self.append_output(f"[system] {msg}\n", "info")
            self.status_var.set(f"Opened {panel} settings")
        except Exception as exc:
            messagebox.showerror("Settings", str(exc))

    def _build_command(self, prompt: str) -> list[str]:
        model = self.model_var.get().replace(" (recommended)", "")
        return [
            sys.executable,
            str(ROOT / "computer_use_agent.py"),
            "--max-steps", self.steps_var.get() or "0",
            "--ctx-size", self.ctx_var.get() or "8192",
            "--max-tokens", self.tokens_var.get() or "900",
            "--command-timeout", "60",
            "--model", model,
            prompt,
        ]

    # ------------------------------------------------------------------ run / stop
    def run_task(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showerror("Busy", "A task is already running.")
            return

        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showerror("Empty Prompt", "Type what you want me to do.")
            return

        self._add_to_history(prompt)
        command = self._build_command(prompt)

        self.append_output("\n" + "=" * 64 + "\n", "header")
        self.append_output(f"Task: {prompt}\n", "header")
        self.append_output("=" * 64 + "\n\n", "header")

        self.status_var.set("Running…")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        self.process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self.reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.reader_thread.start()

    def _read_process_output(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            self.output_queue.put(("line", line))
        code = self.process.wait()
        self.output_queue.put(("done", str(code)))

    def _poll_output(self) -> None:
        while True:
            try:
                kind, payload = self.output_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                tag = self._classify_line(payload)
                self.append_output(payload, tag)
            elif kind == "done":
                code = int(payload)
                self.status_var.set(f"Done (exit {code})")
                self.run_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.process = None
                if code != 0:
                    self.append_output(f"\n[process exited with code {code}]\n", "error")
        self.root.after(100, self._poll_output)

    def _classify_line(self, line: str) -> str:
        lower = line.lower()
        if any(k in lower for k in ("error", "exception", "traceback", "failed", "permission")):
            return "error"
        if any(k in lower for k in ("finish", "completed", "done", "success")):
            return "finish"
        if any(k in lower for k in ("action", "tool", "calling", "executing", "step")):
            return "action"
        return "info"

    def stop_task(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.append_output("\n[Task stopped by user]\n", "error")
            self.status_var.set("Stopped")
        except ProcessLookupError:
            pass

    def append_output(self, text: str, tag: str = "info") -> None:
        self.output_text.configure(state="normal")
        self.output_text.insert("end", text, tag)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def clear_output(self) -> None:
        self._show_empty_state()

    def _copy_last(self) -> None:
        content = self.output_text.get("1.0", "end").strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("Copied output to clipboard")

    def _open_output_folder(self) -> None:
        out = ROOT / "output"
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run(["/usr/bin/open", str(out)], check=False)

    def _manage_screenshots(self) -> None:
        desktop_dir = ROOT / "output" / "desktop"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(desktop_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            messagebox.showinfo("Screenshots", "No screenshots yet.")
            return
        msg = f"{len(files)} screenshot(s) in output/desktop/\n\nNewest: {files[0].name}"
        choice = messagebox.askyesnocancel(
            "Screenshots",
            msg + "\n\nYes = open folder\nNo = delete all\nCancel = dismiss",
        )
        if choice is True:
            subprocess.run(["/usr/bin/open", str(desktop_dir)], check=False)
        elif choice is False:
            for f in files:
                try:
                    f.unlink()
                except Exception:
                    pass
            self.status_var.set("Deleted screenshots")

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Quit", "A task is running. Stop it and close?"):
                return
            self.stop_task()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    AgentGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
