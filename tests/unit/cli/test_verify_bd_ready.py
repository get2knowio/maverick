"""Tests for ``maverick.cli.common.verify_bd_ready``.

This preflight catches missing bd setup in seconds rather than after
the full briefing+decompose burn. Was the cause of a 786-second
``maverick refuel`` run that died on bead-creation because bd had
never been initialized in the project directory.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.cli.common import verify_bd_ready
from maverick.cli.context import ExitCode


def test_verify_bd_ready_exits_when_bd_missing(temp_dir: Path) -> None:
    with patch("shutil.which", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            verify_bd_ready(cwd=temp_dir)
    assert exc_info.value.code == ExitCode.FAILURE


def test_verify_bd_ready_exits_when_beads_not_initialized(temp_dir: Path) -> None:
    """bd is on PATH but the project has no ``.beads/<engine>`` directory."""
    with patch("shutil.which", return_value="/usr/bin/bd"):
        with pytest.raises(SystemExit) as exc_info:
            verify_bd_ready(cwd=temp_dir)
    assert exc_info.value.code == ExitCode.FAILURE


def _seed_metadata(beads: Path, prefix: str = "myproj") -> None:
    """Write a valid ``metadata.json`` so the strict is_initialized passes."""
    import json as _json

    beads.mkdir(parents=True, exist_ok=True)
    (beads / "metadata.json").write_text(
        _json.dumps({"issue_prefix": prefix, "dolt_database": "myproj"})
    )


def test_verify_bd_ready_passes_when_initialized(temp_dir: Path) -> None:
    """bd on PATH + ``.beads/embeddeddolt`` + valid ``metadata.json`` →
    no exit, no exception."""
    (temp_dir / ".beads" / "embeddeddolt").mkdir(parents=True)
    _seed_metadata(temp_dir / ".beads")
    with patch("shutil.which", return_value="/usr/bin/bd"):
        verify_bd_ready(cwd=temp_dir)


def test_verify_bd_ready_passes_with_server_dolt(temp_dir: Path) -> None:
    """Server-mode ``.beads/dolt`` + metadata is also a valid initialised state."""
    (temp_dir / ".beads" / "dolt").mkdir(parents=True)
    _seed_metadata(temp_dir / ".beads")
    with patch("shutil.which", return_value="/usr/bin/bd"):
        verify_bd_ready(cwd=temp_dir)


def test_verify_bd_ready_rejects_dolt_dir_without_metadata(temp_dir: Path) -> None:
    """Half-initialised state — directory exists but metadata.json is
    missing — must fail the preflight even though the directory is
    there. Was the cause of a 670s refuel run that died at bead
    creation with 'database not initialized: issue_prefix config is
    missing'."""
    (temp_dir / ".beads" / "embeddeddolt").mkdir(parents=True)
    with patch("shutil.which", return_value="/usr/bin/bd"):
        with pytest.raises(SystemExit) as exc_info:
            verify_bd_ready(cwd=temp_dir)
    assert exc_info.value.code == ExitCode.FAILURE


def test_verify_bd_ready_jsonl_only_is_not_initialized(temp_dir: Path) -> None:
    """A clone where only ``.beads/issues.jsonl`` exists (no local Dolt
    store yet) must NOT pass — that's the second-developer state where
    bootstrap is still needed."""
    beads = temp_dir / ".beads"
    beads.mkdir()
    (beads / "issues.jsonl").write_text("")
    with patch("shutil.which", return_value="/usr/bin/bd"):
        with pytest.raises(SystemExit) as exc_info:
            verify_bd_ready(cwd=temp_dir)
    assert exc_info.value.code == ExitCode.FAILURE
