# UiBridge MCP — 스크린샷 없이 Windows를 조종하는 로컬 자동화 서버

Claude Code(또는 임의의 MCP 클라이언트)에 붙여서 **Windows 네이티브 앱과 웹 페이지를
"픽셀 추측" 없이 요소 단위로 제어**하는 MCP 서버입니다.

일반적인 컴퓨터 유즈(비전) 방식은 매 단계 스크린샷을 찍어 모델이 좌표를 추측합니다 —
느리고, 토큰이 많이 들고, 창 크기가 바뀌면 오클릭이 납니다. UiBridge는 반대로 갑니다:

- **UI Automation(접근성 API)** 으로 버튼·입력칸을 이름/ID로 지목해 클릭·입력
- **Chrome DevTools Protocol(CDP)** 로 웹 페이지 DOM을 CSS 셀렉터로 직접 제어
- 화면 내용이 모델로 전송되지 않음 — 요청한 요소의 텍스트만 오갑니다 (전부 로컬)

## 3단 폴백 사다리 — 안 잡히는 앱이 거의 없습니다

| 단계 | 방식 | 대상 |
|---|---|---|
| 1 | **UIA / CDP** (기본) | 접근성을 노출하는 대부분의 앱·모든 웹 |
| 2 | **Win32 메시지** (`win32_find`/`win32_set_text`/`win32_click`) | UIA를 숨기는 커스텀 프레임워크 앱 — 표준 Edit/Button 자식 창과 내부 뷰를 클래스·컨트롤ID·텍스트로 탐색, 포커스 안 뺏고 백그라운드 창에도 주입 |
| 3 | **주석 스크린샷 + 좌표** (`screenshot_window`+`click_at`) | 순수 렌더 영역 — 스크린샷에 UIA 요소 번호를 오버레이해 모델은 번호만 고르고 좌표는 코드가 계산 (Set-of-Marks) |

여기에 `run_steps` 배치(여러 단계를 1회 호출로, 단계별 검증 포함)까지 —
알려진 흐름은 왕복 없이 한 번에 실행됩니다.

## 성능

연결을 호출마다 새로 만들지 않고 캐시합니다(끊기면 자동 재접속):

- 웹 요소 읽기: **~2.6ms/호출** (연결 비캐시 방식 대비 수십~수천 배)
- 창 연결: 최초 ~0.9s → 캐시 후 **~5ms**
- CDP 포트 자동 탐색: 기본 9222에 브라우저가 없으면 알려진 포트 폴백
  (`UIBRIDGE_CDP_FALLBACK_PORTS` 환경변수로 지정)

## 제공 도구 (23종 요약)

- 탐색: `list_windows` `inspect_tree` / 상호작용: `click_element` `type_text` `get_value` `set_value`
- 북마크·액션: 자주 쓰는 요소를 이름으로 저장, 파라미터화된 다단계 시퀀스 실행
- 웹(CDP): `web_goto` `web_click_element` `web_type_text` `web_read_text` `web_find_elements` `web_run_js` `web_fill` `web_wait` 등
- Win32: `win32_find` `win32_get_text` `win32_set_text` `win32_click` `win32_key`
- 화면·좌표: `screenshot_window` `click_at` `drag` `scroll_at` `send_keys`
- 배치: `run_steps`

## 설치 (3줄)

```bat
python -m pip install -r requirements.txt
python install.py        :: ~/.claude/settings.json에 자동 등록
:: Claude Code 재시작하면 ui-bridge 도구가 보입니다
```

웹 기능은 브라우저를 디버그 모드로 띄우면 됩니다: `start_edge_debug.bat`
(또는 `chrome.exe --remote-debugging-port=9222`)

설치 확인은 `tests\` 폴더의 하네스로: `python tests\uia_harness.py` (메모장으로 자가 검증)

## 요구 사항

- Windows 10/11, Python 3.10+
- (웹 기능) Chrome 또는 Edge

## 보안

- 스크린샷 기본 미사용 — 3단 폴백에서만 로컬 temp에 저장하고 경로만 반환
- 모든 상호작용이 로컬 API 호출 — 화면·데이터가 외부로 나가지 않음
- 비밀값 하드코딩 없음, 텔레메트리 없음

MIT 라이선스. 자세한 사용법은 `README.md` 참조.
