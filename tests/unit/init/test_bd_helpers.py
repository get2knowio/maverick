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
    # Valid metadata = both ``dolt_database`` AND ``issue_prefix`` present.
    metadata = {
        "dolt_database": "sample_maverick_project",
        "issue_prefix": "smp",
        "project_id": "abc",
    }
    (beads / "metadata.json").write_text(json.dumps(metadata))
    embedded = beads / "embeddeddolt"
    embedded.mkdir()
    (embedded / "data").write_text("real-data")

    _clear_invalid_bd_state(tmp_path)

    # With valid metadata, the embedded Dolt store is left intact so
    # BeadClient.init_or_bootstrap can take the SKIP branch instead of
    # re-cloning. (Aborted previous runs are now detected by missing or
    # corrupt metadata, not by the presence of embeddeddolt.)
    assert (beads / "metadata.json").exists()
    assert embedded.exists()
    assert (embedded / "data").read_text() == "real-data"
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
    """Lock/pid files are transient and always safe to clear; the dolt/
    data directory is preserved when metadata is valid."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps(
            {"dolt_database": "sample_maverick_project", "issue_prefix": "smp"}
        )
    )
    server_dir = beads / "dolt"
    server_dir.mkdir()
    (server_dir / "data").write_text("x")
    for stale in ("dolt-server.lock", "dolt-server.pid", "dolt-monitor.pid"):
        (beads / stale).write_text("")

    _clear_invalid_bd_state(tmp_path)

    # Server-mode data directory preserved (valid metadata = healthy DB).
    assert server_dir.exists()
    assert (server_dir / "data").read_text() == "x"
    # Transient lock/pid files removed unconditionally.
    assert not (beads / "dolt-server.lock").exists()
    assert not (beads / "dolt-server.pid").exists()
    assert not (beads / "dolt-monitor.pid").exists()


def test_clear_invalid_bd_state_wipes_embedded_when_metadata_invalid(
    tmp_path: Path,
) -> None:
    """When metadata is corrupt/invalid, both metadata.json and the
    embedded store are wiped so the next lifecycle call re-creates them."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "has-hyphens-which-are-illegal"})
    )
    embedded = beads / "embeddeddolt"
    embedded.mkdir()
    (embedded / "data").write_text("stale")
    server_dir = beads / "dolt"
    server_dir.mkdir()
    (server_dir / "data").write_text("stale")

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "metadata.json").exists()
    assert not embedded.exists()
    assert not server_dir.exists()


def test_clear_invalid_bd_state_wipes_when_issue_prefix_missing(
    tmp_path: Path,
) -> None:
    """``metadata.json`` with valid ``dolt_database`` but missing
    ``issue_prefix`` is the half-init state that bd's ``bd create``
    rejects with "issue_prefix config is missing". The cleanup must
    wipe so the next ``bd init`` can re-create cleanly — without this,
    bd refuses to re-init because the embeddeddolt/ directory is still
    present, deadlocking the user."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "myproj"})  # no issue_prefix
    )
    embedded = beads / "embeddeddolt"
    embedded.mkdir()
    (embedded / "data").write_text("stale")

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "metadata.json").exists()
    assert not embedded.exists()


def test_clear_invalid_bd_state_wipes_when_issue_prefix_empty(
    tmp_path: Path,
) -> None:
    """Empty-string ``issue_prefix`` is also half-init."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "myproj", "issue_prefix": ""})
    )
    embedded = beads / "embeddeddolt"
    embedded.mkdir()

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "metadata.json").exists()
    assert not embedded.exists()


def test_clear_invalid_bd_state_wipes_config_json_on_invalid_metadata(
    tmp_path: Path,
) -> None:
    """``config.json`` carries ``sync.remote`` from previous runs. When
    metadata is invalid (half-init), the stale config can force the next
    ``bd init`` to "sync from remote" — pointing at a non-Dolt git URL —
    and fail with "remote at that url contains no Dolt data". The cleanup
    must wipe config.json so the next init starts truly fresh."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "myproj"})  # invalid — no issue_prefix
    )
    (beads / "config.json").write_text(
        json.dumps({"sync": {"remote": "git+https://github.com/x/y.git"}})
    )
    (beads / "embeddeddolt").mkdir()

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "config.json").exists()
    assert not (beads / "metadata.json").exists()
    assert not (beads / "embeddeddolt").exists()


def test_clear_invalid_bd_state_wipes_issues_jsonl_on_invalid_metadata(
    tmp_path: Path,
) -> None:
    """A leftover ``issues.jsonl`` from a previous half-init can cause
    the next ``bd bootstrap`` to take an unwanted import path. Since
    half-init states have no real bd issues (you need issue_prefix to
    create them), wiping the JSONL is safe."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "myproj"})  # invalid
    )
    (beads / "issues.jsonl").write_text("{}\n")
    (beads / "embeddeddolt").mkdir()

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "issues.jsonl").exists()


def test_clear_invalid_bd_state_preserves_hooks_dir(tmp_path: Path) -> None:
    """``hooks/`` is project-level git-hook config, not bd state. The
    cleanup must not touch it even when wiping for a fresh init."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "myproj"})  # invalid → triggers wipe
    )
    hooks = beads / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_text("#!/bin/sh\necho hi\n")

    _clear_invalid_bd_state(tmp_path)

    assert hooks.is_dir(), "hooks/ must survive cleanup"
    assert (hooks / "pre-commit").is_file()
