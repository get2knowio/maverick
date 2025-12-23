"""Base interface for step handlers.

This module defines the protocol/ABC for step execution handlers.
"""

from __future__ import annotations

from typing import Any, Protocol

from maverick.dsl.serialization.registry import ComponentRegistry


class StepHandler(Protocol):
    """Protocol for step execution handlers.

    Each step type has a dedicated handler that knows how to execute
    that specific step type using registry-resolved components.
    """

    async def execute(
        self,
        step: Any,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
        registry: ComponentRegistry,
        config: Any = None,
    ) -> Any:
        """Execute a step.

        Args:
            step: Step record to execute.
            resolved_inputs: Resolved input values (expressions evaluated).
            context: Execution context with inputs and step outputs.
            registry: Component registry for resolving references.
            config: Optional configuration.

        Returns:
            Step output value.

        Raises:
            Exception: If step execution fails.
        """
        ...
