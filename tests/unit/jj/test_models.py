"""Unit tests for jj result models."""

from __future__ import annotations

from maverick.jj.models import (
    JjAbsorbResult,
    JjBookmark,
    JjBookmarkResult,
    JjChangeInfo,
    JjCloneResult,
    JjCommitResult,
    JjDescribeResult,
    JjDiffResult,
    JjDiffStatResult,
    JjFetchResult,
    JjLogResult,
    JjNewResult,
    JjPushResult,
    JjRebaseResult,
    JjRestoreResult,
    JjShowResult,
    JjSnapshotResult,
    JjSquashResult,
    JjStatusResult,
)


class TestJjChangeInfo:
    """Tests for JjChangeInfo."""

    def test_defaults(self) -> None:
        info = JjChangeInfo(
            change_id="kxyz",
            commit_id="abc123",
            description="initial commit",
        )
        assert info.change_id == "kxyz"
        assert info.commit_id == "abc123"
        assert info.description == "initial commit"
        assert info.author == ""
        assert info.bookmarks == ()
        assert info.empty is False

    def test_to_dict(self) -> None:
        info = JjChangeInfo(
            change_id="kxyz",
            commit_id="abc123",
            description="feat: add feature",
            author="Alice",
            bookmarks=("main",),
            empty=True,
        )
        d = info.to_dict()
        assert d["change_id"] == "kxyz"
        assert d["bookmarks"] == ("main",)
        assert d["empty"] is True

    def test_frozen(self) -> None:
        info = JjChangeInfo(change_id="a", commit_id="b", description="c")
        import pytest

        with pytest.raises(AttributeError):
            info.change_id = "z"  # type: ignore[misc]


class TestJjBookmark:
    """Tests for JjBookmark."""

    def test_defaults(self) -> None:
        bm = JjBookmark(name="main")
        assert bm.name == "main"
        assert bm.change_id == ""
        assert bm.remote == ""

    def test_to_dict(self) -> None:
        bm = JjBookmark(name="feature", change_id="kxyz", remote="origin")
        d = bm.to_dict()
        assert d["name"] == "feature"
        assert d["remote"] == "origin"


class TestResultModels:
    """Tests for simple result dataclasses."""

    def test_describe_result(self) -> None:
        r = JjDescribeResult(success=True, message="wip")
        assert r.success is True
        assert r.to_dict()["message"] == "wip"

    def test_new_result(self) -> None:
        r = JjNewResult(success=True, change_id="kxyz")
        assert r.change_id == "kxyz"

    def test_commit_result(self) -> None:
        r = JjCommitResult(success=True, change_id="abcd")
        assert r.to_dict()["change_id"] == "abcd"

    def test_diff_result(self) -> None:
        r = JjDiffResult(output="--- a/file\n+++ b/file")
        assert "file" in r.output

    def test_diff_stat_result(self) -> None:
        r = JjDiffStatResult(
            output="1 file changed",
            files_changed=1,
            insertions=5,
            deletions=2,
        )
        assert r.files_changed == 1
        assert r.insertions == 5
        assert r.deletions == 2

    def test_log_result_to_dict(self) -> None:
        change = JjChangeInfo(change_id="a", commit_id="b", description="c")
        r = JjLogResult(output="log output", changes=(change,))
        d = r.to_dict()
        assert len(d["changes"]) == 1
        assert d["changes"][0]["change_id"] == "a"

    def test_status_result(self) -> None:
        r = JjStatusResult(
            output="Working copy",
            working_copy_change_id="kxyz",
            conflict=False,
        )
        assert r.working_copy_change_id == "kxyz"

    def test_show_result(self) -> None:
        r = JjShowResult(output="show output")
        assert r.to_dict()["output"] == "show output"

    def test_snapshot_result(self) -> None:
        r = JjSnapshotResult(operation_id="op123")
        assert r.operation_id == "op123"

    def test_restore_result(self) -> None:
        r = JjRestoreResult(success=True)
        assert r.to_dict()["success"] is True

    def test_clone_result(self) -> None:
        r = JjCloneResult(workspace_path="/tmp/ws")
        assert r.workspace_path == "/tmp/ws"

    def test_fetch_result(self) -> None:
        assert JjFetchResult().to_dict()["success"] is True

    def test_push_result(self) -> None:
        assert JjPushResult().to_dict()["success"] is True

    def test_squash_result(self) -> None:
        assert JjSquashResult().to_dict()["success"] is True

    def test_rebase_result(self) -> None:
        assert JjRebaseResult().to_dict()["success"] is True

    def test_bookmark_result(self) -> None:
        r = JjBookmarkResult(name="feature-x")
        assert r.name == "feature-x"

    def test_absorb_result(self) -> None:
        r = JjAbsorbResult(output="absorbed 3 hunks")
        assert "absorbed" in r.output
