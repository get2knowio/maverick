"""``CodingAgent`` — implements bead work and addresses fix requests.

Owns two structured-output payloads:

* ``submit_implementation`` (:class:`SubmitImplementationPayload`) — returned by
  :meth:`implement`.
* ``submit_fix_result`` (:class:`SubmitFixResultPayload`) — returned by
  :meth:`fix`.

The implement → fix continuity is preserved by the persistent session
(OpenCode session in the legacy path; airframe runtime's context cache
in the Pattern D path): callers reuse the same ``CodingAgent`` instance
across both calls within a bead so the model retains context. Call
:meth:`Agent.rotate_session` between beads to start clean.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.payloads import SubmitFixResultPayload, SubmitImplementationPayload

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import (
        CostSink,
        OpenCodeClient,
        OpenCodeServerHandle,
        Tier,
    )

CODING_PROMPT_TIMEOUT_SECONDS = 1800


class CodingAgent(Agent):
    """Coding agent: implements beads and addresses fixes.

    Supports both the legacy OpenCode HTTP path (``handle=``) and the
    Pattern D :class:`airframe.AgentRuntime` path (``runtime=``).
    """

    # Default schema; ``fix`` overrides per call.
    result_model: ClassVar[type[BaseModel]] = SubmitImplementationPayload
    provider_tier: ClassVar[str] = "implement"
    opencode_agent: ClassVar[str | None] = "maverick.implementer"

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

    async def implement(self, prompt: str) -> SubmitImplementationPayload:
        """Run the implement-phase prompt and return the typed payload.

        Bead identity (and any other workflow vocabulary) flows in via
        :func:`~maverick.agents.context.tagged` — wrap the call in
        ``with tagged(bead_id=...):`` so cost records and structured logs
        get attributed correctly.
        """
        if self._runtime is not None:
            payload = await self._execute_via_runtime(
                prompt,
                schema=SubmitImplementationPayload,
                timeout=CODING_PROMPT_TIMEOUT_SECONDS,
            )
        else:
            payload = await self._send_structured(
                prompt,
                schema=SubmitImplementationPayload,
                timeout=CODING_PROMPT_TIMEOUT_SECONDS,
            )
        assert isinstance(payload, SubmitImplementationPayload)
        return payload

    async def fix(self, prompt: str) -> SubmitFixResultPayload:
        """Run the fix-phase prompt and return the typed payload.

        Reuses the same session as :meth:`implement` (within the same
        bead) so the model retains the implementation context.
        """
        if self._runtime is not None:
            payload = await self._execute_via_runtime(
                prompt,
                schema=SubmitFixResultPayload,
                timeout=CODING_PROMPT_TIMEOUT_SECONDS,
            )
        else:
            payload = await self._send_structured(
                prompt,
                schema=SubmitFixResultPayload,
                timeout=CODING_PROMPT_TIMEOUT_SECONDS,
            )
        assert isinstance(payload, SubmitFixResultPayload)
        return payload


__all__ = ["CODING_PROMPT_TIMEOUT_SECONDS", "CodingAgent"]
