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


def _mock_session(
    models: object = None,
    config_options: object = None,
) -> MagicMock:
    """Create a mock session with optional models/config_options."""
    session = MagicMock()
    session.session_id = "sess-health"
    session.models = models
    session.config_options = config_options
    return session


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
        mock_conn.new_session = AsyncMock(return_value=_mock_session())
        mock_conn.cancel = AsyncMock(return_value=None)
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


class TestModelValidation:
    """Preflight model validation via new_session()."""

    @pytest.mark.asyncio
    async def test_rejects_unavailable_model(self) -> None:
        """Preflight fails when a configured model is not available."""
        model_obj = MagicMock(model_id="sonnet")
        models = MagicMock(available_models=[model_obj])
        session = _mock_session(models=models)

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"nonexistent"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.cancel = AsyncMock(return_value=None)
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
        assert "nonexistent" in result.errors[0]
        assert "sonnet" in result.errors[0]

    @pytest.mark.asyncio
    async def test_error_lists_available_models(self) -> None:
        """Error message includes all available model IDs."""
        m1 = MagicMock(model_id="haiku")
        m2 = MagicMock(model_id="opus")
        m3 = MagicMock(model_id="sonnet")
        models = MagicMock(available_models=[m1, m2, m3])
        session = _mock_session(models=models)

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"gpt-5"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "haiku" in result.errors[0]
        assert "opus" in result.errors[0]
        assert "sonnet" in result.errors[0]

    @pytest.mark.asyncio
    async def test_multiple_invalid_models_all_reported(self) -> None:
        """Each invalid model produces a separate error."""
        model_obj = MagicMock(model_id="sonnet")
        models = MagicMock(available_models=[model_obj])
        session = _mock_session(models=models)

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"bad-one", "bad-two"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert len(result.errors) == 2
        error_text = " ".join(result.errors)
        assert "bad-one" in error_text
        assert "bad-two" in error_text

    @pytest.mark.asyncio
    async def test_passes_when_model_matches(self) -> None:
        """Preflight passes when all models are in available list."""
        model_obj = MagicMock(model_id="sonnet")
        models = MagicMock(available_models=[model_obj])
        session = _mock_session(models=models)

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"sonnet"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_skips_when_no_models_to_validate(self) -> None:
        """No models to validate → skip session, pass."""
        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            # models_to_validate defaults to empty frozenset
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
        # Should not have called new_session since no models to validate
        mock_conn.new_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_models_advertised(self) -> None:
        """No models advertised by provider → skip validation, pass."""
        session = _mock_session()  # models=None, config_options=None

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"any-model"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_session_failure_not_fatal(self) -> None:
        """new_session() failure doesn't fail the health check."""
        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"sonnet"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(
            side_effect=Exception("session failed"),
        )

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        # Session failure is non-fatal — health check still passes
        assert result.success is True

    @pytest.mark.asyncio
    async def test_resolves_semantic_model_before_validation(self) -> None:
        """Preflight resolves 'opus' to 'default' via name-based matching."""
        m1 = MagicMock(model_id="default")
        m1.name = "Claude Opus 4.6"
        m2 = MagicMock(model_id="sonnet")
        m2.name = "Claude Sonnet 4.6"
        models = MagicMock(available_models=[m1, m2])
        session = _mock_session(models=models)

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"opus"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        # "opus" resolves to "default" which IS available → pass
        assert result.success is True

    @pytest.mark.asyncio
    async def test_does_not_resolve_to_extended_variant(self) -> None:
        """Preflight does NOT resolve 'opus' to 'opus[1m]' (different cost)."""
        m1 = MagicMock(model_id="default")
        m1.name = None
        m2 = MagicMock(model_id="opus[1m]")
        m2.name = None
        m3 = MagicMock(model_id="sonnet")
        m3.name = None
        models = MagicMock(available_models=[m1, m2, m3])
        session = _mock_session(models=models)

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"opus"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        # "opus" does NOT resolve to "opus[1m]" — different model → fail
        assert result.success is False
        assert "opus" in result.errors[0]
