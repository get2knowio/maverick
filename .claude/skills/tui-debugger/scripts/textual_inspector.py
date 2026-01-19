#!/usr/bin/env python3
"""
Textual Inspector - Capture complete state of a Textual application.

Usage:
    python textual_inspector.py module:AppClass [--output state.json] [--interact]

Examples:
    python textual_inspector.py my_app:MyApp
    python textual_inspector.py my_app:MyApp --output debug_state.json
    python textual_inspector.py my_app:MyApp --interact  # Keep session open for manual inspection
"""

import argparse
import asyncio
import importlib
import json
import sys
from typing import Any


def widget_to_dict(widget: Any, depth: int = 0, max_depth: int = 10) -> dict:
    """Convert a Textual widget to a dictionary representation."""
    if depth > max_depth:
        return {"_truncated": True, "class": widget.__class__.__name__}

    result = {
        "class": widget.__class__.__name__,
        "id": widget.id,
        "classes": list(widget.classes) if hasattr(widget, "classes") else [],
        "disabled": getattr(widget, "disabled", None),
        "visible": widget.visible if hasattr(widget, "visible") else None,
        "has_focus": widget.has_focus if hasattr(widget, "has_focus") else None,
    }

    # Size and position
    if hasattr(widget, "size"):
        result["size"] = {"width": widget.size.width, "height": widget.size.height}
    if hasattr(widget, "region"):
        r = widget.region
        result["region"] = {"x": r.x, "y": r.y, "width": r.width, "height": r.height}

    # Common widget-specific attributes
    if hasattr(widget, "value"):
        try:
            result["value"] = widget.value
        except Exception:
            result["value"] = "<error reading value>"
    if hasattr(widget, "label"):
        try:
            result["label"] = str(widget.label)
        except Exception:
            pass
    if hasattr(widget, "renderable"):
        try:
            result["renderable"] = str(widget.renderable)[:200]
        except Exception:
            pass

    # Styles (selected important ones)
    if hasattr(widget, "styles"):
        styles = widget.styles
        result["styles"] = {
            "display": str(styles.display) if styles.display else None,
            "visibility": str(styles.visibility) if styles.visibility else None,
            "width": str(styles.width) if styles.width else None,
            "height": str(styles.height) if styles.height else None,
            "background": str(styles.background) if styles.background else None,
            "color": str(styles.color) if styles.color else None,
        }

    # Children
    if hasattr(widget, "children") and widget.children:
        result["children"] = [
            widget_to_dict(child, depth + 1, max_depth) for child in widget.children
        ]

    return result


def get_bindings(app: Any) -> list[dict]:
    """Extract key bindings from the app."""
    bindings = []
    if hasattr(app, "_bindings"):
        for binding in app._bindings:
            bindings.append(
                {
                    "key": binding.key,
                    "action": binding.action,
                    "description": binding.description,
                    "show": binding.show,
                    "priority": binding.priority,
                }
            )
    return bindings


def get_reactive_attrs(obj: Any) -> list[str]:
    """Find reactive attributes on an object."""
    reactives = []
    cls = obj.__class__
    for name in dir(cls):
        try:
            attr = getattr(cls, name)
            if hasattr(attr, "_reactive"):
                reactives.append(name)
        except Exception:
            pass
    return reactives


async def inspect_app(
    app_path: str, output_path: str | None, interactive: bool
) -> dict:
    """Run the app in test mode and capture its state."""

    # Import the app class
    module_path, class_name = app_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    app_class = getattr(module, class_name)

    app = app_class()

    async with app.run_test() as pilot:
        # Let the app fully mount
        await pilot.pause()

        state = {
            "app_class": app_path,
            "title": app.title if hasattr(app, "title") else None,
            "focused": app.focused.id if app.focused else None,
            "focused_class": app.focused.__class__.__name__ if app.focused else None,
            "screen": app.screen.id if hasattr(app, "screen") and app.screen else None,
            "dark_mode": app.dark if hasattr(app, "dark") else None,
            "bindings": get_bindings(app),
            "reactive_attrs": get_reactive_attrs(app),
            "widget_tree": widget_to_dict(app),
        }

        # Query some common widget types for quick reference
        state["widget_summary"] = {
            "buttons": [w.id for w in app.query("Button")],
            "inputs": [w.id for w in app.query("Input")],
            "labels": [w.id for w in app.query("Label")],
            "data_tables": [w.id for w in app.query("DataTable")],
            "list_views": [w.id for w in app.query("ListView")],
        }

        if interactive:
            print("\n=== Interactive Mode ===")
            print("App is running in test mode. You have access to:")
            print("  - pilot: Pilot object for simulation")
            print("  - app: The application instance")
            print("  - state: Captured state dict")
            print("\nExamples:")
            print("  await pilot.press('tab')")
            print("  app.query_one('#my-button')")
            print("  print(json.dumps(state, indent=2))")
            print("\nType 'exit()' or Ctrl+D to quit.\n")

            # Drop into interactive mode
            import code

            code.interact(
                local={"pilot": pilot, "app": app, "state": state, "json": json}
            )

        return state


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a Textual application's state in headless mode"
    )
    parser.add_argument(
        "app_path",
        help="Path to app class in format 'module:ClassName' (e.g., 'my_app:MyApp')",
    )
    parser.add_argument(
        "--output", "-o", help="Output file path for JSON state (default: stdout)"
    )
    parser.add_argument(
        "--interact",
        "-i",
        action="store_true",
        help="Keep session open for interactive inspection",
    )

    args = parser.parse_args()

    try:
        state = asyncio.run(inspect_app(args.app_path, args.output, args.interact))

        output = json.dumps(state, indent=2, default=str)

        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"State written to {args.output}", file=sys.stderr)
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
