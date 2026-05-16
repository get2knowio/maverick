"""``GeneratorAgent`` — generates a flight plan from PRD + briefing."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from maverick.agents.base import Agent
from maverick.payloads import SubmitFlightPlanPayload

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import (
        CostSink,
        OpenCodeClient,
        OpenCodeServerHandle,
        Tier,
    )

GENERATOR_PROMPT_TIMEOUT_SECONDS = 1200


class GeneratorAgent(Agent):
    """Flight-plan generator.

    Supports both the legacy OpenCode HTTP path (``handle=``) and the
    Pattern D :class:`airframe.AgentRuntime` path (``runtime=``).
    """

    result_model: ClassVar[type[SubmitFlightPlanPayload]] = SubmitFlightPlanPayload
    provider_tier: ClassVar[str] = "generate"
    # Persona system prompt is loaded from
    # ``runtime/opencode/profile/agents/maverick.generator.md`` via
    # ``OPENCODE_CONFIG_DIR`` (legacy path), or forwarded as ``persona``
    # on ``runtime.execute()`` (Pattern D path) so OpenCode-compatible
    # runtimes still honour the bundled persona file.
    opencode_agent: ClassVar[str | None] = "maverick.generator"

    def __init__(
        self,
        *,
        handle: OpenCodeServerHandle | None = None,
        cwd: str,
        step_config: StepConfig | dict[str, Any] | None = None,
        tier_overrides: dict[str, Tier] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
        client_factory: Callable[[], OpenCodeClient] | None = None,
        runtime: AgentRuntime | None = None,
    ) -> None:
        if handle is None and runtime is None:
            raise ValueError(f"{type(self).__name__} requires either 'handle' or 'runtime'")
        if handle is not None and runtime is not None:
            raise ValueError(
                f"{type(self).__name__} got both 'handle' and 'runtime'; pass exactly one"
            )

        if runtime is not None:
            # Pattern D path. Skip the OpenCode-shaped base init.
            from maverick.actors.step_config import load_step_config

            if not cwd:
                raise ValueError(f"{type(self).__name__} requires 'cwd'")
            self._handle = None  # type: ignore[assignment]
            self._cwd = cwd
            self._step_config = load_step_config(step_config)
            self._tier_overrides = tier_overrides
            self._cost_sink = cost_sink
            self._tag = tag or type(self).__name__
            self._client_factory = None
            self._result_model_instance = None
            self._opencode_agent_instance = self.opencode_agent
            self._client = None
            self._session_id = None
            self._validated_bindings = set()
            self._failed_bindings = set()
            self._last_cost_record = None
            self._runtime = runtime
            return

        assert handle is not None
        super().__init__(
            handle=handle,
            cwd=cwd,
            step_config=step_config,
            tier_overrides=tier_overrides,
            cost_sink=cost_sink,
            tag=tag,
            client_factory=client_factory,
        )

    async def open(self) -> None:
        if self._runtime is not None:
            return
        await super().open()

    async def close(self) -> None:
        if self._runtime is not None:
            await self._runtime.close()
            return
        await super().close()

    async def rotate_session(self) -> None:
        if self._runtime is not None:
            await self._runtime.reset()
            return
        await super().rotate_session()

    async def generate(self, prompt: str) -> SubmitFlightPlanPayload:
        """Run the flight-plan prompt and return the typed payload.

        ``prompt`` is the per-call user content (PRD + briefing); persona
        system prompt is loaded by OpenCode from the bundled markdown
        agent file so the cache key stays stable across runs.
        """
        wrapped = f"# PRD and briefing\n\n{prompt}"
        if self._runtime is not None:
            payload = await self._execute_via_runtime(
                wrapped, timeout=GENERATOR_PROMPT_TIMEOUT_SECONDS
            )
        else:
            payload = await self._send_structured(
                wrapped, timeout=GENERATOR_PROMPT_TIMEOUT_SECONDS
            )
        assert isinstance(payload, SubmitFlightPlanPayload)
        return payload


__all__ = ["GENERATOR_PROMPT_TIMEOUT_SECONDS", "GeneratorAgent"]
