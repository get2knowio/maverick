"""Typed result models for :class:`~maverick.jj.client.JjClient`.

All models are frozen dataclasses with ``to_dict()`` for DSL compatibility.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# =============================================================================
# Change / revision metadata
# =============================================================================


@dataclass(frozen=True, slots=True)
class JjChangeInfo:
    """A single jj change (revision) from ``jj log``.

    Attributes:
        change_id: Short change-ID prefix (e.g. ``"kxyz"``).
        commit_id: Full or short commit hash.
        description: First line of the change description.
        author: Author name.
        email: Author email.
        timestamp: ISO-8601 timestamp string.
        bookmarks: Bookmarks pointing at this change.
        empty: True if the change contains no file modifications.
    """

    change_id: str
    commit_id: str
    description: str
    author: str = ""
    email: str = ""
    timestamp: str = ""
    bookmarks: tuple[str, ...] = ()
    empty: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjBookmark:
    """A jj bookmark (branch pointer).

    Attributes:
        name: Bookmark name.
        change_id: Change ID the bookmark points to.
        commit_id: Commit hash the bookmark points to.
        remote: Remote name if this is a remote-tracking bookmark.
    """

    name: str
    change_id: str = ""
    commit_id: str = ""
    remote: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# =============================================================================
# Command result types
# =============================================================================


@dataclass(frozen=True, slots=True)
class JjDescribeResult:
    """Result of ``jj describe``."""

    success: bool = True
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjNewResult:
    """Result of ``jj new``.

    Attributes:
        change_id: Change ID of the newly created change.
    """

    success: bool = True
    change_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjCommitResult:
    """Result of ``jj commit``.

    Attributes:
        change_id: Change ID of the committed change.
    """

    success: bool = True
    change_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjDiffResult:
    """Result of ``jj diff``.

    Attributes:
        output: The diff text (git format).
    """

    success: bool = True
    output: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjDiffStatResult:
    """Result of ``jj diff --stat``.

    Attributes:
        output: The diff-stat text.
        files_changed: Number of files with changes.
        insertions: Total lines added.
        deletions: Total lines removed.
    """

    success: bool = True
    output: str = ""
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjLogResult:
    """Result of ``jj log``.

    Attributes:
        output: Raw log text for display.
        changes: Parsed change entries (when structured output was used).
    """

    success: bool = True
    output: str = ""
    changes: tuple[JjChangeInfo, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "output": self.output,
            "changes": [c.to_dict() for c in self.changes],
        }


@dataclass(frozen=True, slots=True)
class JjStatusResult:
    """Result of ``jj status``.

    Attributes:
        output: Raw status text.
        working_copy_change_id: The change ID of the working copy (``@``).
        conflict: True if there are unresolved conflicts.
    """

    success: bool = True
    output: str = ""
    working_copy_change_id: str = ""
    conflict: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjShowResult:
    """Result of ``jj show``.

    Attributes:
        output: Full show output (diff + metadata).
    """

    success: bool = True
    output: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjSnapshotResult:
    """Result of capturing an operation snapshot.

    Attributes:
        operation_id: The captured operation ID for rollback.
    """

    success: bool = True
    operation_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjRestoreResult:
    """Result of ``jj op restore``."""

    success: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjCloneResult:
    """Result of ``jj git clone``.

    Attributes:
        workspace_path: Path to the cloned workspace.
    """

    success: bool = True
    workspace_path: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjFetchResult:
    """Result of ``jj git fetch``."""

    success: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjPushResult:
    """Result of ``jj git push``."""

    success: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjSquashResult:
    """Result of ``jj squash``."""

    success: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjRebaseResult:
    """Result of ``jj rebase``."""

    success: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjBookmarkResult:
    """Result of a bookmark operation."""

    success: bool = True
    name: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JjAbsorbResult:
    """Result of ``jj absorb``."""

    success: bool = True
    output: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
