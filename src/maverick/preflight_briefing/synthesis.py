"""Briefing synthesis — now delegated to serializer.

The typed Pydantic synthesis has been replaced by
``serialize_briefs_to_markdown`` in ``serializer.py`` which works
directly with the raw dicts from MCP tool calls.

This module is kept as a thin re-export for backwards compatibility.
"""

from __future__ import annotations

from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

__all__ = ["serialize_briefs_to_markdown"]
