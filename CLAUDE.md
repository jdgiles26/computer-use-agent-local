# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local, macOS-only "computer use" agent: it drives a locally hosted `llama-server` (serving a
`.gguf` model) in a loop where the model emits one JSON action per step, the agent validates and
executes it, and the observation is fed back for the next step. It is explicitly built for
**unrestricted** system access — shell, filesystem, network scanning, security testing, browser
automation/DevTools, and native macOS desktop control — with no sandboxing or command allowlist.
There is a Tkinter GUI (`agent_gui.py`) and a CLI (`run-agent.sh`) on top of the same engine.

Inspired by Agent TARS, Claude Computer Use, and OpenAI Operator.

## Commands

```bash
# Syntax-check after any Python edit
python3 -m py_compile computer_use_agent.py agent_gui.py desktop_control.py

# Run the full regression suite
python3 -m unittest discover -s tests -v

# Run a single test class or test method
python3 -m unittest tests.test_computer_use_agent.JsonActionParserTests -v
python3 -m unittest tests.test_computer_use_agent.JsonActionParserTests.test_extracts_plain_json -v

# CLI: one-shot task
./run-agent.sh "Open a browser to example.com, take a snapshot, and tell me the page title."

# CLI: interactive prompt mode (no args)
./run-agent.sh

# List/rank locally available .gguf models without running a task
./run-agent.sh --print-models

# Run with a second local model reviewing each proposed action before execution
./run-agent.sh --reviewer-model auto "..."

# Desktop GUI
./launch-agent-gui.sh
```

There is no package manifest (no `requirements.txt`/`pyproject.toml`/`package.json`); dependencies
are external binaries expected on `PATH`:
- `llama-server` (from llama.cpp) — required by both the CLI and GUI.
- `playwright-cli` (or `npx @playwright/cli`) — required for any `browser_*`/`devtools_*` action,
  invoked through `scripts/playwright_cli.sh`.
- PyObjC (`Quartz`, `AppKit`) — required by `desktop_control.py` for native desktop automation;
  this only works on macOS.

## Architecture

Everything but desktop control lives in `computer_use_agent.py` (~2900 lines, single file).
Reading it top-to-bottom roughly matches the request lifecycle:

1. **`ModelSelector`** — scans `models/*.gguf`, skips incomplete multi-shard downloads (matched via
   `-NNNNN-of-NNNNN.gguf` naming), and scores/ranks the rest (instruction-tuned and
   task-oriented names score higher; size is the tiebreaker/fallback). `pick_model("auto")` and
   `pick_reviewer_model("auto", primary)` both go through this — the reviewer model, when set to
   `auto`, is the best-ranked *alternative* to whatever the primary model is.
2. **`LlamaServer`** — owns the `llama-server` subprocess lifecycle for one model: picks a free
   port, launches with `--jinja` and forced JSON responses, health-checks against `/health` and
   `/v1/models`, and does a SIGTERM→SIGKILL process-group teardown in `stop()`. There are up to two
   instances per run: primary and (optionally) reviewer, on separate ports
   (`DEFAULT_PORT=8012` / `DEFAULT_REVIEWER_PORT=8013`).
3. **`ComputerUseAgent.run()`** — the step loop (`max_steps`, default 12 via CLI default 20 in the
   GUI):
   - builds messages from `SYSTEM_PROMPT` + task + `WorkingMemory` summary + recent `history`,
   - calls the primary model, parses its output with `JsonActionParser`,
   - if the model has a second local model configured, sends the proposal through
     `review_action()` (`REVIEWER_PROMPT`) which can approve or replace it,
   - validates the (possibly reviewer-replaced) action with `ActionValidator`,
   - on parse or validation failure, calls `repair_action()` (`REPAIR_PROMPT`) once, using the
     reviewer model if present, otherwise the primary model itself,
   - executes via `ActionExecutor`, records the result into `WorkingMemory` and `history`,
   - stops when the model calls `finish`, or after `max_steps` steps.
4. **`JsonActionParser`** — the model's raw text is not trusted to be clean JSON. It strips
   `<|channel|>...<|end|>`-style reasoning markup some local models emit, strips code fences, and
   falls back to scanning for the last balanced `{...}` object that has a non-empty `"action"` key.
5. **`WorkingMemory`** — keeps the last 6 step records and derives two nudges that get injected
   back into the prompt: a *repeated-signature* warning (same action fired 3+ times in a row —
   shell commands are normalized/whitespace-collapsed before comparing) and a *stall* warning
   (3+ errors or 2+ timeouts recently). This is what's meant to stop a local model from looping.
6. **`ActionValidator`** — a static allowlist (`SUPPORTED_ACTIONS`) plus a required-args map
   (`REQUIRED_ARGS`) per action name. This is the single source of truth for "what actions exist."
   Adding a new action means adding it here *and* wiring a branch in `ActionExecutor.execute()`
   *and* documenting its JSON shape in `ComputerUseAgent.SYSTEM_PROMPT` (the model only knows about
   actions described in the prompt).
7. **`ActionSafety`** — deliberately permissive by design for this project: `is_path_allowed`
   accepts any path (including outside the workspace) and `check_shell` accepts any non-empty
   command (including `sudo`, `rm -rf`, etc.). This is intentional per `AGENTS.md`/`README.md`, not
   an oversight — do not "fix" it into a sandboxed validator without being asked.
8. **`ActionExecutor`** — dispatches by action-name prefix/exact-match to one of:
   - inline handlers for file ops (`list_files`/`read_file`/`write_file`) and `shell`,
   - `BrowserTool` for everything prefixed `browser_` or `devtools_` (Playwright CLI wrapper +
     DevTools Protocol-style features: console eval, network intercept/modify, storage/cookies,
     DOM inspection/mutation, debugger stepping, performance profiling, and a
     reverse-engineering set — deobfuscation, webpack analysis, endpoint/secret extraction),
   - `desktop_control.DesktopTool` for everything prefixed `desktop_` (native macOS mouse/keyboard/
     clipboard/app control via Quartz event taps and AppKit).
9. **`BrowserTool`** shells out to `scripts/playwright_cli.sh` (resolution order: `$PLAYWRIGHT_CLI_WRAPPER`
   env override → local `scripts/playwright_cli.sh` → `playwright-cli` on `PATH` → `npx
   @playwright/cli`) and keeps per-session state under `output/playwright/<session_name>/`.
   `browser_snapshot` returns the latest `.playwright-cli/page-*.yml` snapshot path plus a
   filtered, ref-annotated summary (`summarize_snapshot_text`, biased toward interactive elements:
   textbox/button/link/checkbox/etc.) so the model doesn't need to read the raw snapshot file to
   find refs.

`desktop_control.py` is a standalone module (not entangled with the llama/action-loop logic):
hardcoded macOS virtual keycode and modifier-flag tables, `DesktopTool` for
screenshot/click/drag/scroll/type/hotkey/clipboard/app-launch, and a `DesktopControlError` raised
for missing Accessibility permission or unknown keys/panels. It requires the calling process
(Terminal.app / whatever runs Python) to have Accessibility and Screen Recording permission granted
in macOS System Settings — the GUI has a "Check Permissions" button that surfaces this.

`agent_gui.py` is a thin Tkinter shell: builds a prompt box and controls, then runs
`computer_use_agent.py` as a subprocess (not an in-process import of the agent loop) and streams
its stdout/stderr into the output pane via a background reader thread + queue.

### Prompt/action-set coupling

The model only knows about actions/args described textually in `ComputerUseAgent.SYSTEM_PROMPT`.
`ActionValidator.SUPPORTED_ACTIONS`/`REQUIRED_ARGS` is the enforcement layer, not the source of
truth for what the model attempts — the two must be kept in sync by hand. `README.md`'s "Supported
Actions" section is a third copy of this same list for humans; also keep it in sync when actions
change.

### Output layout

Everything generated at runtime goes under `output/` (gitignored), created on demand by
`ensure_dirs()`:
- `output/logs/llama-server-<port>.log` — llama-server stdout/stderr per instance.
- `output/playwright/<session_name>/` — Playwright CLI working dir and `.playwright-cli/page-*.yml`
  snapshots.
- `output/desktop/` — desktop screenshots (`*.png`).

### Models

`.gguf` model files live in `models/` (gitignored, not present in the repo). Model selection is
local-only — no hardcoded preferred model family; `ModelSelector` just scores whatever is on disk.

## Conventions

- Single-file-per-concern layout: almost all agent logic is in `computer_use_agent.py`; desktop
  automation is isolated in `desktop_control.py` because it's macOS/PyObjC-specific and unit-tested
  by mocking `subprocess.run`/Quartz calls rather than driving real UI.
- When adding a new action, follow the existing three-part pattern: register it in
  `ActionValidator.SUPPORTED_ACTIONS`/`REQUIRED_ARGS`, add an execution branch in
  `ActionExecutor.execute()` (or `BrowserTool`/`DesktopTool` if it belongs there), and document its
  JSON shape in `SYSTEM_PROMPT` so the model can actually emit it.
- Prefer extending the explicit action set over adding new unrestricted execution paths.
- Keep generated artifacts under `output/`.
- Tests mock external processes/APIs (`subprocess.run`, `llama-server` HTTP) rather than requiring
  a real model or macOS permissions to be present — keep new tests runnable without live
  dependencies.
