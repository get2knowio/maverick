"""Unit tests for preflight validation actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.library.actions.preflight import (
    PreflightCheckResult,
    PreflightError,
    run_preflight_checks,
)


class TestPreflightCheckResult:
    """Tests for PreflightCheckResult dataclass."""

    def test_to_dict(self) -> None:
        """Test PreflightCheckResult.to_dict() conversion."""
        result = PreflightCheckResult(
            success=True,
            providers_available=True,
            git_available=True,
            github_cli_available=True,
            validation_tools_available=True,
            errors=("error1",),
            warnings=("warning1",),
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["providers_available"] is True
        assert result_dict["errors"] == ["error1"]
        assert result_dict["warnings"] == ["warning1"]


class TestRunPreflightChecks:
    """Tests for run_preflight_checks action."""

    @pytest.mark.asyncio
    async def test_skip_all_checks_returns_success(self) -> None:
        """Test that skipping all checks returns success."""
        result = await run_preflight_checks(
            check_providers=False,
            check_git=False,
            check_github=False,
            check_validation_tools=False,
            fail_on_error=False,
        )

        assert result.success is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_git_not_found_fails(self) -> None:
        """Test that missing git binary fails the check."""
        with patch("shutil.which", return_value=None):
            result = await run_preflight_checks(
                check_providers=False,
                check_git=True,
                check_github=False,
                check_validation_tools=False,
                fail_on_error=False,
            )

        assert result.success is False
        assert result.git_available is False
        assert any("not installed" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_git_identity_not_configured_fails(self) -> None:
        """Test that missing git user.name fails the check."""
        # Mock shutil.which to return git path
        with patch("shutil.which", return_value="/usr/bin/git"):
            # Mock subprocess for git config user.name returning empty
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))

            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await run_preflight_checks(
                    check_providers=False,
                    check_git=True,
                    check_github=False,
                    check_validation_tools=False,
                    fail_on_error=False,
                )

        assert result.success is False
        assert result.git_available is False
        assert any("user.name" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_git_user_email_not_configured_fails(self) -> None:
        """Test that missing git user.email fails the check."""
        # Mock shutil.which to return git path
        with patch("shutil.which", return_value="/usr/bin/git"):
            # First call (user.name) succeeds, second call (user.email) fails
            call_count = [0]

            async def mock_communicate():
                call_count[0] += 1
                if call_count[0] == 1:
                    return (b"Test User", b"")  # user.name succeeds
                else:
                    return (b"", b"")  # user.email fails

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = mock_communicate

            # Second proc for email check fails
            mock_proc_fail = MagicMock()
            mock_proc_fail.returncode = 1
            mock_proc_fail.communicate = AsyncMock(return_value=(b"", b""))

            proc_index = [0]

            async def create_subprocess(*args, **kwargs):
                idx = proc_index[0]
                proc_index[0] += 1
                if idx == 0:
                    # user.name check - succeeds
                    p = MagicMock()
                    p.returncode = 0
                    p.communicate = AsyncMock(return_value=(b"Test User", b""))
                    return p
                else:
                    # user.email check - fails
                    p = MagicMock()
                    p.returncode = 1
                    p.communicate = AsyncMock(return_value=(b"", b""))
                    return p

            with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
                result = await run_preflight_checks(
                    check_providers=False,
                    check_git=True,
                    check_github=False,
                    check_validation_tools=False,
                    fail_on_error=False,
                )

        assert result.success is False
        assert result.git_available is False
        assert any("user.email" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_git_identity_configured_succeeds(self) -> None:
        """Test that properly configured git identity passes the check."""
        # Mock shutil.which to return git path
        with patch("shutil.which", return_value="/usr/bin/git"):

            async def create_subprocess(*args, **kwargs):
                p = MagicMock()
                p.returncode = 0
                p.communicate = AsyncMock(return_value=(b"configured_value", b""))
                return p

            with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
                result = await run_preflight_checks(
                    check_providers=False,
                    check_git=True,
                    check_github=False,
                    check_validation_tools=False,
                    fail_on_error=False,
                )

        assert result.git_available is True
        # No git-related errors
        assert not any("user.name" in e or "user.email" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_fail_on_error_raises_preflight_error(self) -> None:
        """Test that fail_on_error=True raises PreflightError."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(PreflightError) as exc_info:
                await run_preflight_checks(
                    check_providers=False,
                    check_git=True,
                    check_github=False,
                    check_validation_tools=False,
                    fail_on_error=True,
                )

        assert "not installed" in str(exc_info.value)
        assert len(exc_info.value.errors) > 0

    @pytest.mark.asyncio
    async def test_git_identity_check_timeout_adds_warning(self) -> None:
        """Test that timeout during git identity check adds a warning."""

        with patch("shutil.which", return_value="/usr/bin/git"):

            async def create_subprocess(*args, **kwargs):
                raise TimeoutError()

            with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
                result = await run_preflight_checks(
                    check_providers=False,
                    check_git=True,
                    check_github=False,
                    check_validation_tools=False,
                    fail_on_error=False,
                )

        # Timeout should add a warning, not an error
        assert any("timed out" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_provided_config_is_used(self) -> None:
        """config= skips load_config() and uses the provided config."""
        from maverick.config import AgentProviderConfig, MaverickConfig

        custom_config = MaverickConfig(
            agent_providers={
                "test-provider": AgentProviderConfig(
                    command=["echo", "test"],
                    default=True,
                ),
            },
        )

        with patch("maverick.library.actions.preflight.load_config") as mock_load:
            result = await run_preflight_checks(
                check_providers=False,
                check_git=False,
                check_github=False,
                check_validation_tools=False,
                fail_on_error=False,
                config=custom_config,
            )

        # load_config should NOT have been called
        mock_load.assert_not_called()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_no_config_falls_back_to_load_config(self) -> None:
        """Test that omitting config= falls back to load_config()."""
        with patch("maverick.library.actions.preflight.load_config") as mock_load:
            mock_load.return_value = MagicMock(
                agent_providers={},
                validation=MagicMock(
                    sync_cmd=None,
                    format_cmd=["ruff", "format", "."],
                    lint_cmd=["ruff", "check", "--fix", "."],
                    typecheck_cmd=["mypy", "."],
                    test_cmd=["pytest", "-x", "--tb=short"],
                ),
                preflight=MagicMock(custom_tools=[]),
                agents=MagicMock(values=MagicMock(return_value=[])),
                model=MagicMock(model_id="test", model_fields_set=set()),
            )
            await run_preflight_checks(
                check_providers=False,
                check_git=False,
                check_github=False,
                check_validation_tools=False,
                fail_on_error=False,
            )

        mock_load.assert_called_once()
