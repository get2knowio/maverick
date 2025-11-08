"""Unit tests for tasks.md parsing and hashing utilities."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.models.phase_automation import PhaseExecutionHints
from src.utils.tasks_markdown import (
    compute_tasks_md_hash,
    parse_phase_metadata,
    parse_tasks_markdown,
)


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "phase_automation"


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parse_tasks_markdown_returns_phase_definitions():
    content = read_fixture("sample_tasks.md")

    phases = parse_tasks_markdown(content)

    assert [phase.ordinal for phase in phases] == [1, 2, 3]
    assert phases[0].title == "Repository Preparation"
    assert phases[1].phase_id == "phase-2"
    assert [task.task_id for task in phases[2].tasks] == ["T300", "T301", "T302"]
    assert phases[1].execution_hints is not None
    assert phases[1].execution_hints.model == "gpt-4.1"
    assert phases[1].execution_hints.agent_profile == "builder"
    assert phases[1].execution_hints.extra_env == {"TEMPORAL_HOST": "temporal.local"}
    assert list(phases[0].tasks[1].tags) == ["tooling"]


def test_parse_tasks_markdown_requires_phase_headings():
    content = read_fixture("invalid_missing_phase.md")

    with pytest.raises(ValueError, match="No phase headings found"):
        parse_tasks_markdown(content)


def test_parse_tasks_markdown_handles_empty_phase():
    content = "\n".join(
        [
            "# Tasks",
            "## Phase 1: Empty Phase",
            "",
            "## Phase 2: Actual Tasks",
            "- [ ] T123 Do something",
        ]
    )

    phases = parse_tasks_markdown(content)

    assert len(phases[0].tasks) == 0
    assert phases[1].tasks[0].description == "Do something"


def test_parse_phase_metadata_parses_supported_keys():
    hints = parse_phase_metadata("model=gpt-4o agent=review env.API_TOKEN=secret env.DEBUG=1")

    assert isinstance(hints, PhaseExecutionHints)
    assert hints.model == "gpt-4o"
    assert hints.agent_profile == "review"
    assert hints.extra_env == {"API_TOKEN": "secret", "DEBUG": "1"}


def test_parse_phase_metadata_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Unsupported metadata key"):
        parse_phase_metadata("model=gpt-4 foo=bar")


def test_parse_phase_metadata_requires_uppercase_env_keys():
    with pytest.raises(ValueError, match="uppercase"):
        parse_phase_metadata("env.bad=value")


def test_compute_tasks_md_hash_matches_blake2b():
    content = read_fixture("sample_tasks.md")

    expected = hashlib.blake2b(content.encode("utf-8"), digest_size=32).hexdigest()

    assert compute_tasks_md_hash(content) == expected
