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
    # Valid metadata = bd-written shape: database + backend + dolt_mode
    # + dolt_database + project_id. Note: NO issue_prefix — that lives
    # in config.yaml, not metadata.json (verified empirically against
    # bd 1.0.x).
    metadata = {
        "database": "dolt",
        "backend": "dolt",
        "dolt_mode": "embedded",
        "dolt_database": "sample_maverick_project",
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
            {
                "database": "dolt",
                "backend": "dolt",
                "dolt_mode": "embedded",
                "dolt_database": "sample_maverick_project",
                "project_id": "abc",
            }
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


def test_clear_invalid_bd_state_preserves_metadata_with_only_dolt_database(
    tmp_path: Path,
) -> None:
    """``metadata.json`` with a valid ``dolt_database`` is what
    ``bd init`` actually writes — and it does NOT include
    ``issue_prefix`` (that's in ``config.yaml``). Earlier code wiped
    such metadata as "half-init", which broke fresh bd installs.
    Verify the cleanup leaves a valid bd-written metadata alone."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    metadata = {
        "database": "dolt",
        "backend": "dolt",
        "dolt_mode": "embedded",
        "dolt_database": "myproj",
        "project_id": "abc",
    }
    (beads / "metadata.json").write_text(json.dumps(metadata))
    embedded = beads / "embeddeddolt"
    embedded.mkdir()
    (embedded / "data").write_text("real")

    _clear_invalid_bd_state(tmp_path)

    assert (beads / "metadata.json").exists()
    assert embedded.exists()
    assert (embedded / "data").read_text() == "real"


def test_clear_invalid_bd_state_wipes_config_json_on_invalid_metadata(
    tmp_path: Path,
) -> None:
    """Legacy ``config.json`` (older bd versions used JSON before
    switching to YAML). When metadata is invalid the cleanup wipes
    both formats defensively."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    # Trigger cleanup via "dolt dir present, metadata missing" — the
    # form (4) half-init we actually encounter in the wild. Don't seed
    # metadata.json since bd-written metadata-with-only-dolt_database
    # is VALID under the current contract.
    (beads / "embeddeddolt").mkdir()
    (beads / "config.json").write_text(
        json.dumps({"sync": {"remote": "git+https://github.com/x/y.git"}})
    )

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "config.json").exists()
    assert not (beads / "embeddeddolt").exists()


def test_clear_invalid_bd_state_wipes_issues_jsonl_on_invalid_metadata(
    tmp_path: Path,
) -> None:
    """Stale ``issues.jsonl`` from a previous half-init is wiped so the
    next ``bd bootstrap`` doesn't take the unwanted import path."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "embeddeddolt").mkdir()  # form (4) trigger
    (beads / "issues.jsonl").write_text("{}\n")

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "issues.jsonl").exists()


def test_clear_invalid_bd_state_wipes_dolt_dir_with_no_metadata(
    tmp_path: Path,
) -> None:
    """Server-mode ``dolt/`` directory present with no ``metadata.json``
    is a half-init from a previous failed attempt — must trigger the
    full wipe so the next ``bd init`` starts clean. Was the
    actually-encountered failure mode that survived earlier rounds of
    cleanup tightening (the previous trigger required metadata to
    EXIST and be invalid; a missing metadata file was a no-op)."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    server_dir = beads / "dolt"
    server_dir.mkdir()
    (server_dir / "data").write_text("stale")
    (beads / "config.yaml").write_text(
        "sync:\n  remote: git+https://github.com/x/y.git\n"
    )
    (beads / "interactions.jsonl").write_text("")

    _clear_invalid_bd_state(tmp_path)

    assert not server_dir.exists()
    assert not (beads / "config.yaml").exists()
    assert not (beads / "interactions.jsonl").exists()


def test_clear_invalid_bd_state_wipes_embeddeddolt_with_no_metadata(
    tmp_path: Path,
) -> None:
    """Same trigger but for embedded-mode (``embeddeddolt/``)."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "embeddeddolt").mkdir()
    (beads / "config.yaml").write_text("sync:\n  remote: x\n")

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "embeddeddolt").exists()
    assert not (beads / "config.yaml").exists()


def test_clear_invalid_bd_state_wipes_config_yaml(tmp_path: Path) -> None:
    """bd uses ``config.yaml`` (not ``.json``) for project config, and
    that's where ``sync.remote`` lives. Wiping ``config.json`` alone
    leaves ``sync.remote`` in place and bd's next init still tries to
    clone from a non-Dolt git remote."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    # Trigger via form (4): dolt dir present, no metadata.json.
    (beads / "embeddeddolt").mkdir()
    (beads / "config.yaml").write_text(
        "sync:\n  remote: git+https://github.com/x/y.git\n"
    )

    _clear_invalid_bd_state(tmp_path)

    assert not (beads / "config.yaml").exists()


def test_clear_invalid_bd_state_no_op_when_no_dolt_dir(tmp_path: Path) -> None:
    """A ``.beads/`` with only ``hooks/`` and ``README.md`` — and no
    actual database directory — is not a half-init; it's just a project
    that has bd hooks installed but no DB yet. Must not wipe anything."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    hooks = beads / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_text("#!/bin/sh\n")
    (beads / "README.md").write_text("docs")

    _clear_invalid_bd_state(tmp_path)

    assert hooks.is_dir()
    assert (beads / "README.md").is_file()


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
