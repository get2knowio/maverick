"""Step path utilities for hierarchical event tracking.

This module provides utilities for building hierarchical step paths
and wrapping event callbacks to automatically prefix events with
their position in the workflow tree.

Step paths use '/' as a separator and '[N]' for loop iterations:
    implement_by_phase/[0]/validate_phase/run_validation
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.events import ProgressEvent
    from maverick.dsl.serialization.executor.handlers.base import EventCallback


def build_path(prefix: str | None, segment: str) -> str:
    """Join a prefix and segment with '/'.

    Args:
        prefix: Existing path prefix, or None for root.
        segment: New segment to append.

    Returns:
        Combined path string.

    Examples:
        >>> build_path(None, "step_a")
        'step_a'
        >>> build_path("step_a", "[0]")
        'step_a/[0]'
        >>> build_path("step_a/[0]", "validate")
        'step_a/[0]/validate'
    """
    return f"{prefix}/{segment}" if prefix else segment


def make_prefix_callback(
    prefix: str,
    inner_callback: EventCallback,
) -> EventCallback:
    """Wrap an event_callback to prepend a path prefix to forwarded events.

    Events that have a ``step_path`` attribute get the prefix prepended.
    Events without ``step_path`` (e.g., WorkflowStarted) pass through unchanged.

    Args:
        prefix: Path segment to prepend (e.g., step name or "[N]").
        inner_callback: The original callback to delegate to.

    Returns:
        A new async callback that prepends the prefix before forwarding.
    """

    async def prefixed_callback(event: ProgressEvent) -> None:
        if hasattr(event, "step_path"):
            current = getattr(event, "step_path", None)
            new_path = build_path(prefix, current) if current else prefix
            event = replace(event, step_path=new_path)  # type: ignore[arg-type]
        await inner_callback(event)

    return prefixed_callback
