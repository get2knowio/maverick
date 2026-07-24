"""``SpecChainAgent`` — runs one Spec Kit chain step (`maverick spec`)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from maverick.agents.base import Agent
from maverick.workflows.spec_chain.constants import STEP_TIMEOUT_SECONDS
from maverick.workflows.spec_chain.models import StepReport

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.registry import CostSink

__all__ = ["SpecChainAgent"]

#: Serializes the `os.chdir()`-scoped step execution below across every
#: `SpecChainAgent` instance in this process. airframe-agents 0.9.0rc1 has
#: no per-call (or per-runtime) cwd parameter for the `claude` provider —
#: `ClaudeOptions` carries no `working_directory` field, unlike
#: Copilot/Kimi/OpenCodeServer (research.md R1, an adapter gap, not an SDK
#: limitation). `os.chdir()` is process-wide state; this lock keeps two
#: chain-step calls from racing on it. Safe in practice because chain
#: steps already run strictly sequentially (FR-002) and one Maverick CLI
#: invocation runs exactly one workflow per process.
_CWD_BIND_LOCK = asyncio.Lock()


class SpecChainAgent(Agent):
    """Executes one Spec Kit chain step against the target repository's own
    ``/speckit.*`` command surface, inside the hidden workspace.
    """

    result_model: ClassVar[type[StepReport]] = StepReport
    provider_tier: ClassVar[str] = "generate"
    persona_name: ClassVar[str | None] = "maverick.spec-chain"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        step_config: StepConfig | dict[str, object] | None = None,
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

    async def run_step(self, prompt: str) -> StepReport:
        """Run one chain-step prompt and return its structured report.

        Binds the process working directory to this agent's ``cwd`` (the
        hidden workspace) for the duration of the call — see
        ``_CWD_BIND_LOCK`` for why this is necessary and how it stays safe.
        """
        async with _CWD_BIND_LOCK:
            previous = Path.cwd()
            os.chdir(self._cwd)
            try:
                report = await self._execute_via_runtime(prompt, timeout=STEP_TIMEOUT_SECONDS)
            finally:
                os.chdir(previous)
        assert isinstance(report, StepReport)
        return report
