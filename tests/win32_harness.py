# -*- coding: utf-8 -*-
"""ui-bridge Win32 계층 검증 하네스 — 메모장 Edit 주입·메시지박스 BM_CLICK·카카오 검색창."""
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import win32_native as w

fails = []
def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)

# ── 1) 메모장: Edit 컨트롤 찾기 + WM_SETTEXT/WM_GETTEXT 왕복 ──────────────
np = subprocess.Popen(["notepad.exe"])
try:
    time.sleep(1.5)
    ctrls = w.win32_find_controls(r"메모장|Notepad", class_name="Edit")
    check("win32_find(Edit)", len(ctrls) == 1,
          f"{len(ctrls)}개, control_id={ctrls[0]['control_id'] if ctrls else '-'}")

    r = w.win32_set_text("한글 Win32 주입 'テスト' OK", window_title=r"메모장|Notepad", class_name="Edit")
    check("win32_set_text 검증", "verified" in r, r)

    v = w.win32_get_text(hwnd=ctrls[0]["hwnd"])
    check("win32_get_text(hwnd 직접)", v == "한글 Win32 주입 'テスト' OK", repr(v[:30]))

    # 백그라운드 동작: 다른 창을 앞으로 보내도 주입되는지
    import ctypes
    ctypes.windll.user32.SetForegroundWindow(ctypes.windll.kernel32.GetConsoleWindow())
    r = w.win32_set_text("백그라운드 주입", window_title=r"메모장|Notepad", class_name="Edit")
    check("백그라운드 창 주입", "verified" in r, r)

    # win32_key 실행성(삽입 여부는 앱 의존 — WM_CHAR 미변환)
    w.win32_post_key("end", window_title=r"메모장|Notepad", class_name="Edit")
    check("win32_key 실행", True)
finally:
    np.kill()

# ── 2) 메시지박스: 표준 Button을 BM_CLICK으로 닫기 ────────────────────────
mb = subprocess.Popen([sys.executable, "-c",
                       "import ctypes; ctypes.windll.user32.MessageBoxW(0, 'ui-bridge win32 test', 'WIN32TEST', 0)"])
try:
    time.sleep(1.2)
    btns = w.win32_find_controls("WIN32TEST", class_name="Button")
    check("메시지박스 Button 탐지", len(btns) >= 1,
          f"{len(btns)}개, text={btns[0]['text'] if btns else '-'}")
    w.win32_click_control(hwnd=btns[0]["hwnd"])  # BM_CLICK
    try:
        mb.wait(timeout=5)
        check("BM_CLICK로 닫힘", True, "프로세스 정상 종료")
    except subprocess.TimeoutExpired:
        check("BM_CLICK로 닫힘", False, "5초 내 안 닫힘")
finally:
    if mb.poll() is None:
        mb.kill()

# ── 3) 카카오톡(EVA) 실물 — UIA는 무명 Pane 1개였던 앱 (읽기만) ───────────
# 검색 Edit은 활성화 전 숨김(0x0)이므로 visible_only=False로 존재 확인,
# EVA 하위 뷰는 창 텍스트(ChatRoomListCtrl 등)로 앵커 가능함을 확인.
try:
    edits = w.win32_find_controls(r"^카카오톡$", class_name="Edit", visible_only=False)
    check("카카오톡 Edit 존재(숨김 포함)", len(edits) >= 1, f"{len(edits)}개 (활성화 전 숨김 상태)")
    eva = w.win32_find_controls(r"^카카오톡$", text_re="ChatRoomListCtrl", visible_only=False)
    check("EVA 내부 뷰 텍스트 앵커", len(eva) >= 1,
          f"{eva[0]['text'][:24]} rect={eva[0]['rect']}" if eva else "0개")
except LookupError as e:
    print(f"  [SKIP] 카카오톡 미실행 — {str(e)[:60]}")

print()
if fails:
    print(f"결과: FAIL {len(fails)}건 — {fails}"); sys.exit(1)
print("결과: 전부 PASS"); sys.exit(0)
