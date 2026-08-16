# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local, macOS-only "computer use" agent: it drives a locally hosted `llama-server` (serving a
`.gguf` model) in a loop where the model emits one JSON action per step, the agent validates and
executes it, and the observation is fed back for the next step. It is explicitly built for
**unrestricted** system access — shell, filesystem, network scanning, security testing, browser
automation/DevTools, and native macOS desktop control — with no sandboxing or command allowlist.
There is a Tkinter GUI (`agent_gui.py`) and a CLI (`run-agent.sh`) on top of the same engine.

The agent's action set is not fixed at code-review time: alongside ~150 built-in actions, the
model can call `define_action` to register new shell- or Python-backed actions of its own at
runtime, persisted to `custom_actions.json` for reuse across runs (see `CustomActionRegistry`).
The run loop has no step cap by default (runs until `finish`) and actively self-corrects — asking
for a different next action — when it detects it's stalling or repeating a failing action.

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

# Cap the run instead of the unlimited (run-until-finish) default
./run-agent.sh --max-steps 20 "..."

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
3. **`ComputerUseAgent.run()`** — the step loop. `max_steps` defaults to `0`, meaning
   **unlimited**: the loop runs until the model calls `finish` (pass `--max-steps N` to cap it).
   Per step:
   - if a self-correction override is pending (see below), use it directly instead of calling
     the model — this skips straight to validate/execute for that step,
   - otherwise builds messages from `SYSTEM_PROMPT` + task + known custom actions +
     `WorkingMemory` summary + recent `history`, calls the primary model, parses its output with
     `JsonActionParser`,
   - if a second local model is configured, sends the proposal through `review_action()`
     (`REVIEWER_PROMPT`) which can approve or replace it,
   - validates the (possibly reviewer-replaced) action with `ActionValidator` — against both the
     built-in allowlist and the run's `CustomActionRegistry`,
   - on parse or validation failure, calls `repair_action()` (`REPAIR_PROMPT`) once, using the
     reviewer model if present, otherwise the primary model itself,
   - executes via `ActionExecutor`, records the result into `WorkingMemory` and `history`,
   - **active self-correction**: if the just-executed action's status was `"error"` and
     `WorkingMemory`'s stall/repeated-signature warning fires, proactively calls
     `repair_action()` with that warning as the problem, asking for a different next action
     (not just a passive note in next turn's prompt); the result becomes the pending override
     for the *next* iteration,
   - stops when the model calls `finish`.
4. **`JsonActionParser`** — the model's raw text is not trusted to be clean JSON. It strips
   `<|channel|>...<|end|>`-style reasoning markup some local models emit, strips code fences, and
   falls back to scanning for the last balanced `{...}` object that has a non-empty `"action"` key.
5. **`WorkingMemory`** — keeps the last 6 step records and derives two nudges: a
   *repeated-signature* warning (same action fired 3+ times in a row — shell commands are
   normalized/whitespace-collapsed before comparing) and a *stall* warning (3+ errors or 2+
   timeouts recently). These feed both the passive prompt context and the active self-correction
   trigger in `run()`.
6. **`ActionValidator`** — a static allowlist (`SUPPORTED_ACTIONS`) plus a required-args map
   (`REQUIRED_ARGS`) per built-in action name, *plus* an optional `CustomActionRegistry` passed
   into `validate()` that extends both the allowlist and the required-args lookup at runtime.
   Adding a new **built-in** action means adding it here *and* wiring a branch in
   `ActionExecutor.execute()` *and* documenting its JSON shape in `SYSTEM_PROMPT`. Adding a new
   **custom** action needs none of that — see below.
7. **`CustomActionRegistry` / `CustomAction`** — this is what keeps the agent's action set from
   being hardcoded. The model can call `define_action` (shell-template or Python-snippet backed)
   at any point; the definition is validated (name collision with built-ins, name format, known
   `kind`), stored in-memory, and persisted to `custom_actions.json` at the repo root (gitignored
   — local state, like `models/`/`output/`) so it survives across runs. Once defined, the action
   is indistinguishable from a built-in to `ActionValidator`/`ActionExecutor`. `list_custom_actions`
   and `remove_custom_action` manage the registry; `ComputerUseAgent.custom_actions_context_lines()`
   injects the current registry into every prompt (main loop, repair, review) so the model reuses
   instead of redefining.
8. **`ActionSafety`** — deliberately permissive by design for this project: `is_path_allowed`
   accepts any path (including outside the workspace) and `check_shell` accepts any non-empty
   command (including `sudo`, `rm -rf`, etc.). This is intentional per `AGENTS.md`/`README.md`, not
   an oversight — do not "fix" it into a sandboxed validator without being asked. Custom Python
   actions run via a plain `exec()` in `ActionExecutor._run_custom_python` for the same reason:
   there is no sandbox anywhere in this codebase, by design.
9. **`ActionExecutor`** — dispatches by action-name prefix/exact-match to one of:
   - inline handlers for file ops (`list_files`/`read_file`/`write_file`) and `shell`,
   - `BrowserTool` for everything prefixed `browser_` or `devtools_` (Playwright CLI wrapper +
     DevTools Protocol-style features: console eval, network intercept/modify, storage/cookies,
     DOM inspection/mutation, debugger stepping, performance profiling, and a
     reverse-engineering set — deobfuscation, webpack analysis, endpoint/secret extraction),
   - `desktop_control.DesktopTool` for everything prefixed `desktop_` (native macOS mouse/keyboard/
     clipboard/app control via Quartz event taps and AppKit),
   - `define_action`/`list_custom_actions`/`remove_custom_action`, then finally a lookup in
     `self.custom_actions` for anything not matched above — a "shell" custom action runs its
     `code` as a `str.format()` template with each arg `shlex.quote`-d in; a "python" custom
     action `exec()`s `code` with `args`, `workspace_root`, `run_action(name, **kwargs)` (calls
     back into `self.execute`, letting custom actions compose built-ins or other custom actions),
     and `shell(cmd)` in scope, and requires the snippet to set a `result` string.
10. **`BrowserTool`** shells out to `scripts/playwright_cli.sh` (resolution order: `$PLAYWRIGHT_CLI_WRAPPER`
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

The model only knows about **built-in** actions/args described textually in
`ComputerUseAgent.SYSTEM_PROMPT`. `ActionValidator.SUPPORTED_ACTIONS`/`REQUIRED_ARGS` is the
enforcement layer, not the source of truth for what the model attempts — the two must be kept in
sync by hand. `README.md`'s "Supported Actions" section is a third copy of this same list for
humans; also keep it in sync when built-in actions change. This coupling does *not* apply to
custom actions — those are registered and discovered entirely at runtime through
`define_action`/`list_custom_actions` and the `custom_actions_context_lines()` injected into every
prompt, so there is nothing to keep in sync by hand when the model invents one.

### Output layout

Everything generated at runtime goes under `output/` (gitignored), created on demand by
`ensure_dirs()`:
- `output/logs/llama-server-<port>.log` — llama-server stdout/stderr per instance.
- `output/playwright/<session_name>/` — Playwright CLI working dir and `.playwright-cli/page-*.yml`
  snapshots.
- `output/desktop/` — desktop screenshots (`*.png`).

`custom_actions.json` at the repo root (gitignored) is separate from `output/`: it's the
model-defined action registry (`CustomActionRegistry`), meant to persist and be reused across
runs rather than being disposable per-run output.

### Models

`.gguf` model files live in `models/` (gitignored, not present in the repo). Model selection is
local-only — no hardcoded preferred model family; `ModelSelector` just scores whatever is on disk.

## Conventions

- Single-file-per-concern layout: almost all agent logic is in `computer_use_agent.py`; desktop
  automation is isolated in `desktop_control.py` because it's macOS/PyObjC-specific and unit-tested
  by mocking `subprocess.run`/Quartz calls rather than driving real UI.
- When adding a new **built-in** action, follow the existing three-part pattern: register it in
  `ActionValidator.SUPPORTED_ACTIONS`/`REQUIRED_ARGS`, add an execution branch in
  `ActionExecutor.execute()` (or `BrowserTool`/`DesktopTool` if it belongs there), and document its
  JSON shape in `SYSTEM_PROMPT` so the model can actually emit it. Reserve this for capabilities
  that should ship with the agent regardless of task; a capability only one task needs is what
  `define_action` (custom actions) is for instead.
- Prefer extending the action set (built-in or, more often now, model-defined via
  `define_action`) over adding new *unrestricted execution paths* — i.e. don't add another
  general-purpose "run arbitrary X" primitive next to `shell`/custom-python; compose from what
  exists.
- Keep generated artifacts under `output/`. `custom_actions.json` is the one piece of persisted
  state that intentionally lives outside `output/` (see Output layout above).
- Tests mock external processes/APIs (`subprocess.run`, `llama-server` HTTP) rather than requiring
  a real model or macOS permissions to be present — keep new tests runnable without live
  dependencies. `desktop_control.py` cannot even be imported on non-macOS (it imports `Quartz`/
  `AppKit` unconditionally at module level), so the whole suite only runs on macOS or with those
  modules stubbed into `sys.modules` first.
