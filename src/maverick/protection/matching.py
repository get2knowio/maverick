"""Pure path-normalization and default-rule matching.

See ``specs/056-context-file-protection/data-model.md`` (``ProtectionPolicy``)
and ``research.md`` R5 for the full matching semantics.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pathspec

__all__ = [
    "normalize_relpath",
    "is_default_protected",
    "compile_globs",
    "matches_glob",
]

_DEFAULT_BASENAMES = frozenset({"agents.md", "claude.md"})
_DEFAULT_PREFIX = (".specify", "memory")


def normalize_relpath(candidate: str | Path, *, root: Path, resolve: bool) -> str | None:
    """Compute ``candidate``'s path relative to ``root``, posix-separated.

    ``candidate`` is first made absolute (joined against ``root`` if it is
    relative). Two modes govern how that absolute form is produced:

    - ``resolve=True``: follows symlinks via :meth:`Path.resolve` — the
      "resolved" side of the dual matching in research.md R5. ``root`` is
      resolved too, so both sides are on the same footing.
    - ``resolve=False``: makes the path absolute without touching the
      filesystem (no symlink dereferencing) — the "literal" side, which
      catches a symlink *planted* at a protected path (FR-014) before it is
      dereferenced. ``root`` is likewise left unresolved, only made
      absolute.

    Args:
        candidate: The path to normalize, absolute or relative.
        root: The policy root paths are expressed relative to.
        resolve: Whether to follow symlinks when computing the absolute form.

    Returns:
        The POSIX-style relative path string, or ``None`` if ``candidate``
        resolves outside ``root`` (would require a leading ``..`` to
        express).
    """
    candidate_path = Path(candidate)
    root_path = Path(root)

    if not candidate_path.is_absolute():
        candidate_path = root_path / candidate_path

    if resolve:
        abs_candidate = candidate_path.resolve()
        abs_root = root_path.resolve()
    else:
        abs_candidate = Path(os.path.abspath(candidate_path))
        abs_root = Path(os.path.abspath(root_path))

    try:
        relative = abs_candidate.relative_to(abs_root)
    except ValueError:
        return None

    return relative.as_posix()


def is_default_protected(relpath: str) -> bool:
    """Check ``relpath`` against the hardcoded default protected rules.

    Two rules, neither consulting any config (FR-012 — defaults can never be
    widened or narrowed by misconfiguration since they take no user input):
    the basename case-insensitively equals ``agents.md`` or ``claude.md``, or
    the path's first two segments case-insensitively equal ``.specify``,
    ``memory``.

    Args:
        relpath: A POSIX-style relative path, as returned by
            :func:`normalize_relpath`.

    Returns:
        True if ``relpath`` matches a default protected rule.
    """
    parts = PurePosixPath(relpath).parts
    if not parts:
        return False

    if parts[-1].lower() in _DEFAULT_BASENAMES:
        return True

    return len(parts) >= 2 and (parts[0].lower(), parts[1].lower()) == _DEFAULT_PREFIX


def compile_globs(patterns: list[str]) -> tuple[pathspec.PathSpec, list[str]]:
    """Compile gitignore-style glob patterns, dropping individually-invalid ones.

    Patterns are compiled one at a time so a single bad pattern cannot break
    the whole block (contracts/protection-config.md). This function performs
    no logging — the caller (``protection/config.py``) reports dropped
    patterns.

    Args:
        patterns: Gitignore-style (``gitwildmatch``) glob patterns.

    Returns:
        A tuple of the compiled :class:`pathspec.PathSpec` over the valid
        patterns, and the list of patterns that failed to compile.
    """
    valid: list[str] = []
    dropped: list[str] = []

    for pattern in patterns:
        try:
            pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
        except (ValueError, TypeError):
            dropped.append(pattern)
            continue
        valid.append(pattern)

    spec = pathspec.PathSpec.from_lines("gitwildmatch", valid)
    return spec, dropped


def matches_glob(relpath: str, spec: pathspec.PathSpec) -> bool:
    """Check ``relpath`` against a compiled glob spec.

    Thin wrapper around :meth:`pathspec.PathSpec.match_file` so callers don't
    need to import ``pathspec`` directly.

    Args:
        relpath: A POSIX-style relative path.
        spec: A compiled :class:`pathspec.PathSpec`.

    Returns:
        True if ``relpath`` matches the spec.
    """
    return spec.match_file(relpath)
