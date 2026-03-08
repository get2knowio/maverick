"""Unit tests for open bead analysis action."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.library.actions.open_bead_analysis import (
    FileOverlap,
    OpenBeadAnalysisResult,
    OpenEpicInfo,
    _normalize_scope_path,
    analyze_open_beads,
)

# =============================================================================
# Model tests
# =============================================================================


class TestOpenEpicInfo:
    """Tests for OpenEpicInfo dataclass."""

    def test_to_dict(self) -> None:
        info = OpenEpicInfo(
            epic_id="e-1",
            title="Auth",
            flight_plan_name="add-auth",
            status="open",
            open_bead_count=3,
        )
        d = info.to_dict()
        assert d["epic_id"] == "e-1"
        assert d["flight_plan_name"] == "add-auth"
        assert d["open_bead_count"] == 3


class TestFileOverlap:
    """Tests for FileOverlap dataclass."""

    def test_to_dict(self) -> None:
        overlap = FileOverlap(
            file_path="src/auth.py",
            epic_flight_plan_name="add-auth",
            epic_id="e-1",
        )
        d = overlap.to_dict()
        assert d["file_path"] == "src/auth.py"


class TestOpenBeadAnalysisResult:
    """Tests for OpenBeadAnalysisResult."""

    def test_to_dict_empty(self) -> None:
        result = OpenBeadAnalysisResult()
        d = result.to_dict()
        assert d["open_epics"] == []
        assert d["file_overlaps"] == []
        assert d["total_open_beads"] == 0

    def test_format_for_prompt_empty(self) -> None:
        result = OpenBeadAnalysisResult()
        assert result.format_for_prompt() == ""

    def test_format_for_prompt_with_epics(self) -> None:
        result = OpenBeadAnalysisResult(
            open_epics=(
                OpenEpicInfo(
                    epic_id="e-1",
                    title="Auth",
                    flight_plan_name="add-auth",
                    status="open",
                    open_bead_count=2,
                ),
            ),
            file_overlaps=(),
            total_open_beads=2,
            overlap_count=0,
        )
        prompt = result.format_for_prompt()
        assert "add-auth" in prompt
        assert "2 open beads" in prompt
        assert "No file scope overlaps" in prompt

    def test_format_for_prompt_with_overlaps(self) -> None:
        result = OpenBeadAnalysisResult(
            open_epics=(
                OpenEpicInfo(
                    epic_id="e-1",
                    title="Auth",
                    flight_plan_name="add-auth",
                    status="open",
                    open_bead_count=2,
                ),
            ),
            file_overlaps=(
                FileOverlap(
                    file_path="src/config.py",
                    epic_flight_plan_name="add-auth",
                    epic_id="e-1",
                ),
            ),
            total_open_beads=2,
            overlap_count=1,
        )
        prompt = result.format_for_prompt()
        assert "src/config.py" in prompt
        assert "add-auth" in prompt
        assert "merge conflicts" in prompt


# =============================================================================
# _normalize_scope_path
# =============================================================================


class TestNormalizeScopePath:
    """Tests for _normalize_scope_path helper."""

    def test_plain_path(self) -> None:
        assert _normalize_scope_path("src/foo.py") == "src/foo.py"

    def test_backtick_wrapped(self) -> None:
        assert _normalize_scope_path("`src/foo.py`") == "src/foo.py"

    def test_backtick_with_annotation(self) -> None:
        result = _normalize_scope_path("`src/foo.py` — CLI entry point")
        assert result == "src/foo.py"

    def test_plain_with_dash_annotation(self) -> None:
        result = _normalize_scope_path("src/foo.py - the config")
        assert result == "src/foo.py"

    def test_whitespace_stripped(self) -> None:
        assert _normalize_scope_path("  src/foo.py  ") == "src/foo.py"


# =============================================================================
# analyze_open_beads
# =============================================================================


class TestAnalyzeOpenBeads:
    """Tests for analyze_open_beads action."""

    @pytest.mark.asyncio
    async def test_no_epics_returns_empty(self) -> None:
        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(return_value=[])

            result = await analyze_open_beads(
                new_plan_in_scope=("src/foo.py",),
                cwd=Path("/tmp"),
            )

        assert result.open_epics == ()
        assert result.file_overlaps == ()
        assert result.total_open_beads == 0

    @pytest.mark.asyncio
    async def test_skips_closed_epics(self) -> None:
        closed_epic = MagicMock()
        closed_epic.id = "e-1"
        closed_epic.status = "closed"

        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(return_value=[closed_epic])

            result = await analyze_open_beads(
                new_plan_in_scope=("src/foo.py",),
                cwd=Path("/tmp"),
            )

        assert result.open_epics == ()
        # show should not be called for closed epics
        client.show.assert_not_called()

    @pytest.mark.asyncio
    async def test_finds_file_overlap(self, tmp_path: Path) -> None:
        """Detects overlap when open epic has work units with same files."""
        # Create work unit files on disk
        plan_dir = tmp_path / ".maverick" / "plans" / "old-plan"
        plan_dir.mkdir(parents=True)
        wu_content = """\
---
work-unit: setup-db
flight-plan: old-plan
sequence: 1
depends-on: []
---

## Task

Set up the database.

## Acceptance Criteria

- Database is configured

## File Scope

### Create

- src/db.py

### Modify

- src/config.py

### Protect

## Instructions

Do the thing.

## Verification

- make test
"""
        (plan_dir / "001-setup-db.md").write_text(wu_content)

        # Mock BeadClient
        epic = MagicMock()
        epic.id = "e-old"
        epic.status = "open"

        details = MagicMock()
        details.state = {"flight_plan_name": "old-plan"}

        child = MagicMock()
        child.status = "open"

        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(return_value=[epic])
            client.show = AsyncMock(return_value=details)
            client.children = AsyncMock(return_value=[child])

            result = await analyze_open_beads(
                new_plan_in_scope=("src/config.py",),
                cwd=tmp_path,
            )

        assert len(result.open_epics) == 1
        assert result.open_epics[0].flight_plan_name == "old-plan"
        assert result.overlap_count == 1
        assert result.file_overlaps[0].file_path == "src/config.py"

    @pytest.mark.asyncio
    async def test_no_overlap_when_files_differ(self, tmp_path: Path) -> None:
        """No overlap when work unit files don't match new plan."""
        plan_dir = tmp_path / ".maverick" / "plans" / "other"
        plan_dir.mkdir(parents=True)
        wu_content = """\
---
work-unit: add-widget
flight-plan: other
sequence: 1
depends-on: []
---

## Task

Add widget.

## Acceptance Criteria

- Widget works

## File Scope

### Create

- src/widget.py

### Modify

### Protect

## Instructions

Build it.

## Verification

- make test
"""
        (plan_dir / "001-add-widget.md").write_text(wu_content)

        epic = MagicMock()
        epic.id = "e-other"
        epic.status = "open"

        details = MagicMock()
        details.state = {"flight_plan_name": "other"}

        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(return_value=[epic])
            client.show = AsyncMock(return_value=details)
            client.children = AsyncMock(return_value=[])

            result = await analyze_open_beads(
                new_plan_in_scope=("src/totally-different.py",),
                cwd=tmp_path,
            )

        assert result.overlap_count == 0

    @pytest.mark.asyncio
    async def test_query_failure_returns_empty(self) -> None:
        """Gracefully returns empty result on query failure."""
        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(side_effect=RuntimeError("bd unavailable"))

            result = await analyze_open_beads(
                new_plan_in_scope=("src/foo.py",),
                cwd=Path("/tmp"),
            )

        assert result.open_epics == ()
        assert result.total_open_beads == 0
