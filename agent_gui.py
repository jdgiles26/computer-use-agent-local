#!/usr/bin/env python3
"""
Simplified Computer Use Agent GUI
Just type what you want and the agent figures it out.
"""

from __future__ import annotations

import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from computer_use_agent import ModelSelector, MODELS_DIR, ROOT
from desktop_control import DesktopTool


class AgentGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Computer Use Agent")
        self.root.geometry("1000x700")
        
        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        
        # Simple defaults - no need to configure
        self.model_var = tk.StringVar(value="auto")
        self.steps_var = tk.StringVar(value="0")  # 0 = unlimited, run until the agent calls finish
        self.status_var = tk.StringVar(value="Ready")
        
        self._build_ui()
        self._load_models()
        self.root.after(100, self._poll_output)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Focus on prompt box
        self.root.after(100, lambda: self.prompt_text.focus())

    def _build_ui(self) -> None:
        """Build simple, clean UI."""
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        
        # === Top: Prompt input ===
        input_frame = ttk.LabelFrame(frame, text="What do you want me to do?", padding=10)
        input_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        
        # Prompt text box
        self.prompt_text = tk.Text(input_frame, height=6, wrap="word", font=("System", 12))
        self.prompt_text.grid(row=0, column=0, sticky="nsew")
        self.prompt_text.bind("<Return>", self._on_return)
        self.prompt_text.bind("<Shift-Return>", lambda e: None)  # Allow Shift+Enter for new line
        
        # Hint label
        hint_text = (
            "Examples: 'Open google.com and search for python tutorials', "
            "'Test example.com for SQL injection', "
            "'Debug the JavaScript on this page', "
            "'List files in the current directory'"
        )
        ttk.Label(input_frame, text=hint_text, foreground="gray", wraplength=900).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        
        # === Middle: Controls ===
        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(1, weight=1)
        
        # Run/Stop buttons
        self.run_button = ttk.Button(
            controls, 
            text="▶ Run Task", 
            command=self.run_task,
            width=15
        )
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        
        self.stop_button = ttk.Button(
            controls, 
            text="⏹ Stop", 
            command=self.stop_task,
            width=15,
            state="disabled"
        )
        self.stop_button.grid(row=0, column=1, sticky="w")
        
        # Status
        ttk.Label(controls, textvariable=self.status_var).grid(
            row=0, column=2, sticky="e", padx=(20, 0)
        )
        
        # === Bottom: Output ===
        output_frame = ttk.LabelFrame(frame, text="Output", padding=5)
        output_frame.grid(row=2, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        
        self.output_text = tk.Text(
            output_frame, 
            wrap="word", 
            state="disabled",
            font=("Menlo", 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white"
        )
        self.output_text.grid(row=0, column=0, sticky="nsew")
        
        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=scrollbar.set)
        
        # Clear button below output
        ttk.Button(frame, text="Clear Output", command=self.clear_output).grid(
            row=3, column=0, sticky="e", pady=(5, 0)
        )
        
        # Model selector (small, at bottom)
        model_frame = ttk.Frame(frame)
        model_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        
        ttk.Label(model_frame, text="Model:").pack(side="left", padx=(0, 5))
        self.model_box = ttk.Combobox(
            model_frame, 
            textvariable=self.model_var, 
            state="readonly",
            width=40
        )
        self.model_box.pack(side="left")
        
        # Keyboard shortcut hint
        ttk.Label(
            model_frame, 
            text="Ctrl+Enter to run | Shift+Enter for new line",
            foreground="gray"
        ).pack(side="right")

    def _on_return(self, event) -> str:
        """Handle Return key - run task unless Shift is held."""
        if not (event.state & 0x1):  # Check if Shift is NOT pressed
            self.run_task()
            return "break"  # Prevent default newline
        return None  # Allow Shift+Enter to insert newline

    def _load_models(self) -> None:
        """Load available models."""
        selector = ModelSelector(MODELS_DIR)
        values = ["auto (recommended)"]
        for path in selector.all_models():
            if selector.detect_incomplete_shards(path):
                continue
            values.append(str(path.relative_to(ROOT)))
        self.model_box["values"] = values
        self.model_var.set(values[0] if values else "auto")

    def _build_command(self, prompt: str) -> list[str]:
        """Build command to run agent."""
        model = self.model_var.get().replace(" (recommended)", "")
        
        command = [
            sys.executable,
            str(ROOT / "computer_use_agent.py"),
            "--max-steps", self.steps_var.get(),
            "--ctx-size", "8192",
            "--max-tokens", "900",
            "--command-timeout", "60",
            "--model", model,
            prompt
        ]
        return command

    def run_task(self) -> None:
        """Run the agent with current prompt."""
        if self.process and self.process.poll() is None:
            messagebox.showerror("Busy", "A task is already running.")
            return

        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showerror("Empty Prompt", "Type what you want me to do.")
            return

        command = self._build_command(prompt)

        self.append_output(f"\n{'='*60}\n")
        self.append_output(f"Task: {prompt}\n")
        self.append_output(f"{'='*60}\n\n")
        
        self.status_var.set("Running...")
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
        """Read output from running process."""
        assert self.process is not None
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.output_queue.put(("line", line))
        returncode = self.process.wait()
        self.output_queue.put(("done", str(returncode)))

    def _poll_output(self) -> None:
        """Poll for output updates."""
        while True:
            try:
                kind, payload = self.output_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                self.append_output(payload)
            elif kind == "done":
                code = int(payload)
                self.status_var.set(f"Done (exit {code})")
                self.run_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.process = None
        self.root.after(100, self._poll_output)

    def stop_task(self) -> None:
        """Stop running task."""
        if not self.process or self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.append_output("\n[Task stopped by user]\n")
            self.status_var.set("Stopped")
        except ProcessLookupError:
            pass

    def append_output(self, text: str) -> None:
        """Append text to output."""
        self.output_text.configure(state="normal")
        self.output_text.insert("end", text)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def clear_output(self) -> None:
        """Clear output text."""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

    def _on_close(self) -> None:
        """Handle window close."""
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Quit", "A task is running. Stop it and close?"):
                return
            self.stop_task()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    
    # Use a nice theme if available
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    
    app = AgentGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
