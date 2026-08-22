"""Unit tests for ``maverick.critique.scope``.

Contract: ``specs/058-standalone-code-review/spec.md`` (FR-009, FR-010) with
the rationale in ``research.md`` R3 (bead attribution by subject prefix),
R4 (per-commit diff concatenation, never a range diff), and R5 (truncation
must never blind the agent to *what* changed).

Every git read is mocked at ``maverick.critique.scope.AsyncGitRepository``;
the mocks return the real ``GitStatus`` / ``DiffStats`` / ``CommitInfo``
value objects so the tests pin the module against the actual read contract
rather than against a shape invented here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.critique.models import MAX_EMBEDDED_DIFF_CHARS, CritiqueScopeKind
from maverick.critique.scope import (
    EPIC_COMMIT_SEARCH_LIMIT,
    ScopeResolutionError,
    ScopeValidationError,
    resolve_diff_scope,
    resolve_epic_scope,
    resolve_paths_scope,
)
from maverick.exceptions import GitError
from maverick.git.repository import CommitInfo, DiffStats, GitStatus

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


def _stats(
    *,
    file_list: Sequence[str] = (),
    per_file: Mapping[str, tuple[int, int]] | None = None,
    insertions: int = 0,
    deletions: int = 0,
) -> DiffStats:
    """Build a real :class:`DiffStats` the way the git layer would."""
    files = tuple(file_list)
    return DiffStats(
        files_changed=len(files),
        insertions=insertions,
        deletions=deletions,
        file_list=files,
        per_file=dict(per_file or {}),
    )


def _status(*, untracked: Sequence[str] = (), unstaged: Sequence[str] = ()) -> GitStatus:
    """Build a real :class:`GitStatus`."""
    return GitStatus(
        staged=(),
        unstaged=tuple(unstaged),
        untracked=tuple(untracked),
        branch="058-standalone-code-review",
        ahead=0,
        behind=0,
    )


def _commit(sha: str, message: str) -> CommitInfo:
    """Build a real :class:`CommitInfo`; ``short_sha`` is the first 7 chars."""
    return CommitInfo(
        sha=sha,
        short_sha=sha[:7],
        message=message,
        author="Maverick",
        date="2026-08-22T18:04:11+00:00",
    )


def _repo(
    *,
    diff_stats: object = None,
    diff: object = None,
    status: object = None,
    log: object = None,
) -> AsyncMock:
    """An ``AsyncGitRepository`` double.

    Each argument becomes the method's ``return_value`` unless it is callable
    or an exception, in which case it becomes the ``side_effect`` — that is
    what lets the epic tests answer differently per SHA.
    """
    repo = AsyncMock()
    for name, value in (
        ("diff_stats", diff_stats),
        ("diff", diff),
        ("status", status),
        ("log", log),
    ):
        method = AsyncMock()
        if isinstance(value, BaseException) or callable(value):
            method.side_effect = value
        else:
            method.return_value = value
        setattr(repo, name, method)
    return repo


@pytest.fixture
def git_repo_cls() -> Iterator[MagicMock]:
    """Yield the patched ``AsyncGitRepository`` class object."""
    with patch("maverick.critique.scope.AsyncGitRepository") as cls:
        yield cls


# ---------------------------------------------------------------------------
# resolve_diff_scope
# ---------------------------------------------------------------------------


class TestResolveDiffScope:
    async def test_changed_files_union_includes_untracked(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """Untracked files join the tracked-modified set.

        A newly added file produces no diff hunks against *base*, but it is
        exactly what a pre-push review most needs to see — so the module
        merges ``diff_stats.file_list`` with ``status.untracked``.
        """
        git_repo_cls.return_value = _repo(
            diff_stats=_stats(file_list=("src/b.py", "src/a.py")),
            diff="diff --git a/src/a.py b/src/a.py\n",
            status=_status(untracked=("src/brand_new.py",)),
        )

        scope = await resolve_diff_scope(cwd=temp_dir, base="main")

        assert scope.kind is CritiqueScopeKind.DIFF
        assert scope.paths == ("src/a.py", "src/b.py", "src/brand_new.py")
        assert scope.is_empty is False

    async def test_untracked_only_change_is_not_empty(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """A working copy whose only change is a new file still has a scope."""
        git_repo_cls.return_value = _repo(
            diff_stats=_stats(),
            diff="",
            status=_status(untracked=("src/brand_new.py",)),
        )

        scope = await resolve_diff_scope(cwd=temp_dir, base="main")

        assert scope.paths == ("src/brand_new.py",)
        assert scope.diff_text == ""
        assert scope.is_empty is False

    async def test_base_is_threaded_to_the_git_reads(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """``base`` reaches both git reads and the summary verbatim."""
        repo = _repo(diff_stats=_stats(file_list=("a.py",)), diff="d", status=_status())
        git_repo_cls.return_value = repo

        scope = await resolve_diff_scope(cwd=temp_dir, base="origin/develop")

        git_repo_cls.assert_called_once_with(temp_dir)
        repo.diff_stats.assert_awaited_once_with("origin/develop")
        repo.diff.assert_awaited_once_with("origin/develop")
        assert scope.base == "origin/develop"
        assert scope.summary == "working copy vs origin/develop"

    async def test_empty_diff_and_no_untracked_is_empty(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """Nothing changed → ``is_empty``, checked before any agent is built."""
        git_repo_cls.return_value = _repo(diff_stats=_stats(), diff="", status=_status())

        scope = await resolve_diff_scope(cwd=temp_dir, base="main")

        assert scope.paths == ()
        assert scope.diff_text == ""
        assert scope.diff_truncated is False
        assert scope.is_empty is True

    async def test_diff_at_the_limit_is_not_truncated(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """The bound is inclusive — exactly ``MAX_EMBEDDED_DIFF_CHARS`` fits."""
        git_repo_cls.return_value = _repo(
            diff_stats=_stats(file_list=("a.py",)),
            diff="x" * MAX_EMBEDDED_DIFF_CHARS,
            status=_status(),
        )

        scope = await resolve_diff_scope(cwd=temp_dir, base="main")

        assert scope.diff_truncated is False
        assert len(scope.diff_text) == MAX_EMBEDDED_DIFF_CHARS

    async def test_truncation_keeps_the_complete_file_list(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """Truncation bounds the diff but never the file list (research R5).

        The embedded diff is an aid; the agent reads the working directory
        for the rest. Losing ``paths`` would blind it to *what* changed,
        which is the one thing truncation must never do.
        """
        files = tuple(f"src/mod_{i:03d}.py" for i in range(40))
        git_repo_cls.return_value = _repo(
            diff_stats=_stats(file_list=files),
            diff="y" * (MAX_EMBEDDED_DIFF_CHARS + 5_000),
            status=_status(untracked=("src/untracked.py",)),
        )

        scope = await resolve_diff_scope(cwd=temp_dir, base="main")

        assert scope.diff_truncated is True
        assert len(scope.diff_text) == MAX_EMBEDDED_DIFF_CHARS
        assert scope.diff_text == "y" * MAX_EMBEDDED_DIFF_CHARS
        assert scope.paths == tuple(sorted({*files, "src/untracked.py"}))
        assert len(scope.paths) == len(files) + 1

    @pytest.mark.parametrize("failing", ["diff_stats", "diff", "status"])
    async def test_git_read_failure_raises_scope_resolution_error(
        self, git_repo_cls: MagicMock, temp_dir: Path, failing: str
    ) -> None:
        """Any failing git read is one kind of failure to the caller."""
        repo = _repo(diff_stats=_stats(), diff="", status=_status())
        getattr(repo, failing).side_effect = GitError("bad revision 'main'")
        git_repo_cls.return_value = repo

        with pytest.raises(ScopeResolutionError, match="could not read the repository"):
            await resolve_diff_scope(cwd=temp_dir, base="main")

    async def test_diff_stat_renders_from_structured_stats(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """The ``--stat`` summary is built from ``DiffStats``, not a re-read."""
        repo = _repo(
            diff_stats=_stats(
                file_list=("src/a.py", "src/long_name.py"),
                per_file={"src/a.py": (3, 1), "src/long_name.py": (10, 0)},
                insertions=13,
                deletions=1,
            ),
            diff="d",
            status=_status(),
        )
        git_repo_cls.return_value = repo

        scope = await resolve_diff_scope(cwd=temp_dir, base="main")

        lines = scope.diff_stat.splitlines()
        assert lines[0] == f" {'src/a.py'.ljust(len('src/long_name.py'))} |     4 +3 -1"
        assert lines[1] == " src/long_name.py |    10 +10 -0"
        assert lines[2] == " 2 file(s) changed, 13 insertion(s), 1 deletion(s)"
        # One read serves both the file list and the summary (Guardrail 5).
        repo.diff_stats.assert_awaited_once()

    async def test_diff_stat_is_empty_when_nothing_changed(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        git_repo_cls.return_value = _repo(diff_stats=_stats(), diff="", status=_status())

        scope = await resolve_diff_scope(cwd=temp_dir, base="main")

        assert scope.diff_stat == ""


# ---------------------------------------------------------------------------
# resolve_epic_scope
# ---------------------------------------------------------------------------


def _epic_repo(
    commits: Sequence[CommitInfo],
    *,
    per_commit: Mapping[str, tuple[DiffStats, str]],
    log_error: BaseException | None = None,
) -> AsyncMock:
    """Repo double whose per-commit reads are keyed by full SHA.

    ``resolve_epic_scope`` reads ``diff_stats("<sha>^..<sha>")`` and
    ``diff("<sha>^", "<sha>")``; a SHA missing from *per_commit* raises, which
    is how the root-commit case is modelled.
    """

    async def _diff_stats(rev: str) -> DiffStats:
        sha = rev.split("^", 1)[0]
        if sha not in per_commit:
            raise GitError(f"unknown revision {rev}")
        return per_commit[sha][0]

    async def _diff(base: str, head: str | None = None, staged: bool = False) -> str:
        sha = head or base.split("^", 1)[0]
        if sha not in per_commit:
            raise GitError(f"unknown revision {base}")
        return per_commit[sha][1]

    return _repo(
        diff_stats=_diff_stats,
        diff=_diff,
        log=log_error if log_error is not None else list(commits),
    )


class TestResolveEpicScope:
    async def test_attributes_commits_by_bead_prefix_intersection(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """Attribution is the subject prefix ∩ the epic's bead ids (R3)."""
        commits = [
            _commit("bbbbbbbbbb", "bead(mv-2): second"),
            _commit("aaaaaaaaaa", "bead(mv-1): first"),
            _commit("cccccccccc", "bead(mv-99): someone else's bead"),
            _commit("dddddddddd", "chore: not a bead commit at all"),
        ]
        repo = _epic_repo(
            commits,
            per_commit={
                "aaaaaaaaaa": (_stats(file_list=("a.py",), insertions=2), "DIFF-A"),
                "bbbbbbbbbb": (_stats(file_list=("b.py",), insertions=3), "DIFF-B"),
                "cccccccccc": (_stats(file_list=("other.py",)), "DIFF-OTHER"),
                "dddddddddd": (_stats(file_list=("chore.py",)), "DIFF-CHORE"),
            },
        )
        git_repo_cls.return_value = repo

        scope = await resolve_epic_scope(
            cwd=temp_dir, epic_id="mv-epic", bead_ids=["mv-1", "mv-2"]
        )

        git_repo_cls.assert_called_once_with(temp_dir)
        repo.log.assert_awaited_once_with(n=EPIC_COMMIT_SEARCH_LIMIT)
        assert scope.kind is CritiqueScopeKind.EPIC
        assert scope.epic_id == "mv-epic"
        assert [c.sha for c in scope.commits] == ["aaaaaaa", "bbbbbbb"]
        assert scope.paths == ("a.py", "b.py")
        assert "DIFF-OTHER" not in scope.diff_text
        assert "DIFF-CHORE" not in scope.diff_text

    async def test_interleaved_unrelated_commit_is_excluded(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """An unrelated commit *between* the epic's own is excluded (R4).

        This is the assertion that makes research R4's choice load-bearing.
        The rejected option — one range diff ``oldest^..newest`` — would
        silently swallow ``unrelated.py`` here and present another author's
        work as this epic's. Concatenating each attributed commit's own diff
        is what keeps the interleaved commit out.
        """
        commits = [
            _commit("2222222222", "bead(mv-2): epic work, later"),
            _commit("9999999999", "fix: an unrelated commit by someone else"),
            _commit("1111111111", "bead(mv-1): epic work, earlier"),
        ]
        repo = _epic_repo(
            commits,
            per_commit={
                "1111111111": (_stats(file_list=("epic_early.py",)), "EPIC-EARLY-DIFF"),
                "9999999999": (_stats(file_list=("unrelated.py",)), "UNRELATED-DIFF"),
                "2222222222": (_stats(file_list=("epic_late.py",)), "EPIC-LATE-DIFF"),
            },
        )
        git_repo_cls.return_value = repo

        scope = await resolve_epic_scope(
            cwd=temp_dir, epic_id="mv-epic", bead_ids=["mv-1", "mv-2"]
        )

        assert scope.paths == ("epic_early.py", "epic_late.py")
        assert "unrelated.py" not in scope.paths
        assert "UNRELATED-DIFF" not in scope.diff_text
        assert "UNRELATED-DIFF" not in scope.diff_stat
        assert [c.sha for c in scope.commits] == ["1111111", "2222222"]
        assert "EPIC-EARLY-DIFF" in scope.diff_text
        assert "EPIC-LATE-DIFF" in scope.diff_text
        # The unrelated commit's diff is never even read.
        read_revs = {call.args[0] for call in repo.diff.await_args_list}
        assert read_revs == {"1111111111^", "2222222222^"}

    async def test_commits_are_processed_oldest_first(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """``log`` is newest-first; the scope reads and reports oldest-first."""
        commits = [
            _commit("3333333333", "bead(mv-3): third"),
            _commit("2222222222", "bead(mv-2): second"),
            _commit("1111111111", "bead(mv-1): first"),
        ]
        repo = _epic_repo(
            commits,
            per_commit={
                "1111111111": (_stats(file_list=("one.py",)), "ONE"),
                "2222222222": (_stats(file_list=("two.py",)), "TWO"),
                "3333333333": (_stats(file_list=("three.py",)), "THREE"),
            },
        )
        git_repo_cls.return_value = repo

        scope = await resolve_epic_scope(
            cwd=temp_dir, epic_id="mv-epic", bead_ids=["mv-1", "mv-2", "mv-3"]
        )

        assert [c.sha for c in scope.commits] == ["1111111", "2222222", "3333333"]
        assert [call.args[0] for call in repo.diff.await_args_list] == [
            "1111111111^",
            "2222222222^",
            "3333333333^",
        ]
        assert scope.diff_text.index("ONE") < scope.diff_text.index("TWO")
        assert scope.diff_text.index("TWO") < scope.diff_text.index("THREE")

    async def test_summary_is_plural_for_many_commits(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        commits = [
            _commit("2222222222", "bead(mv-2): second"),
            _commit("1111111111", "bead(mv-1): first"),
        ]
        git_repo_cls.return_value = _epic_repo(
            commits,
            per_commit={
                "1111111111": (_stats(file_list=("one.py",)), "ONE"),
                "2222222222": (_stats(file_list=("two.py",)), "TWO"),
            },
        )

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1", "mv-2"])

        assert scope.summary == "epic mv-42 (2 commits)"

    async def test_summary_is_singular_for_one_commit(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        git_repo_cls.return_value = _epic_repo(
            [_commit("1111111111", "bead(mv-1): only")],
            per_commit={"1111111111": (_stats(file_list=("one.py",)), "ONE")},
        )

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1"])

        assert scope.summary == "epic mv-42 (1 commit)"

    async def test_zero_matching_commits_is_empty(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """An epic whose beads never committed costs zero model calls."""
        git_repo_cls.return_value = _epic_repo(
            [_commit("9999999999", "bead(mv-99): a different epic")],
            per_commit={"9999999999": (_stats(file_list=("other.py",)), "OTHER")},
        )

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1"])

        assert scope.commits == ()
        assert scope.paths == ()
        assert scope.diff_text == ""
        assert scope.diff_stat == ""
        assert scope.is_empty is True
        assert scope.summary == "epic mv-42 (0 commits)"

    async def test_empty_log_is_empty_scope(self, git_repo_cls: MagicMock, temp_dir: Path) -> None:
        git_repo_cls.return_value = _epic_repo([], per_commit={})

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1"])

        assert scope.is_empty is True
        assert scope.summary == "epic mv-42 (0 commits)"

    async def test_scoped_commit_carries_only_matching_bead_ids(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """``bead_ids`` is the intersection, so attribution is verifiable.

        A squashed description can name several beads; only the ones this
        epic owns may be claimed.
        """
        squashed = _commit("1111111111", "bead(mv-1): mine\nbead(mv-99): not mine")
        git_repo_cls.return_value = _epic_repo(
            [squashed],
            per_commit={"1111111111": (_stats(file_list=("one.py",)), "ONE")},
        )

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1"])

        assert len(scope.commits) == 1
        assert scope.commits[0].bead_ids == ("mv-1",)

    async def test_unreadable_commit_drops_out_of_the_attribution_entirely(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """A commit whose content nothing could read is not claimed as reviewed.

        Attributing it while none of its content reached ``diff_text``,
        ``paths``, or the stat totals would present a partial review as a
        complete one — the same failure the truncation path (research R5) is
        careful to report rather than hide. The count, the summary, and
        ``commits`` all have to agree with what the reviewer actually saw.
        """
        commits = [
            _commit("2222222222", "bead(mv-2): second"),
            _commit("1111111111", "bead(mv-1): unreadable"),
        ]
        git_repo_cls.return_value = _epic_repo(
            commits,
            # "1111111111" is absent under BOTH its parent and the empty-tree
            # fallback → every read for it raises.
            per_commit={"2222222222": (_stats(file_list=("two.py",), insertions=4), "TWO")},
        )

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1", "mv-2"])

        assert scope.is_empty is False
        assert scope.paths == ("two.py",)
        assert "TWO" in scope.diff_text
        assert [c.sha for c in scope.commits] == ["2222222"]
        assert scope.summary == "epic mv-42 (1 commit)"
        assert scope.diff_stat.splitlines()[-1] == (
            " 1 file(s) changed across 1 commit(s), 4 insertion(s), 0 deletion(s)"
        )

    async def test_root_commit_falls_back_to_the_empty_tree(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """A root commit has no ``^``; it is still reviewable via the empty tree.

        Otherwise the first commit in a repository would be permanently
        invisible to an epic review.
        """
        empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        repo = _epic_repo([_commit("1111111111", "bead(mv-1): root")], per_commit={})

        async def _diff_stats(rev: str) -> DiffStats:
            if rev == f"{empty_tree}..1111111111":
                return _stats(file_list=("root.py",), insertions=9)
            raise GitError("unknown revision")

        async def _diff(base: str, head: str) -> str:
            if base == empty_tree and head == "1111111111":
                return "ROOT"
            raise GitError("unknown revision")

        repo.diff_stats = AsyncMock(side_effect=_diff_stats)
        repo.diff = AsyncMock(side_effect=_diff)
        git_repo_cls.return_value = repo

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1"])

        assert [c.sha for c in scope.commits] == ["1111111"]
        assert scope.paths == ("root.py",)
        assert "ROOT" in scope.diff_text

    async def test_log_failure_raises_scope_resolution_error(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        git_repo_cls.return_value = _epic_repo(
            [], per_commit={}, log_error=GitError("not a git repository")
        )

        with pytest.raises(ScopeResolutionError, match="could not read the commit log"):
            await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1"])

    async def test_enormous_epic_diff_is_truncated_but_keeps_paths(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        """R5 applies to the epic scope too."""
        git_repo_cls.return_value = _epic_repo(
            [_commit("1111111111", "bead(mv-1): a huge commit")],
            per_commit={
                "1111111111": (
                    _stats(file_list=("big.py", "also_big.py")),
                    "z" * (MAX_EMBEDDED_DIFF_CHARS + 1),
                )
            },
        )

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1"])

        assert scope.diff_truncated is True
        assert len(scope.diff_text) == MAX_EMBEDDED_DIFF_CHARS
        assert scope.paths == ("also_big.py", "big.py")

    async def test_diff_stat_summarizes_across_commits(
        self, git_repo_cls: MagicMock, temp_dir: Path
    ) -> None:
        commits = [
            _commit("2222222222", "bead(mv-2): second"),
            _commit("1111111111", "bead(mv-1): first"),
        ]
        git_repo_cls.return_value = _epic_repo(
            commits,
            per_commit={
                "1111111111": (
                    _stats(
                        file_list=("one.py",),
                        per_file={"one.py": (5, 1)},
                        insertions=5,
                        deletions=1,
                    ),
                    "ONE",
                ),
                "2222222222": (
                    _stats(
                        file_list=("two.py",),
                        per_file={"two.py": (2, 3)},
                        insertions=2,
                        deletions=3,
                    ),
                    "TWO",
                ),
            },
        )

        scope = await resolve_epic_scope(cwd=temp_dir, epic_id="mv-42", bead_ids=["mv-1", "mv-2"])

        assert scope.diff_stat.splitlines()[-1] == (
            " 2 file(s) changed across 2 commit(s), 7 insertion(s), 4 deletion(s)"
        )


# ---------------------------------------------------------------------------
# resolve_paths_scope (synchronous — no git reads at all)
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_root(temp_dir: Path) -> Path:
    """A checkout root with a small tree, plus a sibling *outside* it."""
    root = temp_dir / "checkout"
    (root / "src" / "nested").mkdir(parents=True)
    (root / "src" / "a.py").write_text("a\n")
    (root / "src" / "b.py").write_text("b\n")
    (root / "src" / "nested" / "c.py").write_text("c\n")
    (temp_dir / "outside.txt").write_text("outside\n")
    return root


class TestResolvePathsScope:
    def test_nonexistent_path_raises_naming_the_path(self, repo_root: Path) -> None:
        with pytest.raises(ScopeValidationError, match="src/missing.py"):
            resolve_paths_scope(cwd=repo_root, paths=["src/missing.py"])

    def test_absolute_path_outside_the_repository_is_rejected(self, repo_root: Path) -> None:
        outside = repo_root.parent / "outside.txt"

        with pytest.raises(ScopeValidationError, match="outside the repository"):
            resolve_paths_scope(cwd=repo_root, paths=[str(outside)])

    def test_relative_path_escaping_the_repository_is_rejected(self, repo_root: Path) -> None:
        with pytest.raises(ScopeValidationError, match="outside the repository"):
            resolve_paths_scope(cwd=repo_root, paths=["../outside.txt"])

    def test_relative_paths_are_kept_repo_relative(self, repo_root: Path) -> None:
        scope = resolve_paths_scope(cwd=repo_root, paths=["src/a.py", "src/nested/c.py"])

        assert scope.kind is CritiqueScopeKind.PATHS
        assert scope.paths == ("src/a.py", "src/nested/c.py")

    def test_absolute_paths_inside_the_repository_normalize_to_relative(
        self, repo_root: Path
    ) -> None:
        scope = resolve_paths_scope(cwd=repo_root, paths=[str(repo_root / "src" / "a.py")])

        assert scope.paths == ("src/a.py",)

    def test_the_repository_root_itself_normalizes_to_dot(self, repo_root: Path) -> None:
        scope = resolve_paths_scope(cwd=repo_root, paths=[str(repo_root)])

        assert scope.paths == (".",)

    def test_duplicates_collapse_and_output_is_sorted(self, repo_root: Path) -> None:
        """Same file named three ways collapses to one sorted entry."""
        scope = resolve_paths_scope(
            cwd=repo_root,
            paths=[
                "src/b.py",
                "src/a.py",
                "src/b.py",
                str(repo_root / "src" / "b.py"),
                "./src/a.py",
            ],
        )

        assert scope.paths == ("src/a.py", "src/b.py")

    def test_directories_are_accepted_as_named_without_expansion(self, repo_root: Path) -> None:
        """A directory travels as itself — the agent reads it from disk."""
        scope = resolve_paths_scope(cwd=repo_root, paths=["src"])

        assert scope.paths == ("src",)
        assert "src/a.py" not in scope.paths

    def test_summary_lists_the_normalized_paths(self, repo_root: Path) -> None:
        scope = resolve_paths_scope(cwd=repo_root, paths=["src/b.py", "src/a.py"])

        assert scope.summary == "paths: src/a.py, src/b.py"

    def test_no_diff_is_computed_but_the_scope_is_not_empty(self, repo_root: Path) -> None:
        """This scope asks about present state, so emptiness rides on ``paths``."""
        scope = resolve_paths_scope(cwd=repo_root, paths=["src/a.py"])

        assert scope.diff_text == ""
        assert scope.diff_stat == ""
        assert scope.diff_truncated is False
        assert scope.base is None
        assert scope.epic_id is None
        assert scope.commits == ()
        assert scope.is_empty is False

    def test_no_paths_at_all_is_an_empty_scope(self, repo_root: Path) -> None:
        scope = resolve_paths_scope(cwd=repo_root, paths=[])

        assert scope.paths == ()
        assert scope.is_empty is True
