"""UiBridge MCP Server.

Exposes Windows UI Automation + Chrome DevTools Protocol (CDP) as MCP tools,
enabling any LLM client to control both native Windows applications AND
web pages without screenshots.

Usage:
    python server.py              # stdio transport (for MCP clients)
    fastmcp dev server.py         # interactive MCP Inspector

Web tools require Chrome/Edge started with --remote-debugging-port=9222
"""

from __future__ import annotations

import re
import time
from typing import Any

from fastmcp import FastMCP

from models import Bookmark, ElementLocator
from ui_automation import (
    get_ui_tree,
    list_open_windows,
    perform_click,
    perform_get_value,
    perform_key_press,
    perform_set_value,
    perform_type,
)
from element_finder import find_element
from bookmarks import (
    add_bookmark,
    delete_bookmark as bm_delete,
    list_bookmark_names,
    resolve_bookmark,
)
from actions import (
    execute_action,
    list_action_summaries,
)
from web_automation import (
    DEFAULT_CDP_URL,
    launch_browser as _launch_browser,
    web_click,
    web_execute_js,
    web_fill_form,
    web_get_page_info,
    web_get_text,
    web_list_tabs,
    web_navigate,
    web_query_all,
    web_type,
    web_wait_for,
)
import computer
import win32_native


mcp = FastMCP(
    name="UiBridge",
    version="0.2.1",
    instructions=(
        "Control Windows desktop applications through UI Automation. "
        "No screenshots - all interaction flows through the Windows "
        "Accessibility API, so data stays local on your machine."
    ),
)


# ── Helper ────────────────────────────────────────────────────────────────

def _resolve_target(
    bookmark_name: str | None,
    window_title: str | None,
    automation_id: str | None,
    element_name: str | None,
    control_type: str | None,
    class_name: str | None,
):
    """Resolve either a bookmark or inline locator params to a live element."""
    if bookmark_name:
        return resolve_bookmark(bookmark_name)

    if not window_title:
        raise ValueError(
            "Either bookmark_name or window_title must be provided."
        )

    locator = ElementLocator(
        automation_id=automation_id,
        name=element_name,
        control_type=control_type,
        class_name=class_name,
    )
    return find_element(window_title, locator)


# ══════════════════════════════════════════════════════════════════════════
# MCP Tools
# ══════════════════════════════════════════════════════════════════════════


# ── 1. Discovery ──────────────────────────────────────────────────────────

@mcp.tool()
def list_windows() -> list[dict]:
    """List all visible windows with their titles, class names, and process IDs.

    Use this to discover which applications are currently running.
    """
    return list_open_windows()


@mcp.tool()
def inspect_tree(
    window_title: str,
    max_depth: int = 3,
) -> dict:
    """Get the UI Automation element tree for a window.

    Args:
        window_title: Regex pattern matching the target window title.
        max_depth: How deep to traverse (1-10, default 3).

    Returns a nested dict with name, automation_id, control_type,
    class_name, index_path, and children for each element.
    Use this to explore a window's UI structure before bookmarking elements.
    """
    return get_ui_tree(window_title, max_depth)


# ── 2. Bookmarks ──────────────────────────────────────────────────────────

@mcp.tool()
def bookmark_element(
    name: str,
    app_process: str,
    window_title: str,
    automation_id: str | None = None,
    element_name: str | None = None,
    control_type: str | None = None,
    class_name: str | None = None,
    tree_path: list[int] | None = None,
    description: str = "",
) -> str:
    """Save a UI element as a named bookmark for later reuse.

    Args:
        name: Friendly bookmark name (e.g. "calc_button_5").
        app_process: Process name (e.g. "Calculator").
        window_title: Regex matching the window title.
        automation_id: UIA AutomationId (most reliable).
        element_name: UIA Name (visible text).
        control_type: Control type (Button, Edit, Text, etc.).
        class_name: Win32 class name.
        tree_path: Index-based path from window root (e.g. [0,2,1]).
        description: Optional description.

    At least one of automation_id, element_name, control_type,
    class_name, or tree_path must be provided.
    """
    locator = ElementLocator(
        automation_id=automation_id,
        name=element_name,
        control_type=control_type,
        class_name=class_name,
        tree_path=tree_path,
    )
    bm = Bookmark(
        name=name,
        app_process=app_process,
        window_title_re=window_title,
        locator=locator,
        description=description,
    )
    return add_bookmark(bm)


@mcp.tool()
def list_bookmarks() -> list[dict]:
    """List all saved bookmarks with their names, apps, and locators."""
    return list_bookmark_names()


@mcp.tool()
def delete_bookmark(name: str) -> str:
    """Delete a bookmark by name.

    Args:
        name: The bookmark name to delete.
    """
    return bm_delete(name)


# ── 3. Interaction ────────────────────────────────────────────────────────

@mcp.tool()
def click_element(
    bookmark_name: str | None = None,
    window_title: str | None = None,
    automation_id: str | None = None,
    element_name: str | None = None,
    control_type: str | None = None,
    class_name: str | None = None,
) -> str:
    """Click a UI element.

    Target the element by bookmark name OR by providing window_title
    plus at least one of automation_id / element_name / control_type / class_name.

    Args:
        bookmark_name: Name of a saved bookmark.
        window_title: Regex matching the window title.
        automation_id: UIA AutomationId.
        element_name: UIA Name.
        control_type: Control type.
        class_name: Win32 class name.
    """
    elem = _resolve_target(
        bookmark_name, window_title, automation_id, element_name, control_type, class_name
    )
    return perform_click(elem)


@mcp.tool()
def type_text(
    text: str,
    bookmark_name: str | None = None,
    window_title: str | None = None,
    automation_id: str | None = None,
    element_name: str | None = None,
    control_type: str | None = None,
    class_name: str | None = None,
) -> str:
    """Type text into a UI element using keyboard simulation.

    Args:
        text: The text to type. Supports pywinauto key syntax
              (e.g. "{ENTER}", "{TAB}", "^a" for Ctrl+A).
        bookmark_name: Name of a saved bookmark.
        window_title: Regex matching the window title.
        automation_id: UIA AutomationId.
        element_name: UIA Name.
        control_type: Control type.
        class_name: Win32 class name.
    """
    elem = _resolve_target(
        bookmark_name, window_title, automation_id, element_name, control_type, class_name
    )
    return perform_type(elem, text)


@mcp.tool()
def get_value(
    bookmark_name: str | None = None,
    window_title: str | None = None,
    automation_id: str | None = None,
    element_name: str | None = None,
    control_type: str | None = None,
    class_name: str | None = None,
) -> str:
    """Read the current value or text of a UI element.

    Args:
        bookmark_name: Name of a saved bookmark.
        window_title: Regex matching the window title.
        automation_id: UIA AutomationId.
        element_name: UIA Name.
        control_type: Control type.
        class_name: Win32 class name.
    """
    elem = _resolve_target(
        bookmark_name, window_title, automation_id, element_name, control_type, class_name
    )
    return perform_get_value(elem)


@mcp.tool()
def set_value(
    value: str,
    bookmark_name: str | None = None,
    window_title: str | None = None,
    automation_id: str | None = None,
    element_name: str | None = None,
    control_type: str | None = None,
    class_name: str | None = None,
) -> str:
    """Set the value of a UI element (e.g. text in an input field).

    Args:
        value: The value to set.
        bookmark_name: Name of a saved bookmark.
        window_title: Regex matching the window title.
        automation_id: UIA AutomationId.
        element_name: UIA Name.
        control_type: Control type.
        class_name: Win32 class name.
    """
    elem = _resolve_target(
        bookmark_name, window_title, automation_id, element_name, control_type, class_name
    )
    return perform_set_value(elem, value)


# ── 4. Actions ────────────────────────────────────────────────────────────

@mcp.tool()
def list_actions() -> list[dict]:
    """List all available pre-defined action sequences.

    Action sequences are parameterised multi-step automations
    (e.g. 'excel_write_cell', 'calc_add_two_numbers').
    """
    return list_action_summaries()


@mcp.tool()
def run_action(
    action_name: str,
    parameters: dict[str, str] | None = None,
) -> list[dict]:
    """Execute a pre-defined action sequence.

    Args:
        action_name: Name of the action sequence.
        parameters: Optional dict of {param} substitution values.
                    Example: {"cell_address": "A1", "cell_value": "Hello"}

    Returns a list of per-step results with status and output.
    """
    return execute_action(action_name, parameters)


# ── 5. Web (CDP) ──────────────────────────────────────────────────────────

@mcp.tool()
def launch_browser(cdp_url: str = "http://localhost:9222", url: str | None = None) -> dict:
    """Start Chrome/Edge in CDP debug mode so the web_* tools can connect.

    CALL THIS FIRST before any web_* tool if no debug browser is running (or
    when a web_* call fails with a CDP connection error). Idempotent — does
    nothing if a debug browser is already up.

    Uses an isolated browser profile so it never conflicts with a normal
    Chrome window you already have open (that conflict is the most common
    reason web automation "silently" fails). Log into sites in THIS window;
    the profile persists between runs.

    Args:
        cdp_url: CDP endpoint to open (default http://localhost:9222).
        url: Optional page to open on launch.
    """
    return _launch_browser(cdp_url, url)


@mcp.tool()
def web_tabs(cdp_url: str = "http://localhost:9222") -> list[dict]:
    """List all open browser tabs. Requires a debug browser — if this errors,
    call launch_browser first.

    Args:
        cdp_url: CDP endpoint URL (default: http://localhost:9222).
    """
    return web_list_tabs(cdp_url)


@mcp.tool()
def web_goto(
    url: str,
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> str:
    """Navigate a browser tab to a URL.

    Args:
        url: The URL to navigate to.
        tab: Filter to find the tab by title or URL substring. Uses first tab if omitted.
        cdp_url: CDP endpoint URL.
    """
    return web_navigate(url, tab, cdp_url)


@mcp.tool()
def web_page_info(
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> dict:
    """Get current page title and URL.

    Args:
        tab: Filter to find the tab by title or URL substring.
        cdp_url: CDP endpoint URL.
    """
    return web_get_page_info(tab, cdp_url)


@mcp.tool()
def web_click_element(
    selector: str,
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> str:
    """Click a web page element by CSS selector.

    Args:
        selector: CSS selector (e.g. '#submit', '.btn-primary', 'button[type=submit]').
        tab: Tab filter by title or URL.
        cdp_url: CDP endpoint URL.
    """
    return web_click(selector, tab, cdp_url)


@mcp.tool()
def web_type_text(
    selector: str,
    text: str,
    clear: bool = True,
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> str:
    """Type text into a web input element by CSS selector.

    Args:
        selector: CSS selector for the input element.
        text: Text to type.
        clear: Clear existing value first (default True).
        tab: Tab filter.
        cdp_url: CDP endpoint URL.
    """
    return web_type(selector, text, clear, tab, cdp_url)


@mcp.tool()
def web_read_text(
    selector: str,
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> str:
    """Read text content of a web element by CSS selector.

    Args:
        selector: CSS selector.
        tab: Tab filter.
        cdp_url: CDP endpoint URL.
    """
    return web_get_text(selector, tab, cdp_url)


@mcp.tool()
def web_find_elements(
    selector: str,
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> list[dict]:
    """Find all elements matching a CSS selector. Returns up to 20 elements with tag, text, id, class, href.

    Args:
        selector: CSS selector (e.g. 'a', 'button', '.item', 'input[type=text]').
        tab: Tab filter.
        cdp_url: CDP endpoint URL.
    """
    return web_query_all(selector, tab, cdp_url)


@mcp.tool()
def web_run_js(
    expression: str,
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> str:
    """Execute JavaScript in the browser page and return the result.

    Args:
        expression: JavaScript expression to evaluate.
        tab: Tab filter.
        cdp_url: CDP endpoint URL.
    """
    result = web_execute_js(expression, tab, cdp_url)
    return str(result)


@mcp.tool()
def web_fill(
    form_data: dict[str, str],
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> list[str]:
    """Fill multiple form fields at once. Keys are CSS selectors, values are text.

    Args:
        form_data: Dict of {selector: value} pairs.
                   Example: {"#username": "john", "#password": "secret"}
        tab: Tab filter.
        cdp_url: CDP endpoint URL.
    """
    return web_fill_form(form_data, tab, cdp_url)


@mcp.tool()
def web_wait(
    selector: str,
    timeout_ms: int = 5000,
    tab: str | None = None,
    cdp_url: str = "http://localhost:9222",
) -> str:
    """Wait for an element to appear on the page.

    Args:
        selector: CSS selector to wait for.
        timeout_ms: Maximum wait time in milliseconds (default 5000).
        tab: Tab filter.
        cdp_url: CDP endpoint URL.
    """
    return web_wait_for(selector, timeout_ms, tab, cdp_url)


# ── 6. Screen & coordinates (fallback tier — element tools are primary) ──

@mcp.tool()
def screenshot_window(
    window_title: str | None = None,
    annotate: bool = True,
    max_elems: int = 80,
) -> dict:
    """Screenshot a window (or full screen) to a local temp file.

    FALLBACK ONLY: prefer element-based tools (click_element/web_*). Use this
    when inspect_tree returns no usable elements (custom-rendered apps).

    With annotate=True, UIA element rectangles are numbered on the image and
    returned as an element map — pick a number and click its 'center' via
    click_at (coordinates come from UIA, not pixel guessing).

    Args:
        window_title: Regex matching the window title. None = full screen.
        annotate: Overlay numbered UIA element boxes (default True).
        max_elems: Max elements to annotate (default 80).

    Returns {path, size, origin, elements:[{n, name, control_type,
    automation_id, rect, center}], hint}. Read the image file only if the
    element map is insufficient.
    """
    return computer.take_screenshot(window_title, annotate, max_elems)


@mcp.tool()
def click_at(x: int, y: int, button: str = "left", double: bool = False) -> str:
    """Click at absolute screen coordinates (fallback for apps without UIA elements).

    Args:
        x, y: Screen coordinates (e.g. an element 'center' from screenshot_window).
        button: left | right | middle.
        double: Double-click if True.
    """
    return computer.click_at(x, y, button, double)


@mcp.tool()
def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.4) -> str:
    """Drag from (x1,y1) to (x2,y2) with the left button held.

    Args:
        x1, y1: Start screen coordinates.
        x2, y2: End screen coordinates.
        duration: Drag duration in seconds (default 0.4).
    """
    return computer.drag(x1, y1, x2, y2, duration)


@mcp.tool()
def scroll_at(x: int, y: int, clicks: int = -3) -> str:
    """Scroll the mouse wheel at screen coordinates.

    Args:
        x, y: Screen coordinates to scroll at.
        clicks: Wheel notches; negative = down, positive = up (default -3).
    """
    return computer.scroll_at(x, y, clicks)


@mcp.tool()
def send_keys(keys: str) -> str:
    """Send keystrokes to the foreground window (pywinauto syntax).

    Args:
        keys: e.g. "{ENTER}", "^a", "%{F4}", "hello{TAB}world".
    """
    return computer.send_keys_global(keys)


# ── 6b. Win32 low-level controls (fallback tier 2: UIA → Win32 → screen) ──

@mcp.tool()
def win32_find(
    window_title: str,
    class_name: str | None = None,
    control_id: int | None = None,
    text_re: str | None = None,
    min_width: int = 0,
    visible_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    """Enumerate Win32 child controls of a window (works on apps that hide from UIA).

    Use when inspect_tree returns nothing useful: custom-framework apps
    (e.g. KakaoTalk EVA) often still reuse standard Win32 controls like
    'Edit'/'RICHEDIT50W', and even EVA sub-views are Win32 child windows whose
    window text names them (e.g. text_re="ChatRoomListCtrl"). Filter by
    class_name/control_id/text/min_width.

    Args:
        window_title: Regex matching the top-level window title.
        class_name: Exact Win32 class (e.g. "Edit", "Button", "#32770").
        control_id: Dialog control ID (GetDlgCtrlID).
        text_re: Regex on the control's text.
        min_width: Minimum pixel width (filters tiny decorations).
        visible_only: False includes hidden controls — some apps keep e.g.
            search boxes 0x0/hidden until activated (KakaoTalk).
        limit: Max results (default 50).

    Returns [{hwnd, class, control_id, class_index, text, rect, size, visible}].
    Pass the hwnd to win32_set_text / win32_click / win32_get_text.
    """
    return win32_native.win32_find_controls(
        window_title, class_name, control_id, text_re, min_width, visible_only, limit
    )


@mcp.tool()
def win32_get_text(
    hwnd: int | None = None,
    window_title: str | None = None,
    class_name: str | None = None,
    control_id: int | None = None,
    text_re: str | None = None,
    index: int = 0,
) -> str:
    """Read a Win32 control's text via WM_GETTEXT (no focus needed, background OK).

    Target by hwnd (from win32_find) OR window_title + class_name/control_id.
    index picks the Nth match (0-based).
    """
    return win32_native.win32_get_text(hwnd, window_title, class_name, control_id, text_re, index)


@mcp.tool()
def win32_set_text(
    text: str,
    hwnd: int | None = None,
    window_title: str | None = None,
    class_name: str | None = None,
    control_id: int | None = None,
    text_re: str | None = None,
    index: int = 0,
) -> str:
    """Inject text into a Win32 control via WM_SETTEXT (no keystrokes, no focus steal).

    Note: WM_SETTEXT replaces the text but does NOT fire input events — some
    apps (e.g. chat send buttons) stay disabled. In that case use clipboard
    paste + real keys instead (send_keys).
    """
    return win32_native.win32_set_text(text, hwnd, window_title, class_name, control_id, text_re, index)


@mcp.tool()
def win32_click(
    hwnd: int | None = None,
    window_title: str | None = None,
    class_name: str | None = None,
    control_id: int | None = None,
    text_re: str | None = None,
    index: int = 0,
    method: str = "bm_click",
) -> str:
    """Click a Win32 control by message (BM_CLICK for buttons; method="post" sends
    WM_LBUTTONDOWN/UP to the control center — works on some non-button controls).

    No mouse movement, no focus steal, background windows OK. If neither works
    (custom-rendered), fall back to click_at with screen coordinates.
    """
    return win32_native.win32_click_control(hwnd, window_title, class_name, control_id, text_re, index, method)


@mcp.tool()
def win32_key(
    key: str,
    hwnd: int | None = None,
    window_title: str | None = None,
    class_name: str | None = None,
    control_id: int | None = None,
    text_re: str | None = None,
    index: int = 0,
) -> str:
    """Post a key (enter/tab/esc/... or a single char) directly to a Win32 control.

    Focus-free WM_KEYDOWN/UP. Some apps only accept real keyboard input —
    then use send_keys after focusing.
    """
    return win32_native.win32_post_key(key, hwnd, window_title, class_name, control_id, text_re, index)


# ── 7. Batch execution ────────────────────────────────────────────────────

def _batch_resolve(kw: dict):
    return _resolve_target(
        kw.get("bookmark_name"), kw.get("window_title"), kw.get("automation_id"),
        kw.get("element_name"), kw.get("control_type"), kw.get("class_name"),
    )


def _batch_verify_window(window_title: str, should_exist: bool = True) -> str:
    pat = re.compile(window_title, re.IGNORECASE)
    titles = [w["title"] for w in list_open_windows()]
    found = any(pat.search(t) for t in titles)
    if found == bool(should_exist):
        return f"OK: '{window_title}' {'present' if found else 'absent'}"
    raise RuntimeError(
        f"verify_window failed: '{window_title}' "
        f"{'not found' if should_exist else 'still present'}. Open: {titles[:8]}"
    )


_STEP_TOOLS: dict[str, Any] = {
    # native (element)
    "click_element": lambda **kw: perform_click(_batch_resolve(kw)),
    "type_text": lambda text, **kw: perform_type(_batch_resolve(kw), text),
    "set_value": lambda value, **kw: perform_set_value(_batch_resolve(kw), value),
    "get_value": lambda **kw: perform_get_value(_batch_resolve(kw)),
    # coordinates / keys
    "click_at": computer.click_at,
    "drag": computer.drag,
    "scroll_at": computer.scroll_at,
    "send_keys": computer.send_keys_global,
    "screenshot_window": computer.take_screenshot,
    # win32 (low-level)
    "win32_find": win32_native.win32_find_controls,
    "win32_get_text": win32_native.win32_get_text,
    "win32_set_text": win32_native.win32_set_text,
    "win32_click": win32_native.win32_click_control,
    "win32_key": win32_native.win32_post_key,
    # web (CDP)
    "web_goto": lambda url, tab=None, cdp_url=DEFAULT_CDP_URL: web_navigate(url, tab, cdp_url),
    "web_click_element": lambda selector, tab=None, cdp_url=DEFAULT_CDP_URL: web_click(selector, tab, cdp_url),
    "web_type_text": lambda selector, text, clear=True, tab=None, cdp_url=DEFAULT_CDP_URL: web_type(selector, text, clear, tab, cdp_url),
    "web_read_text": lambda selector, tab=None, cdp_url=DEFAULT_CDP_URL: web_get_text(selector, tab, cdp_url),
    "web_wait": lambda selector, timeout_ms=5000, tab=None, cdp_url=DEFAULT_CDP_URL: web_wait_for(selector, timeout_ms, tab, cdp_url),
    "web_run_js": lambda expression, tab=None, cdp_url=DEFAULT_CDP_URL: str(web_execute_js(expression, tab, cdp_url)),
    # control flow
    "wait_ms": lambda ms: (time.sleep(ms / 1000), f"waited {ms}ms")[1],
    "verify_window": _batch_verify_window,
}


@mcp.tool()
def run_steps(steps: list[dict], stop_on_error: bool = True) -> list[dict]:
    """Execute a sequence of ui-bridge operations in ONE call (saves round-trips).

    Use for known multi-step flows; insert verify_window/get_value steps as
    closed-loop checks. A failing step stops the batch (stop_on_error=True)
    so you can inspect state and continue from that step.

    Args:
        steps: List of {"tool": <name>, "args": {...}}. Tools:
            click_element / type_text / set_value / get_value (element locator args),
            click_at / drag / scroll_at / send_keys / screenshot_window,
            web_goto / web_click_element / web_type_text / web_read_text /
            web_wait / web_run_js,
            wait_ms {"ms": 500},
            verify_window {"window_title": regex, "should_exist": true}.
        stop_on_error: Stop at first failing step (default True).

    Returns per-step results: [{step, tool, status: ok|error, output}].
    """
    results: list[dict] = []
    for i, step in enumerate(steps):
        name = (step or {}).get("tool", "")
        args = (step or {}).get("args") or {}
        fn = _STEP_TOOLS.get(name)
        if fn is None:
            results.append({"step": i + 1, "tool": name, "status": "error",
                            "output": f"unknown tool. valid: {sorted(_STEP_TOOLS)}"})
            if stop_on_error:
                break
            continue
        try:
            out = fn(**args)
            results.append({"step": i + 1, "tool": name, "status": "ok", "output": out})
        except Exception as exc:
            results.append({"step": i + 1, "tool": name, "status": "error",
                            "output": f"{type(exc).__name__}: {exc}"})
            if stop_on_error:
                break
    return results


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
