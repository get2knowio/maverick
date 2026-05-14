"""``CodingAgent`` — implements bead work and addresses fix requests.

Owns two structured-output payloads:

* ``submit_implementation`` (:class:`SubmitImplementationPayload`) — returned by
  :meth:`implement`.
* ``submit_fix_result`` (:class:`SubmitFixResultPayload`) — returned by
  :meth:`fix`.

The implement → fix continuity is preserved by the persistent OpenCode
session: callers reuse the same ``CodingAgent`` instance across both
calls within a bead so the model retains context. Call
:meth:`Agent.rotate_session` between beads to start clean.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.payloads import SubmitFixResultPayload, SubmitImplementationPayload

CODING_PROMPT_TIMEOUT_SECONDS = 1800


class CodingAgent(Agent):
    """OpenCode-backed coding agent: implements beads and addresses fixes."""

    # Default schema; ``fix`` overrides per call.
    result_model: ClassVar[type[BaseModel]] = SubmitImplementationPayload
    provider_tier: ClassVar[str] = "implement"
    # Persona system prompt is loaded from
    # ``runtime/opencode/profile/agents/maverick.implementer.md`` via
    # ``OPENCODE_CONFIG_DIR``.
    opencode_agent: ClassVar[str | None] = "maverick.implementer"

    async def implement(
        self,
        prompt: str,
        *,
        bead_id: str,
    ) -> SubmitImplementationPayload:
        """Run the implement-phase prompt and return the typed payload."""
        self.current_bead_id = bead_id
        payload = await self._send_structured(
            prompt,
            schema=SubmitImplementationPayload,
            timeout=CODING_PROMPT_TIMEOUT_SECONDS,
        )
        assert isinstance(payload, SubmitImplementationPayload)
        return payload

    async def fix(
        self,
        prompt: str,
        *,
        bead_id: str,
    ) -> SubmitFixResultPayload:
        """Run the fix-phase prompt and return the typed payload.

        Reuses the same OpenCode session as :meth:`implement` (within
        the same bead) so the model retains the implementation context.
        """
        self.current_bead_id = bead_id
        payload = await self._send_structured(
            prompt,
            schema=SubmitFixResultPayload,
            timeout=CODING_PROMPT_TIMEOUT_SECONDS,
        )
        assert isinstance(payload, SubmitFixResultPayload)
        return payload


__all__ = ["CODING_PROMPT_TIMEOUT_SECONDS", "CodingAgent"]
