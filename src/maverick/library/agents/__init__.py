"""Agent registration for DSL-based workflow execution.

This module provides functions to register all built-in agents with the
component registry. Agents are MaverickAgent classes that perform complex
tasks (code review, implementation, issue fixing, etc.).

Registration Functions:
    register_all_agents: Register all built-in agents with the registry.

Registered Agents:
    implementer: ImplementerAgent - Executes tasks from task files
    code_reviewer: CodeReviewerAgent - Performs code review
    issue_fixer: IssueFixerAgent - Fixes GitHub issues
    validation_fixer: FixerAgent - Applies validation fixes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry

# Import agent classes
from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.agents.fixer import FixerAgent
from maverick.agents.implementer import ImplementerAgent
from maverick.agents.issue_fixer import IssueFixerAgent

__all__ = [
    "register_all_agents",
]


def register_all_agents(registry: ComponentRegistry) -> None:
    """Register all built-in agents with the component registry.

    This function registers agents that are referenced in workflow YAML files.
    Each agent is registered with a name that matches the YAML reference.

    Registered agents:
    - implementer: ImplementerAgent (executes tasks from task files)
    - code_reviewer: CodeReviewerAgent (performs code review)
    - issue_fixer: IssueFixerAgent (fixes GitHub issues)
    - validation_fixer: FixerAgent (applies validation fixes)

    Note: issue_analyzer is not yet implemented and is not registered.

    Args:
        registry: Component registry to register agents with.

    Example:
        ```python
        from maverick.dsl.serialization.registry import component_registry
        from maverick.library.agents import register_all_agents

        register_all_agents(component_registry)

        # Now agents can be resolved by name
        implementer_class = component_registry.agents.get("implementer")
        ```
    """
    # Register implementer agent (used in fly.yaml)
    registry.agents.register("implementer", ImplementerAgent)

    # Register code reviewer agent (used in fly.yaml, review.yaml)
    registry.agents.register("code_reviewer", CodeReviewerAgent)

    # Register issue fixer agent (used in quick_fix.yaml, process_single_issue.yaml)
    registry.agents.register("issue_fixer", IssueFixerAgent)

    # Register validation fixer agent (used in validate-and-fix fragment)
    registry.agents.register("validation_fixer", FixerAgent)

    # Note: issue_analyzer is referenced in refuel.yaml but not yet implemented
    # TODO: Implement IssueAnalyzerAgent and register it here
