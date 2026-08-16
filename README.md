# Local Computer Use Agent

This app runs a local `.gguf` model, starts `llama-server` on demand, and lets the model take actions through:

- workspace file operations
- **unrestricted shell commands** (security research, pentesting, system administration)
- Playwright browser automation
- native macOS desktop automation through Quartz/AppKit
- **advanced network operations** (HTTP requests, DNS lookup, port scanning)
- **system information gathering** (process management, network info, environment variables)

The agent now also keeps compact working memory across steps, validates actions before execution, and performs one-step action repair when a local model emits malformed JSON or an invalid tool call.

**Inspired by:** Agent TARS, Claude Computer Use, OpenAI Operator

By default it auto-selects the strongest complete instruction-friendly model it finds in [`models/`](/Users/joshua.giles/computer-use-agent-local/models). Model selection is local-only and not tied to any Codex-managed path or model family.

## Start Locally

- Open a terminal in [`/Users/joshua.giles/computer-use-agent-local`](/Users/joshua.giles/computer-use-agent-local).
- Start the GUI:
  ```bash
  ./launch-agent-gui.sh
  ```
- Paste a task prompt into the text box.
- Click `Check Permissions` before using desktop mouse or keyboard actions.
- If Accessibility is not granted, click `Accessibility Settings` in the GUI and allow both `Terminal.app` and `/Users/joshua.giles/miniconda3/bin/python3`.
- If screenshot capture is blocked, click `Screen Recording Settings` in the GUI and allow the same apps there too.
- Run the task with `Run Task`.

## CLI Start

- Run a one-shot task:
  ```bash
  ./run-agent.sh "Open a browser to example.com, take a snapshot, and tell me the page title."
  ```
- Start interactive prompt mode:
  ```bash
  ./run-agent.sh
  ```
- Show ranked models:
  ```bash
  ./run-agent.sh --print-models
  ```

## Test Locally

- Run syntax checks:
  ```bash
  python3 -m py_compile computer_use_agent.py agent_gui.py desktop_control.py
  ```
- Run the regression suite:
  ```bash
  python3 -m unittest discover -s tests -v
  ```

## Main Files

- [`launch-agent-gui.sh`](/Users/joshua.giles/computer-use-agent-local/launch-agent-gui.sh): start the desktop GUI
- [`agent_gui.py`](/Users/joshua.giles/computer-use-agent-local/agent_gui.py): prompt UI, streamed output, permission checks
- [`run-agent.sh`](/Users/joshua.giles/computer-use-agent-local/run-agent.sh): terminal launcher
- [`computer_use_agent.py`](/Users/joshua.giles/computer-use-agent-local/computer_use_agent.py): model selection, `llama-server` lifecycle, action loop
- [`desktop_control.py`](/Users/joshua.giles/computer-use-agent-local/desktop_control.py): native desktop control
- [`tests/test_computer_use_agent.py`](/Users/joshua.giles/computer-use-agent-local/tests/test_computer_use_agent.py): regression tests
- [`output/`](/Users/joshua.giles/computer-use-agent-local/output): logs and generated artifacts
- `custom_actions.json` (gitignored, created on demand): actions the agent has defined for itself at runtime; see [Custom Actions](#custom-actions) below

## Autonomy

- By default the agent runs until it calls `finish` -- there is no step cap (`--max-steps 0`,
  the default, means unlimited). Pass `--max-steps N` to cap it again.
- When recent steps are failing or repeating without progress, the agent no longer just gets a
  passive warning in its context: it proactively asks for a corrected next action (a different
  tool, a narrower target, or `finish` with the best partial result) instead of retrying the
  same failing action indefinitely.

## Custom Actions

The agent is not limited to the fixed action catalog below. It can call `define_action` at any
time to register a new action of its own -- backed by either a shell command template or a
Python snippet -- which is validated and then callable by name for the rest of the run **and**
every future run (it's persisted to `custom_actions.json` at the repo root).

```json
{"action": "define_action", "args": {
  "name": "check_port_open",
  "description": "Check whether a TCP port is open on a host",
  "kind": "shell",
  "code": "nc -z -w2 {host} {port} && echo open || echo closed",
  "args": ["host", "port"],
  "required_args": ["host", "port"]
}}
```

Once defined, `check_port_open` is called directly: `{"action": "check_port_open", "args": {"host": "192.168.1.1", "port": "22"}}`.

Python-kind actions can compose existing actions (built-in or custom) via `run_action(name, **kwargs)`,
and must set a `result` string variable. Manage the registry with `list_custom_actions` and
`remove_custom_action`.

## Browser Setup

- Browser automation uses the repo-local Playwright wrapper at:
  ```bash
  ./scripts/playwright_cli.sh
  ```
- If Playwright CLI is not installed or cached yet:
  ```bash
  npm install -g @playwright/cli@latest
  playwright-cli --help
  ```
- If you want a second local model to review each next action before execution:
  ```bash
  ./run-agent.sh --reviewer-model auto "Open a browser to example.com, take a snapshot, and report the title."
  ```

## Desktop Permissions

- Accessibility is required for:
  - mouse move
  - mouse click
  - drag
  - typing
  - hotkeys
- Screen Recording is required for:
  - desktop screenshots
- The GUI `Check Permissions` button tests both paths live.

## Supported Actions

### File Operations
- `list_files` - List directory contents
- `read_file` - Read file contents
- `write_file` - Write or append to files

### Shell & System
- `shell` - Execute any shell command (unrestricted)
- `process_list` - List running processes
- `process_kill` - Kill a process by PID
- `system_info` - Get system information
- `network_info` - Get network configuration
- `env_get` - Get environment variables
- `env_set` - Set environment variables

### Network Operations
- `http_request` - Make HTTP/HTTPS requests
- `dns_lookup` - Perform DNS lookups
- `port_scan` - Scan ports on a target

### Security Testing
- `security_sql_inject_test` - Test for SQL injection vulnerabilities
- `security_xss_test` - Test for XSS vulnerabilities
- `security_form_fuzz` - Fuzz form inputs with various payloads
- `security_headers_check` - Analyze security headers
- `security_crawl` - Crawl website for endpoints and forms

### DevTools - Console
- `devtools_console_open` - Open DevTools console
- `devtools_console_eval` - Execute JavaScript in console
- `devtools_console_clear` - Clear console
- `devtools_console_get_logs` - Get console logs

### DevTools - Network
- `devtools_network_open` - Open Network panel
- `devtools_network_clear` - Clear network log
- `devtools_network_get_requests` - Get all network requests
- `devtools_network_intercept` - Intercept network requests
- `devtools_network_modify_response` - Modify network responses

### DevTools - Application/Storage
- `devtools_application_open` - Open Application panel
- `devtools_storage_get` - Get all storage items
- `devtools_storage_get_item` - Get specific storage item
- `devtools_storage_set_item` - Set storage item
- `devtools_storage_remove_item` - Remove storage item
- `devtools_storage_clear` - Clear storage
- `devtools_cookies_get` - Get all cookies
- `devtools_cookies_get_by_name` - Get cookie by name
- `devtools_cookies_set` - Set cookie
- `devtools_cookies_delete` - Delete cookie

### DevTools - Elements/DOM
- `devtools_elements_open` - Open Elements panel
- `devtools_dom_inspect` - Inspect DOM element
- `devtools_dom_get_html` - Get element HTML
- `devtools_dom_get_text` - Get element text
- `devtools_dom_get_styles` - Get element styles
- `devtools_dom_get_computed_styles` - Get computed styles
- `devtools_dom_modify` - Modify element HTML
- `devtools_dom_hide_element` - Hide element
- `devtools_dom_show_element` - Show element

### DevTools - Sources/Debugging
- `devtools_sources_open` - Open Sources panel
- `devtools_debugger_set_breakpoint` - Set breakpoint
- `devtools_debugger_remove_breakpoint` - Remove breakpoint
- `devtools_debugger_pause` - Pause execution
- `devtools_debugger_resume` - Resume execution
- `devtools_debugger_step_into` - Step into function
- `devtools_debugger_step_over` - Step over function
- `devtools_debugger_step_out` - Step out of function
- `devtools_get_page_source` - Get page source
- `devtools_get_scripts` - Get all scripts
- `devtools_get_script_source` - Get specific script source

### DevTools - Performance
- `devtools_performance_open` - Open Performance panel
- `devtools_performance_start_profiling` - Start CPU profiling
- `devtools_performance_stop_profiling` - Stop CPU profiling
- `devtools_memory_take_heap_snapshot` - Take heap snapshot

### DevTools - Reverse Engineering
- `devtools_deobfuscate_js` - Analyze and deobfuscate JavaScript
- `devtools_analyze_webpack` - Analyze webpack bundles
- `devtools_extract_api_endpoints` - Extract API endpoints from code
- `devtools_find_secrets` - Find secrets, keys, and tokens
- `devtools_analyze_source_map` - Analyze source maps

### Browser Automation
- `browser_open` - Open a URL
- `browser_snapshot` - Get page accessibility tree
- `browser_click` - Click an element
- `browser_hover` - Hover over an element
- `browser_fill` - Fill a form field
- `browser_select` - Select from dropdown
- `browser_check` / `browser_uncheck` - Toggle checkboxes
- `browser_drag` - Drag and drop
- `browser_type` - Type text
- `browser_press` - Press a key
- `browser_eval` - Execute JavaScript
- `browser_console` - Get console logs
- `browser_network` - Get network activity
- `browser_screenshot` - Capture screenshot
- `browser_tab_list` / `browser_tab_new` / `browser_tab_select` / `browser_tab_close` - Tab management
- `browser_back` / `browser_forward` / `browser_reload` - Navigation
- `browser_download` - Download files
- `browser_upload` - Upload files
- `browser_clear_cookies` - Clear cookies
- `browser_set_viewport` - Set viewport size

### Desktop Automation
- `desktop_get_state` - Get desktop state
- `desktop_screenshot` - Capture screenshot
- `desktop_move_mouse` - Move cursor
- `desktop_click` / `desktop_double_click` / `desktop_right_click` / `desktop_middle_click` - Mouse clicks
- `desktop_drag_mouse` - Drag mouse
- `desktop_scroll` - Scroll
- `desktop_type_text` / `desktop_paste_text` - Text input
- `desktop_press_key` / `desktop_hotkey` - Key presses
- `desktop_get_clipboard` / `desktop_set_clipboard` - Clipboard operations
- `desktop_open_app` - Open applications
- `desktop_open_settings_panel` - Open system settings
- `desktop_wait` - Wait/pause

### Custom Actions
- `define_action` - Register a new shell- or Python-backed action, persisted for reuse
- `list_custom_actions` - List actions the agent has defined for itself
- `remove_custom_action` - Delete a custom action

### Task Control
- `finish` - Complete the task

`browser_snapshot` now returns the latest snapshot file path and a compact list of key refs so the agent can act on the page without hunting through hidden artifact folders.

## Capabilities

This agent has **full system access** and can perform any task you request:

### Security Research & Pentesting
- **Automated Vulnerability Scanning:**
  - SQL injection testing with multiple payload types
  - XSS (Cross-Site Scripting) testing
  - Form fuzzing for input validation issues
  - Security headers analysis
  - Website crawling for endpoint discovery
- Network scanning (`nmap`, port scanning)
- HTTP/HTTPS requests for API testing
- DNS lookups and network reconnaissance
- Process monitoring and management
- Full shell access including `sudo`, `rm`, `chmod`, etc.

### System Administration
- File operations anywhere on the system
- Package installation (`brew`, `npm`, `pip`)
- Service management (`launchctl`)
- Environment variable manipulation
- System and network information gathering

### Browser Automation & DevTools
- Full Playwright-based browser control
- Multi-tab management
- JavaScript evaluation
- Screenshot capture
- Cookie and session management
- **Complete DevTools Integration:**
  - Console: Execute JS, view logs, clear console
  - Network: Monitor requests, intercept traffic, modify responses
  - Application: Inspect storage (localStorage, sessionStorage, IndexedDB), cookies
  - Elements: Inspect DOM, get/modify HTML, CSS analysis
  - Sources: Debug JavaScript, set breakpoints, step through code
  - Performance: CPU profiling, heap snapshots
  - **Reverse Engineering:** Deobfuscate JS, analyze webpack, extract APIs, find secrets

### Desktop Automation
- Native macOS control via Quartz/AppKit
- Mouse and keyboard simulation
- Application launching and control
- Clipboard operations
- Screenshot capture

## Screenshot Management

Screenshots are saved to `output/desktop/` (not your Desktop). The GUI provides screenshot management:

- **View Screenshots Folder** - Opens the folder in Finder
- **List All Screenshots** - Shows all screenshots with size and date
- **Delete All Screenshots** - Removes all screenshots (with confirmation)
- **Delete Old Screenshots** - Removes screenshots older than 7 days

You can also manage screenshots via shell:
```bash
# List screenshots
ls -la output/desktop/

# Delete all screenshots
rm output/desktop/*.png

# Delete screenshots older than 7 days
find output/desktop/ -name "*.png" -mtime +7 -delete
```

## Vision Model Integration

The current agent uses **text-based interaction** (DOM parsing + accessibility trees). Vision models can improve accuracy:

| Approach | Accuracy | Speed | Cost |
|----------|----------|-------|------|
| Text-only (Current) | 60-70% | Fast | Free |
| + OpenCLIP | 75-80% | Medium | Free (local) |
| + **SeeClick** | **85%** | Medium | **Free (local)** |
| + Qwen2-VL | 85-90% | Slow | Free (local GPU) |
| + GPT-4V/Claude | 90-95% | Medium | API cost |
| + UI-TARS | 92%+ | Medium | Local/API |

### Download SeeClick (Recommended)

SeeClick is a specialized GUI grounding model that locates UI elements from screenshots:

```bash
# Download via command line
./download_seeclick.sh

# Or use the GUI: Models → Download SeeClick
```

See `SEECLICK_SETUP.md` for detailed setup instructions and `VISION_MODELS.md` for comparison with other vision models.

## Safety

**WARNING:** This agent executes commands directly on your system. 
- You are responsible for the commands you request.
- The agent has unrestricted access to perform security research, pentesting, and system administration tasks.
- Desktop control is direct and real. Test with simple prompts first.
- Always review commands before execution in sensitive environments.
