# UiBridge MCP

**[English](README.md)** | [한국어](README.ko.md)

**Screenshot-free Windows automation for LLM agents.**

An MCP server that lets Claude Code (or any MCP client) control **native Windows
apps and web pages by element — not by pixel guessing**. Interactions go through
the Windows Accessibility API (UI Automation), Win32 messages, and the Chrome
DevTools Protocol, so everything stays local on your machine.

Typical vision-based computer use takes a screenshot at every step and lets the
model guess coordinates — slow, token-hungry, and fragile when the window moves
or resizes. UiBridge does the opposite:

- **UI Automation (UIA)** — click/type by element name or AutomationId
- **Chrome DevTools Protocol (CDP)** — drive web page DOM with CSS selectors
- Screen content is never sent to the model — only the text of the elements you ask for

## The 3-tier fallback ladder

| Tier | Method | Covers |
|---|---|---|
| 1 | **UIA / CDP** (default) | Most apps that expose accessibility, all web pages |
| 2 | **Win32 messages** (`win32_find` / `win32_set_text` / `win32_click`) | Apps that hide from UIA but still reuse standard Edit/Button child windows or named custom sub-views — no focus steal, works on background windows |
| 3 | **Annotated screenshot + coordinates** (`screenshot_window` + `click_at`) | Purely custom-rendered surfaces — UIA element rectangles are numbered on the image (Set-of-Marks); the model picks a number, the code computes the click point |

Plus `run_steps` — batch multiple operations (with `verify_window` / `wait_ms`
checkpoints) into a single call.

## Install

```bat
python -m pip install -r requirements.txt
python install.py        :: registers the server in ~/.claude/settings.json
:: restart Claude Code — the ui-bridge tools appear
```

For web automation, start a browser in debug mode:

```bat
start_edge_debug.bat
:: or: chrome.exe --remote-debugging-port=9222
```

Verify the install with the self-test harnesses (uses Notepad):

```bat
python tests\uia_harness.py
python tests\stage3_harness.py
python tests\win32_harness.py
```

**Requirements**: Windows 10/11, Python 3.10+, Chrome or Edge (for web tools).

## Usage examples

Once registered, just talk to Claude Code — it picks the right tools. Below,
each prompt is followed by what actually happens under the hood.

### 1. Drive a desktop app

> *"Open Notepad and type 'hello world' into it, then read it back."*

```
inspect_tree(window_title="Notepad")            → finds the edit area (automation_id=15)
set_value(window_title="Notepad", automation_id="15", value="hello world")
get_value(window_title="Notepad", automation_id="15")   → "hello world"
```

No screenshot was taken, no coordinates were guessed. Works even if the
window is resized, moved, or behind other windows.

### 2. Fill a web form

> *"Log in to the admin page on the debug browser."*

```
web_goto(url="https://example.com/login")        → waits for readyState=complete
web_fill(form_data={"#username": "admin", "#password": "..."})
web_click_element(selector="button[type=submit]")
web_wait(selector=".dashboard", timeout_ms=15000)
```

### 3. An app that hides from UIA (custom framework)

Some apps (e.g. chat apps built on custom renderers) expose almost nothing
to UI Automation. Fall to tier 2:

```
win32_find(window_title="MyChatApp", class_name="Edit", visible_only=false)
   → [{hwnd: 132002, class: "Edit", size: [326, 28], ...}]
win32_set_text(hwnd=132002, text="search keyword")    → WM_SETTEXT, no focus steal
win32_find(window_title="MyChatApp", text_re="ChatRoomList")
   → even custom sub-views are Win32 child windows with names and rectangles
```

### 4. Purely custom-rendered surface (tier 3)

```
screenshot_window(window_title="MyChatApp", annotate=true)
   → {path: "...png", elements: [{n: 3, name: "Send", center: [1240, 890]}, ...]}
# the model looks at the numbered overlay, picks #3:
click_at(x=1240, y=890)
```

The model never guesses pixels — it picks an element number, the click point
comes from the UIA rectangle.

### 5. Batch a known flow into one call

```json
run_steps(steps=[
  {"tool": "set_value",     "args": {"window_title": "Notepad", "automation_id": "15", "value": "report done"}},
  {"tool": "wait_ms",       "args": {"ms": 200}},
  {"tool": "get_value",     "args": {"window_title": "Notepad", "automation_id": "15"}},
  {"tool": "verify_window", "args": {"window_title": "Notepad"}}
])
```

Stops at the first failing step and returns per-step results, so the agent
can inspect and resume from exactly where it broke.

## Performance

Connections are cached instead of re-created per command (auto-reconnect on drop):

- Web element read: **~2.6 ms/call** (vs seconds when handshaking per call)
- Window connect: ~0.9 s first → **~5 ms** cached
- CDP port auto-discovery: if nothing listens on the default 9222, known
  fallback ports are scanned (`UIBRIDGE_CDP_FALLBACK_PORTS` env var)

## Tools (23)

- **Discovery**: `list_windows`, `inspect_tree`
- **Interaction**: `click_element`, `type_text`, `get_value`, `set_value`
- **Bookmarks / actions**: `bookmark_element`, `list_bookmarks`, `delete_bookmark`,
  `list_actions`, `run_action` — save frequently used elements by name,
  run parameterised multi-step sequences
- **Web (CDP)**: `web_tabs`, `web_goto`, `web_page_info`, `web_click_element`,
  `web_type_text`, `web_read_text`, `web_find_elements`, `web_run_js`,
  `web_fill`, `web_wait`
- **Win32 low-level** (fallback tier 2): `win32_find`, `win32_get_text`,
  `win32_set_text`, `win32_click`, `win32_key`
- **Screen & coordinates** (fallback tier 3): `screenshot_window`, `click_at`,
  `drag`, `scroll_at`, `send_keys`
- **Batch**: `run_steps`

## Config files

`config/` ships with working examples (Calculator, Excel):

- `config/bookmarks.json` — saved UI element bookmarks
- `config/apps.json` — per-app locator hints
- `config/actions.json` — parameterised multi-step action sequences

## CLI

```bat
python cli.py --help
```

Runs the same operations without an MCP client — handy for scheduled tasks
and deterministic scripts.

## Security

- No screenshots by default — tier 3 only saves to local temp and returns a path
- Every interaction is a local API call; nothing leaves your machine
- No hardcoded secrets, no telemetry

## Contributing

Issues and PRs are welcome — especially reports of apps where the fallback
ladder fails (attach `inspect_tree` / `win32_find` output if you can).

## License

MIT © [cholamb](https://github.com/cholamb)
