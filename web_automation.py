"""UiBridge MCP - Web automation via Chrome DevTools Protocol (CDP).

Controls web pages inside Chrome/Edge by connecting to the browser's
remote debugging port. No screenshots, no data leaves the machine.

Prerequisites:
    Start Chrome with remote debugging enabled:
        chrome.exe --remote-debugging-port=9222

    Or Edge:
        msedge.exe --remote-debugging-port=9222
"""

from __future__ import annotations

import itertools
import json
import os
import time
from typing import Any

import requests


# ── CDP Connection ────────────────────────────────────────────────────────

DEFAULT_CDP_URL = "http://localhost:9222"
# 기본 포트(9222)에 브라우저가 없을 때만 탐색하는 알려진 포트들.
# 이 저장소에선 쿠팡 운영 크롬이 격리 목적으로 18800(COUPANG_CDP_PORT)을 쓴다.
# cdp_url을 명시하면 폴백은 동작하지 않는다.
_FALLBACK_PORTS = [
    p.strip() for p in os.environ.get(
        "UIBRIDGE_CDP_FALLBACK_PORTS",
        os.environ.get("COUPANG_CDP_PORT", "18800"),
    ).split(",") if p.strip()
]
_RESOLVED_DEFAULT: list[str | None] = [None]  # 탐색 결과 캐시(프로세스 수명)

_HTTP = requests.Session()
# tab WebSocket 재사용 캐시: 명령마다 새 연결을 만들면 HTTP+WS 핸드셰이크가
# 호출당 반복된다. 죽은 연결은 _send_cdp가 감지해 1회 재접속한다.
_WS_CACHE: dict[str, Any] = {}
_MSG_ID = itertools.count(1)


def _fetch_tabs(cdp_url: str, timeout: float = 3) -> list[dict]:
    resp = _HTTP.get(f"{cdp_url}/json", timeout=timeout)
    resp.raise_for_status()
    return [t for t in resp.json() if t.get("type") == "page"]


def _get_tabs(cdp_url: str = DEFAULT_CDP_URL) -> list[dict]:
    """List all open browser tabs via CDP.

    cdp_url이 기본값(9222)인데 브라우저가 없으면 _FALLBACK_PORTS를 순서대로
    탐색한다(명시 지정 시엔 탐색 없음). 성공한 URL은 캐시하되, 죽으면 재탐색.
    """
    explicit = cdp_url != DEFAULT_CDP_URL
    candidates = [cdp_url]
    if not explicit:
        if _RESOLVED_DEFAULT[0] and _RESOLVED_DEFAULT[0] != cdp_url:
            candidates.insert(0, _RESOLVED_DEFAULT[0])
        candidates += [f"http://localhost:{p}" for p in _FALLBACK_PORTS]

    tried: list[str] = []
    for url in dict.fromkeys(candidates):
        try:
            tabs = _fetch_tabs(url, timeout=1.5 if len(candidates) > 1 else 3)
            if not explicit:
                _RESOLVED_DEFAULT[0] = url
            return tabs
        except requests.RequestException:
            tried.append(url)
            continue
    raise ConnectionError(
        f"Cannot connect to browser CDP (tried: {', '.join(tried)}). "
        "Start Chrome with:\n"
        '  chrome.exe --remote-debugging-port=9222\n'
        "Or Edge with:\n"
        '  msedge.exe --remote-debugging-port=9222'
    )


def _find_tab(title_or_url: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> dict:
    """Find a tab by title or URL substring. Returns the first active tab if no filter."""
    tabs = _get_tabs(cdp_url)
    if not tabs:
        raise ValueError("No browser tabs found.")

    if title_or_url:
        for tab in tabs:
            if title_or_url.lower() in (tab.get("title", "").lower()) or \
               title_or_url.lower() in (tab.get("url", "").lower()):
                return tab
        raise ValueError(
            f"No tab matching '{title_or_url}'. "
            f"Available: {[t['title'][:50] for t in tabs]}"
        )
    return tabs[0]


def _ws_connect(ws_url: str):
    import websocket  # pip install websocket-client

    # Chrome 111+는 Origin 헤더가 있으면 CDP WebSocket을 403으로 거부한다
    # (--remote-allow-origins 없이도 붙도록 Origin을 보내지 않는다)
    ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
    _WS_CACHE[ws_url] = ws
    return ws


def _ws_drop(ws_url: str) -> None:
    ws = _WS_CACHE.pop(ws_url, None)
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass


def _send_cdp(ws_url: str, method: str, params: dict | None = None, timeout: float = 10) -> dict:
    """Send a CDP command over a cached WebSocket and return the result.

    Connection failures (tab closed, browser restarted, stale socket) drop the
    cached socket and retry once with a fresh connection.
    """
    last_exc: Exception | None = None
    for attempt in (1, 2):
        ws = _WS_CACHE.get(ws_url)
        try:
            if ws is None:
                ws = _ws_connect(ws_url)
            ws.settimeout(timeout)
            msg_id = next(_MSG_ID)
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                response = json.loads(ws.recv())
                # CDP 이벤트/이전 호출의 잔여 응답은 id 불일치로 걸러진다
                if response.get("id") == msg_id:
                    if "error" in response:
                        raise RuntimeError(
                            f"CDP error: {response['error'].get('message', response['error'])}"
                        )
                    return response.get("result", {})
        except RuntimeError:
            raise
        except Exception as exc:
            last_exc = exc
            _ws_drop(ws_url)
    raise ConnectionError(f"CDP connection failed for {method}: {last_exc}")


# ── High-level API ────────────────────────────────────────────────────────

def web_list_tabs(cdp_url: str = DEFAULT_CDP_URL) -> list[dict[str, str]]:
    """List all browser tabs with title and URL."""
    tabs = _get_tabs(cdp_url)
    return [
        {"title": t.get("title", ""), "url": t.get("url", ""), "id": t.get("id", "")}
        for t in tabs
    ]


def web_navigate(url: str, tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> str:
    """Navigate a tab to a URL and wait for document.readyState == complete."""
    tab = _find_tab(tab_filter, cdp_url)
    ws_url = tab["webSocketDebuggerUrl"]
    _send_cdp(ws_url, "Page.navigate", {"url": url})

    # 고정 sleep 대신 readyState 폴링: 빠른 페이지는 즉시, 느린 페이지는
    # 로드 완료까지(최대 15초) 기다린다. 0.3초는 네비게이션 커밋 대기
    # (직후엔 이전 문서의 readyState가 잡힐 수 있음).
    time.sleep(0.3)
    deadline = time.time() + 15
    state = ""
    while time.time() < deadline:
        try:
            r = _send_cdp(ws_url, "Runtime.evaluate", {
                "expression": "document.readyState",
                "returnByValue": True,
            }, timeout=5)
            state = r.get("result", {}).get("value", "")
        except Exception:
            state = ""
        if state == "complete":
            return f"Navigated to {url} (load complete)"
        time.sleep(0.15)
    return f"Navigated to {url} (readyState={state or 'unknown'} after 15s)"


def web_execute_js(expression: str, tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL,
                   timeout: float = 10) -> Any:
    """Execute JavaScript in the page and return the result."""
    tab = _find_tab(tab_filter, cdp_url)
    ws_url = tab["webSocketDebuggerUrl"]
    result = _send_cdp(ws_url, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True,
    }, timeout=timeout)
    value = result.get("result", {}).get("value")
    if value is not None:
        return value
    # Return description for non-serializable values
    return result.get("result", {}).get("description", str(result))


def web_click(selector: str, tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> str:
    """Click an element by CSS selector."""
    js = f"""
    (() => {{
        const sel = {json.dumps(selector)};
        const el = document.querySelector(sel);
        if (!el) return 'ERROR: Element not found: ' + sel;
        el.scrollIntoView({{block: 'center'}});
        el.click();
        return 'clicked: ' + sel;
    }})()
    """
    return str(web_execute_js(js, tab_filter, cdp_url))


def web_type(selector: str, text: str, clear: bool = True, tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> str:
    """Type text into an input element by CSS selector."""
    js = f"""
    (() => {{
        const sel = {json.dumps(selector)};
        const el = document.querySelector(sel);
        if (!el) return 'ERROR: Element not found: ' + sel;
        el.scrollIntoView({{block: 'center'}});
        el.focus();
        if ({json.dumps(bool(clear))}) el.value = '';
        el.value = {json.dumps(text)};
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'typed into: ' + sel;
    }})()
    """
    return str(web_execute_js(js, tab_filter, cdp_url))


def web_get_text(selector: str, tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> str:
    """Get text content of an element by CSS selector."""
    js = f"""
    (() => {{
        const sel = {json.dumps(selector)};
        const el = document.querySelector(sel);
        if (!el) return 'ERROR: Element not found: ' + sel;
        return el.value || el.innerText || el.textContent || '';
    }})()
    """
    return str(web_execute_js(js, tab_filter, cdp_url))


def web_get_page_info(tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> dict:
    """Get current page title and URL.

    /json 탭 목록에 title·url이 이미 들어 있으므로 HTTP 1회로 끝낸다
    (이전 구현은 탭 조회 1회 + JS 평가 2회 = 왕복 5회였다).
    """
    tab = _find_tab(tab_filter, cdp_url)
    return {"title": tab.get("title", ""), "url": tab.get("url", "")}


def web_query_all(selector: str, tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> list[dict]:
    """Query all elements matching a CSS selector. Returns tag, text, and attributes."""
    js = f"""
    (() => {{
        const els = document.querySelectorAll({json.dumps(selector)});
        return Array.from(els).slice(0, 20).map((el, i) => ({{
            index: i,
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.textContent || '').substring(0, 100),
            id: el.id || '',
            className: el.className || '',
            href: el.href || '',
            value: el.value || '',
            type: el.type || '',
        }}));
    }})()
    """
    result = web_execute_js(js, tab_filter, cdp_url)
    return result if isinstance(result, list) else []


def web_fill_form(form_data: dict[str, str], tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> list[str]:
    """Fill multiple form fields. Keys are CSS selectors, values are text to enter."""
    results = []
    for selector, value in form_data.items():
        result = web_type(selector, value, clear=True, tab_filter=tab_filter, cdp_url=cdp_url)
        results.append(result)
    return results


def web_wait_for(selector: str, timeout_ms: int = 5000, tab_filter: str | None = None, cdp_url: str = DEFAULT_CDP_URL) -> str:
    """Wait for an element to appear in the DOM."""
    js = f"""
    new Promise((resolve) => {{
        const sel = {json.dumps(selector)};
        const start = Date.now();
        const check = () => {{
            const el = document.querySelector(sel);
            if (el) return resolve('found: ' + sel);
            if (Date.now() - start > {int(timeout_ms)}) return resolve('TIMEOUT: ' + sel + ' not found after {int(timeout_ms)}ms');
            setTimeout(check, 200);
        }};
        check();
    }})
    """
    # WS 타임아웃을 페이지 대기시간보다 길게 — timeout_ms > 10s에서
    # WS가 먼저 끊기던 버그 수정
    return str(web_execute_js(js, tab_filter, cdp_url, timeout=timeout_ms / 1000 + 5))
