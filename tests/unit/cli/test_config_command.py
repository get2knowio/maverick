"""Unit tests for the config CLI command.

Tests config command functionality:
- Config init command (deprecated, delegates to 'maverick init')
- Config show command with different formats
- Config edit command
- Config validate command
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli

# =============================================================================
# Config Init Command Tests (T069-T070)
# NOTE: Since T044-T046, 'config init' is deprecated and delegates to 'maverick init'.
# These tests verify the deprecation/delegation behavior.
# =============================================================================


def test_config_init_delegates_to_init_command(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T069 (updated): Test 'config init' delegates to 'maverick init'."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock the init module and ctx.invoke to verify delegation
    mock_init_module = MagicMock()
    mock_init_cmd = MagicMock()
    mock_init_module.init = mock_init_cmd

    with patch.dict("sys.modules", {"maverick.cli.commands.init": mock_init_module}):
        with patch("click.Context.invoke") as mock_invoke:
            cli_runner.invoke(cli, ["config", "init"])

    # Verify init command was invoked (delegation works)
    assert mock_invoke.call_count >= 1


def test_config_init_shows_deprecation_in_docstring(
    cli_runner: CliRunner,
) -> None:
    """Test config init has deprecation notice in docstring."""
    from maverick.cli.commands.config import config_init

    callback = config_init.callback
    assert callback.__doc__ is not None
    assert "deprecated" in callback.__doc__.lower()


def test_config_init_with_existing_file_delegates_to_init(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T069 (updated): Test config init with existing file still delegates."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create existing config
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("# Existing config\n")

    mock_init_module = MagicMock()
    mock_init_cmd = MagicMock()
    mock_init_module.init = mock_init_cmd

    with patch.dict("sys.modules", {"maverick.cli.commands.init": mock_init_module}):
        with patch("click.Context.invoke") as mock_invoke:
            cli_runner.invoke(cli, ["config", "init"])

    # Still delegates to init command (let init handle the error)
    assert mock_invoke.call_count >= 1


def test_config_init_force_passes_to_init(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T070 (updated): Test config init --force passes flag to init."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    mock_init_module = MagicMock()
    mock_init_cmd = MagicMock()
    mock_init_module.init = mock_init_cmd

    with patch.dict("sys.modules", {"maverick.cli.commands.init": mock_init_module}):
        with patch("click.Context.invoke") as mock_invoke:
            cli_runner.invoke(cli, ["config", "init", "--force"])

    # Verify invoke was called with force=True
    found_force = False
    for call in mock_invoke.call_args_list:
        if call.kwargs and call.kwargs.get("force") is True:
            found_force = True
            break
    assert found_force, "force=True not passed to init command"


# NOTE: UTF-8 encoding test removed since 'config init' now delegates to
# 'maverick init' - the encoding behavior is tested in init command tests.


# =============================================================================
# Config Show Command Tests (T071-T072)
# =============================================================================


def test_config_show_displays_yaml(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T071: Test config show displays YAML - 'maverick config show'."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
github:
  owner: "test-org"
  repo: "test-repo"
verbosity: "info"
""")

    result = cli_runner.invoke(cli, ["config", "show"])

    # Should succeed
    assert result.exit_code == 0
    # Should show YAML content
    assert "github:" in result.output
    assert "test-org" in result.output
    assert "test-repo" in result.output


def test_config_show_format_json(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T072: Test config show --format json outputs JSON."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
github:
  owner: "test-org"
  repo: "test-repo"
verbosity: "info"
""")

    result = cli_runner.invoke(cli, ["config", "show", "--format", "json"])

    # Should succeed
    assert result.exit_code == 0
    # Should be valid JSON
    try:
        data = json.loads(result.output)
        assert "github" in data
        assert data["github"]["owner"] == "test-org"
        assert data["github"]["repo"] == "test-repo"
    except json.JSONDecodeError:
        pytest.fail("Output is not valid JSON")


def test_config_show_format_short_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T072: Test config show -f json (short flag)."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text('verbosity: "debug"\n')

    result = cli_runner.invoke(cli, ["config", "show", "-f", "json"])

    # Should succeed
    assert result.exit_code == 0
    # Should be valid JSON
    data = json.loads(result.output)
    assert data is not None


# =============================================================================
# Config Edit Command Tests (T073)
# =============================================================================


def test_config_edit_opens_editor(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T073: Test config edit opens editor - 'maverick config edit'."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("# Test config\n")

    # Mock click.edit to simulate editor opening
    with patch("click.edit") as mock_edit:
        mock_edit.return_value = "# Modified config\n"

        result = cli_runner.invoke(cli, ["config", "edit"])

        # Should succeed
        assert result.exit_code == 0
        # Should call click.edit with file content
        mock_edit.assert_called_once()


def test_config_edit_user_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T073: Test config edit --user opens user config."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create user config directory and file
    user_config_dir = temp_dir / ".config" / "maverick"
    user_config_dir.mkdir(parents=True, exist_ok=True)
    user_config_file = user_config_dir / "config.yaml"
    user_config_file.write_text("# User config\n")

    # Mock click.edit
    with patch("click.edit") as mock_edit:
        mock_edit.return_value = "# Modified user config\n"

        result = cli_runner.invoke(cli, ["config", "edit", "--user"])

        # Should succeed
        assert result.exit_code == 0
        # Should call click.edit
        mock_edit.assert_called_once()


def test_config_edit_creates_file_if_not_exists(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T073: Test config edit creates file if it doesn't exist."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Ensure no config exists
    config_file = temp_dir / "maverick.yaml"
    assert not config_file.exists()

    # Mock click.edit
    with patch("click.edit") as mock_edit:
        mock_edit.return_value = "# New config\n"

        result = cli_runner.invoke(cli, ["config", "edit"])

        # Should succeed
        assert result.exit_code == 0
        # Should call click.edit (with empty or None text)
        mock_edit.assert_called_once()


# =============================================================================
# Config Validate Command Tests (T074-T075)
# =============================================================================


def test_config_validate_with_valid_config(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T074: Test config validate with valid config."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create valid config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
github:
  owner: "test-org"
  repo: "test-repo"
  default_branch: "main"
verbosity: "info"
""")

    result = cli_runner.invoke(cli, ["config", "validate"])

    # Should succeed
    assert result.exit_code == 0
    # Should show validation success message
    assert "valid" in result.output.lower() or "success" in result.output.lower()


def test_config_validate_with_invalid_config(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T075: Test config validate with invalid config."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create invalid config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
model:
  max_tokens: -1
verbosity: "invalid_level"
""")

    result = cli_runner.invoke(cli, ["config", "validate"])

    # Should fail
    assert result.exit_code == 1
    # Should show validation error
    assert "error" in result.output.lower() or "invalid" in result.output.lower()


def test_config_validate_with_file_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T075: Test config validate --file option."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create custom config file
    custom_config = temp_dir / "custom.yaml"
    custom_config.write_text("""
github:
  owner: "custom-org"
verbosity: "debug"
""")

    result = cli_runner.invoke(
        cli, ["config", "validate", "--file", str(custom_config)]
    )

    # Should succeed
    assert result.exit_code == 0
    # Should show validation success
    assert "valid" in result.output.lower() or "success" in result.output.lower()


def test_config_validate_nonexistent_file(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T075: Test config validate with nonexistent file."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # No config file exists
    result = cli_runner.invoke(cli, ["config", "validate"])

    # Should still succeed (no project config = use defaults)
    assert result.exit_code == 0
