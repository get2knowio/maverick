"""Shared fixtures for jj tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.jj.client import JjClient
from maverick.runners.command import CommandRunner
from maverick.runners.models import CommandResult


def make_result(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    duration_ms: int = 50,
    timed_out: bool = False,
) -> CommandResult:
    """Create a CommandResult with convenient defaults."""
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


@pytest.fixture
def mock_runner() -> AsyncMock:
    """Create a mock CommandRunner that returns success by default."""
    runner = AsyncMock(spec=CommandRunner)
    runner.run.return_value = make_result()
    return runner


@pytest.fixture
def jj_client(mock_runner: AsyncMock, temp_dir: Path) -> JjClient:
    """Create a JjClient with a mocked runner."""
    return JjClient(cwd=temp_dir, runner=mock_runner)
