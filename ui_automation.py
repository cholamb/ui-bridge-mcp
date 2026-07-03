"""UiBridge MCP - pywinauto wrapper.

All direct pywinauto calls live here.  The rest of the codebase
imports only this module, making it easy to mock for testing.
"""

from __future__ import annotations

import ctypes
import re
import time
from typing import Any

import pywinauto
from pywinauto import Desktop
from pywinauto.application import Application
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import ElementNotFoundError

from models import ElementLocator


# ── Window discovery ──────────────────────────────────────────────────────

def list_open_windows() -> list[dict[str, Any]]:
    """Return information about every visible top-level window."""
    desktop = Desktop(backend="uia")
    results: list[dict[str, Any]] = []
    for win in desktop.windows():
        try:
            info = {
                "title": win.window_text(),
                "class_name": win.element_info.class_name,
                "control_type": win.element_info.control_type,
                "process_id": win.element_info.process_id,
                "handle": win.handle,
                "visible": win.is_visible(),
                "rectangle": {
                    "left": win.rectangle().left,
                    "top": win.rectangle().top,
                    "right": win.rectangle().right,
                    "bottom": win.rectangle().bottom,
                },
            }
            # Only include windows that have a title and are visible
            if info["title"] and info["visible"]:
                results.append(info)
        except Exception:
            continue
    return results


# ── UI tree traversal ─────────────────────────────────────────────────────

def _element_to_dict(elem: UIAWrapper, current_depth: int, max_depth: int, index_path: list[int]) -> dict[str, Any]:
    """Recursively convert a UI element and its children to a dict."""
    node: dict[str, Any] = {
        "name": elem.element_info.name or "",
        "automation_id": elem.element_info.automation_id or "",
        "control_type": elem.element_info.control_type or "",
        "class_name": elem.element_info.class_name or "",
        "index_path": list(index_path),
    }

    if current_depth < max_depth:
        children = []
        try:
            for i, child in enumerate(elem.children()):
                child_path = index_path + [i]
                children.append(
                    _element_to_dict(child, current_depth + 1, max_depth, child_path)
                )
        except Exception:
            pass
        if children:
            node["children"] = children

    return node


def get_ui_tree(window_title_re: str, max_depth: int = 3) -> dict[str, Any]:
    """Get the UI Automation tree for a window matching *window_title_re*."""
    max_depth = max(1, min(max_depth, 10))
    win = _connect_window(window_title_re)
    # Ensure we have a UIAWrapper (not a WindowSpecification)
    wrapper = win.wrapper_object() if hasattr(win, "wrapper_object") else win
    return _element_to_dict(wrapper, 0, max_depth, [])


# ── Window connection helper ──────────────────────────────────────────────

# 제목 정규식 → 창 핸들 캐시. 같은 창을 반복 조작할 때(대부분의 작업이 그렇다)
# 매 호출 재연결·재열거 비용을 없앤다. 유효성은 IsWindow+제목 재확인으로 검증.
_WIN_CACHE: dict[str, int] = {}


def _connect_window(window_title_re: str):
    """Connect to a window by title regex.

    Returns a pywinauto ``WindowSpecification`` (which supports
    ``child_window``) when possible, falling back to a raw
    ``UIAWrapper`` for UWP / multi-process apps.
    """
    pattern = re.compile(window_title_re, re.IGNORECASE)

    # Strategy 0: handle cache (validated before reuse)
    hwnd = _WIN_CACHE.get(window_title_re)
    if hwnd:
        try:
            if ctypes.windll.user32.IsWindow(hwnd):
                spec = Desktop(backend="uia").window(handle=hwnd)
                if pattern.search(spec.wrapper_object().window_text() or ""):
                    return spec
        except Exception:
            pass
        _WIN_CACHE.pop(window_title_re, None)

    # Strategy 1: Application.connect → returns WindowSpecification
    # (timeout 3→0.7: 실패 경로에서 매번 3초를 버리던 대기 단축 —
    #  UWP·멀티프로세스 앱은 어차피 Strategy 2로 잡힌다)
    try:
        app = Application(backend="uia").connect(title_re=window_title_re, timeout=0.7)
        win_spec = app.top_window()
        # Verify the window actually matches
        wrapper = win_spec.wrapper_object()
        if pattern.search(wrapper.window_text() or ""):
            _WIN_CACHE[window_title_re] = wrapper.handle
            return win_spec
    except Exception:
        pass

    # Strategy 2: Desktop search (UWP, multi-process apps)
    try:
        desktop = Desktop(backend="uia")
        for w in desktop.windows():
            try:
                if pattern.search(w.window_text() or ""):
                    try:
                        _WIN_CACHE[window_title_re] = w.handle
                    except Exception:
                        pass
                    return w
            except Exception:
                continue
    except Exception:
        pass

    # List available windows for a helpful error message
    available = [w["title"] for w in list_open_windows()]
    raise ElementNotFoundError(
        f"No window matching '{window_title_re}'. Available: {available[:10]}"
    )


# ── Element interaction ───────────────────────────────────────────────────

def perform_click(element: UIAWrapper) -> str:
    """Click a UI element."""
    element.set_focus()
    time.sleep(0.05)
    element.click_input()
    return "clicked"


def perform_type(element: UIAWrapper, text: str) -> str:
    """Type text into a UI element using keyboard simulation."""
    element.set_focus()
    time.sleep(0.05)
    element.type_keys(text, with_spaces=True, with_tabs=True)
    return f"typed: {text}"


def perform_key_press(element: UIAWrapper, keys: str) -> str:
    """Send special key presses (e.g. {ENTER}, {TAB}, {ESC})."""
    element.set_focus()
    time.sleep(0.05)
    element.type_keys(keys)
    return f"key_press: {keys}"


def perform_get_value(element: UIAWrapper) -> str:
    """Read the value / text of a UI element.

    Tries the UIA ValuePattern first, then falls back to window_text().
    """
    # Try ValuePattern
    try:
        iface = element.iface_value
        if iface is not None:
            val = iface.CurrentValue
            if val is not None:
                return str(val)
    except Exception:
        pass

    # Fallback: window text
    return element.window_text() or ""


def perform_set_value(element: UIAWrapper, value: str) -> str:
    """Set the value of a UI element.

    Tries ValuePattern.SetValue → set_edit_text → type_keys.
    """
    # Try ValuePattern
    try:
        iface = element.iface_value
        if iface is not None:
            iface.SetValue(value)
            return f"set_value (ValuePattern): {value}"
    except Exception:
        pass

    # Try set_edit_text (for Edit controls)
    try:
        element.set_edit_text(value)
        return f"set_value (set_edit_text): {value}"
    except Exception:
        pass

    # Fallback: select all and type
    element.set_focus()
    time.sleep(0.05)
    element.type_keys("^a")  # Ctrl+A
    time.sleep(0.05)
    element.type_keys(value, with_spaces=True)
    return f"set_value (type_keys): {value}"


def perform_focus(element: UIAWrapper) -> str:
    """Bring an element into focus."""
    element.set_focus()
    return "focused"
