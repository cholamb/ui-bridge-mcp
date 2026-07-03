"""UiBridge MCP - 화면·좌표 계층 (3단계: 컴퓨터 유즈 폴백).

요소 기반(UIA/CDP)이 항상 1순위다. 이 모듈은 UIA 트리가 비는 커스텀 렌더
앱(카카오 EVA 등)을 위한 폴백만 제공한다:

- screenshot_window: 창 스크린샷. annotate=True면 UIA 요소 사각형에 번호를
  오버레이하고 번호→요소(좌표 포함) 매핑을 함께 반환한다(Set-of-Marks).
  모델은 픽셀 좌표를 추측하지 않고 번호만 고르며, 클릭 좌표는 UIA rect
  중심을 코드가 계산한다 → 창 크기·해상도 무관 정확도 유지.
- click_at / drag / scroll_at / send_keys: 좌표·전역 키 입력(최후 수단).

스크린샷 파일은 로컬 temp에 저장하고 경로만 반환한다(이미지 자체를
MCP 응답에 싣지 않음 — 모델이 필요할 때만 Read로 열어 토큰을 쓴다).
"""

from __future__ import annotations

import ctypes
import tempfile
import time
from pathlib import Path
from typing import Any

from ui_automation import _connect_window

SHOT_DIR = Path(tempfile.gettempdir()) / "ui-bridge-shots"

# 주석 오버레이 색상 순환(가독성)
_COLORS = [(230, 30, 30), (30, 110, 230), (20, 150, 60), (200, 120, 0), (140, 40, 180)]


def _virtual_origin() -> tuple[int, int]:
    u = ctypes.windll.user32
    return u.GetSystemMetrics(76), u.GetSystemMetrics(77)  # SM_X/YVIRTUALSCREEN


def _collect_elements(wrapper, win_rect, max_elems: int, max_depth: int) -> list[dict]:
    """보이는 UIA 하위 요소를 rect와 함께 수집(번호 매김용)."""
    out: list[dict] = []

    def visit(elem, depth: int):
        if len(out) >= max_elems or depth > max_depth:
            return
        try:
            children = elem.children()
        except Exception:
            return
        for ch in children:
            if len(out) >= max_elems:
                return
            try:
                info = ch.element_info
                r = ch.rectangle()
                w, h = r.right - r.left, r.bottom - r.top
                visible = (
                    w >= 8 and h >= 8
                    and r.right > win_rect.left and r.left < win_rect.right
                    and r.bottom > win_rect.top and r.top < win_rect.bottom
                )
                if visible:
                    out.append({
                        "n": len(out) + 1,
                        "name": (info.name or "")[:80],
                        "control_type": info.control_type or "",
                        "automation_id": info.automation_id or "",
                        "rect": [r.left, r.top, r.right, r.bottom],
                        "center": [(r.left + r.right) // 2, (r.top + r.bottom) // 2],
                    })
            except Exception:
                continue
            visit(ch, depth + 1)

    visit(wrapper, 1)
    return out


def take_screenshot(
    window_title: str | None = None,
    annotate: bool = True,
    max_elems: int = 80,
    max_depth: int = 6,
) -> dict[str, Any]:
    """창(또는 전체 화면) 스크린샷을 temp에 저장하고 경로+요소 매핑을 반환."""
    from PIL import Image, ImageDraw, ImageGrab

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    ox, oy = _virtual_origin()

    wrapper = None
    if window_title:
        win = _connect_window(window_title)
        wrapper = win.wrapper_object() if hasattr(win, "wrapper_object") else win
        try:
            wrapper.set_focus()  # 가려진 창은 캡처가 무의미
            time.sleep(0.15)
        except Exception:
            pass
        r = wrapper.rectangle()
        bbox = (r.left - ox, r.top - oy, r.right - ox, r.bottom - oy)
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        base = (r.left, r.top)
        win_rect = r
    else:
        img = ImageGrab.grab(all_screens=True)
        base = (ox, oy)

        class _R:  # 전체 화면 rect 대용
            left, top = ox, oy
            right, bottom = ox + img.width, oy + img.height
        win_rect = _R()

    elements: list[dict] = []
    if annotate and wrapper is not None:
        elements = _collect_elements(wrapper, win_rect, max_elems, max_depth)
        dr = ImageDraw.Draw(img)
        for el in elements:
            l, t, rt, b = el["rect"]
            x0, y0 = l - base[0], t - base[1]
            x1, y1 = rt - base[0], b - base[1]
            c = _COLORS[(el["n"] - 1) % len(_COLORS)]
            dr.rectangle([x0, y0, x1, y1], outline=c, width=2)
            label = str(el["n"])
            tx, ty = x0 + 2, max(0, y0 - 14)
            tw = 7 * len(label) + 6
            dr.rectangle([tx - 2, ty, tx + tw, ty + 13], fill=c)
            dr.text((tx + 1, ty + 1), label, fill=(255, 255, 255))

    name = f"shot_{time.strftime('%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.png"
    path = SHOT_DIR / name
    img.save(path)

    result: dict[str, Any] = {
        "path": str(path),
        "window": window_title or "(full screen)",
        "size": [img.width, img.height],
        "origin": list(base),  # 이미지 (0,0)의 실제 화면 좌표 — 좌표 환산용
    }
    if annotate and wrapper is not None:
        result["elements"] = elements
        result["hint"] = (
            "Pick an element number and click its 'center' with click_at, "
            "or use its automation_id/name with click_element. "
            "If elements is empty (custom-rendered app), Read the image and "
            "estimate: screen_xy = origin + image_xy."
        )
    return result


# ── 좌표·전역 입력 (최후 수단) ────────────────────────────────────────────

def click_at(x: int, y: int, button: str = "left", double: bool = False) -> str:
    from pywinauto import mouse

    if double:
        mouse.double_click(button=button, coords=(int(x), int(y)))
        return f"double-clicked ({x},{y})"
    mouse.click(button=button, coords=(int(x), int(y)))
    return f"clicked ({x},{y}) [{button}]"


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.4) -> str:
    from pywinauto import mouse

    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    mouse.press(coords=(x1, y1))
    steps = max(2, int(duration / 0.02))
    for i in range(1, steps + 1):
        mouse.move(coords=(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps))
        time.sleep(duration / steps)
    mouse.release(coords=(x2, y2))
    return f"dragged ({x1},{y1}) -> ({x2},{y2})"


def scroll_at(x: int, y: int, clicks: int = -3) -> str:
    """음수=아래로, 양수=위로 (마우스 휠 노치 단위)."""
    from pywinauto import mouse

    mouse.scroll(coords=(int(x), int(y)), wheel_dist=int(clicks))
    return f"scrolled {clicks} at ({x},{y})"


def send_keys_global(keys: str) -> str:
    """포그라운드 창에 키 전송(pywinauto 키 문법: {ENTER}, ^a, %{F4} 등)."""
    from pywinauto.keyboard import send_keys as _sk

    _sk(keys, with_spaces=True, with_tabs=True)
    return f"sent keys: {keys}"
