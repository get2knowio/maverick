"""Unit tests for AcpProviderHealthCheck."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.config import AgentProviderConfig, PermissionMode
from maverick.runners.provider_health import AcpProviderHealthCheck

_MOD = "maverick.runners.provider_health"
_WHICH = f"{_MOD}.shutil.which"
_SPAWN = "acp.spawn_agent_process"


def _make_config(
    command: list[str] | None = None,
    **kwargs: object,
) -> AgentProviderConfig:
    return AgentProviderConfig(
        command=command or ["claude-agent-acp"],
        permission_mode=PermissionMode.AUTO_APPROVE,
        default=True,
        **kwargs,  # type: ignore[arg-type]
    )


class TestBinaryNotFound:
    """Binary not on PATH → ValidationResult(success=False)."""

    @pytest.mark.asyncio
    async def test_binary_not_found(self) -> None:
        hc = AcpProviderHealthCheck(
            provider_name="test",
            provider_config=_make_config(
                command=["nonexistent-binary"],
            ),
        )
        with patch(_WHICH, return_value=None):
            result = await hc.validate()

        assert result.success is False
        assert "not found on PATH" in result.errors[0]
        assert result.component == "ACP:test"

    @pytest.mark.asyncio
    async def test_empty_command_list_fails(self) -> None:
        config = _make_config(command=["some-binary"])
        patched = config.model_copy(update={"command": []})

        hc = AcpProviderHealthCheck(
            provider_name="empty",
            provider_config=patched,
        )
        result = await hc.validate()

        assert result.success is False
        assert "empty command" in result.errors[0]


class TestSpawnFailure:
    """Spawn fails → ValidationResult(success=False)."""

    @pytest.mark.asyncio
    async def test_file_not_found_error(self) -> None:
        hc = AcpProviderHealthCheck(
            provider_name="bad",
            provider_config=_make_config(),
        )

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            side_effect=FileNotFoundError("not found"),
        )

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_os_error(self) -> None:
        hc = AcpProviderHealthCheck(
            provider_name="bad",
            provider_config=_make_config(),
        )

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            side_effect=OSError("permission denied"),
        )

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "permission denied" in result.errors[0]


class TestInitializeFailure:
    """Initialize handshake fails → success=False."""

    @pytest.mark.asyncio
    async def test_initialize_error(self) -> None:
        hc = AcpProviderHealthCheck(
            provider_name="auth-fail",
            provider_config=_make_config(),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(
            side_effect=Exception("auth failed"),
        )
        mock_proc = MagicMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, mock_proc),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "handshake failed" in result.errors[0]
        assert "auth failed" in result.errors[0]


class TestSuccess:
    """Full success path → ValidationResult(success=True)."""

    @pytest.mark.asyncio
    async def test_full_success(self) -> None:
        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_proc = MagicMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, mock_proc),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is True
        assert result.component == "ACP:claude"
        assert result.duration_ms >= 0


class TestTimeout:
    """Health check timeout → ValidationResult(success=False)."""

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        import asyncio

        hc = AcpProviderHealthCheck(
            provider_name="slow",
            provider_config=_make_config(),
            timeout=0.05,
        )

        async def slow_enter(
            *args: object,
            **kwargs: object,
        ) -> tuple[object, object]:
            await asyncio.sleep(10)
            return MagicMock(), MagicMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = slow_enter

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "timed out" in result.errors[0]


class TestDefaultModel:
    """Provider with default_model passes through to config."""

    def test_config_with_default_model(self) -> None:
        config = _make_config(default_model="gpt-4o")
        assert config.default_model == "gpt-4o"

    def test_config_without_default_model(self) -> None:
        config = _make_config()
        assert config.default_model is None
