"""``CodingAgent`` — implements bead work and addresses fix requests.

Owns two structured-output payloads:

* ``SubmitImplementationPayload`` — returned by :meth:`implement`.
* ``SubmitFixResultPayload`` — returned by :meth:`fix`.

The implement → fix continuity is preserved by the airframe runtime's
context cache: callers reuse the same ``CodingAgent`` instance across
both calls within a bead so the model retains context. Call
:meth:`Agent.rotate_session` between beads to start clean.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.payloads import SubmitFixResultPayload, SubmitImplementationPayload

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.registry import CostSink

CODING_PROMPT_TIMEOUT_SECONDS = 1800


class CodingAgent(Agent):
    """Coding agent: implements beads and addresses fixes."""

    # Default schema; ``fix`` overrides per call.
    result_model: ClassVar[type[BaseModel]] = SubmitImplementationPayload
    provider_tier: ClassVar[str] = "implement"
    opencode_agent: ClassVar[str | None] = "maverick.implementer"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        step_config: StepConfig | dict[str, Any] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(
            runtime=runtime,
            cwd=cwd,
            step_config=step_config,
            cost_sink=cost_sink,
            tag=tag,
        )

    async def implement(self, prompt: str) -> SubmitImplementationPayload:
        """Run the implement-phase prompt and return the typed payload.

        Bead identity (and any other workflow vocabulary) flows in via
        :func:`~maverick.agents.context.tagged` — wrap the call in
        ``with tagged(bead_id=...):`` so cost records and structured logs
        get attributed correctly.
        """
        payload = await self._execute_via_runtime(
            prompt,
            schema=SubmitImplementationPayload,
            timeout=CODING_PROMPT_TIMEOUT_SECONDS,
        )
        assert isinstance(payload, SubmitImplementationPayload)
        return payload

    async def fix(self, prompt: str) -> SubmitFixResultPayload:
        """Run the fix-phase prompt and return the typed payload.

        Reuses the same airframe runtime scope as :meth:`implement`
        (within the same bead) so the model retains the implementation
        context.
        """
        payload = await self._execute_via_runtime(
            prompt,
            schema=SubmitFixResultPayload,
            timeout=CODING_PROMPT_TIMEOUT_SECONDS,
        )
        assert isinstance(payload, SubmitFixResultPayload)
        return payload


__all__ = ["CODING_PROMPT_TIMEOUT_SECONDS", "CodingAgent"]
