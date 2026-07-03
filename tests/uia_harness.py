# -*- coding: utf-8 -*-
"""ui-bridge UIA 2단계 검증 하네스 — 메모장 실기: 창 캐시·요소 탐색·값 주입."""
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import ElementLocator
from ui_automation import _connect_window, perform_get_value, perform_set_value, get_ui_tree
from element_finder import find_element

TITLE = r"메모장|Notepad"
fails = []
def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)

proc = subprocess.Popen(["notepad.exe"])
try:
    time.sleep(1.5)

    t0 = time.time(); win = _connect_window(TITLE); first = time.time() - t0
    t0 = time.time(); win = _connect_window(TITLE); cached = time.time() - t0
    check("창 연결", win is not None, f"최초 {first*1000:.0f}ms → 캐시 {cached*1000:.0f}ms")
    check("캐시 가속", cached < first, f"{first/max(cached,1e-6):.1f}x")

    # 미존재 창: 실패 경로 대기 단축 확인 (구버전은 connect timeout=3s 고정)
    t0 = time.time()
    try:
        _connect_window("존재하지않는창제목XYZ123")
        check("미존재 창 예외", False)
    except Exception:
        check("미존재 창 예외", True, f"{time.time()-t0:.2f}s (구버전 [측정불가], connect 대기 3s→0.7s)")

    elem = find_element(TITLE, ElementLocator(automation_id="15"))  # 메모장 편집영역
    perform_set_value(elem, "양고기 'LAMB' 테스트 \"인용\"")
    v = perform_get_value(elem)
    check("set/get_value 왕복", v == "양고기 'LAMB' 테스트 \"인용\"", repr(v[:40]))

    tree = get_ui_tree(TITLE, 2)
    check("inspect_tree", bool(tree.get("children")), f"루트={tree.get('control_type')}")

    print()
    if fails:
        print(f"결과: FAIL {len(fails)}건 — {fails}"); sys.exit(1)
    print("결과: 전부 PASS"); sys.exit(0)
finally:
    proc.kill()
