"""Unit tests for ``_ensure_gitignore_entries`` in :mod:`maverick.init`."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.init import _ensure_gitignore_entries


@pytest.mark.asyncio
async def test_creates_gitignore_when_missing(tmp_path: Path) -> None:
    """No existing .gitignore — one is created with the maverick block."""
    ok = await _ensure_gitignore_entries(tmp_path, verbose=False)
    assert ok is True

    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert ".maverick/runs/" in content
    assert "# maverick" in content


@pytest.mark.asyncio
async def test_appends_to_existing_gitignore(tmp_path: Path) -> None:
    """Existing .gitignore — entry is appended without losing prior lines."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("node_modules/\ndist/\n", encoding="utf-8")

    ok = await _ensure_gitignore_entries(tmp_path, verbose=False)
    assert ok is True

    content = gitignore.read_text(encoding="utf-8")
    # Prior lines preserved
    assert "node_modules/" in content
    assert "dist/" in content
    # New entry added
    assert ".maverick/runs/" in content


@pytest.mark.asyncio
async def test_idempotent_when_entry_already_present(tmp_path: Path) -> None:
    """Re-running on a file that already has the entry is a no-op."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".maverick/runs/\n", encoding="utf-8")

    ok = await _ensure_gitignore_entries(tmp_path, verbose=False)
    assert ok is True

    content = gitignore.read_text(encoding="utf-8")
    # Exactly one occurrence — no duplicate.
    assert content.count(".maverick/runs/") == 1


@pytest.mark.asyncio
async def test_recognizes_broader_patterns(tmp_path: Path) -> None:
    """A broader pattern like ``.maverick/`` already covers the entry."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".maverick/\n", encoding="utf-8")

    ok = await _ensure_gitignore_entries(tmp_path, verbose=False)
    assert ok is True

    content = gitignore.read_text(encoding="utf-8")
    # We should NOT have appended a redundant ``.maverick/runs/``.
    assert ".maverick/runs/" not in content
    # Original pattern still there.
    assert ".maverick/" in content


@pytest.mark.asyncio
async def test_recognizes_entry_without_trailing_slash(tmp_path: Path) -> None:
    """``.maverick/runs`` (no trailing slash) is treated as equivalent."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".maverick/runs\n", encoding="utf-8")

    ok = await _ensure_gitignore_entries(tmp_path, verbose=False)
    assert ok is True

    content = gitignore.read_text(encoding="utf-8")
    # No duplicate added.
    assert content.count(".maverick/runs") == 1


@pytest.mark.asyncio
async def test_handles_missing_trailing_newline(tmp_path: Path) -> None:
    """If existing file doesn't end in \\n, we add one before appending."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("node_modules/", encoding="utf-8")  # no trailing newline

    ok = await _ensure_gitignore_entries(tmp_path, verbose=False)
    assert ok is True

    content = gitignore.read_text(encoding="utf-8")
    # The original line should not be glued to the new entry.
    assert "node_modules/\n" in content
    assert ".maverick/runs/" in content
