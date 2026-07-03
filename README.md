# UiBridge MCP

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

## Performance

Connections are cached instead of re-created per command (auto-reconnect on drop):

- Web element read: **~2.6 ms/call** (vs seconds when handshaking per call)
- Window connect: ~0.9 s first → **~5 ms** cached
- CDP port auto-discovery: if nothing listens on the default 9222, known
  fallback ports are scanned (`UIBRIDGE_CDP_FALLBACK_PORTS` env var)

## Requirements

- Windows 10/11, Python 3.10+
- Chrome or Edge (for the web tools)

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

## Tools (23)

- **Discovery**: `list_windows`, `inspect_tree`
- **Interaction**: `click_element`, `type_text`, `get_value`, `set_value`
- **Bookmarks / actions**: `bookmark_element`, `list_bookmarks`, `delete_bookmark`,
  `list_actions`, `run_action` — save frequently used elements by name,
  run parameterised multi-step sequences
- **Web (CDP)**: `web_tabs`, `web_goto`, `web_page_info`, `web_click_element`,
  `web_type_text`, `web_read_text`, `web_find_elements`, `web_run_js`,
  `web_fill`, `web_wait`
- **Win32 low-level** (fallback tier 2): `win32_find` (filter by class /
  control ID / text regex; `visible_only=false` includes hidden controls),
  `win32_get_text` / `win32_set_text` (WM_GETTEXT / WM_SETTEXT — no focus
  needed), `win32_click` (BM_CLICK / posted mouse messages), `win32_key`
- **Screen & coordinates** (fallback tier 3): `screenshot_window` (numbered
  UIA overlay + element map), `click_at`, `drag`, `scroll_at`, `send_keys`
- **Batch**: `run_steps` — several steps in one call, stops at the first
  failing step so you can inspect and resume

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

## License

MIT

---

# 한국어 안내

**스크린샷 없이 Windows를 조종하는 LLM 에이전트용 MCP 서버입니다.**

일반적인 비전 방식 컴퓨터 유즈는 매 단계 스크린샷을 찍어 모델이 좌표를
추측합니다 — 느리고, 토큰이 많이 들고, 창 크기가 바뀌면 오클릭이 납니다.
UiBridge는 반대로, 버튼·입력칸을 **이름/ID로 지목**해 조작합니다. 모든
상호작용이 로컬 API(UIA·Win32·CDP)를 거치므로 화면 내용이 외부로 나가지
않습니다.

## 3단 폴백 사다리

| 단계 | 방식 | 대상 |
|---|---|---|
| 1 | **UIA / CDP** (기본) | 접근성을 노출하는 대부분의 앱·모든 웹 |
| 2 | **Win32 메시지** (`win32_find`/`win32_set_text`/`win32_click`) | UIA를 숨기는 커스텀 프레임워크 앱 — 표준 Edit/Button 자식 창과 내부 뷰를 클래스·컨트롤ID·텍스트로 탐색, 포커스 안 뺏고 백그라운드 창에도 주입 |
| 3 | **주석 스크린샷 + 좌표** (`screenshot_window`+`click_at`) | 순수 렌더 영역 — 스크린샷에 UIA 요소 번호를 오버레이해 모델은 번호만 고르고 좌표는 코드가 계산 (Set-of-Marks) |

여기에 `run_steps` 배치(여러 단계를 1회 호출로, 단계별 검증 포함)까지 —
알려진 흐름은 왕복 없이 한 번에 실행됩니다.

## 설치

```bat
python -m pip install -r requirements.txt
python install.py        :: ~/.claude/settings.json에 자동 등록
:: Claude Code 재시작하면 ui-bridge 도구가 보입니다
```

웹 기능은 브라우저를 디버그 모드로 띄우면 됩니다: `start_edge_debug.bat`
(또는 `chrome.exe --remote-debugging-port=9222`)

설치 확인은 `tests\` 폴더의 하네스로(메모장으로 자가 검증):

```bat
python tests\uia_harness.py
```

## 제공 도구

- **탐색**: `list_windows`, `inspect_tree`
- **상호작용**: `click_element`, `type_text`, `get_value`, `set_value`
- **북마크·액션**: 자주 쓰는 요소를 이름으로 저장, 파라미터화된 다단계 시퀀스 실행
- **웹(CDP)**: `web_tabs`, `web_goto`, `web_page_info`, `web_click_element`,
  `web_type_text`, `web_read_text`, `web_find_elements`, `web_run_js`,
  `web_fill`, `web_wait`
- **Win32 저수준**(폴백 2단): `win32_find`(클래스·컨트롤ID·텍스트 앵커,
  `visible_only=false`로 숨김 포함), `win32_get_text`/`win32_set_text`
  (WM_GETTEXT/WM_SETTEXT, 포커스·전면 불필요), `win32_click`(BM_CLICK/post),
  `win32_key`
- **화면·좌표 폴백**(3단): `screenshot_window`(주석=UIA 요소 번호
  오버레이+좌표 매핑), `click_at`, `drag`, `scroll_at`, `send_keys`
- **배치**: `run_steps` — 여러 단계를 1회 호출로 실행, 실패 시 해당 단계에서
  중단

## 설정 파일

`config/` 폴더에는 동작 예시(계산기, Excel)가 들어 있습니다.
필요에 맞게 수정하거나 비우고 사용하세요.

- `config/bookmarks.json` — 저장된 UI 요소 북마크
- `config/apps.json` — 앱별 공통 로케이터 힌트
- `config/actions.json` — 파라미터화된 멀티스텝 액션 시퀀스

## 보안

- 스크린샷 기본 미사용 — 3단 폴백에서만 로컬 temp에 저장하고 경로만 반환
- 모든 상호작용이 로컬 API 호출 — 화면·데이터가 외부로 나가지 않음
- 비밀값 하드코딩 없음, 텔레메트리 없음

## 라이선스

MIT
