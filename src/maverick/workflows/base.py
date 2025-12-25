"""Base classes and utilities for workflow DSL integration.

This module provides common patterns shared across workflow implementations
for loading workflows, translating events, and building results from DSL execution.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from maverick.library.builtins import create_builtin_library

if TYPE_CHECKING:
    from maverick.config import PreflightValidationConfig
    from maverick.runners.preflight import PreflightResult
    from maverick.runners.protocols import ValidatableRunner


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

    def _discover_runners(self) -> list[ValidatableRunner]:
        """Discover runners from workflow instance attributes.

        Scans instance attributes for objects that implement the
        ValidatableRunner protocol (have an async validate() method).
        Checks both public and private attributes ending in '_runner'.

        Note:
            This method verifies that validate() is an actual coroutine function
            using inspect.iscoroutinefunction(). This prevents issues during
            testing where auto-generated MagicMock attributes pass the protocol
            check but don't provide actual async methods. Test mocks that use
            AsyncMock for validate() will still be discovered correctly.

        Returns:
            List of ValidatableRunner instances found on this workflow.
        """
        import inspect

        from maverick.runners.protocols import ValidatableRunner

        runners: list[ValidatableRunner] = []
        seen_ids: set[int] = set()  # Avoid duplicates

        # Check all attributes including private runner attributes
        for attr_name in dir(self):
            # Skip dunder attributes but allow _*_runner private attrs
            if attr_name.startswith("__"):
                continue

            # Only process public attrs or private attrs ending in _runner
            if attr_name.startswith("_") and not attr_name.endswith("_runner"):
                continue

            try:
                attr = getattr(self, attr_name)
                # Skip None attributes
                if attr is None:
                    continue

                # Check if it implements ValidatableRunner protocol
                if (
                    hasattr(attr, "validate")
                    and callable(getattr(attr, "validate", None))
                    and isinstance(attr, ValidatableRunner)
                ):
                    # Verify validate() is actually async - this catches MagicMock
                    # objects that have auto-generated validate attributes that
                    # aren't real coroutine functions
                    validate_method = getattr(attr, "validate", None)
                    if not inspect.iscoroutinefunction(validate_method):
                        continue

                    # Avoid duplicates (same object via different names)
                    obj_id = id(attr)
                    if obj_id not in seen_ids:
                        seen_ids.add(obj_id)
                        runners.append(attr)
            except Exception:  # noqa: BLE001
                # Skip attributes that raise on access
                continue

        return runners

    async def run_preflight(
        self,
        runners: list[ValidatableRunner] | None = None,
        timeout_per_check: float | None = None,
        include_custom_tools: bool = True,
    ) -> PreflightResult:
        """Run preflight validation before workflow execution.

        This method validates that all required tools and configurations
        are in place before any state-changing operations occur.

        Args:
            runners: Runners to validate. If None, discovers from instance.
            timeout_per_check: Maximum seconds per validation. If None, uses
                config value or default (5.0).
            include_custom_tools: Whether to include custom tools from
                maverick.yaml config (default: True).

        Returns:
            PreflightResult with aggregated validation results.

        Raises:
            PreflightValidationError: If any critical validation fails.

        Contract:
            - MUST be called before any state-changing operations
            - MUST run even in dry_run mode
            - MUST aggregate all failures (not fail on first)
            - SHOULD discover runners from workflow instance if not provided

        Example:
            ```python
            class MyWorkflow(WorkflowDSLMixin):
                def __init__(self):
                    self.git_runner = GitRunner()
                    self.github_runner = GitHubCLIRunner()

                async def execute(self):
                    # Always call preflight first
                    await self.run_preflight()
                    # Now safe to proceed...
            ```
        """
        from maverick.exceptions import PreflightValidationError
        from maverick.runners.preflight import (
            CustomToolValidator,
            PreflightConfig,
            PreflightResult,
            PreflightValidator,
            ValidationResult,
        )

        # Load config for timeout and custom tools
        preflight_config = self._load_preflight_config()

        # Use provided timeout or fall back to config or default
        effective_timeout = timeout_per_check or preflight_config.timeout_per_check

        # Discover runners if not provided
        if runners is None:
            runners = self._discover_runners()

        # Start with validation results from discovered runners
        all_results: list[ValidationResult] = []
        start_time = time.monotonic()

        # Validate discovered runners
        if runners:
            config = PreflightConfig(timeout_per_check=effective_timeout)
            validator = PreflightValidator(runners=runners, config=config)
            runner_result = await validator.run()
            all_results.extend(runner_result.results)

        # Validate custom tools from config
        if include_custom_tools and preflight_config.custom_tools:
            custom_validator = CustomToolValidator(preflight_config.custom_tools)
            custom_result = await custom_validator.validate()
            all_results.append(custom_result)

        # Build final result
        total_duration_ms = int((time.monotonic() - start_time) * 1000)
        result = PreflightResult.from_results(all_results, total_duration_ms)

        # Raise if any validation failed
        if not result.success:
            raise PreflightValidationError(result)

        return result

    def _load_preflight_config(self) -> PreflightValidationConfig:
        """Load preflight configuration from maverick config.

        Returns:
            PreflightValidationConfig from loaded config, or default.
        """
        try:
            from maverick.config import PreflightValidationConfig, load_config

            config = load_config()
            return config.preflight
        except Exception:  # noqa: BLE001
            # If config loading fails, return defaults
            from maverick.config import PreflightValidationConfig

            return PreflightValidationConfig()


__all__ = [
    "WorkflowDSLMixin",
]
