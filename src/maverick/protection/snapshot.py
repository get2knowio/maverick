"""``SnapshotManifest`` — the Layer 2 (backstop) detect-and-restore engine.

Captures protected-file bytes before an agent execution, re-scans after,
and restores any unauthorized mutation — the deterministic,
provider-independent guarantee (SC-001, SC-006). See
``specs/056-context-file-protection/research.md`` R6 and ``data-model.md``'s
"SnapshotManifest" section for the normative restore matrix.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.logging import get_logger
from maverick.protection.records import BlockRecord
from maverick.utils.atomic import atomic_write_bytes

if TYPE_CHECKING:
    from collections.abc import Mapping

    from maverick.protection.policy import ProtectionPolicy
    from maverick.protection.records import BlockCollector

logger = get_logger(__name__)

__all__ = ["SnapshotEntry", "SnapshotManifest", "restore_and_report"]

#: Directory names never descended into during the pruned walk — VCS
#: internals, virtualenvs, dependency trees, and Maverick's own run
#: metadata. Symlinked directories are additionally pruned (see
#: ``_iter_protected_paths``) regardless of name.
_PRUNED_DIR_NAMES = frozenset({".git", ".jj", ".venv", "node_modules", ".maverick"})


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    """One protected file's captured state.

    Attributes:
        sha256: Hex digest of ``content`` (or, for a symlink, of the
            encoded link target) — used to detect an edit without a
            byte-for-byte compare on every reconcile pass.
        content: The file's raw bytes, or the UTF-8-encoded symlink target
            when ``is_symlink`` is ``True``.
        is_symlink: Whether the captured path was itself a symlink (not
            whether it *points at* one).
    """

    sha256: str
    content: bytes
    is_symlink: bool


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    """Protected-file state captured before one agent execution.

    Attributes:
        root: The policy root the manifest was captured relative to.
        entries: ``{relpath: SnapshotEntry}`` — POSIX-style paths relative
            to ``root``, one entry per protected file that existed on disk
            at capture time. A protected path created *after* capture has
            no entry (that's the "create" restore case).
        unreadable: Protected paths that existed at capture time but could
            not be read (permissions, races, ...). They have no ``entries``
            row, so without this set the post-step scan would mistake them
            for agent-created files and delete them. Restore skips them
            entirely.
    """

    root: Path
    entries: Mapping[str, SnapshotEntry]
    unreadable: frozenset[str] = frozenset()

    @classmethod
    async def capture(cls, root: Path, policy: ProtectionPolicy) -> SnapshotManifest:
        """Capture the current state of every protected file under ``root``.

        Runs the filesystem walk + hashing off the event loop
        (:func:`asyncio.to_thread`, Guardrail 1). Protected sets are small
        (a handful of files), so this is fast even on large trees — the
        walk itself is pruned (see :data:`_PRUNED_DIR_NAMES`).

        Args:
            root: The policy root to walk.
            policy: The policy whose :meth:`~ProtectionPolicy.decide`
                determines which paths are captured.

        Returns:
            The captured manifest. An unreadable individual file is
            skipped with a warning rather than aborting the whole capture
            — a partial manifest still protects everything it could read.
        """
        entries, unreadable = await asyncio.to_thread(_capture_sync, root, policy)
        return cls(root=root, entries=entries, unreadable=unreadable)


def _iter_protected_relpaths(root: Path, policy: ProtectionPolicy) -> list[str]:
    """Pruned walk of ``root``, yielding every relpath ``policy`` protects.

    Matches on the walked (literal) relpath via
    :meth:`ProtectionPolicy.protects_relpath` rather than
    :meth:`ProtectionPolicy.decide`. ``decide`` additionally resolves
    symlinks, which costs two :meth:`Path.resolve` syscalls *per walked
    file* — on a repo of any size that dominates the whole snapshot pass
    (measured ~17x slower on this checkout), and it buys nothing here:
    every path comes from the walk itself, already rooted under ``root``,
    and it is the path's location in the tree — not its symlink target —
    that decides whether the backstop must guard it. ``decide``'s
    resolved side still applies where it matters, at the pre-write gate,
    where the *model* supplies the path.

    Returns POSIX-style paths relative to the resolved ``root``.
    """
    resolved_root = root.resolve()
    protected: list[str] = []
    for dirpath, dirnames, filenames in os.walk(resolved_root, followlinks=False):
        # ``followlinks=False`` already stops os.walk descending into
        # symlinked directories, so pruning by name is all that's left.
        dirnames[:] = [d for d in dirnames if d not in _PRUNED_DIR_NAMES]
        rel_dir = os.path.relpath(dirpath, resolved_root)
        prefix = "" if rel_dir == "." else f"{rel_dir.replace(os.sep, '/')}/"
        for filename in filenames:
            relpath = f"{prefix}{filename}"
            try:
                blocked, _rule = policy.protects_relpath(relpath)
            except Exception as exc:  # noqa: BLE001 — one bad path must not abort the walk
                logger.warning("protection_snapshot_decide_failed", path=relpath, error=str(exc))
                continue
            if blocked:
                protected.append(relpath)
    return protected


def _capture_sync(
    root: Path, policy: ProtectionPolicy
) -> tuple[dict[str, SnapshotEntry], frozenset[str]]:
    resolved_root = root.resolve()
    entries: dict[str, SnapshotEntry] = {}
    unreadable: set[str] = set()
    for relpath in _iter_protected_relpaths(root, policy):
        entry = _read_entry(resolved_root / relpath)
        if entry is not None:
            entries[relpath] = entry
        else:
            # Protected, present, but unreadable. Recorded so the
            # post-step scan doesn't mistake it for an agent-created
            # file and delete it.
            unreadable.add(relpath)
    return entries, frozenset(unreadable)


def _read_entry(path: Path) -> SnapshotEntry | None:
    try:
        if path.is_symlink():
            target = os.readlink(path)
            content = target.encode("utf-8", errors="surrogateescape")
            return SnapshotEntry(
                sha256=hashlib.sha256(content).hexdigest(), content=content, is_symlink=True
            )
        content = path.read_bytes()
        return SnapshotEntry(
            sha256=hashlib.sha256(content).hexdigest(), content=content, is_symlink=False
        )
    except OSError as exc:
        logger.warning("protection_snapshot_read_failed", path=str(path), error=str(exc))
        return None


async def restore_and_report(
    manifest: SnapshotManifest,
    policy: ProtectionPolicy,
    *,
    agent_role: str,
    workflow: str,
    bead_id: str | None = None,
    collector: BlockCollector | None = None,
) -> list[BlockRecord]:
    """Re-scan protected paths and restore any unauthorized mutation.

    Compares the current on-disk state against ``manifest`` (captured
    before the agent execution this brackets) and undoes any drift, per
    the restore matrix in data-model.md:

    - Manifest entry missing on disk → rewrite it (delete/rename-away
      undone).
    - Manifest entry's hash differs → rewrite it (edit undone).
    - A currently-protected path with no manifest entry → remove it
      (create/rename-to undone; unlinked if it's a symlink).

    Every restore — and every restore *failure* — is recorded as a
    ``BlockRecord(operation="restore", layer="backstop")``; a failure
    logs an error and continues (never raises), so one unrestorable file
    doesn't hide restores of the others. Records are appended to
    ``collector`` (when given) in addition to being returned.

    Args:
        manifest: The pre-step snapshot to restore toward.
        policy: The policy used to detect newly-created protected paths.
        agent_role: Recorded on every emitted :class:`BlockRecord`.
        workflow: Recorded on every emitted :class:`BlockRecord`.
        bead_id: Recorded on every emitted :class:`BlockRecord`, when
            inside a bead.
        collector: Optional sink each record is also appended to.

    Returns:
        Every :class:`BlockRecord` produced by this pass, in the order
        restores were applied (manifest entries first, then new-creates).
    """
    records = await asyncio.to_thread(
        _restore_sync, manifest, policy, agent_role, workflow, bead_id
    )
    if collector is not None:
        for record in records:
            collector.append(record)
    return records


def _restore_sync(
    manifest: SnapshotManifest,
    policy: ProtectionPolicy,
    agent_role: str,
    workflow: str,
    bead_id: str | None,
) -> list[BlockRecord]:
    resolved_root = manifest.root.resolve()
    records: list[BlockRecord] = []

    for relpath, entry in manifest.entries.items():
        path = resolved_root / relpath
        exists = path.exists() or path.is_symlink()
        current = _read_entry(path) if exists else None
        if current is not None and current.sha256 == entry.sha256:
            continue  # unchanged — no restore needed

        # ``current is None`` covers both "gone" and "present but
        # unreadable"; only the former is a delete/rename.
        inferred = "edit" if exists else "delete/rename"
        record = _restore_one(
            path=path,
            relpath=relpath,
            entry=entry,
            inferred_detail=inferred,
            agent_role=agent_role,
            workflow=workflow,
            bead_id=bead_id,
        )
        records.append(record)

    # New protected paths not present in the pre-step manifest.
    for relpath in _iter_protected_relpaths(manifest.root, policy):
        if relpath in manifest.entries or relpath in manifest.unreadable:
            # ``unreadable`` existed before the step but couldn't be
            # snapshotted — deleting it would destroy the user's own
            # file, which is the exact opposite of protecting it.
            continue
        records.append(
            _remove_created(
                path=resolved_root / relpath,
                relpath=relpath,
                agent_role=agent_role,
                workflow=workflow,
                bead_id=bead_id,
            )
        )

    return records


def _restore_one(
    *,
    path: Path,
    relpath: str,
    entry: SnapshotEntry,
    inferred_detail: str,
    agent_role: str,
    workflow: str,
    bead_id: str | None,
) -> BlockRecord:
    try:
        if entry.is_symlink:
            target = os.fsdecode(entry.content)
            if path.exists() or path.is_symlink():
                path.unlink()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)
        else:
            # Bytes, never a decode/encode round-trip: the captured
            # content may not be valid UTF-8, and a text-mode rewrite
            # would raise UnicodeEncodeError (a ValueError, not an
            # OSError) and escape this handler entirely.
            atomic_write_bytes(path, entry.content)
        detail = f"restored after backstop-detected mutation (inferred: {inferred_detail})"
    except (OSError, ValueError) as exc:
        logger.error("protection_restore_failed", path=relpath, error=str(exc))
        detail = f"restore FAILED (inferred: {inferred_detail}): {exc}"

    return BlockRecord(
        agent_role=agent_role,
        workflow=workflow,
        operation="restore",
        path=relpath,
        layer="backstop",
        bead_id=bead_id,
        detail=detail,
    )


def _remove_created(
    *,
    path: Path,
    relpath: str,
    agent_role: str,
    workflow: str,
    bead_id: str | None,
) -> BlockRecord:
    try:
        path.unlink()
        detail = "restored after backstop-detected mutation (inferred: create/rename-to)"
    except (OSError, ValueError) as exc:
        logger.error("protection_restore_failed", path=relpath, error=str(exc))
        detail = f"restore FAILED (inferred: create/rename-to): {exc}"

    return BlockRecord(
        agent_role=agent_role,
        workflow=workflow,
        operation="restore",
        path=relpath,
        layer="backstop",
        bead_id=bead_id,
        detail=detail,
    )
