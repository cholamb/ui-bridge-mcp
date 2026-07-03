"""UiBridge MCP - Pydantic data models."""

from __future__ import annotations

from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# ElementLocator – describes *how* to find a single UI element
# ---------------------------------------------------------------------------

class ElementLocator(BaseModel):
    """Identification info for a UI Automation element.

    At least one field must be set. The element finder tries them in
    priority order: automation_id → name+control_type → class_name → tree_path.
    """

    automation_id: str | None = None
    name: str | None = None
    control_type: str | None = None
    class_name: str | None = None
    tree_path: list[int] | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "ElementLocator":
        if not any([
            self.automation_id,
            self.name,
            self.control_type,
            self.class_name,
            self.tree_path,
        ]):
            raise ValueError("ElementLocator must have at least one identification field set.")
        return self


# ---------------------------------------------------------------------------
# Bookmark – a persisted reference to a UI element
# ---------------------------------------------------------------------------

class Bookmark(BaseModel):
    """A named, persistently-stored reference to a UI element."""

    name: str
    app_process: str
    window_title_re: str
    locator: ElementLocator
    description: str = ""


# ---------------------------------------------------------------------------
# ActionStep / ActionSequence – pre-defined automation sequences
# ---------------------------------------------------------------------------

class ActionStep(BaseModel):
    """One step in a multi-step action sequence.

    ``target`` is either a bookmark name or an inline ElementLocator JSON string.
    ``value`` supports ``{param}`` placeholders that are substituted at runtime.
    """

    action: str  # click | type_text | set_value | get_value | focus | wait | key_press
    target: str  # bookmark name or inline locator JSON
    value: str | None = None
    delay_after_ms: int = 100


class ActionSequence(BaseModel):
    """A named, parameterised sequence of UI actions."""

    name: str
    description: str
    app_process: str
    window_title_re: str
    steps: list[ActionStep]


# ---------------------------------------------------------------------------
# AppConfig – per-application metadata
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Per-application configuration stored in apps.json."""

    process_name: str
    window_title_re: str
    description: str = ""
    common_locators: dict[str, ElementLocator] = {}
