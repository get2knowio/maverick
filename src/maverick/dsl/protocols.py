"""Protocol definitions for Maverick DSL agents and generators.

This module defines the runtime protocols that agents and generators must
implement to be used in workflow steps. These are Protocol classes, not
abstract base classes, allowing for structural subtyping.
"""

from __future__ import annotations

from typing import Any, Protocol


class AgentProtocol(Protocol):
    """Protocol for agents that can be used in AgentStep.

    Any class that implements an async execute() method with this signature
    can be used as an agent in the workflow DSL, regardless of inheritance.

    Example:
        >>> class MyAgent:
        ...     async def execute(self, context: dict[str, Any]) -> Any:
        ...         return {"status": "done"}
        >>> # MyAgent satisfies AgentProtocol without inheriting from it
    """

    async def execute(self, context: dict[str, Any]) -> Any:
        """Execute the agent with the given context.

        Args:
            context: Dictionary of inputs for the agent.

        Returns:
            Agent execution result (structure depends on agent implementation).

        Raises:
            Exception: If execution fails.
        """
        ...


class GeneratorProtocol(Protocol):
    """Protocol for generators that can be used in GenerateStep.

    Any class that implements an async generate() method with this signature
    can be used as a generator in the workflow DSL.

    Example:
        >>> class MyGenerator:
        ...     async def generate(self, context: dict[str, Any]) -> str:
        ...         return "Generated text"
        >>> # MyGenerator satisfies GeneratorProtocol without inheriting from it
    """

    async def generate(self, context: dict[str, Any]) -> str:
        """Generate text output based on the given context.

        Args:
            context: Dictionary of inputs for text generation.

        Returns:
            Generated text as a string.

        Raises:
            Exception: If generation fails.
        """
        ...
