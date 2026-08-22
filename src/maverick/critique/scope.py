"""Scope resolution for ``maverick critique``.

Answers "what is being reviewed" *before* any agent is built, so an empty
scope costs zero model calls (FR-009, SC-004).

Every read here is read-only: GitPython through
:class:`~maverick.git.repository.AsyncGitRepository` for the VCS (CLAUDE.md's
read-path rule), and ``bd`` only on the epic scope, only to list beads.
Nothing in this module writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from maverick.critique.models import (
    MAX_EMBEDDED_DIFF_CHARS,
    CritiqueScopeKind,
    ResolvedScope,
    ScopedCommit,
)
from maverick.exceptions import MaverickError
from maverick.git.repository import AsyncGitRepository, DiffStats
from maverick.library.actions.curation import extract_bead_ids
from maverick.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "EPIC_COMMIT_SEARCH_LIMIT",
    "ScopeNotFoundError",
    "ScopeResolutionError",
    "ScopeValidationError",
    "resolve_diff_scope",
    "resolve_epic_scope",
    "resolve_paths_scope",
]

logger = get_logger(__name__)

#: How far back to search for an epic's commits. Bounded on purpose: an
#: unbounded ``git log`` on a long-lived repository is a latency cliff for a
#: command whose whole value is being quick to reach for. A commit older than
#: this belongs to an epic that has long since landed.
EPIC_COMMIT_SEARCH_LIMIT = 500


class ScopeResolutionError(MaverickError):
    """Base for scope-resolution failures."""


class ScopeValidationError(ScopeResolutionError):
    """The invocation itself was wrong — bad path, conflicting scopes."""


class ScopeNotFoundError(ScopeResolutionError):
    """A named resource (an epic) does not exist."""


def _render_stat(stats: DiffStats) -> str:
    """Render :class:`DiffStats` as ``git diff --stat``-style text.

    Built from the structured stats rather than shelling out for
    ``--stat`` — one read serves both the file list and the summary, and
    Guardrail 5 says not to add a second VCS wrapper for output a canonical
    one already produces.
    """
    if not stats.file_list:
        return ""
    width = max(len(name) for name in stats.file_list)
    lines = [
        f" {name.ljust(width)} | {ins + dels:>5} +{ins} -{dels}"
        for name, (ins, dels) in (
            (name, stats.per_file.get(name, (0, 0))) for name in stats.file_list
        )
    ]
    lines.append(
        f" {stats.files_changed} file(s) changed, "
        f"{stats.insertions} insertion(s), {stats.deletions} deletion(s)"
    )
    return "\n".join(lines)


def _truncate(diff_text: str) -> tuple[str, bool]:
    """Bound the embedded diff (research R5).

    Returns ``(text, truncated)``. Truncation is never silent: the caller
    reports it, and the complete file list travels regardless, so the agent
    keeps a full picture of *what* changed and can read the rest itself.
    """
    if len(diff_text) <= MAX_EMBEDDED_DIFF_CHARS:
        return diff_text, False
    return diff_text[:MAX_EMBEDDED_DIFF_CHARS], True


async def resolve_diff_scope(*, cwd: Path, base: str) -> ResolvedScope:
    """Resolve the working copy against *base*.

    Untracked files are included in ``paths`` even though they contribute no
    diff hunks — a newly added file is precisely what a pre-push review most
    needs to see, and the reviewer reads it from the working directory.

    Args:
        cwd: The checkout. Threaded from the CLI boundary (Guardrail 7).
        base: Base revision, e.g. ``"main"``.

    Returns:
        The resolved scope; ``is_empty`` when nothing differs.

    Raises:
        ScopeResolutionError: The repository could not be read.
    """
    repo = AsyncGitRepository(cwd)
    try:
        stats = await repo.diff_stats(base)
        diff_text = await repo.diff(base)
        status = await repo.status()
    except Exception as exc:  # noqa: BLE001 — every git read failure is one kind
        raise ScopeResolutionError(f"could not read the repository: {exc}") from exc

    paths = tuple(sorted({*stats.file_list, *status.untracked}))
    text, truncated = _truncate(diff_text)
    return ResolvedScope(
        kind=CritiqueScopeKind.DIFF,
        summary=f"working copy vs {base}",
        paths=paths,
        diff_text=text,
        diff_truncated=truncated,
        diff_stat=_render_stat(stats),
        base=base,
    )


#: git's canonical empty-tree object. Diffing a root commit against it is the
#: standard way to get "everything this commit introduced" when it has no
#: parent to diff against.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


async def _read_commit_change(
    repo: AsyncGitRepository, *, sha: str
) -> tuple[DiffStats, str] | None:
    """Return one commit's ``(stats, diff)``, or ``None`` if unreadable.

    Falls back to the empty tree for a root commit, which has no ``^`` to
    diff against — otherwise the first commit in a repository would be
    silently unreviewable.
    """
    for base in (f"{sha}^", _EMPTY_TREE):
        try:
            stats = await repo.diff_stats(f"{base}..{sha}")
            body = await repo.diff(base, sha)
        except Exception:  # noqa: BLE001 — try the next base, then give up
            continue
        return stats, body
    return None


async def resolve_epic_scope(
    *,
    cwd: Path,
    epic_id: str,
    bead_ids: Sequence[str],
) -> ResolvedScope:
    """Resolve everything *epic_id*'s beads committed.

    Commits are attributed by the ``bead(<id>):`` subject prefix via the
    existing :func:`~maverick.library.actions.curation.extract_bead_ids` —
    the one reader of bead identity in the tree (research R3). The ``Bead:``
    trailer is not used: nothing reads it today and no log helper exposes a
    commit body to read it from.

    The combined change is the **concatenation of each attributed commit's
    own diff**, not a range diff (research R4). A range would silently pull
    in every unrelated commit interleaved between the epic's own, presenting
    other people's work as this epic's.

    Args:
        cwd: The checkout.
        epic_id: The epic being reviewed — used only for the summary.
        bead_ids: The epic's bead ids, already fetched by the caller (which
            owns the ``bd`` availability check and its error classification).

    Returns:
        The resolved scope; ``is_empty`` when the epic's beads produced no
        commits.

    Raises:
        ScopeResolutionError: The repository could not be read.
    """
    repo = AsyncGitRepository(cwd)
    wanted = set(bead_ids)
    try:
        commits = await repo.log(n=EPIC_COMMIT_SEARCH_LIMIT)
    except Exception as exc:  # noqa: BLE001
        raise ScopeResolutionError(f"could not read the commit log: {exc}") from exc

    scoped: list[ScopedCommit] = []
    diff_parts: list[str] = []
    files: set[str] = set()
    insertions = deletions = 0
    stat_lines: list[str] = []

    for commit in reversed(commits):  # oldest first — the order they were made
        matched = tuple(bid for bid in extract_bead_ids(commit.message) if bid in wanted)
        if not matched:
            continue
        read = await _read_commit_change(repo, sha=commit.sha)
        if read is None:
            # The commit is dropped from `scoped` too, not just from the diff.
            # Leaving it attributed would make the summary and the artifact
            # claim a commit was reviewed whose content nothing ever saw —
            # a partial review presented as a complete one, which is the exact
            # failure the truncation path (research R5) is careful to avoid.
            logger.warning(
                "critique_epic_commit_unreadable",
                sha=commit.short_sha,
                subject=commit.message,
            )
            continue
        scoped.append(ScopedCommit(sha=commit.short_sha, subject=commit.message, bead_ids=matched))
        stats, body = read
        files.update(stats.file_list)
        insertions += stats.insertions
        deletions += stats.deletions
        stat_lines.append(f" {commit.short_sha} {commit.message}\n{_render_stat(stats)}")
        diff_parts.append(f"### {commit.short_sha} {commit.message}\n\n{body}")

    if stat_lines:
        stat_lines.append(
            f" {len(files)} file(s) changed across {len(scoped)} commit(s), "
            f"{insertions} insertion(s), {deletions} deletion(s)"
        )

    text, truncated = _truncate("\n\n".join(diff_parts))
    plural = "" if len(scoped) == 1 else "s"
    return ResolvedScope(
        kind=CritiqueScopeKind.EPIC,
        summary=f"epic {epic_id} ({len(scoped)} commit{plural})",
        paths=tuple(sorted(files)),
        diff_text=text,
        diff_truncated=truncated,
        diff_stat="\n".join(stat_lines),
        epic_id=epic_id,
        commits=tuple(scoped),
    )


def resolve_paths_scope(*, cwd: Path, paths: Sequence[str]) -> ResolvedScope:
    """Resolve an explicit path set as it currently stands.

    No diff is computed — this scope asks about the code's present state, not
    about a change. The reviewer reads the named paths from the working
    directory directly.

    Args:
        cwd: The checkout.
        paths: What the user named, absolute or repo-relative.

    Returns:
        The resolved scope, with ``paths`` normalized repo-relative.

    Raises:
        ScopeValidationError: A path does not exist, or resolves outside the
            repository.
    """
    root = cwd.resolve()
    normalized: list[str] = []
    for raw in paths:
        candidate = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        if not candidate.exists():
            raise ScopeValidationError(f"path does not exist: {raw}")
        if candidate != root and not candidate.is_relative_to(root):
            raise ScopeValidationError(f"path is outside the repository: {raw}")
        normalized.append("." if candidate == root else candidate.relative_to(root).as_posix())

    unique = tuple(sorted(set(normalized)))
    return ResolvedScope(
        kind=CritiqueScopeKind.PATHS,
        summary=f"paths: {', '.join(unique)}",
        paths=unique,
        # No diff: the agent reads these paths from the working directory.
        # `diff_text` stays empty, so `is_empty` is driven entirely by whether
        # any path resolved — which is the right emptiness test for this scope.
        diff_stat="",
    )
