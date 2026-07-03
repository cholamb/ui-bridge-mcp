"""UiBridge MCP - Resilient element finding with multi-strategy fallback.

Priority order:
1. AutomationId (+ControlType)
2. Name + ControlType
3. ClassName + Name
4. Tree path (index-based)
"""

from __future__ import annotations

from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import ElementNotFoundError, ElementAmbiguousError

from models import ElementLocator
from ui_automation import _connect_window


def _has_child_window(win) -> bool:
    """Check if *win* supports the child_window() method (WindowSpecification)."""
    return hasattr(win, "child_window")


def _get_wrapper(win) -> UIAWrapper:
    """Get a UIAWrapper from either a WindowSpecification or UIAWrapper."""
    if hasattr(win, "wrapper_object"):
        try:
            return win.wrapper_object()
        except Exception:
            pass
    return win


def find_element(window_title_re: str, locator: ElementLocator) -> UIAWrapper:
    """Find a UI element using multiple fallback strategies.

    Raises a descriptive error if no strategy succeeds.
    """
    win = _connect_window(window_title_re)
    tried: list[str] = []

    # Build strategy list: each entry is (description, child_window kwargs)
    strategies: list[tuple[str, dict]] = []

    if locator.automation_id:
        kwargs: dict = {"auto_id": locator.automation_id}
        desc = f"auto_id={locator.automation_id}"
        if locator.control_type:
            kwargs["control_type"] = locator.control_type
            desc += f", control_type={locator.control_type}"
        strategies.append((desc, kwargs))

    if locator.name and locator.control_type:
        strategies.append((
            f"title={locator.name}, control_type={locator.control_type}",
            {"title": locator.name, "control_type": locator.control_type},
        ))

    if locator.name and locator.class_name:
        strategies.append((
            f"title={locator.name}, class_name={locator.class_name}",
            {"title": locator.name, "class_name": locator.class_name},
        ))

    if locator.name and not locator.control_type and not locator.class_name:
        strategies.append((
            f"title={locator.name}",
            {"title": locator.name},
        ))

    # Strategy A: Use child_window() if available (WindowSpecification)
    if _has_child_window(win):
        for desc, kwargs in strategies:
            tried.append(f"child_window({desc})")
            try:
                elem = win.child_window(**kwargs).wrapper_object()
                return elem
            except (ElementNotFoundError, ElementAmbiguousError):
                continue
            except Exception:
                continue

    # Strategy B: Search via children() traversal (UIAWrapper)
    wrapper = _get_wrapper(win)
    for desc, kwargs in strategies:
        tried.append(f"children_search({desc})")
        try:
            match = _search_children(wrapper, kwargs)
            if match is not None:
                return match
        except Exception:
            continue

    # Last resort: tree path navigation
    if locator.tree_path:
        tried.append(f"tree_path={locator.tree_path}")
        try:
            node = wrapper
            for idx in locator.tree_path:
                children = node.children()
                if idx < len(children):
                    node = children[idx]
                else:
                    raise IndexError(
                        f"Tree path index {idx} out of range "
                        f"(parent has {len(children)} children)"
                    )
            return node
        except IndexError:
            raise
        except Exception as exc:
            raise ElementNotFoundError(
                f"Tree path navigation failed: {exc}"
            ) from exc

    raise ElementNotFoundError(
        f"Could not find element. Tried strategies: [{', '.join(tried)}]. "
        f"Locator: {locator.model_dump_json(exclude_none=True)}. "
        "Use inspect_tree to verify the element exists."
    )


def _search_children(parent: UIAWrapper, criteria: dict, max_depth: int = 8) -> UIAWrapper | None:
    """Recursively search children for an element matching *criteria*.

    Supports keys: auto_id, title, control_type, class_name.
    """
    for child in parent.children():
        if _matches(child, criteria):
            return child
        if max_depth > 1:
            result = _search_children(child, criteria, max_depth - 1)
            if result is not None:
                return result
    return None


def _matches(elem: UIAWrapper, criteria: dict) -> bool:
    """Check if a UI element matches the given criteria dict."""
    info = elem.element_info
    for key, value in criteria.items():
        if key == "auto_id":
            if info.automation_id != value:
                return False
        elif key == "title":
            if info.name != value:
                return False
        elif key == "control_type":
            if info.control_type != value:
                return False
        elif key == "class_name":
            if info.class_name != value:
                return False
    return True
