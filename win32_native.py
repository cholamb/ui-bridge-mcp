"""UiBridge MCP - Win32 저수준 컨트롤 계층.

폴백 사다리의 2단: UIA(1단)가 노출하지 않는 앱(카카오 EVA 등)이라도
표준 Win32 클래스 자식 창(Edit, Button 등)이 있으면 여기서 잡힌다.
그것마저 없는 순수 렌더 영역만 3단(screenshot_window+click_at)으로 간다.

원리: 고전 컨트롤은 전부 hwnd를 가진 '창'이다. EnumChildWindows로 열거해
클래스명·컨트롤ID·크기로 찾고, SendMessage로 OS 메시지를 직접 쏜다
(WM_SETTEXT=텍스트 주입, BM_CLICK=버튼 클릭). 키 시뮬레이션이 아니라
컨트롤에 메시지를 전달하는 것이라 포커스를 뺏지 않고 백그라운드 창에도
동작한다. record-skill이 남기는 win32 앵커(class/control_id/class_index/size)와
필드가 호환된다.

모든 SendMessage는 SendMessageTimeout(ABORTIFHUNG)으로 보내 응답 없는
창에 서버가 매달리지 않는다.
"""

from __future__ import annotations

import ctypes
import re
from ctypes import wintypes
from typing import Any

_u = ctypes.windll.user32

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
BM_CLICK = 0x00F5
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
SMTO_ABORTIFHUNG = 0x0002

_VK = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
    "f4": 0x73, "f5": 0x74,
}

_SendMessageTimeoutW = _u.SendMessageTimeoutW
_SendMessageTimeoutW.argtypes = [
    wintypes.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p,
    ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t),
]
_SendMessageTimeoutW.restype = ctypes.c_size_t


def _send(hwnd: int, msg: int, wparam: int = 0, lparam: Any = None,
          timeout_ms: int = 2000) -> int:
    res = ctypes.c_size_t(0)
    ok = _SendMessageTimeoutW(hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG,
                              timeout_ms, ctypes.byref(res))
    if not ok:
        raise TimeoutError(f"SendMessage timeout (hwnd={hwnd}, msg=0x{msg:04X})")
    return res.value


def _class_of(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _text_of(hwnd: int, max_len: int = 512) -> str:
    """WM_GETTEXT — 표준 컨트롤은 크로스 프로세스에서도 OS가 버퍼를 마샬링한다."""
    try:
        n = _send(hwnd, WM_GETTEXTLENGTH, timeout_ms=500)
        if n <= 0:
            return ""
        n = min(int(n), max_len)
        buf = ctypes.create_unicode_buffer(n + 1)
        _send(hwnd, WM_GETTEXT, n + 1, ctypes.cast(buf, ctypes.c_void_p), timeout_ms=1000)
        return buf.value
    except Exception:
        return ""


def _rect_of(hwnd: int) -> list[int]:
    r = wintypes.RECT()
    _u.GetWindowRect(hwnd, ctypes.byref(r))
    return [r.left, r.top, r.right, r.bottom]


def _find_root(window_title: str) -> int:
    """제목 정규식으로 최상위 창 hwnd를 찾는다."""
    pat = re.compile(window_title, re.IGNORECASE)
    found: list[int] = []
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if _u.IsWindowVisible(h):
            n = _u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                _u.GetWindowTextW(h, b, n + 1)
                titles.append(b.value[:80])
                if not found and pat.search(b.value):
                    found.append(h)
        return True

    _u.EnumWindows(cb, 0)
    if not found:
        raise LookupError(f"No window matching '{window_title}'. Open: {titles[:10]}")
    return found[0]


def _enum_descendants(root: int) -> list[int]:
    """EnumChildWindows는 직계가 아니라 전체 자손을 열거한다."""
    out: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        out.append(h)
        return True

    _u.EnumChildWindows(root, cb, 0)
    return out


def _describe(hwnd: int, class_counter: dict[str, int]) -> dict:
    cls = _class_of(hwnd)
    idx = class_counter.get(cls, 0)
    class_counter[cls] = idx + 1
    r = _rect_of(hwnd)
    return {
        "hwnd": hwnd,
        "class": cls,
        "control_id": _u.GetDlgCtrlID(hwnd),
        "class_index": idx,  # 같은 클래스 중 몇 번째(record-skill win32 앵커와 동일 의미)
        "text": _text_of(hwnd, 100),
        "rect": r,
        "size": [r[2] - r[0], r[3] - r[1]],
        "visible": bool(_u.IsWindowVisible(hwnd)),
    }


def win32_find_controls(
    window_title: str,
    class_name: str | None = None,
    control_id: int | None = None,
    text_re: str | None = None,
    min_width: int = 0,
    visible_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    """조건에 맞는 Win32 자식 컨트롤을 열거한다(필터 없으면 전체, 최대 limit)."""
    root = _find_root(window_title)
    tpat = re.compile(text_re, re.IGNORECASE) if text_re else None
    counter: dict[str, int] = {}
    out: list[dict] = []
    for h in _enum_descendants(root):
        d = _describe(h, counter)
        if visible_only and not d["visible"]:
            continue
        if class_name and d["class"] != class_name:
            continue
        if control_id is not None and d["control_id"] != control_id:
            continue
        if min_width and d["size"][0] < min_width:
            continue
        if tpat and not tpat.search(d["text"] or ""):
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return out


def _resolve_hwnd(
    hwnd: int | None,
    window_title: str | None,
    class_name: str | None,
    control_id: int | None,
    text_re: str | None,
    index: int,
    min_width: int = 0,
) -> int:
    if hwnd:
        if not _u.IsWindow(hwnd):
            raise LookupError(f"hwnd {hwnd} is no longer a valid window")
        return int(hwnd)
    if not window_title:
        raise ValueError("Provide hwnd, or window_title (+ class_name/control_id/text_re).")
    matches = win32_find_controls(
        window_title, class_name, control_id, text_re, min_width,
        visible_only=True, limit=max(index + 1, 10),
    )
    if len(matches) <= index:
        raise LookupError(
            f"No control #{index} matching class={class_name} control_id={control_id} "
            f"text_re={text_re} in '{window_title}' ({len(matches)} matches). "
            "Use win32_find to inspect."
        )
    return matches[index]["hwnd"]


def win32_get_text(hwnd: int | None = None, window_title: str | None = None,
                   class_name: str | None = None, control_id: int | None = None,
                   text_re: str | None = None, index: int = 0) -> str:
    h = _resolve_hwnd(hwnd, window_title, class_name, control_id, text_re, index)
    return _text_of(h, 4000)


def win32_set_text(text: str, hwnd: int | None = None, window_title: str | None = None,
                   class_name: str | None = None, control_id: int | None = None,
                   text_re: str | None = None, index: int = 0) -> str:
    h = _resolve_hwnd(hwnd, window_title, class_name, control_id, text_re, index)
    buf = ctypes.create_unicode_buffer(text)
    _send(h, WM_SETTEXT, 0, ctypes.cast(buf, ctypes.c_void_p))
    back = _text_of(h, len(text) + 10)
    status = "verified" if back == text else f"read-back mismatch: {back[:40]!r}"
    return f"WM_SETTEXT to hwnd={h} ({status})"


def win32_click_control(hwnd: int | None = None, window_title: str | None = None,
                        class_name: str | None = None, control_id: int | None = None,
                        text_re: str | None = None, index: int = 0,
                        method: str = "bm_click") -> str:
    """BM_CLICK(버튼 표준) 또는 post(WM_LBUTTONDOWN/UP를 컨트롤 중앙 클라이언트 좌표로)."""
    h = _resolve_hwnd(hwnd, window_title, class_name, control_id, text_re, index)
    if method == "bm_click":
        _send(h, BM_CLICK)
        return f"BM_CLICK sent to hwnd={h}"
    r = _rect_of(h)
    cx, cy = (r[2] - r[0]) // 2, (r[3] - r[1]) // 2
    lparam = (cy << 16) | (cx & 0xFFFF)
    _u.PostMessageW(h, WM_LBUTTONDOWN, 1, lparam)
    _u.PostMessageW(h, WM_LBUTTONUP, 0, lparam)
    return f"WM_LBUTTON down/up posted to hwnd={h} at client ({cx},{cy})"


def win32_post_key(key: str, hwnd: int | None = None, window_title: str | None = None,
                   class_name: str | None = None, control_id: int | None = None,
                   text_re: str | None = None, index: int = 0) -> str:
    """WM_KEYDOWN/UP을 컨트롤에 직접 포스트(포커스 불필요). 일부 앱은 실키 입력만 받음."""
    vk = _VK.get(key.lower())
    if vk is None and len(key) == 1:
        vk = ord(key.upper())
    if vk is None:
        raise ValueError(f"Unknown key '{key}'. Known: {sorted(_VK)} or single chars.")
    h = _resolve_hwnd(hwnd, window_title, class_name, control_id, text_re, index)
    _u.PostMessageW(h, WM_KEYDOWN, vk, 0)
    _u.PostMessageW(h, WM_KEYUP, vk, 0xC0000000)
    return f"posted {key} (vk=0x{vk:02X}) to hwnd={h}"
