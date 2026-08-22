"""SC-002 proof: ``maverick critique`` never mutates the repository (T030).

FR-012 says the command is read-only "with respect to the repository", and
the only writes it is permitted on any path are the two artifact files under
``.maverick/runs/<run-id>/``. That is a claim about *every* invocation —
success, refusal, and failure alike — so this module runs the command across
all three scopes, both output modes, and the failure paths, and after each
one compares four independent before/after snapshots:

* ``git log --format=%H %B`` — no commit created, amended, reworded, or moved.
* ``git status --porcelain`` — no tracked content changed, nothing staged.
* a SHA-256 of every tracked file's bytes — content, not just git's opinion
  of it.
* the working-tree file set excluding ``.maverick/runs/**`` — nothing
  created or deleted outside the one permitted directory.

The last snapshot is deliberately paired with a *positive* assertion rather
than left as an exclusion: the new paths must be exactly one run directory
holding exactly ``critique-report.json`` and ``critique-report.md``. An
exclusion alone would let the command write anything at all under
``.maverick/runs`` and still pass.

The agent layer is stubbed (no model calls) following
``tests/unit/critique/test_runner.py``'s ``CritiqueSquadron`` fake — the
guarantee under test is about the filesystem and the commit graph, and a
real reviewer would only add latency and nondeterminism to it. ``bd`` is not
assumed to be installed: the ``--epic`` scope patches the command's own
``bd_ready_reason`` preflight and ``BeadClient.children``, which is exactly
the seam the command owns (see ``critique.py``'s ``_resolve_scope``).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from click.testing import CliRunner

from maverick.beads.client import BeadClient
from maverick.cli.commands.critique import critique
from maverick.config import MaverickConfig
from maverick.payloads import ReviewFindingPayload, SubmitReviewPayload

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: The bead the fixture's epic owns, and the id in its commit subject.
EPIC_ID = "mv-0040"
BEAD_ID = "mv-0041"

#: Artifact filenames the command is permitted to create, and nothing else.
PERMITTED_ARTIFACTS = frozenset({"critique-report.json", "critique-report.md"})

RUN_DIR_PREFIX = ".maverick/runs/"


# ---------------------------------------------------------------------------
# Fixture repository
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Path]:
    """A real git repo on ``main`` with a bead commit and dirty working copy.

    The uncommitted edit plus the untracked file are what give the default
    ``--base main`` scope something to review; the ``bead(...)`` commit is
    what gives ``--epic`` something to attribute. ``.gitignore`` carries the exact
    entry ``maverick init`` writes (``init/__init__.py``'s
    ``_MAVERICK_GITIGNORE_ENTRIES``), so the artifact directory the command
    is allowed to write never perturbs ``git status --porcelain`` — as it
    would not in any repository maverick has been initialized in.
    """
    root = (tmp_path / "checkout").resolve()
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _git(root, "config", "commit.gpgsign", "false")

    (root / ".gitignore").write_text(".maverick/runs/\n", encoding="utf-8")
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial commit")

    (root / "src" / "feature.py").write_text("def feature() -> int:\n    return 2\n", "utf-8")
    _git(root, "add", "src/feature.py")
    _git(root, "commit", "-m", f"bead({BEAD_ID}): add the feature")

    # Uncommitted state: one tracked edit and one untracked file, so the
    # default diff scope is non-empty and `git status --porcelain` has real
    # content to be compared against rather than an empty string.
    (root / "src" / "app.py").write_text("VALUE = 1\nEXTRA = 3\n", encoding="utf-8")
    (root / "scratch.txt").write_text("uncommitted and untracked\n", encoding="utf-8")

    yield root


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepoSnapshot:
    """Everything SC-002 promises stays put."""

    log: str
    status: str
    tracked_hashes: dict[str, str]
    files: frozenset[str]

    @property
    def stable_files(self) -> frozenset[str]:
        """The file set minus the one directory writes are permitted in."""
        return frozenset(p for p in self.files if not p.startswith(RUN_DIR_PREFIX))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(repo: Path) -> RepoSnapshot:
    """Capture the four independent views of repository state.

    ``.git/`` is excluded from the file walk on purpose: reading the
    repository at all (``git status``, GitPython's diff) legitimately
    refreshes git's own index stat cache, which is not repository *state* in
    the sense SC-002 means. The commit graph and the tracked content are
    snapshotted directly instead, which is the stronger check anyway.
    """
    tracked = [line for line in _git(repo, "ls-files").splitlines() if line]
    files = {
        path.relative_to(repo).as_posix()
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(repo).parts
    }
    return RepoSnapshot(
        log=_git(repo, "log", "--format=%H %B"),
        status=_git(repo, "status", "--porcelain"),
        tracked_hashes={name: _sha256(repo / name) for name in tracked},
        files=frozenset(files),
    )


def _assert_unchanged(
    before: RepoSnapshot,
    after: RepoSnapshot,
    *,
    artifacts_expected: bool,
) -> None:
    """Assert the repository is byte-identical apart from permitted artifacts.

    Args:
        before: Snapshot taken immediately before the invocation.
        after: Snapshot taken immediately after it returned.
        artifacts_expected: Whether the invocation got far enough to persist
            a report. A refusal (bad scope, missing epic) never does, and
            "wrote nothing at all" is asserted rather than tolerated.
    """
    assert after.log == before.log, "the commit graph changed"
    assert after.status == before.status, "the working-tree/index status changed"
    assert after.tracked_hashes == before.tracked_hashes, "tracked file content changed"
    assert after.stable_files == before.stable_files, "files appeared or vanished"
    assert not (before.files - after.files), "the command deleted a file"

    new_paths = after.files - before.files
    if not artifacts_expected:
        assert new_paths == frozenset(), f"a refusing invocation wrote {sorted(new_paths)}"
        return

    # Positive form: the new paths are exactly one run directory's report pair.
    assert new_paths, "the invocation persisted no artifact"
    run_dirs = {path[len(RUN_DIR_PREFIX) :].split("/")[0] for path in new_paths}
    assert len(run_dirs) == 1, f"more than one run directory written: {sorted(run_dirs)}"
    run_id = next(iter(run_dirs))
    assert new_paths == {f"{RUN_DIR_PREFIX}{run_id}/{name}" for name in PERMITTED_ARTIFACTS}


# ---------------------------------------------------------------------------
# Agent stub
# ---------------------------------------------------------------------------


class _FakeReviewer:
    """One lens with a canned payload — the shape ``test_runner.py`` uses."""

    def __init__(self, *, lens: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self._payload = SubmitReviewPayload(
            approved=False,
            findings=(
                ReviewFindingPayload(
                    severity="major",
                    issue=f"{lens} lens says something",
                    file="src/app.py",
                    line=2,
                    reviewer=lens,  # type: ignore[arg-type]
                ),
            ),
        )

    async def critique(self, **kwargs: Any) -> SubmitReviewPayload:
        self.calls.append(kwargs)
        return self._payload


@pytest.fixture
def stub_squadron(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``CritiqueSquadron`` so no model is ever contacted."""
    record: dict[str, Any] = {"entered": 0}

    class _FakeSquadron:
        correctness_reviewer = _FakeReviewer(lens="correctness")
        completeness_reviewer = _FakeReviewer(lens="completeness")

        def __init__(self, **kwargs: Any) -> None:
            record["kwargs"] = kwargs

        async def __aenter__(self) -> _FakeSquadron:
            record["entered"] += 1
            return self

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    monkeypatch.setattr("maverick.critique.runner.CritiqueSquadron", _FakeSquadron)
    return record


@pytest.fixture
def stub_beads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the ``--epic`` preflight pass without a real ``bd`` on PATH.

    ``bd`` is not installed in every environment this suite runs in, and the
    bead lookup is not what SC-002 is about — the command's own seam is
    patched, not the ledger beneath it.
    """
    monkeypatch.setattr("maverick.cli.commands.critique.bd_ready_reason", lambda _cwd: None)

    async def _children(self: BeadClient, parent_id: str) -> list[Any]:
        if parent_id != EPIC_ID:
            return []
        return [type("_Bead", (), {"id": BEAD_ID})()]

    monkeypatch.setattr(BeadClient, "children", _children)


# ---------------------------------------------------------------------------
# Invocation helper
# ---------------------------------------------------------------------------


def _invoke(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Any:
    """Run ``critique`` in *repo* with a default config, snapshot-neutral.

    ``obj`` carries a constructed :class:`MaverickConfig` so the command
    never calls ``load_config()``, which would read whatever
    ``~/.config/maverick/config.yaml`` the host happens to have.
    """
    monkeypatch.chdir(repo)
    runner = CliRunner()
    return runner.invoke(critique, list(args), obj={"config": MaverickConfig()})


def _run_and_assert(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    artifacts_expected: bool,
) -> Any:
    before = _snapshot(repo)
    result = _invoke(repo, monkeypatch, *args)
    after = _snapshot(repo)
    _assert_unchanged(before, after, artifacts_expected=artifacts_expected)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("stub_squadron")
class TestSuccessfulScopesAreReadOnly:
    def test_default_diff_scope_with_uncommitted_changes(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        result = _run_and_assert(repo, monkeypatch, artifacts_expected=True)

        assert result.exit_code == 0, result.output
        assert "working copy vs main" in result.stdout

    def test_epic_scope(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_beads: None,
    ) -> None:
        result = _run_and_assert(repo, monkeypatch, "--epic", EPIC_ID, artifacts_expected=True)

        assert result.exit_code == 0, result.output
        assert f"epic {EPIC_ID} (1 commit)" in result.stdout

    def test_paths_scope(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _run_and_assert(repo, monkeypatch, "src", artifacts_expected=True)

        assert result.exit_code == 0, result.output
        assert "paths: src" in result.stdout

    def test_diff_scope_json(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _run_and_assert(repo, monkeypatch, "--json", artifacts_expected=True)

        assert result.exit_code == 0, result.output
        document = json.loads(result.stdout)
        assert document["ok"] is True
        assert document["result"]["scope"]["kind"] == "diff"

    def test_paths_scope_json(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _run_and_assert(
            repo, monkeypatch, "src/app.py", "--json", artifacts_expected=True
        )

        assert result.exit_code == 0, result.output
        document = json.loads(result.stdout)
        assert document["ok"] is True
        assert document["result"]["scope"]["paths"] == ["src/app.py"]

    def test_epic_scope_json(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_beads: None,
    ) -> None:
        result = _run_and_assert(
            repo, monkeypatch, "--epic", EPIC_ID, "--json", artifacts_expected=True
        )

        assert result.exit_code == 0, result.output
        document = json.loads(result.stdout)
        assert document["result"]["scope"]["epic_id"] == EPIC_ID


@pytest.mark.usefixtures("stub_squadron")
class TestFailurePathsAreReadOnly:
    """SC-002 covers "every failure path", which is the harder half.

    A command that cleans up after itself on success but leaves a partial
    write behind on refusal is not read-only; each of these asserts the
    repository gained *nothing at all*.
    """

    def test_nonexistent_epic(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_beads: None,
    ) -> None:
        result = _run_and_assert(repo, monkeypatch, "--epic", "mv-9999", artifacts_expected=False)

        assert result.exit_code == 1
        assert "mv-9999" in result.stderr

    def test_nonexistent_epic_json(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_beads: None,
    ) -> None:
        result = _run_and_assert(
            repo, monkeypatch, "--epic", "mv-9999", "--json", artifacts_expected=False
        )

        assert result.exit_code == 1
        document = json.loads(result.stdout)
        assert document["ok"] is False
        assert document["error"]["kind"] == "not-found"

    def test_nonexistent_path(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _run_and_assert(repo, monkeypatch, "does/not/exist.py", artifacts_expected=False)

        assert result.exit_code == 1
        assert "does not exist" in result.stderr

    def test_nonexistent_path_json(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _run_and_assert(
            repo, monkeypatch, "does/not/exist.py", "--json", artifacts_expected=False
        )

        assert result.exit_code == 1
        document = json.loads(result.stdout)
        assert document["error"]["kind"] == "validation"

    def test_conflicting_scopes(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """FR-004: an ambiguous invocation is refused, and refuses cleanly."""
        result = _run_and_assert(
            repo,
            monkeypatch,
            "--epic",
            EPIC_ID,
            "--base",
            "main",
            artifacts_expected=False,
        )

        assert result.exit_code == 1
        assert "select different scopes" in result.stderr

    def test_conflicting_scopes_json(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        result = _run_and_assert(
            repo,
            monkeypatch,
            "--epic",
            EPIC_ID,
            "src",
            "--json",
            artifacts_expected=False,
        )

        assert result.exit_code == 1
        document = json.loads(result.stdout)
        assert document["error"]["kind"] == "validation"

    def test_unreadable_base_revision(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A base that does not resolve is a VCS failure, still read-only."""
        result = _run_and_assert(
            repo, monkeypatch, "--base", "no-such-ref", "--json", artifacts_expected=False
        )

        assert result.exit_code == 1
        document = json.loads(result.stdout)
        assert document["error"]["kind"] == "vcs"


class TestNoModelCallWithoutASquadron:
    def test_every_scope_ran_through_the_stub(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_squadron: dict[str, Any],
    ) -> None:
        """Guard the guard: the stub really is the thing being exercised.

        Every read-only assertion above would also pass against a command
        that silently did nothing, so this pins that the reviewed path was
        actually taken — and that it was taken through the fake squadron
        rather than a real one, which is what keeps this suite offline.
        """
        result = _invoke(repo, monkeypatch)

        assert result.exit_code == 0, result.output
        assert stub_squadron["entered"] == 1
        assert stub_squadron["kwargs"]["cwd"] == repo
