"""xoscar GeneratorActor — thin shell over :class:`GeneratorAgent`.

The actor is the xoscar-mailbox boundary; the runtime scope +
structured-output cascade live in :class:`maverick.agents.generator.GeneratorAgent`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xoscar as xo
from airframe.errors import AgentRuntimeError

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import GenerateRequest, PromptError
from maverick.agents.generator import GeneratorAgent
from maverick.logging import get_logger
from maverick.runtime.agent_factory import runtime_for_agent
from maverick.runtime.registry import agents_config_for, cost_sink_for

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


class GeneratorActor(xo.Actor):
    """Generates a flight plan from PRD + briefing context."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
        agent: GeneratorAgent | None = None,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("GeneratorActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)
        # Pre-built agent provided by the squadron (Pattern D) or test
        # harness. When None, ``_make_agent`` falls back to constructing
        # one from the legacy pool registries.
        self._injected_agent = agent
        self._agent: GeneratorAgent | None = None

    async def __post_create__(self) -> None:
        self._agent = self._make_agent()
        await self._agent.open()

    def _make_agent(self) -> GeneratorAgent:
        """Return the injected agent or construct one via airframe."""
        if self._injected_agent is not None:
            return self._injected_agent
        pool_address: str = self.address
        agents_config = agents_config_for(pool_address)
        if agents_config is None:
            raise RuntimeError(
                f"GeneratorActor at {pool_address!r}: no agent= injected "
                "and no AgentsConfig registered on the pool. Pass either "
                "agent= explicitly or wrap actor_pool() with agents_config=."
            )
        runtime, _ = runtime_for_agent("generate", agents_config=agents_config)
        return GeneratorAgent(
            runtime=runtime,
            cwd=self._cwd,
            step_config=self._step_config,
            cost_sink=cost_sink_for(pool_address),
            tag=f"generator[{self.uid.decode()}]",
        )

    async def __pre_destroy__(self) -> None:
        # Squadron owns the lifecycle of injected agents; the actor only
        # closes agents it constructed itself via the legacy fallback.
        if self._agent is not None and self._injected_agent is None:
            await self._agent.close()

    # ------------------------------------------------------------------
    # Supervisor → agent
    # ------------------------------------------------------------------

    @xo.no_lock
    async def send_generate(self, request: GenerateRequest) -> None:
        """Run the flight-plan generation prompt and forward the typed payload."""
        assert self._agent is not None
        logger.debug("generator.prompt_starting")
        try:
            payload = await self._agent.generate(request.prompt)
        except AgentRuntimeError as exc:
            await self._report_prompt_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_prompt_error(str(exc))
            return
        await self._supervisor_ref.flight_plan_ready(payload)

    async def _report_prompt_error(self, error: str) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        logger.debug("generator.prompt_failed", error=error)
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase="generate",
                error=error,
                quota_exhausted=is_quota_error(error),
                transient=is_transient_error(error),
            )
        )
