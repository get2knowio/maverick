from __future__ import annotations

from typing import TypedDict

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from maverick.tui.widgets.stage_indicator import StageIndicator


class NavigationItemDict(TypedDict, total=False):
    """Type definition for navigation item dictionary.

    Attributes:
        id: Item identifier
        label: Display label
        icon: Icon character
        shortcut: Keyboard shortcut (optional)
    """

    id: str
    label: str
    icon: str
    shortcut: str | None


class StageDict(TypedDict, total=False):
    """Type definition for workflow stage dictionary.

    Attributes:
        name: Stage identifier
        display_name: Display name (optional, defaults to name)
        status: Stage status (pending, active, completed, failed)
    """

    name: str
    display_name: str
    status: str


class Sidebar(Widget):
    """Sidebar widget displaying navigation or workflow stages."""

    DEFAULT_CSS = """
    Sidebar {
        width: 30;
        height: 100%;
    }
    """

    NAVIGATION_ITEMS: list[NavigationItemDict] = [
        {"id": "home", "label": "Home", "icon": "H", "shortcut": "Ctrl+H"},
        {"id": "workflows", "label": "Workflows", "icon": "W", "shortcut": None},
        {"id": "settings", "label": "Settings", "icon": "S", "shortcut": "Ctrl+,"},
    ]

    mode: reactive[str] = reactive("navigation")

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Initialize the sidebar widget.

        Args:
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes for the widget.
            disabled: Whether the widget is disabled or not.
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self._stages: list[StageDict] = []

    def compose(self) -> ComposeResult:
        """Create the sidebar layout."""
        with Vertical(id="sidebar-content"):
            yield Static("Navigation", classes="sidebar-title")
            with Vertical(classes="nav-items"):
                for item in self.NAVIGATION_ITEMS:
                    shortcut = f" ({item['shortcut']})" if item["shortcut"] else ""
                    yield Static(
                        f"[{item['icon']}] {item['label']}{shortcut}",
                        id=f"nav-{item['id']}",
                        classes="nav-item",
                    )

    def set_navigation_mode(self) -> None:
        """Switch to navigation menu mode.

        Clears workflow stages and displays the standard navigation menu.
        Workflows should call this when exiting or resetting to idle state.
        """
        self.mode = "navigation"
        self._rebuild_content()

    def set_workflow_mode(self, stages: list[StageDict]) -> None:
        """Switch to workflow stages mode.

        Args:
            stages: List of stage dictionaries with name, display_name, and
                   status fields. Each dict should have:
                   - name (str): Stage identifier
                   - display_name (str, optional): Display name (defaults to name)
                   - status (str): Stage status
                     ("pending", "active", "completed", "failed")

        Note:
            Workflows should call this method when starting execution to display
            their stages. Use update_stage_status() to update individual stages
            during workflow execution, and set_navigation_mode() when complete.
        """
        self._stages = stages
        self.mode = "workflow"
        self._rebuild_content()

    def update_stage_status(self, stage_name: str, status: str) -> None:
        """Update the status of a workflow stage.

        Args:
            stage_name: Name of the stage (internal identifier, not display name).
            status: New status ("pending", "active", "completed", "failed").

        Note:
            This method searches for the stage by its ID (stage-{name}), not by
            the displayed name, to properly handle stages with custom display names.
            The status is persisted in _stages to survive content rebuilds.
        """
        # Update the status in _stages to persist across rebuilds
        for stage in self._stages:
            if stage.get("name") == stage_name:
                stage["status"] = status
                break

        # Find the stage indicator by its ID (which uses the internal stage name)
        stage_id = f"stage-{stage_name}"
        try:
            indicator = self.query_one(f"#{stage_id}", StageIndicator)
            indicator.status = status
        except Exception:
            # Stage not found or not in workflow mode - silently ignore
            pass

    def _rebuild_content(self) -> None:
        """Rebuild the sidebar content based on current mode."""
        content = self.query_one("#sidebar-content", Vertical)

        # Remove children properly to clear ID registry
        for child in list(content.children):
            child.remove()

        if self.mode == "navigation":
            content.mount(Static("Navigation", classes="sidebar-title"))
            nav_container = Vertical(classes="nav-items")
            content.mount(nav_container)
            for item in self.NAVIGATION_ITEMS:
                shortcut = f" ({item['shortcut']})" if item["shortcut"] else ""
                nav_container.mount(
                    Static(
                        f"[{item['icon']}] {item['label']}{shortcut}",
                        id=f"nav-{item['id']}",
                        classes="nav-item",
                    )
                )
        else:
            content.mount(Static("Workflow Stages", classes="sidebar-title"))
            stages_container = Vertical(classes="stage-items")
            content.mount(stages_container)
            for stage in self._stages:
                stage_name = stage.get("name", "")
                # Use display_name if available, otherwise fall back to name
                display_name = stage.get("display_name", stage_name)
                stages_container.mount(
                    StageIndicator(
                        name=display_name,
                        status=stage.get("status", "pending"),
                        id=f"stage-{stage_name}",
                    )
                )
