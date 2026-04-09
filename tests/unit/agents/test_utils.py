"""Unit tests for agent utility functions.

Tests for detect_file_changes and related utilities in maverick.agents.utils.

Note: Tests for extract_text and extract_all_text were removed because those
functions were removed as part of the ACP/SDK migration (T047).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.agents.utils import detect_file_changes
from maverick.models.implementation import ChangeType, FileChange

# =============================================================================
# detect_file_changes Tests
# =============================================================================


class TestDetectFileChanges:
    """Tests for detect_file_changes function."""

    @pytest.mark.asyncio
    async def test_detect_file_changes_returns_list(self, tmp_path: Path) -> None:
        """Test returns list of FileChange objects."""
        from maverick.git import DiffStats

        mock_stats = DiffStats(
            files_changed=2,
            insertions=30,
            deletions=2,
            file_list=("src/file.py", "tests/test_file.py"),
            per_file={
                "src/file.py": (10, 2),
                "tests/test_file.py": (20, 0),
            },
        )

        mock_repo = MagicMock()
        mock_repo.diff_stats = AsyncMock(return_value=mock_stats)

        with patch("maverick.git.AsyncGitRepository", return_value=mock_repo):
            changes = await detect_file_changes(tmp_path)

            assert isinstance(changes, list)
            assert len(changes) == 2
            assert all(isinstance(c, FileChange) for c in changes)

    @pytest.mark.asyncio
    async def test_detect_file_changes_parses_stats_correctly(self, tmp_path: Path) -> None:
        """Test correctly parses file stats into FileChange objects."""
        from maverick.git import DiffStats

        mock_stats = DiffStats(
            files_changed=1,
            insertions=15,
            deletions=3,
            file_list=("src/module.py",),
            per_file={"src/module.py": (15, 3)},
        )

        mock_repo = MagicMock()
        mock_repo.diff_stats = AsyncMock(return_value=mock_stats)

        with patch("maverick.git.AsyncGitRepository", return_value=mock_repo):
            changes = await detect_file_changes(tmp_path)

            assert len(changes) == 1
            assert changes[0].file_path == "src/module.py"
            assert changes[0].lines_added == 15
            assert changes[0].lines_removed == 3
            assert changes[0].change_type == ChangeType.MODIFIED

    @pytest.mark.asyncio
    async def test_detect_file_changes_handles_errors_gracefully(self, tmp_path: Path) -> None:
        """Test returns empty list on git errors."""
        with patch(
            "maverick.git.AsyncGitRepository",
            side_effect=Exception("Git command failed"),
        ):
            changes = await detect_file_changes(tmp_path)

            assert changes == []

    @pytest.mark.asyncio
    async def test_detect_file_changes_handles_empty_diff(self, tmp_path: Path) -> None:
        """Test handles empty diff stats (no changes)."""
        from maverick.git import DiffStats

        mock_stats = DiffStats(
            files_changed=0,
            insertions=0,
            deletions=0,
            file_list=(),
            per_file={},
        )

        mock_repo = MagicMock()
        mock_repo.diff_stats = AsyncMock(return_value=mock_stats)

        with patch("maverick.git.AsyncGitRepository", return_value=mock_repo):
            changes = await detect_file_changes(tmp_path)

            assert changes == []
