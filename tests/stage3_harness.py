# -*- coding: utf-8 -*-
"""ui-bridge 3단계 검증 하네스 — 스크린샷(주석)·좌표 클릭·배치 실행. 메모장 실기."""
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import computer
from models import ElementLocator
from ui_automation import list_open_windows, perform_get_value
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

    # 1) 주석 스크린샷: 요소 매핑 + 파일 생성
    shot = computer.take_screenshot(TITLE, annotate=True)
    p = Path(shot["path"])
    check("screenshot 파일 생성", p.exists() and p.stat().st_size > 5000, f"{p.name} {p.stat().st_size}B")
    els = shot.get("elements", [])
    check("주석 요소 매핑", len(els) >= 3, f"{len(els)}개 요소")
    edit = next((e for e in els if e["control_type"] in ("Document", "Edit")), None)
    check("편집영역 요소 식별", edit is not None,
          f"#{edit['n']} {edit['control_type']} auto_id={edit['automation_id']}" if edit else "")

    # 2) 좌표 클릭: 주석 매핑의 center로 클릭(=Set-of-Marks 경로) 후 전역 키 입력
    computer.click_at(*edit["center"])
    computer.send_keys_global("좌표입력OK")
    time.sleep(0.3)
    elem = find_element(TITLE, ElementLocator(automation_id="15"))
    v = perform_get_value(elem)
    check("click_at+send_keys 반영", "좌표입력OK" in v, repr(v[:30]))

    # 3) 스크롤·드래그 — 예외 없이 수행되는지(효과 검증은 앱 의존이라 실행성만)
    cx, cy = edit["center"]
    computer.scroll_at(cx, cy, -2)
    computer.drag(cx, cy, cx + 40, cy + 20, duration=0.2)
    check("scroll/drag 실행", True)

    # 4) 배치 실행: server.py의 run_steps 디스패치 직접 검사
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "srv", Path(__file__).resolve().parent.parent / "server.py")
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    steps = [
        {"tool": "set_value", "args": {"window_title": TITLE, "automation_id": "15",
                                       "value": "배치 1단계"}},
        {"tool": "wait_ms", "args": {"ms": 100}},
        {"tool": "get_value", "args": {"window_title": TITLE, "automation_id": "15"}},
        {"tool": "verify_window", "args": {"window_title": TITLE}},
        {"tool": "verify_window", "args": {"window_title": "없는창XYZ", "should_exist": False}},
    ]
    res = srv.run_steps.fn(steps) if hasattr(srv.run_steps, "fn") else srv.run_steps(steps)
    ok = [r["status"] for r in res]
    check("run_steps 5단계 전부 ok", ok == ["ok"] * 5, str(ok))
    check("배치 내 get_value 값", res[2]["output"] == "배치 1단계", repr(res[2]["output"]))

    # 5) 배치 오류 중단: 미존재 요소 클릭 → 그 지점에서 멈춤
    res = srv.run_steps.fn if hasattr(srv.run_steps, "fn") else srv.run_steps
    res = res([
        {"tool": "get_value", "args": {"window_title": TITLE, "automation_id": "15"}},
        {"tool": "click_element", "args": {"window_title": TITLE, "automation_id": "no_such_id_999"}},
        {"tool": "wait_ms", "args": {"ms": 10}},
    ])
    check("run_steps 오류 중단", len(res) == 2 and res[1]["status"] == "error",
          f"{len(res)}단계 실행, 마지막={res[-1]['status']}")

    print()
    if fails:
        print(f"결과: FAIL {len(fails)}건 — {fails}"); sys.exit(1)
    print("결과: 전부 PASS"); sys.exit(0)
finally:
    proc.kill()
