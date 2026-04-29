"""Unit tests for AcpProviderHealthCheck."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.config import AgentProviderConfig, PermissionMode
from maverick.runners.provider_health import AcpProviderHealthCheck

_MOD = "maverick.runners.provider_health"
_WHICH = f"{_MOD}.shutil.which"
_SPAWN = "acp.spawn_agent_process"
_ACCUMULATED = "maverick.executor.acp_client.MaverickAcpClient.get_accumulated_text"


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
        mock_conn.prompt = AsyncMock(return_value=None)
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
            patch(_ACCUMULATED, return_value="ok"),
        ):
            result = await hc.validate()

        assert result.success is True
        assert result.component == "ACP:claude"
        assert result.duration_ms >= 0
        # The prompt-test step ran
        mock_conn.prompt.assert_awaited_once()


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
        mock_conn.prompt = AsyncMock(return_value=None)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
            patch(_ACCUMULATED, return_value="ok"),
        ):
            result = await hc.validate()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_no_models_to_validate_still_runs_prompt_test(self) -> None:
        """Even without configured models we still create a session and
        run the prompt test — that's the whole point of the prompt step,
        catching providers that can negotiate but won't generate."""
        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            # models_to_validate defaults to empty frozenset
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=_mock_session())
        mock_conn.prompt = AsyncMock(return_value=None)
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
            patch(_ACCUMULATED, return_value="ok"),
        ):
            result = await hc.validate()

        assert result.success is True
        mock_conn.new_session.assert_awaited_once()
        mock_conn.prompt.assert_awaited_once()

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
        mock_conn.prompt = AsyncMock(return_value=None)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
            patch(_ACCUMULATED, return_value="ok"),
        ):
            result = await hc.validate()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_session_failure_is_fatal(self) -> None:
        """new_session() failure now fails the health check.

        Previously this was non-fatal: if a provider couldn't even
        create a session, we'd still mark it healthy. That hid real
        provider problems behind a green preflight, so the prompt-test
        rework treats session-creation failure as fatal too.
        """
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

        assert result.success is False
        assert "session creation failed" in result.errors[0]
        assert "session failed" in result.errors[0]

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
        mock_conn.prompt = AsyncMock(return_value=None)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
            patch(_ACCUMULATED, return_value="ok"),
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


class TestMcpToolCallProbe:
    """Coverage for the opt-in MCP tool-call probe (``test_mcp_tool_call=True``).

    The probe spins up a real ``AgentToolGateway`` and uses the live
    ACP connection, so we mock the connection but let the gateway run
    for real — that's the part most likely to break in production.
    """

    def _build_conn_with_handler_capture(
        self,
        *,
        invoke_handler_with: dict[str, object] | None,
    ) -> MagicMock:
        """Build a mock conn whose second ``new_session`` + ``prompt``
        invokes the registered MCP handler (or doesn't, depending on
        ``invoke_handler_with``).

        This simulates a well-behaved provider that calls the
        MCP-hosted tool when prompted (vs a misbehaving one that doesn't).
        The connection records both new_session calls so the test can
        assert MCP attachment landed on the second one.
        """
        from maverick.tools.agent_inbox.gateway import AgentToolGateway

        conn = MagicMock()
        conn.initialize = AsyncMock(return_value=None)
        conn.cancel = AsyncMock(return_value=None)

        sessions = [_mock_session(), _mock_session()]
        sessions[0].session_id = "sess-prompt"
        sessions[1].session_id = "sess-mcp"
        conn.new_session = AsyncMock(side_effect=sessions)

        async def _prompt(prompt: object, session_id: str) -> None:  # type: ignore[no-untyped-def]
            if session_id != "sess-mcp":
                return
            # Simulate the agent calling the MCP tool by reaching into the
            # gateway and invoking the registered handler directly.
            if invoke_handler_with is None:
                return
            for gw_inst in AgentToolGateway._instances_for_test:  # type: ignore[attr-defined]
                for route in gw_inst._routes.values():
                    await route.handler("submit_health_check", invoke_handler_with)

        conn.prompt = AsyncMock(side_effect=_prompt)
        return conn

    @pytest.mark.asyncio
    async def test_records_failure_when_tool_not_called(self) -> None:
        """Provider passes basic prompt but never calls the MCP tool.
        That's the silent-failure pattern we built this probe to catch."""
        # Sidestep the gateway-spy plumbing — we just need the probe to
        # go through with no handler invocation.
        hc = AcpProviderHealthCheck(
            provider_name="silent",
            provider_config=_make_config(),
            test_mcp_tool_call=True,
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(side_effect=[_mock_session(), _mock_session()])
        mock_conn.prompt = AsyncMock(return_value=None)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
            patch(_ACCUMULATED, return_value="ok"),
        ):
            result = await hc.validate()

        assert result.success is False
        # Both sessions were created — basic prompt + MCP probe.
        assert mock_conn.new_session.await_count == 2
        # The MCP attachment landed on the second new_session.
        second_call_kwargs = mock_conn.new_session.await_args_list[1].kwargs
        assert "mcp_servers" in second_call_kwargs
        attached = second_call_kwargs["mcp_servers"]
        assert len(attached) == 1
        # And the failure message names the suspect.
        assert "submit_health_check" in result.errors[0]

    @pytest.mark.asyncio
    async def test_passes_when_tool_call_lands(self) -> None:
        """Provider calls the diagnostic tool — probe reports success."""

        hc = AcpProviderHealthCheck(
            provider_name="good",
            provider_config=_make_config(),
            test_mcp_tool_call=True,
        )

        # Track tool-call invocation by hooking the registered handler.
        # We can't reach into the gateway from outside, so simulate by
        # capturing the handler reference passed to gateway.register and
        # invoking it inside the prompt mock.
        from maverick.tools.agent_inbox import gateway as gw_module

        original_register = gw_module.AgentToolGateway.register
        captured: dict[str, object] = {}

        async def spy_register(self, uid, tool_names, handler):  # type: ignore[no-untyped-def]
            captured["handler"] = handler
            return await original_register(self, uid, tool_names, handler)

        async def call_handler_during_prompt(*_args: object, **kwargs: object) -> None:
            handler = captured.get("handler")
            if handler is not None and kwargs.get("session_id") == "sess-mcp":
                await handler("submit_health_check", {"status": "ok"})  # type: ignore[misc]

        sessions = [_mock_session(), _mock_session()]
        sessions[0].session_id = "sess-prompt"
        sessions[1].session_id = "sess-mcp"

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(side_effect=sessions)
        mock_conn.prompt = AsyncMock(side_effect=call_handler_during_prompt)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
            patch(_ACCUMULATED, return_value="ok"),
            patch.object(gw_module.AgentToolGateway, "register", spy_register),
        ):
            result = await hc.validate()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_probe_skipped_when_flag_off(self) -> None:
        """Default ``test_mcp_tool_call=False`` skips the probe entirely.
        Only the basic prompt session is created."""
        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            test_mcp_tool_call=False,
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=_mock_session())
        mock_conn.prompt = AsyncMock(return_value=None)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
            patch(_ACCUMULATED, return_value="ok"),
        ):
            result = await hc.validate()

        assert result.success is True
        # Only ONE session — no MCP probe was attempted.
        assert mock_conn.new_session.await_count == 1


class TestPromptStep:
    """Coverage for the post-init "say ok" prompt verification."""

    def _setup_mocks(
        self,
        *,
        prompt_side_effect: object = None,
        prompt_return: object = None,
    ) -> tuple[MagicMock, MagicMock]:
        """Build a (mock_conn, mock_ctx) pair with all the protocol stages
        wired up. Caller supplies the prompt behaviour they want to exercise."""
        session = _mock_session()
        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        if prompt_side_effect is not None:
            mock_conn.prompt = AsyncMock(side_effect=prompt_side_effect)
        else:
            mock_conn.prompt = AsyncMock(return_value=prompt_return)
        mock_conn.cancel = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=(mock_conn, MagicMock()),
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        return mock_conn, mock_ctx

    @pytest.mark.asyncio
    async def test_empty_response_fails_with_auth_hint(self) -> None:
        """Provider negotiates the protocol but streams zero text — the
        gemini-without-authenticate failure mode. We surface a clear
        auth-related error message."""
        hc = AcpProviderHealthCheck(
            provider_name="gemini",
            provider_config=_make_config(command=["gemini", "--acp"]),
        )
        _, mock_ctx = self._setup_mocks()

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
            patch(_ACCUMULATED, return_value=""),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "no content" in result.errors[0]
        assert "GEMINI_API_KEY" in result.errors[0]

    @pytest.mark.asyncio
    async def test_prompt_timeout_fails_with_clear_message(self) -> None:
        """Provider hangs during prompt — we hit our inner timeout."""
        import asyncio as _asyncio

        async def hang(*_args: object, **_kwargs: object) -> None:
            await _asyncio.sleep(60)

        # Outer must be larger than the inner 20s prompt timeout so we
        # actually surface the prompt-specific message instead of the
        # generic outer timeout.
        hc = AcpProviderHealthCheck(
            provider_name="gemini",
            provider_config=_make_config(command=["gemini", "--acp"]),
            timeout=30.0,
        )
        _, mock_ctx = self._setup_mocks(prompt_side_effect=hang)

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "timed out" in result.errors[0]
        assert "auth" in result.errors[0] or "rate-limited" in result.errors[0]

    @pytest.mark.asyncio
    async def test_prompt_exception_propagates_clearly(self) -> None:
        """A generic exception during prompt surfaces with the provider name."""
        hc = AcpProviderHealthCheck(
            provider_name="copilot",
            provider_config=_make_config(command=["copilot", "--acp", "--stdio"]),
        )
        _, mock_ctx = self._setup_mocks(
            prompt_side_effect=Exception("HTTP 401 Unauthorized"),
        )

        with (
            patch(_WHICH, return_value="/usr/bin/x"),
            patch(_SPAWN, return_value=mock_ctx),
        ):
            result = await hc.validate()

        assert result.success is False
        assert "copilot" in result.errors[0]
        assert "HTTP 401" in result.errors[0]

    @pytest.mark.asyncio
    async def test_prompt_skipped_when_model_validation_already_failed(
        self,
    ) -> None:
        """No point testing a model that doesn't exist — skip the prompt
        when model validation already produced an error."""
        m1 = MagicMock(model_id="sonnet")
        models = MagicMock(available_models=[m1])
        session = _mock_session(models=models)

        hc = AcpProviderHealthCheck(
            provider_name="claude",
            provider_config=_make_config(),
            models_to_validate=frozenset({"nonexistent"}),
        )

        mock_conn = MagicMock()
        mock_conn.initialize = AsyncMock(return_value=None)
        mock_conn.new_session = AsyncMock(return_value=session)
        mock_conn.prompt = AsyncMock(return_value=None)
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
        # Failure is the model-availability error, not a prompt error
        assert "not available" in result.errors[0]
        # Prompt was never called
        mock_conn.prompt.assert_not_called()
