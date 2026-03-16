"""Generator agents for stateless text generation.

This package provides lightweight, single-purpose text generators that use
Claude Agent SDK's query() function for stateless, tool-free generation.

Available generators:
    GeneratorAgent: Abstract base class for all generators.
    CommitMessageGenerator: Generates conventional commit messages.
    PRDescriptionGenerator: Generates markdown PR descriptions.

Example:
    >>> from maverick.agents.generators import CommitMessageGenerator
    >>> generator = CommitMessageGenerator()
    >>> message = await generator.generate({"diff": "...", "file_stats": {}})
"""

from __future__ import annotations

from maverick.agents.generators.base import (
    DEFAULT_MODEL,
    DEFAULT_PR_SECTIONS,
    MAX_DIFF_SIZE,
    MAX_SNIPPET_SIZE,
    MAX_TURNS,
    GeneratorAgent,
)
from maverick.agents.generators.bead_enricher import BeadEnricherGenerator
from maverick.agents.generators.commit_message import CommitMessageGenerator
from maverick.agents.generators.consolidator import ConsolidatorAgent
from maverick.agents.generators.dependency_extractor import DependencyExtractor
from maverick.agents.generators.pr_description import PRDescriptionGenerator
from maverick.agents.generators.pr_title import PRTitleGenerator

__all__ = [
    # Base class
    "GeneratorAgent",
    # Concrete generators
    "BeadEnricherGenerator",
    "CommitMessageGenerator",
    "ConsolidatorAgent",
    "DependencyExtractor",
    "PRDescriptionGenerator",
    "PRTitleGenerator",
    # Constants
    "DEFAULT_MODEL",
    "DEFAULT_PR_SECTIONS",
    "MAX_DIFF_SIZE",
    "MAX_SNIPPET_SIZE",
    "MAX_TURNS",
]
