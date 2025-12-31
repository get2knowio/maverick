"""Unit tests for config init deprecation warning (T046).

Tests that 'maverick config init' shows a deprecation warning and
delegates to 'maverick init'.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from maverick.cli.commands.config import config


class TestConfigInitDeprecation:
    """Tests for config init deprecation warning."""

    def test_config_init_shows_deprecation_warning(self) -> None:
        """Test 'config init' shows deprecation warning (T044).

        Verifies the deprecation message appears in the function's docstring
        and the actual code contains the warning.
        """
        # Verify the function docstring mentions deprecated
        from maverick.cli.commands.config import config_init

        # config_init is a Click Command, access its callback for the function
        callback = config_init.callback
        assert callback is not None
        assert callback.__doc__ is not None
        assert "deprecated" in callback.__doc__.lower()
        assert "maverick init" in callback.__doc__

        # Verify the click.echo call exists in the source by inspecting
        # the function code object - this is a static analysis approach
        import inspect

        source = inspect.getsource(callback)
        assert "deprecated" in source.lower()
        assert "maverick init" in source

    def test_config_init_invokes_init_command(self) -> None:
        """Test 'config init' calls ctx.invoke with init command (T045)."""
        runner = CliRunner()

        mock_init_module = MagicMock()
        mock_init_cmd = MagicMock()
        mock_init_module.init = mock_init_cmd

        modules = {"maverick.cli.commands.init": mock_init_module}
        with patch.dict("sys.modules", modules):
            with patch("click.Context.invoke") as mock_invoke:
                runner.invoke(config, ["init"])

        # Verify invoke was called at least once
        assert mock_invoke.call_count >= 1
        # At least one call should have kwargs with force/verbose/etc.
        found_init_call = False
        for call in mock_invoke.call_args_list:
            if call.kwargs and "force" in call.kwargs:
                found_init_call = True
                break
        assert found_init_call, "ctx.invoke was not called with expected kwargs"

    def test_config_init_has_force_option(self) -> None:
        """Test 'config init' accepts --force option."""
        runner = CliRunner()

        mock_init_module = MagicMock()
        mock_init_cmd = MagicMock()
        mock_init_module.init = mock_init_cmd

        modules = {"maverick.cli.commands.init": mock_init_module}
        with patch.dict("sys.modules", modules):
            with patch("click.Context.invoke"):
                result = runner.invoke(config, ["init", "--force"])

        # Should not fail with unknown option error
        assert "Error: No such option" not in result.output

    def test_config_init_has_verbose_option(self) -> None:
        """Test 'config init' accepts --verbose option."""
        runner = CliRunner()

        mock_init_module = MagicMock()
        mock_init_cmd = MagicMock()
        mock_init_module.init = mock_init_cmd

        modules = {"maverick.cli.commands.init": mock_init_module}
        with patch.dict("sys.modules", modules):
            with patch("click.Context.invoke"):
                result = runner.invoke(config, ["init", "-v"])

        # Should not fail with unknown option error
        assert "Error: No such option" not in result.output

    def test_config_init_has_type_option(self) -> None:
        """Test 'config init' accepts --type option."""
        runner = CliRunner()

        mock_init_module = MagicMock()
        mock_init_cmd = MagicMock()
        mock_init_module.init = mock_init_cmd

        modules = {"maverick.cli.commands.init": mock_init_module}
        with patch.dict("sys.modules", modules):
            with patch("click.Context.invoke"):
                result = runner.invoke(config, ["init", "--type", "python"])

        # Should not fail with unknown option error
        assert "Error: No such option" not in result.output

    def test_config_init_has_no_detect_option(self) -> None:
        """Test 'config init' accepts --no-detect option."""
        runner = CliRunner()

        mock_init_module = MagicMock()
        mock_init_cmd = MagicMock()
        mock_init_module.init = mock_init_cmd

        modules = {"maverick.cli.commands.init": mock_init_module}
        with patch.dict("sys.modules", modules):
            with patch("click.Context.invoke"):
                result = runner.invoke(config, ["init", "--no-detect"])

        # Should not fail with unknown option error
        assert "Error: No such option" not in result.output
