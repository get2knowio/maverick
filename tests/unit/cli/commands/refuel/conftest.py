"""Shared fixtures for ``maverick refuel`` CLI command tests.

Provides directory-scoped fixtures that eliminate repeated ``os.chdir`` /
``Path.home`` monkeypatching boilerplate across refuel sub-command test
modules.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def refuel_env(
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Set up a clean working directory and ``Path.home()`` for refuel tests.

    This fixture is ``autouse`` so every test in the refuel test directory
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
