"""UiBridge MCP - Bookmark management.

Bookmarks are persisted to config/bookmarks.json and can be
resolved at runtime to live UI Automation wrapper objects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pywinauto.controls.uiawrapper import UIAWrapper

from models import Bookmark, ElementLocator
from element_finder import find_element

CONFIG_DIR = Path(__file__).parent / "config"
BOOKMARKS_FILE = CONFIG_DIR / "bookmarks.json"


def _ensure_file() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not BOOKMARKS_FILE.exists():
        BOOKMARKS_FILE.write_text("[]", encoding="utf-8")


def load_bookmarks() -> list[Bookmark]:
    """Load all bookmarks from disk."""
    _ensure_file()
    raw = json.loads(BOOKMARKS_FILE.read_text(encoding="utf-8"))
    return [Bookmark(**item) for item in raw]


def save_bookmarks(bookmarks: list[Bookmark]) -> None:
    """Persist bookmarks to disk."""
    _ensure_file()
    data = [bm.model_dump() for bm in bookmarks]
    BOOKMARKS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_bookmark(name: str) -> Bookmark | None:
    """Get a bookmark by name, or ``None``."""
    for bm in load_bookmarks():
        if bm.name == name:
            return bm
    return None


def add_bookmark(bookmark: Bookmark) -> str:
    """Add or overwrite a bookmark. Returns a status message."""
    bookmarks = load_bookmarks()
    existing = [bm for bm in bookmarks if bm.name != bookmark.name]
    action = "updated" if len(existing) < len(bookmarks) else "created"
    existing.append(bookmark)
    save_bookmarks(existing)
    return f"Bookmark '{bookmark.name}' {action}."


def delete_bookmark(name: str) -> str:
    """Delete a bookmark by name."""
    bookmarks = load_bookmarks()
    filtered = [bm for bm in bookmarks if bm.name != name]
    if len(filtered) == len(bookmarks):
        available = [bm.name for bm in bookmarks]
        raise KeyError(
            f"No bookmark '{name}'. Available: {available}"
        )
    save_bookmarks(filtered)
    return f"Bookmark '{name}' deleted."


def resolve_bookmark(name: str) -> UIAWrapper:
    """Resolve a bookmark name to a live UI element.

    Looks up the bookmark, extracts the locator and window pattern,
    then delegates to :func:`element_finder.find_element`.
    """
    bm = get_bookmark(name)
    if bm is None:
        available = [b.name for b in load_bookmarks()]
        raise KeyError(
            f"No bookmark '{name}'. Available: {available}"
        )
    return find_element(bm.window_title_re, bm.locator)


def list_bookmark_names() -> list[dict[str, Any]]:
    """Return a summary list of all bookmarks (for MCP tool responses)."""
    return [
        {
            "name": bm.name,
            "app_process": bm.app_process,
            "description": bm.description,
            "locator": bm.locator.model_dump(exclude_none=True),
        }
        for bm in load_bookmarks()
    ]
