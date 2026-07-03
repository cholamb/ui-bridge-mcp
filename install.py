#!/usr/bin/env python3
"""Register UiBridge MCP in an MCP client's settings.json.

By default registers this folder's server.py into ~/.claude/settings.json.

Usage:
    python install.py                 # use this folder's server.py
    python install.py --settings PATH # custom settings.json location
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SERVER_PATH = Path(__file__).resolve().parent / "server.py"


def find_python() -> str:
    """Prefer a python on PATH; fall back to the current interpreter."""
    for candidate in ("python", "python3"):
        found = shutil.which(candidate)
        if found:
            return found
    return sys.executable


def register(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            settings = {}
    if not isinstance(settings, dict):
        settings = {}

    settings.setdefault("mcpServers", {})
    settings["mcpServers"]["ui-bridge"] = {
        "command": find_python(),
        "args": [str(SERVER_PATH)],
        "env": {"PYTHONUTF8": "1"},
    }

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] ui-bridge registered in {settings_path}")
    print(f"     server: {SERVER_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--settings",
        default=str(Path.home() / ".claude" / "settings.json"),
        help="Path to the MCP client settings.json",
    )
    args = parser.parse_args()

    if not SERVER_PATH.exists():
        print(f"[ERROR] server.py not found next to install.py: {SERVER_PATH}")
        return 1

    register(Path(args.settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
