"""Typed output models for step handlers.

This module defines the canonical return type for all step handlers,
replacing ad-hoc dict returns with a frozen dataclass per Architectural
Guardrail #4: "Actions must have a single, typed contract."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HandlerOutput:
    """Typed output from a step handler.

    All step handlers that need to return both a result value and
    emitted progress events MUST use this dataclass instead of
    returning bare ``dict[str, Any]`` blobs.

    Attributes:
        result: The step's primary result value.  For loop steps this
            is the list of iteration results; for agent steps this is
            the agent execution result, etc.
        events: Progress events emitted during execution (e.g.
            ``AgentStreamChunk``, ``LoopIterationStarted``).  Defaults
            to an empty list when the handler has no embedded events.
    """

    result: Any
    events: list[Any] = field(default_factory=list)


__all__ = [
    "HandlerOutput",
]
