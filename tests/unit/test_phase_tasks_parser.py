"""Unit tests for the parse_tasks_md Temporal activity."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.activities.phase_tasks_parser import ParseTasksMdRequest, parse_tasks_md
from src.utils.tasks_markdown import compute_tasks_md_hash


@pytest.mark.asyncio
async def test_parse_tasks_md_from_path_returns_phase_definitions(
    sample_tasks_md_path: Path,
    sample_tasks_md_content: str,
) -> None:
    """Activity should load markdown from path and emit parsed phases."""

    request = ParseTasksMdRequest(tasks_md_path=sample_tasks_md_path)

    result = await parse_tasks_md(request)

    assert len(result.phases) == 3
    assert result.source_path == str(sample_tasks_md_path)
    assert result.source_content.startswith("# Tasks")
    assert result.tasks_md_hash == compute_tasks_md_hash(sample_tasks_md_content)
    assert result.phases[1].execution_hints is not None
    assert result.phases[1].execution_hints.model == "gpt-4.1"
    assert result.phases[1].execution_hints.agent_profile == "builder"
    assert result.phases[1].execution_hints.extra_env == {"TEMPORAL_HOST": "temporal.local"}


@pytest.mark.asyncio
async def test_parse_tasks_md_prefers_inline_content(sample_tasks_md_content: str, tmp_path: Path) -> None:
    """Providing inline content should skip disk reads and return phases."""

    extra_content = sample_tasks_md_content + "\n"
    request = ParseTasksMdRequest(tasks_md_content=extra_content)

    result = await parse_tasks_md(request)

    assert result.source_path is None
    assert result.source_content == extra_content
    assert result.tasks_md_hash == compute_tasks_md_hash(extra_content)


@pytest.mark.asyncio
async def test_parse_tasks_md_rejects_multiple_sources(
    sample_tasks_md_path: Path, sample_tasks_md_content: str
) -> None:
    """Request must provide exactly one source of markdown content."""

    with pytest.raises(ValueError, match="Provide either tasks_md_path or tasks_md_content"):
        ParseTasksMdRequest(
            tasks_md_path=sample_tasks_md_path,
            tasks_md_content=sample_tasks_md_content,
        )


@pytest.mark.asyncio
async def test_parse_tasks_md_requires_phase_headings(invalid_tasks_md_content: str) -> None:
    """Activity should raise a clear error when markdown lacks phase headings."""

    request = ParseTasksMdRequest(tasks_md_content=invalid_tasks_md_content)

    with pytest.raises(ValueError, match="No phase headings"):
        await parse_tasks_md(request)


@pytest.mark.asyncio
async def test_parse_tasks_md_requires_existing_file(tmp_path: Path) -> None:
    """Activity should surface FileNotFoundError for missing paths."""

    missing_path = tmp_path / "missing_tasks.md"
    request = ParseTasksMdRequest(tasks_md_path=missing_path)

    with pytest.raises(FileNotFoundError):
        await parse_tasks_md(request)
