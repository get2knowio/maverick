"""Base classes and utilities for workflow DSL integration.

This module provides common patterns shared across workflow implementations
for loading workflows, translating events, and building results from DSL execution.
"""

from __future__ import annotations

from typing import Any

from maverick.library.builtins import create_builtin_library


class WorkflowDSLMixin:
    """Mixin providing common DSL integration utilities for workflow classes.

    This mixin extracts shared patterns from FlyWorkflow and RefuelWorkflow:
    - Workflow file loading from built-in library
    - Common DSL execution patterns

    Workflows using this mixin should:
    1. Define their own event translation logic (_translate_event)
    2. Define their own result building logic (_build_*_result)
    3. Call enable_dsl_execution() to enable DSL mode
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize DSL execution state.

        Note: This should be called via super() in subclass __init__.
        """
        super().__init__(*args, **kwargs)
        self._use_dsl = False

    def enable_dsl_execution(self) -> None:
        """Enable DSL-based workflow execution.

        When enabled, the workflow will use the WorkflowFileExecutor to execute
        a YAML workflow definition instead of the legacy Python implementation.
        """
        self._use_dsl = True

    def _load_workflow(self, workflow_name: str) -> Any:
        """Load workflow file from built-in library.

        This method provides a common pattern for loading workflow files used by
        both FlyWorkflow and RefuelWorkflow. It uses the builtin library registry
        instead of hard-coded paths.

        Args:
            workflow_name: Name of the workflow to load (e.g., "fly", "refuel").

        Returns:
            Parsed WorkflowFile instance.

        Raises:
            FileNotFoundError: If workflow file doesn't exist.
            WorkflowParseError: If workflow file is invalid.
            KeyError: If workflow name is not a built-in.
        """
        builtin_library = create_builtin_library()
        return builtin_library.get_workflow(workflow_name)


__all__ = [
    "WorkflowDSLMixin",
]
