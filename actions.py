"""UiBridge MCP - Action sequence management.

Action sequences are parameterised multi-step automations stored in
config/actions.json.  At execution time, ``{param}`` placeholders in
*target* and *value* fields are substituted from a caller-supplied dict.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from models import ActionSequence, ActionStep, ElementLocator
from bookmarks import get_bookmark, resolve_bookmark
from element_finder import find_element
from ui_automation import (
    perform_click,
    perform_focus,
    perform_get_value,
    perform_key_press,
    perform_set_value,
    perform_type,
)

CONFIG_DIR = Path(__file__).parent / "config"
ACTIONS_FILE = CONFIG_DIR / "actions.json"


# ── CRUD ──────────────────────────────────────────────────────────────────

def _ensure_file() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not ACTIONS_FILE.exists():
        ACTIONS_FILE.write_text("[]", encoding="utf-8")


def load_actions() -> list[ActionSequence]:
    _ensure_file()
    raw = json.loads(ACTIONS_FILE.read_text(encoding="utf-8"))
    return [ActionSequence(**item) for item in raw]


def save_actions(actions: list[ActionSequence]) -> None:
    _ensure_file()
    data = [a.model_dump() for a in actions]
    ACTIONS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_action(name: str) -> ActionSequence | None:
    for a in load_actions():
        if a.name == name:
            return a
    return None


def add_action(action: ActionSequence) -> str:
    actions = load_actions()
    existing = [a for a in actions if a.name != action.name]
    verb = "updated" if len(existing) < len(actions) else "created"
    existing.append(action)
    save_actions(existing)
    return f"Action '{action.name}' {verb}."


def delete_action(name: str) -> str:
    actions = load_actions()
    filtered = [a for a in actions if a.name != name]
    if len(filtered) == len(actions):
        available = [a.name for a in actions]
        raise KeyError(f"No action '{name}'. Available: {available}")
    save_actions(filtered)
    return f"Action '{name}' deleted."


def list_action_summaries() -> list[dict[str, Any]]:
    return [
        {
            "name": a.name,
            "description": a.description,
            "app_process": a.app_process,
            "steps_count": len(a.steps),
        }
        for a in load_actions()
    ]


# ── Execution ─────────────────────────────────────────────────────────────

class _MissingParam(dict):
    """Raises on missing keys instead of returning a default."""

    def __missing__(self, key: str) -> str:
        raise KeyError(f"Missing required parameter: '{key}'")


def _substitute(template: str | None, params: dict[str, str]) -> str | None:
    if template is None:
        return None
    try:
        return template.format_map(_MissingParam(params))
    except KeyError:
        raise


def _resolve_step_target(
    target: str, window_title_re: str
) -> Any:
    """Resolve a step target to a live UI element.

    If *target* matches a bookmark name, use the bookmark.
    Otherwise try to parse it as inline ``ElementLocator`` JSON.
    """
    # Check bookmark first
    bm = get_bookmark(target)
    if bm is not None:
        return resolve_bookmark(target)

    # Try inline locator JSON
    try:
        locator_data = json.loads(target)
        locator = ElementLocator(**locator_data)
        return find_element(window_title_re, locator)
    except (json.JSONDecodeError, Exception):
        pass

    raise ValueError(
        f"Cannot resolve target '{target}': not a known bookmark "
        "and not valid ElementLocator JSON."
    )


def execute_action(
    name: str, parameters: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Execute a named action sequence.

    Parameters
    ----------
    name:
        The action sequence name (must exist in actions.json).
    parameters:
        Optional dict of ``{param}`` substitution values.

    Returns
    -------
    A list of per-step result dicts.
    """
    action_seq = get_action(name)
    if action_seq is None:
        available = [a.name for a in load_actions()]
        raise KeyError(f"No action '{name}'. Available: {available}")

    params = parameters or {}
    results: list[dict[str, Any]] = []

    for i, step in enumerate(action_seq.steps):
        step_result: dict[str, Any] = {
            "step_index": i,
            "action": step.action,
            "status": "ok",
            "result": None,
        }

        try:
            target_str = _substitute(step.target, params)
            value_str = _substitute(step.value, params)

            if step.action == "wait":
                wait_ms = int(value_str) if value_str else step.delay_after_ms
                time.sleep(wait_ms / 1000)
                step_result["result"] = f"waited {wait_ms}ms"
            else:
                element = _resolve_step_target(target_str, action_seq.window_title_re)

                if step.action == "click":
                    step_result["result"] = perform_click(element)
                elif step.action == "type_text":
                    step_result["result"] = perform_type(element, value_str or "")
                elif step.action == "set_value":
                    step_result["result"] = perform_set_value(element, value_str or "")
                elif step.action == "get_value":
                    step_result["result"] = perform_get_value(element)
                elif step.action == "focus":
                    step_result["result"] = perform_focus(element)
                elif step.action == "key_press":
                    step_result["result"] = perform_key_press(element, value_str or "")
                else:
                    step_result["status"] = "error"
                    step_result["result"] = f"Unknown action: {step.action}"

        except Exception as exc:
            step_result["status"] = "error"
            step_result["result"] = str(exc)

        results.append(step_result)

        # Post-step delay
        if step.delay_after_ms > 0 and step.action != "wait":
            time.sleep(step.delay_after_ms / 1000)

    return results
