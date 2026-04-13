"""Unit tests for maverick.preflight_briefing.models.

The Pydantic brief models are no longer used by the runtime — agent
briefs are raw dicts from MCP tool calls. These tests verify the
models still import (backwards compat) but are not exercised in depth.
"""

from __future__ import annotations


def test_models_importable() -> None:
    """Verify the models module is still importable."""
    from maverick.preflight_briefing.models import (  # noqa: F401
        CodebaseAnalystBrief,
        CriteriaWriterBrief,
        PreFlightBriefingDocument,
        PreFlightContrarianBrief,
        ScopistBrief,
    )
