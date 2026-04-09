# AGENTS.md

## Purpose

This repo contains a local macOS computer-use agent with **full system access** for advanced tasks including security research and penetration testing:

- a Tkinter GUI
- a CLI launcher
- a local `llama-server` backend
- Playwright browser automation
- native Quartz/AppKit desktop control
- unrestricted shell command execution
- network operations (HTTP, DNS, port scanning)
- system information gathering

**Inspired by:** Agent TARS, Claude Computer Use, OpenAI Operator

## Local Run

- Start the GUI with:
  ```bash
  ./launch-agent-gui.sh
  ```
- Start the CLI with:
  ```bash
  ./run-agent.sh "your prompt here"
  ```
- List available local models with:
  ```bash
  ./run-agent.sh --print-models
  ```

## Required Local Checks

- Run syntax checks after Python edits:
  ```bash
  python3 -m py_compile computer_use_agent.py agent_gui.py desktop_control.py
  ```
- Run tests after logic changes:
  ```bash
  python3 -m unittest discover -s tests -v
  ```

## GUI Notes

- The GUI has a `Check Permissions` button.
- Accessibility permission is required for desktop mouse and keyboard actions.
- Screen Recording permission is required for desktop screenshots.
- The GUI includes buttons to open the macOS Accessibility and Screen Recording settings panels.

## Model Selection

- Default model selection is automatic.
- No model family is hardcoded as preferred; auto-selection should work across local GGUF models.
- Incomplete shard sets must be skipped.

## Capabilities

This agent has **unrestricted system access**:

- **Full filesystem access** - Read/write anywhere on the system
- **Unrestricted shell commands** - sudo, rm, chmod, chown, etc. all allowed
- **Security research tools** - nmap, curl, netcat, scanning tools
- **Process management** - List and kill processes
- **Network operations** - HTTP requests, DNS lookup, port scanning
- **System information** - Full system and network info gathering

## Editing Rules

- Keep output artifacts under `output/`.
- Prefer extending the explicit action set over adding unrestricted execution paths.
- When adding new actions, follow the pattern in `ActionValidator` and `ActionExecutor`.
