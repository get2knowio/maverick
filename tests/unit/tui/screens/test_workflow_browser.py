"""Unit tests for WorkflowBrowserScreen."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from maverick.tui.screens.workflow_browser import SOURCE_ICONS, WorkflowBrowserScreen


# Mock workflow for testing
def create_mock_workflow(
    name: str = "test-workflow",
    description: str = "Test workflow description",
    source: str = "builtin",
    inputs: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock DiscoveredWorkflow for testing."""
    mock_workflow = MagicMock()
    mock_workflow.workflow.name = name
    mock_workflow.workflow.description = description
    mock_workflow.workflow.inputs = inputs or {}
    mock_workflow.source = source
    return mock_workflow


# Initialization Tests
class TestWorkflowBrowserInitialization:
    """Tests for WorkflowBrowserScreen initialization."""

    def test_screen_has_correct_title(self):
        """Test that screen has correct title."""
        assert WorkflowBrowserScreen.TITLE == "Workflows"

    def test_screen_has_required_bindings(self):
        """Test that screen has all required key bindings."""
        binding_keys = [b.key for b in WorkflowBrowserScreen.BINDINGS]
        assert "enter" in binding_keys
        assert "s" in binding_keys
        assert "/" in binding_keys
        assert "escape" in binding_keys
        assert "r" in binding_keys

    def test_screen_initializes_with_correct_attributes(self):
        """Test that screen initializes with correct default attributes."""
        screen = WorkflowBrowserScreen()
        assert screen._discovery_result is None
        assert screen._workflows == []
        assert screen._filtered_workflows == []


# Source Icons Tests
class TestSourceIcons:
    """Tests for source icon mapping."""

    def test_builtin_icon(self):
        """Test builtin source has package emoji."""
        assert SOURCE_ICONS["builtin"] == "\U0001f4e6"

    def test_user_icon(self):
        """Test user source has person emoji."""
        assert SOURCE_ICONS["user"] == "\U0001f464"

    def test_project_icon(self):
        """Test project source has home emoji."""
        assert SOURCE_ICONS["project"] == "\U0001f3e0"


# Filtering Tests
# Note: The reactive properties trigger watchers that require mounted widgets.
# These tests use mock.patch to set property values without triggering watchers.
class TestWorkflowFiltering:
    """Tests for workflow filtering functionality."""

    def test_filter_by_source(self):
        """Test filtering workflows by source."""
        screen = WorkflowBrowserScreen()
        screen._workflows = [
            create_mock_workflow(name="builtin-wf", source="builtin"),
            create_mock_workflow(name="user-wf", source="user"),
            create_mock_workflow(name="project-wf", source="project"),
        ]

        # Use property mock to avoid triggering watchers
        with (
            patch.object(
                type(screen),
                "source_filter",
                new_callable=lambda: property(lambda s: "builtin"),
            ),
            patch.object(
                type(screen),
                "search_query",
                new_callable=lambda: property(lambda s: ""),
            ),
        ):
            screen._apply_filters()

        assert len(screen._filtered_workflows) == 1
        assert screen._filtered_workflows[0].workflow.name == "builtin-wf"

    def test_filter_all_sources(self):
        """Test filtering with 'all' shows all workflows."""
        screen = WorkflowBrowserScreen()
        screen._workflows = [
            create_mock_workflow(name="builtin-wf", source="builtin"),
            create_mock_workflow(name="user-wf", source="user"),
            create_mock_workflow(name="project-wf", source="project"),
        ]

        with (
            patch.object(
                type(screen),
                "source_filter",
                new_callable=lambda: property(lambda s: "all"),
            ),
            patch.object(
                type(screen),
                "search_query",
                new_callable=lambda: property(lambda s: ""),
            ),
        ):
            screen._apply_filters()

        assert len(screen._filtered_workflows) == 3

    def test_search_by_name(self):
        """Test searching workflows by name."""
        screen = WorkflowBrowserScreen()
        screen._workflows = [
            create_mock_workflow(name="feature-workflow", source="builtin"),
            create_mock_workflow(name="review-workflow", source="builtin"),
            create_mock_workflow(name="test-workflow", source="builtin"),
        ]

        with (
            patch.object(
                type(screen),
                "source_filter",
                new_callable=lambda: property(lambda s: "all"),
            ),
            patch.object(
                type(screen),
                "search_query",
                new_callable=lambda: property(lambda s: "feature"),
            ),
        ):
            screen._apply_filters()

        assert len(screen._filtered_workflows) == 1
        assert screen._filtered_workflows[0].workflow.name == "feature-workflow"

    def test_search_by_description(self):
        """Test searching workflows by description."""
        screen = WorkflowBrowserScreen()
        screen._workflows = [
            create_mock_workflow(
                name="wf1",
                description="Implements new features",
                source="builtin",
            ),
            create_mock_workflow(
                name="wf2",
                description="Code review workflow",
                source="builtin",
            ),
        ]

        with (
            patch.object(
                type(screen),
                "source_filter",
                new_callable=lambda: property(lambda s: "all"),
            ),
            patch.object(
                type(screen),
                "search_query",
                new_callable=lambda: property(lambda s: "review"),
            ),
        ):
            screen._apply_filters()

        assert len(screen._filtered_workflows) == 1
        assert screen._filtered_workflows[0].workflow.name == "wf2"

    def test_search_case_insensitive(self):
        """Test that search is case insensitive."""
        screen = WorkflowBrowserScreen()
        screen._workflows = [
            create_mock_workflow(name="Feature-Workflow", source="builtin"),
        ]

        with (
            patch.object(
                type(screen),
                "source_filter",
                new_callable=lambda: property(lambda s: "all"),
            ),
            patch.object(
                type(screen),
                "search_query",
                new_callable=lambda: property(lambda s: "FEATURE"),
            ),
        ):
            screen._apply_filters()

        assert len(screen._filtered_workflows) == 1


# Reactive Default Tests (checking class-level defaults)
class TestReactiveDefaults:
    """Tests for reactive property default values."""

    def test_source_filter_default(self):
        """Test source_filter reactive default is 'all'."""
        assert WorkflowBrowserScreen.source_filter._default == "all"

    def test_search_query_default(self):
        """Test search_query reactive default is empty string."""
        assert WorkflowBrowserScreen.search_query._default == ""

    def test_loading_default(self):
        """Test loading reactive default is True."""
        assert WorkflowBrowserScreen.loading._default is True
