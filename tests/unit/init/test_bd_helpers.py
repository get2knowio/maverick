"""Unit tests for bd-init helpers in :mod:`maverick.init`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.init import (
    _clear_invalid_bd_state,
    _is_valid_dolt_db_name,
    _sanitize_bd_prefix,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("sample-maverick-project", "sample_maverick_project"),
        ("my.project", "my_project"),
        ("a---b", "a_b"),
        ("clean_name", "clean_name"),
        ("CamelCase", "CamelCase"),
        ("123project", "_123project"),
        ("---", "project"),
    ],
)
def test_sanitize_bd_prefix(raw: str, expected: str) -> None:
    assert _sanitize_bd_prefix(raw) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("sample_maverick_project", True),
        ("project1", True),
        ("Beads", True),
        ("beads_sample-maverick-project", False),
        ("1leading_digit", False),
        ("", False),
        ("with space", False),
    ],
)
def test_is_valid_dolt_db_name(name: str, expected: bool) -> None:
    assert _is_valid_dolt_db_name(name) is expected


def test_clear_invalid_bd_state_removes_hyphenated_metadata(tmp_path: Path) -> None:
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "beads_sample-maverick-project"})
    )
    embedded = beads / "embeddeddolt"
    embedded.mkdir()
    (embedded / ".lock").write_text("")

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "metadata.json").exists()
    assert not embedded.exists()


def test_clear_invalid_bd_state_preserves_valid_metadata(tmp_path: Path) -> None:
    beads = tmp_path / ".beads"
    beads.mkdir()
    metadata = {"dolt_database": "sample_maverick_project", "project_id": "abc"}
    (beads / "metadata.json").write_text(json.dumps(metadata))
    embedded = beads / "embeddeddolt"
    embedded.mkdir()

    _clear_invalid_bd_state(tmp_path)

    assert (beads / "metadata.json").exists()
    # embeddeddolt is still removed (handles aborted previous runs).
    assert not embedded.exists()
    assert json.loads((beads / "metadata.json").read_text()) == metadata


def test_clear_invalid_bd_state_handles_missing_files(tmp_path: Path) -> None:
    # Should not raise when .beads doesn't exist or metadata.json is absent.
    _clear_invalid_bd_state(tmp_path)
    (tmp_path / ".beads").mkdir()
    _clear_invalid_bd_state(tmp_path)


def test_clear_invalid_bd_state_handles_corrupt_metadata(tmp_path: Path) -> None:
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text("{not valid json")
    embedded = beads / "embeddeddolt"
    embedded.mkdir()

    _clear_invalid_bd_state(tmp_path)

    # Corrupt metadata is treated as invalid → removed.
    assert not (beads / "metadata.json").exists()
    assert not embedded.exists()


def test_clear_invalid_bd_state_removes_stale_server_artifacts(tmp_path: Path) -> None:
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "sample_maverick_project"})
    )
    server_dir = beads / "dolt"
    server_dir.mkdir()
    (server_dir / "data").write_text("x")
    for stale in ("dolt-server.lock", "dolt-server.pid", "dolt-monitor.pid"):
        (beads / stale).write_text("")

    _clear_invalid_bd_state(tmp_path)

    assert not server_dir.exists()
    assert not (beads / "dolt-server.lock").exists()
    assert not (beads / "dolt-server.pid").exists()
    assert not (beads / "dolt-monitor.pid").exists()
