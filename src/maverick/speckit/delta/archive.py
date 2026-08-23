"""Archive an applied delta document.

See ``specs/059-spec-delta-layer/contracts/delta-document-format.md``'s
"Application record" section and research R10 for archive ordering.

Pure — computes text and paths only. The caller (``apply.py``) performs
the actual filesystem move last, after both ``spec.md``/``tasks.md``
writes have already succeeded (research R8's compute-then-write shape).
The one interruption window this does *not* fully close is between the
archive file being written and the pending document being unlinked: both
copies then exist on disk, and ``apply_delta`` detects that specific
window (the archive copy is already there) and finishes the cleanup on
the next run rather than re-validating a delta whose target files it
already rewrote. An interruption *before* the archive write (e.g.
between the ``spec.md`` and ``tasks.md`` writes) is not recoverable
automatically — the pending document remains, but re-validating it
against the now-partially-rewritten ``spec.md``/``tasks.md`` will
correctly refuse (typically as ``stale-before``), and requires manual
intervention to resolve.
"""

from __future__ import annotations

import re
from pathlib import Path

from maverick.speckit.delta.models import ApplicationRecord

_SEQUENCE_PREFIX_RE = re.compile(r"^(\d+)-")
_APPLIED_AT_RE = re.compile(r"^\*\*At\*\*:\s*(.+)$", re.MULTILINE)


def extract_applied_at(document_text: str) -> str | None:
    """Read the ``**At**: <timestamp>`` line out of an archived document's
    ``## Applied`` record, or ``None`` if it has none (not actually applied)."""
    m = _APPLIED_AT_RE.search(document_text)
    return m.group(1).strip() if m else None


def render_application_record(record: ApplicationRecord) -> str:
    """Render the ``## Applied`` block appended to a document as it archives."""
    lines = [
        "",
        "---",
        "",
        "## Applied",
        "",
        f"**At**: {record.applied_at}",
        (
            f"**Operations**: {record.counts.get('added', 0)} added, "
            f"{record.counts.get('modified', 0)} modified, "
            f"{record.counts.get('removed', 0)} removed, "
            f"{record.counts.get('renamed', 0)} renamed"
        ),
        (
            f"**Tasks**: {record.task_counts.get('added', 0)} added, "
            f"{record.task_counts.get('withdrawn', 0)} withdrawn"
        ),
    ]
    if record.shrink_intended_ids:
        lines.append(f"**Declared reductions**: {', '.join(record.shrink_intended_ids)}")
    if record.acknowledgements:
        lines.extend(["", "### Acknowledged impacts", ""])
        for ack in record.acknowledgements:
            lines.append(
                f"- {ack.task_id} — bead `{ack.bead_id}`, status `{ack.bead_status}` "
                f"at {ack.acknowledged_at}"
            )
    lines.append("")
    return "\n".join(lines)


def archive_delta(
    document_text: str, *, record: ApplicationRecord, source_path: Path
) -> tuple[str, Path]:
    """Compute the archived document's content and destination path.

    Args:
        document_text: The pending delta document's current on-disk text.
        record: The application record to append (FR-022 — the archive
            is readable without any other source).
        source_path: Where the pending document currently lives —
            ``specs/<feature>/deltas/<file>.md``.

    Returns:
        ``(new_text, destination_path)`` — *destination_path* is
        ``specs/<feature>/deltas/archive/<file>.md`` (same filename;
        FR-023 makes location alone the pending/applied state).
    """
    new_text = document_text.rstrip("\n") + "\n" + render_application_record(record)
    destination = source_path.parent / "archive" / source_path.name
    return new_text, destination


def list_delta_files(directory: Path) -> tuple[Path, ...]:
    """List ``*.md`` files directly in *directory*, ordered by numeric
    filename prefix (research R10) — survives a ``git clone``, which
    mtime-based ordering does not.
    """
    if not directory.is_dir():
        return ()

    def _key(path: Path) -> tuple[int, str]:
        m = _SEQUENCE_PREFIX_RE.match(path.stem)
        return (int(m.group(1)) if m else 0, path.name)

    return tuple(sorted((p for p in directory.glob("*.md") if p.is_file()), key=_key))


__all__ = ["archive_delta", "extract_applied_at", "list_delta_files", "render_application_record"]
