"""Unit tests for the `maverick init` Spec Kit install-offer flow (R7/US5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from maverick.init import _maybe_offer_speckit_install, install_speckit


class TestAlreadyInstalled:
    async def test_compatible_speckit_present_is_silent_no_offer(self, tmp_path: Path) -> None:
        specify_dir = tmp_path / ".specify"
        specify_dir.mkdir()
        (specify_dir / "init-options.json").write_text(
            '{"speckit_version": "0.14.0"}', encoding="utf-8"
        )

        with patch("click.confirm") as mock_confirm:
            result = await _maybe_offer_speckit_install(tmp_path, verbose=False)

        assert result is None
        mock_confirm.assert_not_called()


class TestInteractiveAccept:
    async def test_accept_invokes_installer_via_command_runner(self, tmp_path: Path) -> None:
        with (
            patch("sys.stdin") as mock_stdin,
            patch("click.confirm", return_value=True),
            patch(
                "maverick.init.install_speckit", new=AsyncMock(return_value=True)
            ) as mock_install,
        ):
            mock_stdin.isatty.return_value = True
            result = await _maybe_offer_speckit_install(tmp_path, verbose=False)

        assert result is True
        mock_install.assert_awaited_once_with(tmp_path)

    async def test_install_speckit_runs_pinned_uvx_command(self, tmp_path: Path) -> None:
        from maverick.runners.command import CommandRunner
        from maverick.runners.models import CommandResult

        async def fake_run(self: CommandRunner, cmd: list[str], **kwargs: object) -> CommandResult:
            fake_run.captured = cmd  # type: ignore[attr-defined]
            return CommandResult(returncode=0, stdout="", stderr="", duration_ms=10)

        with patch.object(CommandRunner, "run", new=fake_run):
            result = await install_speckit(tmp_path)

        assert result is True
        cmd = fake_run.captured  # type: ignore[attr-defined]
        assert cmd[0] == "uvx"
        assert "--from" in cmd
        assert any(arg.startswith("specify-cli==") for arg in cmd)
        assert cmd[cmd.index("specify") + 1 : cmd.index("specify") + 3] == ["init", "--here"]
        # Every flag that keeps the installer from blocking on a prompt
        # under CommandRunner — see `install_speckit`.
        assert "--force" in cmd
        assert cmd[cmd.index("--integration") + 1] == "claude"
        assert "--ignore-agent-tools" in cmd

    async def test_install_failure_returns_false(self, tmp_path: Path) -> None:
        from maverick.runners.command import CommandRunner
        from maverick.runners.models import CommandResult

        async def fake_run(self: CommandRunner, cmd: list[str], **kwargs: object) -> CommandResult:
            return CommandResult(returncode=1, stdout="", stderr="boom", duration_ms=10)

        with patch.object(CommandRunner, "run", new=fake_run):
            result = await install_speckit(tmp_path)

        assert result is False


class TestInteractiveDecline:
    async def test_decline_returns_none_and_does_not_install(self, tmp_path: Path) -> None:
        with (
            patch("sys.stdin") as mock_stdin,
            patch("click.confirm", return_value=False),
            patch("maverick.init.install_speckit", new=AsyncMock()) as mock_install,
        ):
            mock_stdin.isatty.return_value = True
            result = await _maybe_offer_speckit_install(tmp_path, verbose=False)

        assert result is None
        mock_install.assert_not_called()


class TestNonInteractive:
    async def test_non_tty_skips_offer_entirely(self, tmp_path: Path) -> None:
        with (
            patch("sys.stdin") as mock_stdin,
            patch("click.confirm") as mock_confirm,
            patch("maverick.init.install_speckit", new=AsyncMock()) as mock_install,
        ):
            mock_stdin.isatty.return_value = False
            result = await _maybe_offer_speckit_install(tmp_path, verbose=False)

        assert result is None
        mock_confirm.assert_not_called()
        mock_install.assert_not_called()


class TestIdempotentReinit:
    async def test_unsupported_version_still_offers_on_reinit(self, tmp_path: Path) -> None:
        """Present-but-incompatible version is not silently accepted —
        re-init still surfaces the offer (or notice) rather than treating
        "something is there" as good enough."""
        specify_dir = tmp_path / ".specify"
        specify_dir.mkdir()
        (specify_dir / "init-options.json").write_text(
            '{"speckit_version": "0.9.0"}', encoding="utf-8"
        )

        with (
            patch("sys.stdin") as mock_stdin,
            patch("click.confirm") as mock_confirm,
        ):
            mock_stdin.isatty.return_value = False
            result = await _maybe_offer_speckit_install(tmp_path, verbose=False)

        assert result is None
        mock_confirm.assert_not_called()  # non-interactive: notice only, no prompt

    async def test_compatible_reinit_never_calls_confirm(self, tmp_path: Path) -> None:
        specify_dir = tmp_path / ".specify"
        specify_dir.mkdir()
        (specify_dir / "init-options.json").write_text(
            '{"speckit_version": "0.14.0"}', encoding="utf-8"
        )

        with patch("sys.stdin") as mock_stdin, patch("click.confirm") as mock_confirm:
            mock_stdin.isatty.return_value = True
            result = await _maybe_offer_speckit_install(tmp_path, verbose=True)

        assert result is None
        mock_confirm.assert_not_called()
