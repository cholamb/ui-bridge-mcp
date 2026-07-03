"""UiBridge CLI - command-line interface for OpenClaw integration.

Usage:
    python cli.py list-windows
    python cli.py inspect <window_title> [--depth 3]
    python cli.py click --window <title> --name <element_name>
    python cli.py click --bookmark <name>
    python cli.py type --window <title> --name <element_name> --text "hello"
    python cli.py get-value --window <title> --name <element_name>
    python cli.py set-value --window <title> --name <element_name> --value "hello"
    python cli.py list-bookmarks
    python cli.py web-tabs
    python cli.py web-goto <url>
    python cli.py web-click <selector>
    python cli.py web-type <selector> --text "hello"
    python cli.py web-read <selector>
    python cli.py web-find <selector>
    python cli.py web-js <expression>
"""

from __future__ import annotations

import argparse
import json
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure we can import sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import ElementLocator
from ui_automation import (
    get_ui_tree,
    list_open_windows,
    perform_click,
    perform_get_value,
    perform_key_press,
    perform_set_value,
    perform_type,
)
from element_finder import find_element
from bookmarks import (
    add_bookmark,
    delete_bookmark as bm_delete,
    list_bookmark_names,
    resolve_bookmark,
)
from actions import execute_action, list_action_summaries
from web_automation import (
    web_click,
    web_execute_js,
    web_fill_form,
    web_get_page_info,
    web_get_text,
    web_list_tabs,
    web_navigate,
    web_query_all,
    web_type,
    web_wait_for,
)


def _json_out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _resolve_target(args):
    if getattr(args, "bookmark", None):
        return resolve_bookmark(args.bookmark)
    locator = ElementLocator(
        automation_id=getattr(args, "automation_id", None),
        name=getattr(args, "name", None),
        control_type=getattr(args, "control_type", None),
        class_name=getattr(args, "class_name", None),
    )
    return find_element(args.window, locator)


def main():
    parser = argparse.ArgumentParser(prog="uibridge", description="UiBridge CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # -- list-windows --
    sub.add_parser("list-windows", help="List all visible windows")

    # -- inspect --
    p = sub.add_parser("inspect", help="Inspect UI tree of a window")
    p.add_argument("window", help="Window title (regex)")
    p.add_argument("--depth", type=int, default=3, help="Max depth (1-10)")

    # -- click --
    p = sub.add_parser("click", help="Click a UI element")
    p.add_argument("--window", help="Window title (regex)")
    p.add_argument("--bookmark", help="Bookmark name")
    p.add_argument("--name", help="Element name")
    p.add_argument("--automation-id", help="Automation ID")
    p.add_argument("--control-type", help="Control type")
    p.add_argument("--class-name", help="Class name")

    # -- type --
    p = sub.add_parser("type", help="Type text into element")
    p.add_argument("--window", help="Window title (regex)")
    p.add_argument("--bookmark", help="Bookmark name")
    p.add_argument("--name", help="Element name")
    p.add_argument("--automation-id", help="Automation ID")
    p.add_argument("--control-type", help="Control type")
    p.add_argument("--class-name", help="Class name")
    p.add_argument("--text", required=True, help="Text to type")

    # -- get-value --
    p = sub.add_parser("get-value", help="Read value of a UI element")
    p.add_argument("--window", help="Window title (regex)")
    p.add_argument("--bookmark", help="Bookmark name")
    p.add_argument("--name", help="Element name")
    p.add_argument("--automation-id", help="Automation ID")
    p.add_argument("--control-type", help="Control type")
    p.add_argument("--class-name", help="Class name")

    # -- set-value --
    p = sub.add_parser("set-value", help="Set value of a UI element")
    p.add_argument("--window", help="Window title (regex)")
    p.add_argument("--bookmark", help="Bookmark name")
    p.add_argument("--name", help="Element name")
    p.add_argument("--automation-id", help="Automation ID")
    p.add_argument("--control-type", help="Control type")
    p.add_argument("--class-name", help="Class name")
    p.add_argument("--value", required=True, help="Value to set")

    # -- key-press --
    p = sub.add_parser("key-press", help="Send key presses")
    p.add_argument("--window", help="Window title (regex)")
    p.add_argument("--bookmark", help="Bookmark name")
    p.add_argument("--name", help="Element name")
    p.add_argument("--automation-id", help="Automation ID")
    p.add_argument("--control-type", help="Control type")
    p.add_argument("--class-name", help="Class name")
    p.add_argument("--keys", required=True, help="Keys to press (e.g. {ENTER})")

    # -- list-bookmarks --
    sub.add_parser("list-bookmarks", help="List saved bookmarks")

    # -- list-actions --
    sub.add_parser("list-actions", help="List action sequences")

    # -- run-action --
    p = sub.add_parser("run-action", help="Run a pre-defined action")
    p.add_argument("action_name", help="Action name")
    p.add_argument("--params", help="JSON parameters", default="{}")

    # -- web-tabs --
    p = sub.add_parser("web-tabs", help="List browser tabs")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-goto --
    p = sub.add_parser("web-goto", help="Navigate to URL")
    p.add_argument("url", help="URL to navigate to")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-click --
    p = sub.add_parser("web-click", help="Click web element")
    p.add_argument("selector", help="CSS selector")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-type --
    p = sub.add_parser("web-type", help="Type into web element")
    p.add_argument("selector", help="CSS selector")
    p.add_argument("--text", required=True, help="Text to type")
    p.add_argument("--no-clear", action="store_true", help="Don't clear first")
    p.add_argument("--enter", action="store_true", help="Press Enter after typing")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-read --
    p = sub.add_parser("web-read", help="Read web element text")
    p.add_argument("selector", help="CSS selector")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-find --
    p = sub.add_parser("web-find", help="Find web elements")
    p.add_argument("selector", help="CSS selector")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-fill --
    p = sub.add_parser("web-fill", help="Fill multiple form fields")
    p.add_argument("form_data", help="JSON dict of {selector: value}")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-js --
    p = sub.add_parser("web-js", help="Execute JavaScript")
    p.add_argument("expression", help="JS expression")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    # -- web-page-info --
    p = sub.add_parser("web-page-info", help="Get page title/URL")
    p.add_argument("--tab", help="Tab filter")
    p.add_argument("--cdp", default="http://localhost:9222", help="CDP URL")

    args = parser.parse_args()

    try:
        if args.command == "list-windows":
            _json_out(list_open_windows())

        elif args.command == "inspect":
            _json_out(get_ui_tree(args.window, args.depth))

        elif args.command == "click":
            elem = _resolve_target(args)
            print(perform_click(elem))

        elif args.command == "type":
            elem = _resolve_target(args)
            print(perform_type(elem, args.text))

        elif args.command == "get-value":
            elem = _resolve_target(args)
            print(perform_get_value(elem))

        elif args.command == "set-value":
            elem = _resolve_target(args)
            print(perform_set_value(elem, args.value))

        elif args.command == "key-press":
            elem = _resolve_target(args)
            print(perform_key_press(elem, args.keys))

        elif args.command == "list-bookmarks":
            _json_out(list_bookmark_names())

        elif args.command == "list-actions":
            _json_out(list_action_summaries())

        elif args.command == "run-action":
            params = json.loads(args.params)
            _json_out(execute_action(args.action_name, params))

        elif args.command == "web-tabs":
            _json_out(web_list_tabs(args.cdp))

        elif args.command == "web-goto":
            print(web_navigate(args.url, args.tab, args.cdp))

        elif args.command == "web-click":
            print(web_click(args.selector, args.tab, args.cdp))

        elif args.command == "web-type":
            print(web_type(args.selector, args.text, not args.no_clear, getattr(args, 'enter', False), args.tab, args.cdp))

        elif args.command == "web-read":
            print(web_get_text(args.selector, args.tab, args.cdp))

        elif args.command == "web-find":
            _json_out(web_query_all(args.selector, args.tab, args.cdp))

        elif args.command == "web-fill":
            _json_out(web_fill_form(json.loads(args.form_data), args.tab, args.cdp))

        elif args.command == "web-js":
            result = web_execute_js(args.expression, args.tab, args.cdp)
            print(json.dumps(result, ensure_ascii=False, default=str) if not isinstance(result, str) else result)

        elif args.command == "web-page-info":
            _json_out(web_get_page_info(args.tab, args.cdp))

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
