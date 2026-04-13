"""Unit tests for maverick.preflight_briefing.synthesis (re-export)."""

from __future__ import annotations

from maverick.preflight_briefing.synthesis import serialize_briefs_to_markdown


class TestSynthesisReExport:
    """Verify the synthesis module re-exports serialize_briefs_to_markdown."""

    def test_re_export_works(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            scope={"in_scope": ["Auth"]},
        )
        assert "Auth" in result
