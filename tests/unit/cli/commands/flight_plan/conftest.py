"""Shared fixtures for ``maverick flight-plan`` CLI command tests.

Provides directory-scoped fixtures that eliminate repeated ``os.chdir`` /
``Path.home`` monkeypatching boilerplate across flight-plan sub-command test
modules.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal valid flight plan content
# Canonical source of truth: tests/unit/flight/conftest.py
# ---------------------------------------------------------------------------

VALID_FLIGHT_PLAN_CONTENT = """\
---
name: test-plan
version: "1.0"
created: 2026-02-28
---

## Objective

This is the objective text.

## Success Criteria

- [ ] First criterion
- [ ] Second criterion

## Scope

### In

- Something in scope

### Out

- Something out of scope
"""


@pytest.fixture(autouse=True)
def flight_plan_env(
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Set up a clean working directory and ``Path.home()`` for flight-plan tests.

    This fixture is ``autouse`` so every test in the flight-plan test directory
    automatically gets:
      - ``os.chdir(temp_dir)``
      - ``Path.home()`` pointing at *temp_dir*
      - A clean environment (no ``MAVERICK_`` vars)

    Returns:
        The temporary directory path, in case a test needs to reference it.
    """
    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    return temp_dir


@pytest.fixture
def write_flight_plan(tmp_path: Path):
    """Return a helper that writes content to a temp file and returns its path."""

    def _write(content: str, filename: str = "plan.md") -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return p

    return _write
