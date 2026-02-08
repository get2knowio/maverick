"""Generator registration for DSL-based workflow execution.

This module provides functions to register all built-in generators with the
component registry. Generators are lightweight agents that generate text
(commit messages, PR descriptions, etc.) using Claude's query() API.

Registration Functions:
    register_all_generators: Register all built-in generators with the registry.

Registered Generators:
    commit_message_generator: CommitMessageGenerator - Generates commit messages
    pr_body_generator: PRDescriptionGenerator - Generates PR descriptions
    pr_title_generator: PRTitleGenerator - Generates PR titles
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry

# Import generator classes
from maverick.agents.generators import (
    CommitMessageGenerator,
    DependencyExtractor,
    PRDescriptionGenerator,
    PRTitleGenerator,
)

__all__ = [
    "register_all_generators",
]


def register_all_generators(registry: ComponentRegistry) -> None:
    """Register all built-in generators with the component registry.

    This function registers generators that are referenced in workflow YAML files.
    Each generator is registered with a name that matches the YAML reference.

    Registered generators:
    - commit_message_generator: CommitMessageGenerator (generates commit messages)
    - pr_body_generator: PRDescriptionGenerator (generates PR descriptions)
    - pr_title_generator: PRTitleGenerator (generates PR titles)

    Args:
        registry: Component registry to register generators with.

    Example:
        ```python
        from maverick.dsl.serialization.registry import component_registry
        from maverick.library.generators import register_all_generators

        register_all_generators(component_registry)

        # Now generators can be resolved by name
        commit_gen_class = component_registry.generators.get("commit_message_generator")
        ```
    """
    # Register commit message generator (used in commit-and-push fragment)
    registry.generators.register("commit_message_generator", CommitMessageGenerator)  # type: ignore[arg-type]

    # Register PR body generator (used in create-pr-with-summary fragment)
    registry.generators.register("pr_body_generator", PRDescriptionGenerator)  # type: ignore[arg-type]

    # Register PR title generator (used in create-pr-with-summary fragment)
    registry.generators.register("pr_title_generator", PRTitleGenerator)  # type: ignore[arg-type]

    # Register dependency extractor (used in refuel-speckit workflow)
    registry.generators.register("dependency_extractor", DependencyExtractor)  # type: ignore[arg-type]
