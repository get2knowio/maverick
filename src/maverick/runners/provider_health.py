"""ACP provider health check — validates provider binary, auth, and protocol."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import os
import shutil
import time
from dataclasses import dataclass
from typing import Any

from maverick.config import AgentProviderConfig
from maverick.logging import get_logger
from maverick.runners.preflight import ValidationResult

__all__ = ["AcpProviderHealthCheck", "build_provider_health_checks"]

logger = get_logger(__name__)


def build_provider_health_checks(
    config: Any,
    *,
    timeout: float = 15.0,
) -> list[AcpProviderHealthCheck]:
    """Build one ``AcpProviderHealthCheck`` per configured provider.

    Bundles up the model-collection logic that was previously inlined in
    ``run_preflight_checks``: every provider gets its ``default_model``
    in its validation set, and the *default* provider additionally
    inherits the global ``config.model.model_id`` (when explicitly set)
    plus any per-agent ``model_id`` overrides.

    Shared by ``run_preflight_checks`` (the workflow preflight step) and
    ``maverick doctor`` (the standalone CLI command) so both surfaces
    test the exact same set.

    Args:
        config: A loaded ``MaverickConfig``.
        timeout: Per-provider health-check timeout in seconds. Default
            15s mirrors the workflow preflight.

    Returns:
        Health checks ordered by provider name (stable for display).
    """
    from maverick.executor.provider_registry import AgentProviderRegistry

    registry = AgentProviderRegistry.from_config(config.agent_providers)

    default_provider_name: str | None = None
    for name, pcfg in registry.items():
        if pcfg.default:
            default_provider_name = name
            break
    if default_provider_name is None and registry.items():
        default_provider_name = next(iter(registry.items()))[0]

    provider_models: dict[str, set[str]] = {}
    for name, pcfg in registry.items():
        models_set: set[str] = set()
        if pcfg.default_model:
            models_set.add(pcfg.default_model)
        provider_models[name] = models_set

    # Global ``model.model_id`` only counts when the user explicitly set
    # it — the Pydantic default (a Claude alias) is meaningless for
    # non-Claude providers.
    model_id_explicit = "model_id" in config.model.model_fields_set
    if default_provider_name and config.model.model_id and model_id_explicit:
        provider_models.setdefault(default_provider_name, set()).add(
            config.model.model_id,
        )

    if default_provider_name:
        for agent_cfg in config.agents.values():
            if agent_cfg.model_id:
                provider_models.setdefault(
                    default_provider_name,
                    set(),
                ).add(agent_cfg.model_id)

    return [
        AcpProviderHealthCheck(
            provider_name=name,
            provider_config=provider_cfg,
            models_to_validate=frozenset(provider_models.get(name, set())),
            timeout=timeout,
        )
        for name, provider_cfg in sorted(registry.items())
    ]


@dataclass(frozen=True, slots=True)
class AcpProviderHealthCheck:
    """Spawns an ACP provider, runs the initialize handshake, and tears down.

    Validates binary presence, auth, protocol compatibility, and model
    availability in one shot.

    Attributes:
        provider_name: Logical name for this provider (e.g. "claude").
        provider_config: Provider configuration with command and env.
        models_to_validate: Model IDs from maverick.yaml to check against
            this provider's available models. Collected from provider
            default_model, global model.model_id, and per-agent overrides.
        timeout: Maximum seconds for the entire health check.
    """

    provider_name: str
    provider_config: AgentProviderConfig
    models_to_validate: frozenset[str] = frozenset()
    timeout: float = 15.0

    async def validate(self) -> ValidationResult:
        """Run the ACP health check.

        Returns:
            ValidationResult with success=True if initialize handshake succeeds.
        """
        start_time = time.monotonic()
        component = f"ACP:{self.provider_name}"

        # Step 1: Check binary exists on PATH
        command_args = self.provider_config.command
        if not command_args:
            return ValidationResult(
                success=False,
                component=component,
                errors=(f"Provider '{self.provider_name}' has an empty command list",),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        binary = command_args[0]
        if shutil.which(binary) is None:
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"Binary '{binary}' for provider '{self.provider_name}' not found on PATH",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 2: Spawn process and run ACP initialize handshake
        try:
            result = await asyncio.wait_for(
                self._spawn_and_initialize(),
                timeout=self.timeout,
            )
            return result
        except TimeoutError:
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"Provider '{self.provider_name}' health check timed out "
                    f"after {self.timeout}s",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

    async def _spawn_and_initialize(self) -> ValidationResult:
        """Spawn the ACP subprocess and run the initialize handshake."""
        from acp import PROTOCOL_VERSION, spawn_agent_process
        from acp.schema import ClientCapabilities, Implementation

        start_time = time.monotonic()
        component = f"ACP:{self.provider_name}"

        command_args = self.provider_config.command
        if not command_args:
            raise ValueError(f"Provider {self.provider_name} has no command")
        command = command_args[0]
        args = tuple(command_args[1:])

        extra_env = dict(self.provider_config.env) if self.provider_config.env else {}
        env = {**os.environ, **extra_env}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        client_info = Implementation(
            name="maverick-healthcheck",
            version=importlib.metadata.version("maverick-cli"),
        )

        # We need a minimal client for spawn_agent_process. Import the real
        # one to satisfy the protocol, but we don't need full functionality.
        from maverick.executor.acp_client import MaverickAcpClient

        client = MaverickAcpClient(  # type: ignore[abstract]
            permission_mode=self.provider_config.permission_mode,
        )

        try:
            # Match the executor's stdio buffer (1 MiB). Without this the
            # default 64 KiB asyncio.StreamReader limit overflows on
            # agents that emit large initialize responses (opencode's
            # provider/model catalogue, gemini's authMethods + capabilities)
            # and the receive loop crashes with LimitOverrunError before
            # the health check even gets a result back.
            from maverick.executor._subprocess import STDIO_BUFFER_LIMIT

            ctx = spawn_agent_process(
                client,
                command,
                *args,
                env=env,
                transport_kwargs={"limit": STDIO_BUFFER_LIMIT},
            )
            conn, _proc = await ctx.__aenter__()
        except FileNotFoundError:
            return ValidationResult(
                success=False,
                component=component,
                errors=(f"Binary '{command}' for provider '{self.provider_name}' not found",),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
        except OSError as exc:
            return ValidationResult(
                success=False,
                component=component,
                errors=(f"Failed to spawn provider '{self.provider_name}': {exc}",),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        try:
            await conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=client_info,
            )
        except Exception as exc:
            # Teardown on failure
            with contextlib.suppress(Exception):
                await ctx.__aexit__(None, None, None)
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"ACP initialize handshake failed for provider '{self.provider_name}': {exc}",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 3: Create session, validate models, and exercise the prompt
        # path. Skipping the prompt step lets a provider that can negotiate
        # the protocol but won't actually generate (gemini ACP without
        # ``authenticate``, copilot logged out, quota exceeded) sail through
        # preflight and die on the first real bead — so we send a tiny
        # "say ok" prompt and fail fast if the response is empty.
        errors: list[str] = []
        session: Any = None
        try:
            session = await conn.new_session(
                cwd=os.getcwd(),
                mcp_servers=[],
            )

            # 3a: Validate configured models are available on this provider.
            if self.models_to_validate:
                from maverick.executor._model_resolver import (
                    get_available_model_ids,
                    resolve_model_for_provider,
                )

                available = get_available_model_ids(session)
                if available:
                    for model_id in sorted(self.models_to_validate):
                        resolved = resolve_model_for_provider(model_id, session)
                        if resolved not in available:
                            available_list = ", ".join(sorted(available))
                            errors.append(
                                f"Model '{model_id}' is not available "
                                f"for provider '{self.provider_name}'. "
                                f"Available models: {available_list}"
                            )

            # 3b: Tiny prompt test — only worth running when the model
            # itself isn't already known-bad. Capped at 10s; the outer
            # ``self.timeout`` (default 15s) is the hard ceiling.
            if not errors:
                from acp import text_block

                client.reset(
                    step_name="healthcheck",
                    agent_name="healthcheck",
                    event_callback=None,
                    allowed_tools=None,
                )
                try:
                    await asyncio.wait_for(
                        conn.prompt(
                            prompt=[text_block("Respond with the single word: ok")],
                            session_id=session.session_id,
                        ),
                        timeout=10.0,
                    )
                except TimeoutError:
                    errors.append(
                        f"Provider '{self.provider_name}' prompt test "
                        f"timed out after 10s. The provider negotiated "
                        f"the protocol but never produced a response — "
                        f"likely hung waiting for auth, or rate-limited."
                    )
                except Exception as prompt_exc:
                    errors.append(
                        f"Provider '{self.provider_name}' prompt test "
                        f"failed: {prompt_exc}"
                    )
                else:
                    accumulated = client.get_accumulated_text().strip()
                    if not accumulated:
                        errors.append(
                            f"Provider '{self.provider_name}' accepted "
                            f"the prompt but returned no content. Likely "
                            f"cause: provider needs authentication "
                            f"(e.g. set GEMINI_API_KEY for gemini, or "
                            f"run `copilot auth login`)."
                        )
        except Exception as exc:
            logger.debug(
                "provider_health.session_check_error",
                provider=self.provider_name,
                error=str(exc),
            )
            errors.append(
                f"Provider '{self.provider_name}' session creation "
                f"failed: {exc}"
            )
        finally:
            if session is not None:
                with contextlib.suppress(Exception):
                    await conn.cancel(session_id=session.session_id)

        # Teardown — health check only, we don't keep the connection.
        # Wait for subprocess to fully exit so BaseSubprocessTransport.__del__
        # does not fire after the event loop closes.
        #
        # The ACP library's internal receive loop fires a background task
        # callback (_on_done) that logs "Receive loop failed" / "message
        # queue already closed" at ERROR level to the root logger when the
        # connection is torn down.  This is a benign race (the health check
        # already succeeded), but the traceback is alarming.  Temporarily
        # suppress root-logger ERROR output during teardown.
        import logging as _logging

        _root = _logging.getLogger()
        _prev = _root.level
        _root.setLevel(_logging.CRITICAL)
        try:
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug(
                    "provider_health.teardown_error",
                    provider=self.provider_name,
                    error=str(exc),
                )
            try:
                _proc.terminate()
                await asyncio.wait_for(_proc.wait(), timeout=3.0)
            except (TimeoutError, asyncio.CancelledError):
                with contextlib.suppress(OSError, ProcessLookupError):
                    _proc.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(_proc.wait(), timeout=1.0)
            except Exception:
                pass
        finally:
            _root.setLevel(_prev)

        if errors:
            return ValidationResult(
                success=False,
                component=component,
                errors=tuple(errors),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        return ValidationResult(
            success=True,
            component=component,
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
