# UiBridge MCP

### 스크린샷 없는 윈도우 컴퓨터 유즈.

[English](README.md) | **[한국어](README.ko.md)**

![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows) ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white) ![MCP](https://img.shields.io/badge/MCP-server-8A2BE2) ![License](https://img.shields.io/badge/license-MIT-green)

AI가 스크린샷에서 픽셀을 추측하는 대신 버튼을 **이름으로** 클릭합니다 —
그래서 빠르고(명령당 수 ms), 창이 움직여도 오클릭이 없고, 화면이 밖으로
나가지 않습니다.

Claude Code(또는 임의의 MCP 클라이언트)에 붙여서 **Windows 네이티브 앱과 웹
페이지를 "픽셀 추측" 없이 요소 단위로 제어**합니다. 모든 상호작용이 로컬
API(UI Automation·Win32 메시지·Chrome DevTools Protocol)를 거치므로 화면
내용이 외부로 나가지 않습니다.

일반적인 비전 방식 컴퓨터 유즈는 매 단계 스크린샷을 찍어 모델이 좌표를
추측합니다 — 느리고, 토큰이 많이 들고, 창이 움직이면 오클릭이 납니다.
UiBridge는 반대로 갑니다:

- **UI Automation(UIA)** — 버튼·입력칸을 이름/AutomationId로 지목해 클릭·입력
- **Chrome DevTools Protocol(CDP)** — 웹 페이지 DOM을 CSS 셀렉터로 직접 제어
- 화면 내용이 모델로 전송되지 않음 — 요청한 요소의 텍스트만 오갑니다

## 3단 폴백 사다리

| 단계 | 방식 | 대상 |
|---|---|---|
| 1 | **UIA / CDP** (기본) | 접근성을 노출하는 대부분의 앱·모든 웹 |
| 2 | **Win32 메시지** (`win32_find`/`win32_set_text`/`win32_click`) | UIA를 숨기는 커스텀 프레임워크 앱 — 표준 Edit/Button 자식 창과 내부 뷰를 클래스·컨트롤ID·텍스트로 탐색, 포커스 안 뺏고 백그라운드 창에도 주입 |
| 3 | **주석 스크린샷 + 좌표** (`screenshot_window`+`click_at`) | 순수 렌더 영역 — 스크린샷에 UIA 요소 번호를 오버레이해 모델은 번호만 고르고 좌표는 코드가 계산 (Set-of-Marks) |

여기에 `run_steps` 배치(여러 단계를 1회 호출로, 단계별 검증 포함)까지.

## 설치

```bat
python -m pip install -r requirements.txt
python install.py        :: ~/.claude/settings.json에 자동 등록
:: Claude Code 재시작하면 ui-bridge 도구가 보입니다
```

웹 기능은 브라우저를 디버그 모드로 띄우면 됩니다:

```bat
start_edge_debug.bat
:: 또는: chrome.exe --remote-debugging-port=9222
```

설치 확인은 자가 검증 하네스로(메모장 사용):

```bat
python tests\uia_harness.py
python tests\stage3_harness.py
python tests\win32_harness.py
```

**요구 사항**: Windows 10/11, Python 3.10+, (웹 기능) Chrome 또는 Edge.

## 사용 예시

등록만 하면 Claude Code에 말로 시키면 됩니다 — 알아서 맞는 도구를 고릅니다.
아래는 각 요청에서 내부적으로 일어나는 일입니다.

### 1. 데스크톱 앱 조작

> *"메모장 열어서 'hello world' 입력하고 다시 읽어줘"*

```
inspect_tree(window_title="메모장")             → 편집 영역 발견 (automation_id=15)
set_value(window_title="메모장", automation_id="15", value="hello world")
get_value(window_title="메모장", automation_id="15")   → "hello world"
```

스크린샷 0장, 좌표 추측 0회. 창이 리사이즈되거나 다른 창 뒤에 있어도 동작합니다.

### 2. 웹 폼 입력

> *"디버그 브라우저에서 관리자 페이지 로그인해줘"*

```
web_goto(url="https://example.com/login")        → readyState=complete까지 대기
web_fill(form_data={"#username": "admin", "#password": "..."})
web_click_element(selector="button[type=submit]")
web_wait(selector=".dashboard", timeout_ms=15000)
```

### 3. UIA를 숨기는 앱 (커스텀 프레임워크)

일부 앱(커스텀 렌더러 기반 메신저 등)은 UIA에 거의 아무것도 노출하지
않습니다. 2단으로 내려갑니다:

```
win32_find(window_title="MyChatApp", class_name="Edit", visible_only=false)
   → [{hwnd: 132002, class: "Edit", size: [326, 28], ...}]
win32_set_text(hwnd=132002, text="검색어")       → WM_SETTEXT, 포커스 안 뺏음
win32_find(window_title="MyChatApp", text_re="ChatRoomList")
   → 커스텀 하위 뷰도 이름·좌표를 가진 Win32 자식 창이라 잡힙니다
```

### 4. 순수 렌더 영역 (3단)

```
screenshot_window(window_title="MyChatApp", annotate=true)
   → {path: "...png", elements: [{n: 3, name: "보내기", center: [1240, 890]}, ...]}
# 모델은 번호 오버레이를 보고 3번을 고른다:
click_at(x=1240, y=890)
```

모델이 픽셀을 추측하지 않습니다 — 요소 번호만 고르고, 클릭 좌표는 UIA
사각형에서 코드가 계산합니다.

### 5. 알려진 흐름을 1회 호출로 배치

```json
run_steps(steps=[
  {"tool": "set_value",     "args": {"window_title": "메모장", "automation_id": "15", "value": "보고 완료"}},
  {"tool": "wait_ms",       "args": {"ms": 200}},
  {"tool": "get_value",     "args": {"window_title": "메모장", "automation_id": "15"}},
  {"tool": "verify_window", "args": {"window_title": "메모장"}}
])
```

실패한 단계에서 멈추고 단계별 결과를 반환하므로, 에이전트가 정확히 끊긴
지점부터 재개할 수 있습니다.

## 성능

연결을 명령마다 새로 만들지 않고 캐시합니다(끊기면 자동 재접속):

- 웹 요소 읽기: **호출당 ~2.6ms** (매번 핸드셰이크하는 방식은 초 단위)
- 창 연결: 최초 ~0.9초 → 캐시 후 **~5ms**
- CDP 포트 자동 탐색: 기본 9222에 브라우저가 없으면 알려진 포트 폴백
  (`UIBRIDGE_CDP_FALLBACK_PORTS` 환경변수)

## 제공 도구 (23종)

- **탐색**: `list_windows`, `inspect_tree`
- **상호작용**: `click_element`, `type_text`, `get_value`, `set_value`
- **북마크·액션**: `bookmark_element`, `list_bookmarks`, `delete_bookmark`,
  `list_actions`, `run_action` — 자주 쓰는 요소를 이름으로 저장, 파라미터화된
  다단계 시퀀스 실행
- **웹(CDP)**: `web_tabs`, `web_goto`, `web_page_info`, `web_click_element`,
  `web_type_text`, `web_read_text`, `web_find_elements`, `web_run_js`,
  `web_fill`, `web_wait`
- **Win32 저수준**(폴백 2단): `win32_find`, `win32_get_text`, `win32_set_text`,
  `win32_click`, `win32_key`
- **화면·좌표**(폴백 3단): `screenshot_window`, `click_at`, `drag`,
  `scroll_at`, `send_keys`
- **배치**: `run_steps`

## 설정 파일

`config/` 폴더에는 동작 예시(계산기, Excel)가 들어 있습니다.
필요에 맞게 수정하거나 비우고 사용하세요.

- `config/bookmarks.json` — 저장된 UI 요소 북마크
- `config/apps.json` — 앱별 공통 로케이터 힌트
- `config/actions.json` — 파라미터화된 멀티스텝 액션 시퀀스

## CLI

```bat
python cli.py --help
```

MCP 클라이언트 없이 같은 기능을 실행합니다 — 예약작업·결정형 스크립트에 유용.

## 보안

- 스크린샷 기본 미사용 — 3단 폴백에서만 로컬 temp에 저장하고 경로만 반환
- 모든 상호작용이 로컬 API 호출 — 화면·데이터가 외부로 나가지 않음
- 비밀값 하드코딩 없음, 텔레메트리 없음

## 기여

이슈·PR 환영합니다 — 특히 폴백 사다리가 실패하는 앱 제보가 큰 도움이 됩니다
(`inspect_tree` / `win32_find` 출력을 첨부해 주시면 좋습니다).

## 라이선스

MIT © [cholamb](https://github.com/cholamb)
