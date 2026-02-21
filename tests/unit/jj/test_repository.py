"""Unit tests for JjRepository."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.git.repository import CommitInfo, DiffStats, GitStatus
from maverick.jj.client import JjClient
from maverick.jj.models import (
    JjChangeInfo,
    JjDiffResult,
    JjDiffStatResult,
    JjLogResult,
    JjStatusResult,
)
from maverick.jj.repository import (
    JjRepository,
    _extract_changed_files,
    _parse_stat_output,
    _translate_ref,
)

# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock JjClient."""
    return AsyncMock(spec=JjClient)


@pytest.fixture
def repo(temp_dir: Path, mock_client: AsyncMock) -> JjRepository:
    """Create a JjRepository with a mocked client."""
    return JjRepository(path=temp_dir, client=mock_client)


# =====================================================================
# _translate_ref helper
# =====================================================================


class TestTranslateRef:
    """Tests for the _translate_ref helper."""

    def test_head_translates_to_at_minus(self) -> None:
        assert _translate_ref("HEAD") == "@-"

    def test_main_passes_through(self) -> None:
        assert _translate_ref("main") == "main"

    def test_branch_name_passes_through(self) -> None:
        assert _translate_ref("feature/my-branch") == "feature/my-branch"

    def test_revset_passes_through(self) -> None:
        assert _translate_ref("@") == "@"

    def test_empty_string_passes_through(self) -> None:
        assert _translate_ref("") == ""


# =====================================================================
# _extract_changed_files helper
# =====================================================================


class TestExtractChangedFiles:
    """Tests for _extract_changed_files helper."""

    def test_extracts_files_from_git_diff(self) -> None:
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "index abc1234..def5678 100644\n"
            "--- a/src/main.py\n"
            "+++ b/src/main.py\n"
            "@@ -1,3 +1,4 @@\n"
            "+import os\n"
            " def main():\n"
            "diff --git a/README.md b/README.md\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
        )
        assert _extract_changed_files(diff) == ["src/main.py", "README.md"]

    def test_empty_diff(self) -> None:
        assert _extract_changed_files("") == []

    def test_no_diff_headers(self) -> None:
        assert _extract_changed_files("some random text\n") == []


# =====================================================================
# _parse_stat_output helper
# =====================================================================


class TestParseStatOutput:
    """Tests for _parse_stat_output helper."""

    def test_parses_stat_lines(self) -> None:
        raw = (
            " src/main.py | 5 +++--\n"
            " README.md   | 2 ++\n"
            " 2 files changed, 5 insertions(+), 2 deletions(-)\n"
        )
        files, per_file = _parse_stat_output(raw)
        assert files == ["src/main.py", "README.md"]
        assert per_file["src/main.py"] == (3, 2)
        assert per_file["README.md"] == (2, 0)

    def test_empty_output(self) -> None:
        files, per_file = _parse_stat_output("")
        assert files == []
        assert per_file == {}


# =====================================================================
# JjRepository.path property
# =====================================================================


class TestJjRepositoryPath:
    """Tests for JjRepository.path property."""

    def test_path_resolved(self, temp_dir: Path) -> None:
        repo = JjRepository(path=temp_dir)
        assert repo.path == temp_dir.resolve()

    def test_path_from_string(self, temp_dir: Path) -> None:
        repo = JjRepository(path=str(temp_dir))
        assert repo.path == temp_dir.resolve()


# =====================================================================
# JjRepository.current_branch
# =====================================================================


class TestJjRepositoryCurrentBranch:
    """Tests for current_branch()."""

    @pytest.mark.asyncio
    async def test_returns_bookmark(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.log.return_value = JjLogResult(
            changes=(
                JjChangeInfo(
                    change_id="kxyz",
                    commit_id="abc123",
                    description="test",
                    bookmarks=("main",),
                ),
            ),
        )
        assert await repo.current_branch() == "main"

    @pytest.mark.asyncio
    async def test_returns_change_id_when_no_bookmarks(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.log.return_value = JjLogResult(
            changes=(
                JjChangeInfo(
                    change_id="kxyz",
                    commit_id="abc123",
                    description="test",
                ),
            ),
        )
        assert await repo.current_branch() == "kxyz"

    @pytest.mark.asyncio
    async def test_falls_back_to_status(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.log.return_value = JjLogResult(changes=())
        mock_client.status.return_value = JjStatusResult(
            working_copy_change_id="wxyz",
        )
        assert await repo.current_branch() == "wxyz"

    @pytest.mark.asyncio
    async def test_unknown_when_no_info(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.log.return_value = JjLogResult(changes=())
        mock_client.status.return_value = JjStatusResult()
        assert await repo.current_branch() == "unknown"


# =====================================================================
# JjRepository.diff
# =====================================================================


class TestJjRepositoryDiff:
    """Tests for diff()."""

    @pytest.mark.asyncio
    async def test_diff_default_head(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff.return_value = JjDiffResult(output="diff text")
        result = await repo.diff()
        assert result == "diff text"
        mock_client.diff.assert_called_once_with(revision="@", from_rev="@-")

    @pytest.mark.asyncio
    async def test_diff_custom_base(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff.return_value = JjDiffResult(output="diff text")
        await repo.diff(base="main")
        mock_client.diff.assert_called_once_with(revision="@", from_rev="main")

    @pytest.mark.asyncio
    async def test_diff_with_head(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff.return_value = JjDiffResult(output="diff text")
        await repo.diff(base="main", head="feature")
        mock_client.diff.assert_called_once_with(revision="feature", from_rev="main")

    @pytest.mark.asyncio
    async def test_diff_head_translates(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff.return_value = JjDiffResult(output="diff text")
        await repo.diff(base="HEAD", head="HEAD")
        mock_client.diff.assert_called_once_with(revision="@-", from_rev="@-")


# =====================================================================
# JjRepository.diff_stats
# =====================================================================


class TestJjRepositoryDiffStats:
    """Tests for diff_stats()."""

    @pytest.mark.asyncio
    async def test_returns_diff_stats(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff_stat.return_value = JjDiffStatResult(
            files_changed=2,
            insertions=5,
            deletions=2,
            output=" src/main.py | 5 +++--\n README.md   | 2 ++\n",
        )
        stats = await repo.diff_stats()
        assert isinstance(stats, DiffStats)
        assert stats.files_changed == 2
        assert stats.insertions == 5
        assert stats.deletions == 2
        assert stats.file_list == ("src/main.py", "README.md")
        assert stats.per_file["src/main.py"] == (3, 2)

    @pytest.mark.asyncio
    async def test_diff_stats_translates_head(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff_stat.return_value = JjDiffStatResult()
        await repo.diff_stats(base="HEAD")
        mock_client.diff_stat.assert_called_once_with(revision="@", from_rev="@-")


# =====================================================================
# JjRepository.get_changed_files
# =====================================================================


class TestJjRepositoryGetChangedFiles:
    """Tests for get_changed_files()."""

    @pytest.mark.asyncio
    async def test_returns_files(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff.return_value = JjDiffResult(
            output="diff --git a/foo.py b/foo.py\n+stuff\n"
        )
        files = await repo.get_changed_files()
        assert files == ["foo.py"]

    @pytest.mark.asyncio
    async def test_translates_head(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.diff.return_value = JjDiffResult(output="")
        await repo.get_changed_files(ref="HEAD")
        mock_client.diff.assert_called_once_with(revision="@", from_rev="@-")


# =====================================================================
# JjRepository.log
# =====================================================================


class TestJjRepositoryLog:
    """Tests for log()."""

    @pytest.mark.asyncio
    async def test_returns_commit_infos(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.log.return_value = JjLogResult(
            changes=(
                JjChangeInfo(
                    change_id="kxyz",
                    commit_id="abc1234567890",
                    description="feat: add feature",
                    author="Test User",
                    timestamp="2026-01-15T10:00:00Z",
                ),
                JjChangeInfo(
                    change_id="mwxy",
                    commit_id="def5678901234",
                    description="fix: bug fix",
                    author="Other User",
                    timestamp="2026-01-14T09:00:00Z",
                ),
            ),
        )
        commits = await repo.log(n=5)
        assert len(commits) == 2
        assert isinstance(commits[0], CommitInfo)
        assert commits[0].sha == "abc1234567890"
        assert commits[0].short_sha == "abc1234"
        assert commits[0].message == "feat: add feature"
        assert commits[0].author == "Test User"
        assert commits[0].date == "2026-01-15T10:00:00Z"
        mock_client.log.assert_called_once_with(revset="@-", limit=5)

    @pytest.mark.asyncio
    async def test_empty_commit_id(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.log.return_value = JjLogResult(
            changes=(
                JjChangeInfo(
                    change_id="kxyz",
                    commit_id="",
                    description="empty",
                ),
            ),
        )
        commits = await repo.log()
        assert commits[0].short_sha == ""


# =====================================================================
# JjRepository.status
# =====================================================================


class TestJjRepositoryStatus:
    """Tests for status()."""

    @pytest.mark.asyncio
    async def test_parses_status(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.status.return_value = JjStatusResult(
            output="M src/main.py\nA new_file.py\n",
            working_copy_change_id="kxyz",
        )
        status = await repo.status()
        assert isinstance(status, GitStatus)
        assert status.staged == ()
        assert status.unstaged == ("src/main.py",)
        assert status.untracked == ("new_file.py",)
        assert status.branch == "kxyz"
        assert status.ahead == 0
        assert status.behind == 0

    @pytest.mark.asyncio
    async def test_empty_status(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.status.return_value = JjStatusResult(output="")
        status = await repo.status()
        assert status.unstaged == ()
        assert status.untracked == ()
        assert status.branch == "unknown"


# =====================================================================
# JjRepository.commit_messages
# =====================================================================


class TestJjRepositoryCommitMessages:
    """Tests for commit_messages()."""

    @pytest.mark.asyncio
    async def test_returns_descriptions(
        self, repo: JjRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.log.return_value = JjLogResult(
            changes=(
                JjChangeInfo(change_id="a", commit_id="a1", description="first"),
                JjChangeInfo(change_id="b", commit_id="b1", description=""),
                JjChangeInfo(change_id="c", commit_id="c1", description="third"),
            ),
        )
        messages = await repo.commit_messages(limit=5)
        assert messages == ["first", "third"]
        mock_client.log.assert_called_once_with(revset="@-", limit=5)
