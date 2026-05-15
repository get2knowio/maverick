"""Ambient-tag scope for agent telemetry.

Agents no longer carry workflow vocabulary (``bead_id``, ``complexity``,
``workflow``) on their domain methods or as mutable instance attributes.
Instead, callers wrap a block of work in :func:`tagged` and the
:class:`~maverick.agents.base.Agent`'s cost-recording path reads
:func:`current_tags` to stamp every send.

This decouples three concerns that were tangled in the previous design:

* Workflow vocabulary (bead/complexity) lives in workflow + squadron code,
  not in agent signatures — a ``CodingAgent`` is usable from a one-shot
  script with no fake ``bead_id`` argument.
* Concurrent fan-out (`asyncio.gather`, future Burr ``MapStates``) is
  race-free: each task gets its own :class:`ContextVar` view, so a cost
  record captured async after a follow-up call can't be attributed to the
  wrong bead.
* Tags compose. A workflow can ``tagged(workflow="fly")`` once at the top
  and an inner ``tagged(bead_id=...)`` extends rather than replaces.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# The default is ``None`` (not ``{}``) so we don't share a mutable default
# across all importers — the dict is built on first read.
_TAGS: ContextVar[dict[str, str] | None] = ContextVar("agent_tags", default=None)


@contextmanager
def tagged(**new_tags: str) -> Iterator[None]:
    """Extend the ambient tag set for the duration of the block.

    Inner tags override outer ones with the same key. The previous tag
    map is restored on exit (including on exception) via
    :meth:`ContextVar.reset`.
    """
    current = _TAGS.get() or {}
    token = _TAGS.set({**current, **new_tags})
    try:
        yield
    finally:
        _TAGS.reset(token)


def current_tags() -> dict[str, str]:
    """Snapshot the active tag map.

    Returns a shallow copy — callers can mutate the result without
    affecting the live context.
    """
    return dict(_TAGS.get() or {})


__all__ = ["current_tags", "tagged"]
