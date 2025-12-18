from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_subprocess() -> MagicMock:
    """Create a mock subprocess object with common methods and attributes."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = MagicMock()
    mock.stderr = MagicMock()
    mock.communicate = AsyncMock(return_value=(b"stdout output", b""))
    mock.wait = AsyncMock()
    mock.terminate = MagicMock()
    mock.kill = MagicMock()
    mock.pid = 12345
    return mock


@pytest.fixture
def tmp_cwd(tmp_path):
    """Create a temporary working directory for tests."""
    return tmp_path
