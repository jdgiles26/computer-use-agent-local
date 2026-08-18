#!/usr/bin/env python3
"""
Computer Use Agent GUI — full UX upgrade (pure Tkinter/ttk).

Features:
- Live step timeline from agent [step N] lines
- Permission badges + open Settings
- Color-coded logs + filter chips
- Compact last-action / working-memory pane
- Screenshot list strip (open on click)
- Prompt history + favorites / quick-re-run chips
- Collapsible Advanced (model, steps, ctx, tokens, reviewer)
- Adaptive density (compact / detailed)
- Progressive Tools reference drawer
- Copy last / open output folder / better empty states
"""

from __future__ import annotations

import json
import os
import queue
import re
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
FAVORITES_FILE = ROOT / "prompt_favorites.json"
MAX_HISTORY = 30
MAX_FAVORITES = 12
STEP_RE = re.compile(r"\[step\s+(\d+)\]\s+(\S+)\s*(.*)", re.I)
REASON_RE = re.compile(r"^\s*reason:\s*(.+)", re.I)
REPAIR_RE = re.compile(r"repaired action|self-correcting|repair_|validation_error|pattern warning|stall warning", re.I)


class AgentGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Computer Use Agent")
        self.root.geometry("1180x860")
        self.root.minsize(960, 680)

        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self.model_var = tk.StringVar(value="auto")
        self.reviewer_var = tk.StringVar(value="")
        self.steps_var = tk.StringVar(value="0")
        self.ctx_var = tk.StringVar(value="8192")
        self.tokens_var = tk.StringVar(value="900")
        self.status_var = tk.StringVar(value="Ready")
        self.step_var = tk.StringVar(value="Step: —")
        self.action_var = tk.StringVar(value="Action: —")
        self.last_var = tk.StringVar(value="Last: —")
        self.perm_access_var = tk.StringVar(value="Accessibility: …")
        self.perm_screen_var = tk.StringVar(value="Screen Recording: …")
        self.advanced_visible = tk.BooleanVar(value=False)
        self.tools_visible = tk.BooleanVar(value=False)
        self.compact_density = tk.BooleanVar(value=False)
        self.filter_info = tk.BooleanVar(value=True)
        self.filter_action = tk.BooleanVar(value=True)
        self.filter_error = tk.BooleanVar(value=True)
        self.filter_finish = tk.BooleanVar(value=True)

        self.history: list[str] = []
        self.favorites: list[str] = []
        self.step_count = 0
        self.start_time: float | None = None
        self._all_lines: list[tuple[str, str]] = []  # (tag, text) for re-filter

        self._configure_styles()
        self._build_ui()
        self._load_models()
        self._load_history()
        self._load_favorites()
        self._refresh_permissions()
        self._refresh_screenshots()
        self.root.after(100, self._poll_output)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, lambda: self.prompt_text.focus_set())

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        bg, panel, accent, accent_h, fg, muted = (
            "#1e1e1e", "#252526", "#0e639c", "#1177bb", "#d4d4d4", "#858585"
        )
        self.root.configure(bg=bg)
        style.configure(".", background=bg, foreground=fg, fieldbackground=panel)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg, font=("System", 11, "bold"))
        style.configure("TButton", padding=(10, 5))
        style.configure("Primary.TButton", background=accent, foreground="#fff", font=("System", 11, "bold"))
        style.map("Primary.TButton", background=[("active", accent_h), ("disabled", "#3c3c3c")])
        style.configure("Danger.TButton", foreground="#f14c4c")
        style.configure("Chip.TButton", padding=(6, 2))
        style.configure("Muted.TLabel", foreground=muted)
        style.configure("StatusOK.TLabel", foreground="#4ec9b0")
        style.configure("StatusBad.TLabel", foreground="#f14c4c")
        style.configure("StatusWarn.TLabel", foreground="#dcdcaa")
        style.configure("Action.TLabel", foreground="#4fc1ff")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        # --- Prompt ---
        pf = ttk.LabelFrame(outer, text="What do you want me to do?", padding=8)
        pf.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        pf.columnconfigure(0, weight=1)

        self.prompt_text = tk.Text(
            pf, height=4, wrap="word", font=("System", 12),
            bg="#252526", fg="#d4d4d4", insertbackground="#fff",
            relief="flat", padx=8, pady=6,
            highlightthickness=1, highlightbackground="#3c3c3c", highlightcolor="#0e639c",
        )
        self.prompt_text.grid(row=0, column=0, sticky="nsew")
        self.prompt_text.bind("<Control-Return>", lambda e: self.run_task())
        self.prompt_text.bind("<Command-Return>", lambda e: self.run_task())
        self.prompt_text.bind("<Return>", self._on_return)

        ttk.Label(
            pf,
            text="Examples: Open google.com and search… · Test example.com for SQL injection · List files",
            style="Muted.TLabel", wraplength=1000,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Favorites / quick chips
        self.fav_row = ttk.Frame(pf)
        self.fav_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        hist_row = ttk.Frame(pf)
        hist_row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(hist_row, text="History:", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        self.history_box = ttk.Combobox(hist_row, state="readonly", width=55)
        self.history_box.pack(side="left", fill="x", expand=True)
        self.history_box.bind("<<ComboboxSelected>>", self._on_history_select)
        ttk.Button(hist_row, text="★ Fav", command=self._add_favorite, width=8).pack(side="left", padx=(6, 0))
        ttk.Button(hist_row, text="Clear", command=self._clear_history, width=7).pack(side="left", padx=(4, 0))

        # --- Controls ---
        controls = ttk.Frame(outer)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.run_button = ttk.Button(controls, text="▶  Run Task", style="Primary.TButton", command=self.run_task, width=13)
        self.run_button.pack(side="left", padx=(0, 6))
        self.stop_button = ttk.Button(controls, text="⏹ Stop", style="Danger.TButton", command=self.stop_task, width=9, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="Check Permissions", command=self._refresh_permissions).pack(side="left", padx=(0, 10))
        ttk.Label(controls, textvariable=self.status_var).pack(side="right")

        # Permissions
        perm = ttk.Frame(outer)
        perm.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        self.access_label = ttk.Label(perm, textvariable=self.perm_access_var)
        self.access_label.pack(side="left", padx=(0, 8))
        ttk.Button(perm, text="Open Accessibility", command=lambda: self._open_settings("accessibility"), width=15).pack(side="left", padx=(0, 14))
        self.screen_label = ttk.Label(perm, textvariable=self.perm_screen_var)
        self.screen_label.pack(side="left", padx=(0, 8))
        ttk.Button(perm, text="Open Screen Recording", command=lambda: self._open_settings("screen_recording"), width=17).pack(side="left")

        # Step timeline + last action pane
        timeline = ttk.LabelFrame(outer, text="Live status", padding=6)
        timeline.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(timeline, textvariable=self.step_var).pack(side="left", padx=(0, 16))
        ttk.Label(timeline, textvariable=self.action_var, style="Action.TLabel").pack(side="left", padx=(0, 16))
        ttk.Label(timeline, textvariable=self.last_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)

        # --- Main output + right strip ---
        mid = ttk.Frame(outer)
        mid.grid(row=4, column=0, sticky="nsew")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)

        out_frame = ttk.LabelFrame(mid, text="Output", padding=4)
        out_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        out_frame.columnconfigure(0, weight=1)
        out_frame.rowconfigure(1, weight=1)

        # Filter chips
        filters = ttk.Frame(out_frame)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(filters, text="Show:", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        for label, var in (("info", self.filter_info), ("action", self.filter_action),
                           ("error", self.filter_error), ("finish", self.filter_finish)):
            ttk.Checkbutton(filters, text=label, variable=var, command=self._reapply_filters).pack(side="left", padx=2)
        ttk.Checkbutton(filters, text="Compact", variable=self.compact_density, command=self._toggle_density).pack(side="right")

        self.output_text = tk.Text(
            out_frame, wrap="word", state="disabled", font=("Menlo", 11),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white", relief="flat", padx=6, pady=4,
        )
        self.output_text.grid(row=1, column=0, sticky="nsew")
        for tag, color in (("info", "#d4d4d4"), ("action", "#4fc1ff"), ("error", "#f14c4c"),
                           ("finish", "#4ec9b0"), ("header", "#dcdcaa"), ("repair", "#ce9178")):
            self.output_text.tag_configure(tag, foreground=color)
        self.output_text.tag_configure("header", font=("Menlo", 11, "bold"))

        sb = ttk.Scrollbar(out_frame, orient="vertical", command=self.output_text.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=sb.set)

        # Right: screenshots strip
        right = ttk.LabelFrame(mid, text="Screenshots", padding=4)
        right.grid(row=0, column=1, sticky="ns")
        self.shot_list = tk.Listbox(
            right, height=18, width=22, bg="#252526", fg="#d4d4d4",
            selectbackground="#0e639c", relief="flat", font=("Menlo", 10),
        )
        self.shot_list.pack(fill="both", expand=True)
        self.shot_list.bind("<Double-Button-1>", self._open_selected_shot)
        ttk.Button(right, text="Refresh", command=self._refresh_screenshots).pack(fill="x", pady=(4, 0))
        ttk.Button(right, text="Open folder", command=lambda: subprocess.run(["/usr/bin/open", str(ROOT / "output" / "desktop")], check=False)).pack(fill="x", pady=(2, 0))

        self._show_empty_state()

        # --- Bottom toolbar ---
        bottom = ttk.Frame(outer)
        bottom.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(bottom, text="Clear Output", command=self.clear_output).pack(side="left")
        ttk.Button(bottom, text="Copy Last", command=self._copy_last).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="Open Output Folder", command=self._open_output_folder).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(bottom, text="Tools reference", variable=self.tools_visible, command=self._toggle_tools).pack(side="right", padx=(0, 8))
        ttk.Checkbutton(bottom, text="Advanced", variable=self.advanced_visible, command=self._toggle_advanced).pack(side="right", padx=(0, 8))
        ttk.Label(bottom, text="⌘/Ctrl+Enter run", style="Muted.TLabel").pack(side="right", padx=(0, 12))

        # Advanced drawer
        self.advanced_frame = ttk.Frame(outer)
        adv = ttk.Frame(self.advanced_frame)
        adv.pack(fill="x", pady=(6, 0))
        ttk.Label(adv, text="Model:").pack(side="left", padx=(0, 4))
        self.model_box = ttk.Combobox(adv, textvariable=self.model_var, state="readonly", width=36)
        self.model_box.pack(side="left", padx=(0, 10))
        ttk.Label(adv, text="Reviewer:").pack(side="left", padx=(0, 4))
        self.reviewer_box = ttk.Combobox(adv, textvariable=self.reviewer_var, state="readonly", width=18)
        self.reviewer_box.pack(side="left", padx=(0, 10))
        ttk.Label(adv, text="Max steps:").pack(side="left", padx=(0, 4))
        ttk.Entry(adv, textvariable=self.steps_var, width=5).pack(side="left", padx=(0, 8))
        ttk.Label(adv, text="Ctx:").pack(side="left", padx=(0, 4))
        ttk.Entry(adv, textvariable=self.ctx_var, width=5).pack(side="left", padx=(0, 8))
        ttk.Label(adv, text="Tokens:").pack(side="left", padx=(0, 4))
        ttk.Entry(adv, textvariable=self.tokens_var, width=5).pack(side="left")

        # Tools progressive disclosure
        self.tools_frame = ttk.LabelFrame(outer, text="Common tools (progressive disclosure)", padding=6)
        tools_text = (
            "Browser: browser_open · browser_snapshot · browser_click · browser_fill\n"
            "Desktop: desktop_screenshot · desktop_click · desktop_type_text · desktop_open_app\n"
            "Security: security_sql_inject_test · security_xss_test · security_headers_check · security_crawl\n"
            "DevTools: devtools_console_eval · devtools_network_get_requests · devtools_find_secrets\n"
            "System: shell · list_files · http_request · process_list · system_info\n"
            "Custom: define_action · list_custom_actions"
        )
        ttk.Label(self.tools_frame, text=tools_text, style="Muted.TLabel", justify="left").pack(anchor="w")

    # ---------- helpers ----------
    def _show_empty_state(self) -> None:
        self._all_lines.clear()
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        msg = "Ready.\n\nPaste a task and press Run (⌘/Ctrl+Enter).\n"
        self.output_text.insert("end", msg, "info")
        self.output_text.configure(state="disabled")
        self.step_var.set("Step: —")
        self.action_var.set("Action: —")
        self.last_var.set("Last: —")

    def _on_return(self, event) -> str | None:
        if not (event.state & 0x1):
            self.run_task()
            return "break"
        return None

    def _toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_frame.grid(row=6, column=0, sticky="ew")
        else:
            self.advanced_frame.grid_remove()

    def _toggle_tools(self) -> None:
        if self.tools_visible.get():
            self.tools_frame.grid(row=7, column=0, sticky="ew", pady=(4, 0))
        else:
            self.tools_frame.grid_remove()

    def _toggle_density(self) -> None:
        size = 10 if self.compact_density.get() else 11
        self.output_text.configure(font=("Menlo", size))

    def _load_models(self) -> None:
        selector = ModelSelector(MODELS_DIR)
        values = ["auto (recommended)"]
        for path in selector.all_models():
            if selector.detect_incomplete_shards(path):
                continue
            values.append(str(path.relative_to(ROOT)))
        self.model_box["values"] = values
        self.model_var.set(values[0] if values else "auto")
        rev = [""] + values
        self.reviewer_box["values"] = rev
        self.reviewer_var.set("")

    def _load_history(self) -> None:
        try:
            if HISTORY_FILE.exists():
                data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.history = [str(x) for x in data][:MAX_HISTORY]
        except Exception:
            self.history = []
        self.history_box["values"] = self.history

    def _save_history(self) -> None:
        try:
            HISTORY_FILE.write_text(json.dumps(self.history[:MAX_HISTORY], indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_favorites(self) -> None:
        try:
            if FAVORITES_FILE.exists():
                data = json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.favorites = [str(x) for x in data][:MAX_FAVORITES]
        except Exception:
            self.favorites = []
        self._render_favorite_chips()

    def _save_favorites(self) -> None:
        try:
            FAVORITES_FILE.write_text(json.dumps(self.favorites[:MAX_FAVORITES], indent=2), encoding="utf-8")
        except Exception:
            pass

    def _render_favorite_chips(self) -> None:
        for w in self.fav_row.winfo_children():
            w.destroy()
        ttk.Label(self.fav_row, text="Quick:", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        for fav in self.favorites[:8]:
            short = (fav[:42] + "…") if len(fav) > 42 else fav
            ttk.Button(
                self.fav_row, text=short, style="Chip.TButton",
                command=lambda p=fav: self._run_favorite(p),
            ).pack(side="left", padx=2)

    def _run_favorite(self, prompt: str) -> None:
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)
        self.run_task()

    def _add_favorite(self) -> None:
        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            return
        if prompt in self.favorites:
            self.favorites.remove(prompt)
        self.favorites.insert(0, prompt)
        self.favorites = self.favorites[:MAX_FAVORITES]
        self._save_favorites()
        self._render_favorite_chips()
        self.status_var.set("Added to favorites")

    def _on_history_select(self, _e=None) -> None:
        val = self.history_box.get()
        if val:
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.insert("1.0", val)

    def _clear_history(self) -> None:
        self.history = []
        self._save_history()
        self.history_box["values"] = []

    def _add_to_history(self, prompt: str) -> None:
        prompt = prompt.strip()
        if not prompt:
            return
        if prompt in self.history:
            self.history.remove(prompt)
        self.history.insert(0, prompt)
        self.history = self.history[:MAX_HISTORY]
        self._save_history()
        self.history_box["values"] = self.history

    def _refresh_permissions(self) -> None:
        try:
            ok = DesktopTool.has_accessibility_access()
            self.perm_access_var.set("Accessibility: ✓ granted" if ok else "Accessibility: ✗ missing")
            self.access_label.configure(style="StatusOK.TLabel" if ok else "StatusBad.TLabel")
        except Exception:
            self.perm_access_var.set("Accessibility: ?")
            self.access_label.configure(style="StatusWarn.TLabel")
        self.perm_screen_var.set("Screen Recording: check on first screenshot")
        self.screen_label.configure(style="StatusWarn.TLabel")
        self.status_var.set("Permissions refreshed")

    def _open_settings(self, panel: str) -> None:
        try:
            msg = DesktopTool.open_settings_panel(panel)
            self.append_output(f"[system] {msg}\n", "info")
        except Exception as exc:
            messagebox.showerror("Settings", str(exc))

    def _refresh_screenshots(self) -> None:
        self.shot_list.delete(0, "end")
        desktop = ROOT / "output" / "desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        files = sorted(desktop.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
        for f in files:
            self.shot_list.insert("end", f.name)

    def _open_selected_shot(self, _e=None) -> None:
        sel = self.shot_list.curselection()
        if not sel:
            return
        name = self.shot_list.get(sel[0])
        path = ROOT / "output" / "desktop" / name
        if path.exists():
            subprocess.run(["/usr/bin/open", str(path)], check=False)

    def _build_command(self, prompt: str) -> list[str]:
        model = self.model_var.get().replace(" (recommended)", "")
        cmd = [
            sys.executable, str(ROOT / "computer_use_agent.py"),
            "--max-steps", self.steps_var.get() or "0",
            "--ctx-size", self.ctx_var.get() or "8192",
            "--max-tokens", self.tokens_var.get() or "900",
            "--command-timeout", "60",
            "--model", model,
        ]
        rev = self.reviewer_var.get().replace(" (recommended)", "").strip()
        if rev:
            cmd.extend(["--reviewer-model", rev])
        cmd.append(prompt)
        return cmd

    def run_task(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showerror("Busy", "A task is already running.")
            return
        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showerror("Empty Prompt", "Type what you want me to do.")
            return
        self._add_to_history(prompt)
        self.step_count = 0
        self.start_time = time.time()
        self.append_output("\n" + "=" * 64 + "\n", "header")
        self.append_output(f"Task: {prompt}\n", "header")
        self.append_output("=" * 64 + "\n\n", "header")
        self.status_var.set("Running…")
        self.step_var.set("Step: 0")
        self.action_var.set("Action: starting…")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.process = subprocess.Popen(
            self._build_command(prompt), cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, start_new_session=True,
        )
        self.reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.reader_thread.start()

    def _read_process_output(self) -> None:
        assert self.process and self.process.stdout
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
                self._handle_line(payload)
            elif kind == "done":
                code = int(payload)
                elapsed = ""
                if self.start_time:
                    elapsed = f" · {time.time() - self.start_time:.1f}s"
                self.status_var.set(f"Done (exit {code}){elapsed}")
                self.run_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.process = None
                self._refresh_screenshots()
                if code != 0:
                    self.append_output(f"\n[process exited with code {code}]\n", "error")
        self.root.after(80, self._poll_output)

    def _handle_line(self, line: str) -> None:
        tag = self._classify_line(line)
        # Step timeline
        m = STEP_RE.search(line)
        if m:
            self.step_count = int(m.group(1))
            action = m.group(2)
            self.step_var.set(f"Step: {self.step_count}")
            self.action_var.set(f"Action: {action}")
            self.last_var.set(f"Last: {action} {m.group(3)[:80]}")
            tag = "action"
        rm = REASON_RE.match(line)
        if rm:
            self.last_var.set(f"Why: {rm.group(1)[:100]}")
            tag = "repair" if REPAIR_RE.search(line) else "info"
        if REPAIR_RE.search(line):
            tag = "repair"
            self.last_var.set(f"Repair: {line.strip()[:100]}")
        self.append_output(line, tag)

    def _classify_line(self, line: str) -> str:
        lower = line.lower()
        if REPAIR_RE.search(line):
            return "repair"
        if any(k in lower for k in ("error", "exception", "traceback", "failed", "permission")):
            return "error"
        if any(k in lower for k in ("finish", "completed", "task complete")):
            return "finish"
        if any(k in lower for k in ("[step", "action=", "tool", "calling")):
            return "action"
        return "info"

    def append_output(self, text: str, tag: str = "info") -> None:
        self._all_lines.append((tag, text))
        if not self._filter_allows(tag):
            return
        self.output_text.configure(state="normal")
        self.output_text.insert("end", text, tag)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def _filter_allows(self, tag: str) -> bool:
        if tag == "header":
            return True
        if tag == "repair":
            return self.filter_error.get() or self.filter_action.get()
        return {
            "info": self.filter_info.get(),
            "action": self.filter_action.get(),
            "error": self.filter_error.get(),
            "finish": self.filter_finish.get(),
        }.get(tag, True)

    def _reapply_filters(self) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        for tag, text in self._all_lines:
            if self._filter_allows(tag):
                self.output_text.insert("end", text, tag)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def stop_task(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.append_output("\n[Task stopped by user]\n", "error")
            self.status_var.set("Stopped")
        except ProcessLookupError:
            pass

    def clear_output(self) -> None:
        self._show_empty_state()

    def _copy_last(self) -> None:
        content = self.output_text.get("1.0", "end").strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("Copied output")

    def _open_output_folder(self) -> None:
        out = ROOT / "output"
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run(["/usr/bin/open", str(out)], check=False)

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
