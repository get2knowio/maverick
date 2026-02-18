"""Unit tests for JjClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.exceptions.jj import (
    JjCloneError,
    JjConflictError,
    JjError,
    JjOperationError,
    JjPushError,
)
from maverick.jj.client import JjClient, _parse_diff_stat_summary, _parse_log_output

from .conftest import make_result

# =========================================================================
# Lifecycle
# =========================================================================


class TestVerifyAvailable:
    """Tests for JjClient.verify_available()."""

    @pytest.mark.asyncio
    async def test_available(self, jj_client: JjClient, mock_runner: AsyncMock) -> None:
        mock_runner.run.return_value = make_result(stdout="jj 0.24.0")
        assert await jj_client.verify_available()

    @pytest.mark.asyncio
    async def test_not_available(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=127, stderr="command not found: jj"
        )
        assert not await jj_client.verify_available()


class TestGitClone:
    """Tests for JjClient.git_clone()."""

    @pytest.mark.asyncio
    async def test_clone_success(
        self, jj_client: JjClient, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="Fetching into new repo")
        target = temp_dir / "workspace"
        result = await jj_client.git_clone("https://github.com/org/repo", target)
        assert result.success is True
        assert result.workspace_path == str(target)

        cmd = mock_runner.run.call_args[0][0]
        assert cmd[:3] == ["jj", "git", "clone"]
        assert "--colocate" not in cmd

    @pytest.mark.asyncio
    async def test_clone_colocate(
        self, jj_client: JjClient, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = make_result()
        target = temp_dir / "workspace"
        await jj_client.git_clone("/local/repo", target, colocate=True)

        cmd = mock_runner.run.call_args[0][0]
        assert "--colocate" in cmd

    @pytest.mark.asyncio
    async def test_clone_failure(
        self, jj_client: JjClient, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="fatal: repository not found"
        )
        with pytest.raises(JjCloneError) as exc_info:
            await jj_client.git_clone("bad-url", temp_dir / "ws")
        assert exc_info.value.source == "bad-url"

    @pytest.mark.asyncio
    async def test_clone_uses_extended_timeout(
        self, jj_client: JjClient, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.git_clone("/repo", temp_dir / "ws")

        call_kwargs = mock_runner.run.call_args[1]
        assert call_kwargs["timeout"] == 600.0

    @pytest.mark.asyncio
    async def test_clone_uses_retries(
        self, jj_client: JjClient, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.git_clone("/repo", temp_dir / "ws")

        call_kwargs = mock_runner.run.call_args[1]
        assert call_kwargs["max_retries"] == 3


class TestGitFetch:
    """Tests for JjClient.git_fetch()."""

    @pytest.mark.asyncio
    async def test_fetch_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.git_fetch()
        assert result.success is True

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "git", "fetch", "--remote", "origin"]

    @pytest.mark.asyncio
    async def test_fetch_custom_remote(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.git_fetch(remote="upstream")

        cmd = mock_runner.run.call_args[0][0]
        assert "upstream" in cmd

    @pytest.mark.asyncio
    async def test_fetch_failure(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="could not resolve host"
        )
        with pytest.raises(JjError, match="jj git fetch failed"):
            await jj_client.git_fetch()


class TestGitPush:
    """Tests for JjClient.git_push()."""

    @pytest.mark.asyncio
    async def test_push_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.git_push()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_push_with_bookmark(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.git_push(bookmark="feature-x")

        cmd = mock_runner.run.call_args[0][0]
        assert "--bookmark" in cmd
        assert "feature-x" in cmd

    @pytest.mark.asyncio
    async def test_push_failure(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="rejected: non-fast-forward"
        )
        with pytest.raises(JjPushError) as exc_info:
            await jj_client.git_push(remote="origin", bookmark="main")
        assert exc_info.value.remote == "origin"
        assert exc_info.value.bookmark == "main"


# =========================================================================
# Change management
# =========================================================================


class TestDescribe:
    """Tests for JjClient.describe()."""

    @pytest.mark.asyncio
    async def test_describe_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.describe("wip: working on feature")
        assert result.success is True
        assert result.message == "wip: working on feature"

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "describe", "-r", "@", "-m", "wip: working on feature"]

    @pytest.mark.asyncio
    async def test_describe_custom_revision(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.describe("msg", revision="kxyz")

        cmd = mock_runner.run.call_args[0][0]
        assert "-r" in cmd
        assert "kxyz" in cmd

    @pytest.mark.asyncio
    async def test_describe_failure(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="revision not found"
        )
        with pytest.raises(JjError, match="jj describe failed"):
            await jj_client.describe("msg")


class TestNew:
    """Tests for JjClient.new()."""

    @pytest.mark.asyncio
    async def test_new_default(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="Working copy now at: kxyz")
        result = await jj_client.new()
        assert result.success is True

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "new"]

    @pytest.mark.asyncio
    async def test_new_with_parents(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="kxyz")
        await jj_client.new(parents=["main", "feature"])

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "new", "-r", "main", "-r", "feature"]

    @pytest.mark.asyncio
    async def test_new_with_message(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.new(message="start work")

        cmd = mock_runner.run.call_args[0][0]
        assert "-m" in cmd
        assert "start work" in cmd


class TestCommit:
    """Tests for JjClient.commit()."""

    @pytest.mark.asyncio
    async def test_commit_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="kxyz")
        result = await jj_client.commit("feat: add feature")
        assert result.success is True

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "commit", "-m", "feat: add feature"]

    @pytest.mark.asyncio
    async def test_commit_failure(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="nothing to commit"
        )
        with pytest.raises(JjError, match="jj commit failed"):
            await jj_client.commit("msg")


# =========================================================================
# Read operations
# =========================================================================


class TestDiff:
    """Tests for JjClient.diff()."""

    @pytest.mark.asyncio
    async def test_diff_default(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="--- a/f\n+++ b/f\n+line")
        result = await jj_client.diff()
        assert "+line" in result.output

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "diff", "--git", "-r", "@"]

    @pytest.mark.asyncio
    async def test_diff_from_rev(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="diff output")
        await jj_client.diff(revision="@", from_rev="main")

        cmd = mock_runner.run.call_args[0][0]
        assert "--from" in cmd
        assert "main" in cmd
        assert "--to" in cmd
        assert "@" in cmd


class TestDiffStat:
    """Tests for JjClient.diff_stat()."""

    @pytest.mark.asyncio
    async def test_diff_stat(self, jj_client: JjClient, mock_runner: AsyncMock) -> None:
        stat_output = (
            " src/main.py | 10 +++++-----\n"
            " 1 file changed, 5 insertions(+), 5 deletions(-)"
        )
        mock_runner.run.return_value = make_result(stdout=stat_output)
        result = await jj_client.diff_stat()
        assert result.files_changed == 1
        assert result.insertions == 5
        assert result.deletions == 5


class TestLog:
    """Tests for JjClient.log()."""

    @pytest.mark.asyncio
    async def test_log_parses_structured_output(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        sep = "\x1f"
        structured = (
            f"kxyz{sep}abc123{sep}feat: add feature{sep}"
            f"Alice{sep}alice@example.com{sep}2026-01-01{sep}main{sep}false\n"
        )
        # First call: structured log; second call: display log
        mock_runner.run.side_effect = [
            make_result(stdout=structured),
            make_result(stdout="display log"),
        ]

        result = await jj_client.log()
        assert len(result.changes) == 1
        assert result.changes[0].change_id == "kxyz"
        assert result.changes[0].author == "Alice"
        assert result.changes[0].bookmarks == ("main",)
        assert result.output == "display log"

    @pytest.mark.asyncio
    async def test_log_empty(self, jj_client: JjClient, mock_runner: AsyncMock) -> None:
        mock_runner.run.side_effect = [
            make_result(stdout=""),
            make_result(stdout=""),
        ]
        result = await jj_client.log()
        assert len(result.changes) == 0


class TestStatus:
    """Tests for JjClient.status()."""

    @pytest.mark.asyncio
    async def test_status_parses_change_id(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        status_output = (
            "Working copy changes:\nM src/main.py\nWorking copy : kxyz description\n"
        )
        mock_runner.run.return_value = make_result(stdout=status_output)
        result = await jj_client.status()
        assert result.success is True
        assert result.working_copy_change_id == "kxyz"
        assert result.conflict is False

    @pytest.mark.asyncio
    async def test_status_detects_conflict(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            stdout="There are unresolved conflicts in these files:\nsrc/main.py"
        )
        result = await jj_client.status()
        assert result.conflict is True


class TestShow:
    """Tests for JjClient.show()."""

    @pytest.mark.asyncio
    async def test_show_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="commit details...")
        result = await jj_client.show(revision="kxyz")
        assert result.output == "commit details..."

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "show", "-r", "kxyz"]


# =========================================================================
# Operation log safety
# =========================================================================


class TestSnapshotOperation:
    """Tests for JjClient.snapshot_operation()."""

    @pytest.mark.asyncio
    async def test_snapshot_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="op-abc123\n")
        result = await jj_client.snapshot_operation()
        assert result.success is True
        assert result.operation_id == "op-abc123"

    @pytest.mark.asyncio
    async def test_snapshot_failure(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="operation log corrupted"
        )
        with pytest.raises(JjOperationError):
            await jj_client.snapshot_operation()


class TestRestoreOperation:
    """Tests for JjClient.restore_operation()."""

    @pytest.mark.asyncio
    async def test_restore_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.restore_operation("op-abc123")
        assert result.success is True

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "op", "restore", "op-abc123"]

    @pytest.mark.asyncio
    async def test_restore_failure(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="unknown operation"
        )
        with pytest.raises(JjOperationError) as exc_info:
            await jj_client.restore_operation("bad-op")
        assert exc_info.value.operation_id == "bad-op"


# =========================================================================
# History curation
# =========================================================================


class TestSquash:
    """Tests for JjClient.squash()."""

    @pytest.mark.asyncio
    async def test_squash_default(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.squash()
        assert result.success is True

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "squash"]

    @pytest.mark.asyncio
    async def test_squash_custom_revision(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.squash(revision="kxyz")

        cmd = mock_runner.run.call_args[0][0]
        assert "-r" in cmd
        assert "kxyz" in cmd

    @pytest.mark.asyncio
    async def test_squash_into_target(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.squash(into="main")

        cmd = mock_runner.run.call_args[0][0]
        assert "--into" in cmd
        assert "main" in cmd


class TestAbsorb:
    """Tests for JjClient.absorb()."""

    @pytest.mark.asyncio
    async def test_absorb_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="Absorbed into 3 commits")
        result = await jj_client.absorb()
        assert result.success is True
        assert "Absorbed" in result.output


class TestRebase:
    """Tests for JjClient.rebase()."""

    @pytest.mark.asyncio
    async def test_rebase_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.rebase(revision="kxyz", destination="main")
        assert result.success is True

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "rebase", "-r", "kxyz", "-d", "main"]


# =========================================================================
# Bookmarks
# =========================================================================


class TestBookmarkSet:
    """Tests for JjClient.bookmark_set()."""

    @pytest.mark.asyncio
    async def test_bookmark_set_success(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.bookmark_set("feature-x", revision="kxyz")
        assert result.success is True
        assert result.name == "feature-x"

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "bookmark", "set", "feature-x", "-r", "kxyz"]


# =========================================================================
# Conflict detection
# =========================================================================


class TestConflictDetection:
    """Tests for automatic conflict error detection."""

    @pytest.mark.asyncio
    async def test_conflict_raises_specific_error(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(
            returncode=1, stderr="New conflicts in: src/main.py"
        )
        with pytest.raises(JjConflictError):
            await jj_client.describe("msg")


# =========================================================================
# Parsing helpers
# =========================================================================


class TestParseDiffStatSummary:
    """Tests for _parse_diff_stat_summary."""

    def test_full_summary(self) -> None:
        raw = " 3 files changed, 10 insertions(+), 5 deletions(-)"
        files, ins, dels = _parse_diff_stat_summary(raw)
        assert files == 3
        assert ins == 10
        assert dels == 5

    def test_insertions_only(self) -> None:
        raw = " 1 file changed, 7 insertions(+)"
        files, ins, dels = _parse_diff_stat_summary(raw)
        assert files == 1
        assert ins == 7
        assert dels == 0

    def test_deletions_only(self) -> None:
        raw = " 2 files changed, 3 deletions(-)"
        files, ins, dels = _parse_diff_stat_summary(raw)
        assert files == 2
        assert ins == 0
        assert dels == 3

    def test_no_match(self) -> None:
        raw = "nothing changed"
        files, ins, dels = _parse_diff_stat_summary(raw)
        assert files == 0
        assert ins == 0
        assert dels == 0


class TestParseLogOutput:
    """Tests for _parse_log_output."""

    def test_parses_entries(self) -> None:
        sep = "\x1f"
        raw = (
            f"kxyz{sep}abc123{sep}feat: add{sep}Alice{sep}"
            f"alice@ex.com{sep}2026-01-01{sep}main{sep}false\n"
            f"kabc{sep}def456{sep}fix: bug{sep}Bob{sep}"
            f"bob@ex.com{sep}2026-01-02{sep}{sep}true\n"
        )
        changes = _parse_log_output(raw)
        assert len(changes) == 2
        assert changes[0].change_id == "kxyz"
        assert changes[0].bookmarks == ("main",)
        assert changes[0].empty is False
        assert changes[1].change_id == "kabc"
        assert changes[1].empty is True

    def test_empty_output(self) -> None:
        assert _parse_log_output("") == []

    def test_skips_short_lines(self) -> None:
        sep = "\x1f"
        raw = f"a{sep}b\nproper{sep}line{sep}desc{sep}author\n"
        changes = _parse_log_output(raw)
        assert len(changes) == 1
        assert changes[0].change_id == "proper"
