"""Epic scope resolution against a **real** git repository (T026).

The unit suite (``tests/unit/critique/test_scope.py``) mocks
``AsyncGitRepository`` and therefore asserts against a commit log this repo
invented. That is enough to pin the attribution *logic* but not enough to
prove research R4 — "concatenate each attributed commit's own diff, never a
range diff" — because a mock can be made to answer either way. This module
builds a genuine git history with an unrelated commit **interleaved between**
two bead commits and asserts against real ``git diff`` output, which is the
only shape of test a range-diff regression cannot pass.

No agent, no model call, no CLI: :func:`resolve_epic_scope` is called
directly, since bead identity is the only thing under test here and the
command's ``bd`` lookup that supplies ``bead_ids`` is exercised in
``test_read_only.py``.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from maverick.critique.models import CritiqueScopeKind
from maverick.critique.scope import resolve_epic_scope

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# The unrelated commit's content. Asserted *absent* from the epic's diff, so
# it is deliberately a string that appears nowhere else in this module.
UNRELATED_MARKER = "value_from_an_unrelated_commit"

FIRST_MARKER = "value_added_by_bead_one"
SECOND_MARKER = "value_added_by_bead_two"


def _git(repo: Path, *args: str) -> str:
    """Run git in *repo* and return stdout.

    Plain subprocess rather than GitPython: this is a synchronous fixture
    building a fixture repository, not production code, and ``git commit -m``
    with an exact subject is the one thing the test's correctness hinges on.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _commit(repo: Path, *, subject: str, filename: str, content: str) -> None:
    """Write *filename* and commit it with exactly *subject*."""
    (repo / filename).write_text(f"{content}\n", encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", subject)


@pytest.fixture
def epic_repo(tmp_path: Path) -> Iterator[Path]:
    """A real git repo with two bead commits and one unrelated one between.

    History, oldest first::

        initial commit                          README.md
        bead(mv-1): first bead change           one.py
        chore: unrelated work by someone else   other.py   <- interleaved
        bead(mv-2): second bead change          two.py

    The interleaving is the whole point: a range diff (``mv-1^..mv-2``) would
    sweep ``other.py`` in, a per-commit concatenation cannot.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")

    _commit(repo, subject="initial commit", filename="README.md", content="# fixture")
    _commit(
        repo,
        subject="bead(mv-1): first bead change",
        filename="one.py",
        content=f'ONE = "{FIRST_MARKER}"',
    )
    _commit(
        repo,
        subject="chore: unrelated work by someone else",
        filename="other.py",
        content=f'OTHER = "{UNRELATED_MARKER}"',
    )
    _commit(
        repo,
        subject="bead(mv-2): second bead change",
        filename="two.py",
        content=f'TWO = "{SECOND_MARKER}"',
    )
    yield repo


class TestEpicScopeAgainstRealHistory:
    async def test_interleaved_unrelated_commit_is_not_attributed_to_the_epic(
        self,
        epic_repo: Path,
    ) -> None:
        """Research R4, proven against a real repository rather than a mock.

        ``resolve_epic_scope`` must concatenate each attributed commit's own
        diff. The alternative implementation — one range diff from the first
        attributed commit's parent to the last — would produce a superset
        containing ``other.py``, presenting a third party's unrelated work as
        this epic's for review. The interleaved ``chore:`` commit in the
        fixture is what makes the two implementations distinguishable; a
        mocked git log cannot tell them apart.
        """
        scope = await resolve_epic_scope(
            cwd=epic_repo,
            epic_id="mv-0",
            bead_ids=["mv-1", "mv-2"],
        )

        assert scope.kind is CritiqueScopeKind.EPIC
        assert scope.is_empty is False

        # Exactly the two bead commits, oldest first — the order they were made.
        assert [commit.subject for commit in scope.commits] == [
            "bead(mv-1): first bead change",
            "bead(mv-2): second bead change",
        ]
        assert [commit.bead_ids for commit in scope.commits] == [("mv-1",), ("mv-2",)]

        # The load-bearing assertion: `other.py` is absent.
        assert scope.paths == ("one.py", "two.py")

        # ...and absent from the diff body too, not merely from the file list.
        assert FIRST_MARKER in scope.diff_text
        assert SECOND_MARKER in scope.diff_text
        assert UNRELATED_MARKER not in scope.diff_text
        assert "other.py" not in scope.diff_text

        assert scope.summary == "epic mv-0 (2 commits)"

    async def test_attributed_shas_match_the_real_commits(self, epic_repo: Path) -> None:
        """The attributed shas are the actual bead commits, not neighbours."""
        expected = {
            _git(epic_repo, "rev-parse", "--short=7", rev).strip()
            for rev in ("HEAD~2", "HEAD")  # the two bead commits
        }

        scope = await resolve_epic_scope(cwd=epic_repo, epic_id="mv-0", bead_ids=["mv-1", "mv-2"])

        assert {commit.sha for commit in scope.commits} == expected
        unrelated = _git(epic_repo, "rev-parse", "--short=7", "HEAD~1").strip()
        assert unrelated not in {commit.sha for commit in scope.commits}

    async def test_diff_stat_covers_only_the_attributed_commits(
        self,
        epic_repo: Path,
    ) -> None:
        scope = await resolve_epic_scope(cwd=epic_repo, epic_id="mv-0", bead_ids=["mv-1", "mv-2"])

        assert "one.py" in scope.diff_stat
        assert "two.py" in scope.diff_stat
        assert "other.py" not in scope.diff_stat
        assert "2 file(s) changed across 2 commit(s)" in scope.diff_stat
        assert scope.diff_truncated is False


class TestEpicScopeAttributionBoundaries:
    async def test_an_epic_whose_beads_match_nothing_is_empty(self, epic_repo: Path) -> None:
        """FR-009: an empty scope is detected before any agent is built."""
        scope = await resolve_epic_scope(
            cwd=epic_repo,
            epic_id="mv-99",
            bead_ids=["mv-404", "mv-405"],
        )

        assert scope.is_empty is True
        assert scope.commits == ()
        assert scope.paths == ()
        assert scope.diff_text == ""
        assert scope.diff_stat == ""
        assert scope.summary == "epic mv-99 (0 commits)"

    async def test_a_bead_id_in_a_subject_but_not_in_bead_ids_is_excluded(
        self,
        epic_repo: Path,
    ) -> None:
        """Attribution is an intersection, not a "looks like a bead commit" test.

        ``bead(mv-2):`` is right there in the log, and the regex matches it.
        It is excluded solely because ``mv-2`` is not one of the epic's beads
        — otherwise ``--epic`` would review every epic's work at once.
        """
        scope = await resolve_epic_scope(cwd=epic_repo, epic_id="mv-0", bead_ids=["mv-1"])

        assert [commit.subject for commit in scope.commits] == ["bead(mv-1): first bead change"]
        assert scope.paths == ("one.py",)
        assert FIRST_MARKER in scope.diff_text
        assert SECOND_MARKER not in scope.diff_text
        assert UNRELATED_MARKER not in scope.diff_text
        # Singular, per the summary's plural rule.
        assert scope.summary == "epic mv-0 (1 commit)"

    async def test_a_root_bead_commit_resolves_against_the_empty_tree(
        self,
        tmp_path: Path,
    ) -> None:
        """The very first commit in a repository has no ``^`` to diff against.

        Without the empty-tree fallback it would be silently unreviewable —
        attributed by the log walk, then dropped as unreadable.
        """
        repo = tmp_path / "root-repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test User")
        _git(repo, "config", "commit.gpgsign", "false")
        _commit(
            repo,
            subject="bead(mv-1): the very first commit",
            filename="one.py",
            content=f'ONE = "{FIRST_MARKER}"',
        )

        scope = await resolve_epic_scope(cwd=repo, epic_id="mv-0", bead_ids=["mv-1"])

        assert scope.paths == ("one.py",)
        assert FIRST_MARKER in scope.diff_text
        assert scope.summary == "epic mv-0 (1 commit)"
