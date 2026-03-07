"""ACP provider health check — validates provider binary, auth, and protocol."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import os
import shutil
import time
from dataclasses import dataclass

from maverick.config import AgentProviderConfig
from maverick.logging import get_logger
from maverick.runners.preflight import ValidationResult

__all__ = ["AcpProviderHealthCheck"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AcpProviderHealthCheck:
    """Spawns an ACP provider, runs the initialize handshake, and tears down.

    Validates binary presence, auth, and protocol compatibility in one shot.

    Attributes:
        provider_name: Logical name for this provider (e.g. "claude").
        provider_config: Provider configuration with command and env.
        timeout: Maximum seconds for the entire health check.
    """

    provider_name: str
    provider_config: AgentProviderConfig
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
                    f"Binary '{binary}' for provider '{self.provider_name}' "
                    f"not found on PATH",
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
            ctx = spawn_agent_process(client, command, *args, env=env)
            conn, _proc = await ctx.__aenter__()
        except FileNotFoundError:
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"Binary '{command}' for provider '{self.provider_name}' not found",
                ),
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
                    f"ACP initialize handshake failed for provider "
                    f"'{self.provider_name}': {exc}",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Teardown — health check only, we don't keep the connection
        try:
            await ctx.__aexit__(None, None, None)
        except Exception as exc:
            logger.debug(
                "provider_health.teardown_error",
                provider=self.provider_name,
                error=str(exc),
            )

        return ValidationResult(
            success=True,
            component=component,
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
