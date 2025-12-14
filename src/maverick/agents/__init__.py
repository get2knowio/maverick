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
    CodeReviewerAgent: Concrete agent for code review (if available)
    ImplementerAgent: Concrete agent for task implementation (if available)
    IssueFixerAgent: Concrete agent for issue fixing (if available)
"""
from __future__ import annotations

from typing import Any

# Import public API components
from maverick.agents.base import BUILTIN_TOOLS, DEFAULT_MODEL, MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.registry import AgentRegistry, register, registry
from maverick.agents.result import AgentResult, AgentUsage
from maverick.agents.utils import extract_all_text, extract_text

# Conditional import for concrete agent implementations
try:
    from maverick.agents.code_reviewer import CodeReviewerAgent
except ImportError:
    CodeReviewerAgent = None  # type: ignore[assignment]  # Not yet implemented

try:
    from maverick.agents.implementer import ImplementerAgent
except ImportError:
    ImplementerAgent = None  # type: ignore[assignment]  # Not yet implemented

try:
    from maverick.agents.issue_fixer import IssueFixerAgent
except ImportError:
    IssueFixerAgent = None  # type: ignore[assignment]  # Not yet implemented

# Type alias for SDK Message type (T032)
# At runtime, this is Any since SDK may not be installed.
# For type checking, this would be claude_agent_sdk.Message
AgentMessage = Any

__all__: list[str] = [
    # Base class and constants
    "MaverickAgent",
    "BUILTIN_TOOLS",
    "DEFAULT_MODEL",
    # Result types
    "AgentResult",
    "AgentUsage",
    # Context
    "AgentContext",
    # Registry
    "AgentRegistry",
    "registry",
    "register",
    # Utilities
    "extract_text",
    "extract_all_text",
    # Type alias
    "AgentMessage",
]

# Conditionally add concrete agents to __all__ if they were successfully imported
if CodeReviewerAgent is not None:
    __all__.append("CodeReviewerAgent")

if ImplementerAgent is not None:
    __all__.append("ImplementerAgent")

if IssueFixerAgent is not None:
    __all__.append("IssueFixerAgent")
