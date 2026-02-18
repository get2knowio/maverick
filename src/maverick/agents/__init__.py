"""Maverick Agents Module.

This module provides the base agent abstraction layer for Maverick.

Public API:
    MaverickAgent: Abstract base class for all agents
    AgentResult: Structured result from agent execution
    AgentUsage: Usage statistics (tokens, cost, duration)
    AgentContext: Runtime context for agent execution
    AgentRegistry: Registry for agent discovery and instantiation
    registry: Module-level registry singleton
    register: Decorator for registering agent classes
    extract_text: Extract text from a single message
    extract_all_text: Extract text from multiple messages
    AgentMessage: Type alias for SDK Message type
    BUILTIN_TOOLS: Set of built-in tools available to agents
    DEFAULT_MODEL: Default Claude model for agents
    REVIEWER_TOOLS: Read-only tools for code analysis agents
    IMPLEMENTER_TOOLS: Code modification tools without command execution
    FIXER_TOOLS: Minimal tools for targeted file fixes
    ISSUE_FIXER_TOOLS: Issue resolution with file search capability
    GENERATOR_TOOLS: Empty set for text generation agents
    CodeReviewerAgent: Concrete agent for code review (if available)
    ImplementerAgent: Concrete agent for task implementation (if available)
    IssueFixerAgent: Concrete agent for issue fixing (if available)

Submodules:
    generators: Lightweight text generators (CommitMessageGenerator, etc.)
"""

from __future__ import annotations

from typing import Any

# Import public API components
from maverick.agents.base import BUILTIN_TOOLS, DEFAULT_MODEL, MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.registry import AgentRegistry, register, registry
from maverick.agents.result import AgentResult, AgentUsage
from maverick.agents.tools import (
    CURATOR_TOOLS,
    FIXER_TOOLS,
    GENERATOR_TOOLS,
    IMPLEMENTER_TOOLS,
    ISSUE_FIXER_TOOLS,
    REVIEWER_TOOLS,
)
from maverick.agents.utils import extract_all_text, extract_text

# Conditional import for concrete agent implementations
try:
    from maverick.agents.code_reviewer import CodeReviewerAgent
except ImportError:
    CodeReviewerAgent = None  # type: ignore[misc,assignment]  # Not yet implemented

try:
    from maverick.agents.implementer import ImplementerAgent
except ImportError:
    ImplementerAgent = None  # type: ignore[misc,assignment]  # Not yet implemented

try:
    from maverick.agents.issue_fixer import IssueFixerAgent
except ImportError:
    IssueFixerAgent = None  # type: ignore[misc,assignment]  # Not yet implemented

try:
    from maverick.agents.fixer import FixerAgent
except ImportError:
    FixerAgent = None  # type: ignore[misc,assignment]  # Not yet implemented

try:
    from maverick.agents.curator import CuratorAgent
except ImportError:
    CuratorAgent = None  # type: ignore[misc,assignment]  # Not yet implemented

# Type alias for SDK Message type (T032)
# At runtime, this is Any since SDK may not be installed.
# For type checking, this would be claude_agent_sdk.Message
AgentMessage = Any

__all__: list[str] = [
    # Base class and constants
    "BUILTIN_TOOLS",
    "DEFAULT_MODEL",
    "MaverickAgent",
    # Tool permission constants
    "CURATOR_TOOLS",
    "FIXER_TOOLS",
    "GENERATOR_TOOLS",
    "IMPLEMENTER_TOOLS",
    "ISSUE_FIXER_TOOLS",
    "REVIEWER_TOOLS",
    # Result types
    "AgentResult",
    "AgentUsage",
    # Context
    "AgentContext",
    # Registry
    "AgentRegistry",
    "register",
    "registry",
    # Utilities
    "extract_all_text",
    "extract_text",
    # Type alias
    "AgentMessage",
    # Submodules
    "generators",
]

# Conditionally add concrete agents to __all__ if they were successfully imported
if CodeReviewerAgent is not None:
    __all__ += ["CodeReviewerAgent"]

if ImplementerAgent is not None:
    __all__ += ["ImplementerAgent"]

if IssueFixerAgent is not None:
    __all__ += ["IssueFixerAgent"]

if FixerAgent is not None:
    __all__ += ["FixerAgent"]

if CuratorAgent is not None:
    __all__ += ["CuratorAgent"]
