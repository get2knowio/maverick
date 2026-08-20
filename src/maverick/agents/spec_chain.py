"""``SpecChainAgent`` — runs one Spec Kit chain step (`maverick spec`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from maverick.agents.base import Agent
from maverick.workflows.spec_chain.constants import STEP_TIMEOUT_SECONDS
from maverick.workflows.spec_chain.models import StepReport
from maverick.workspace.cwd_scope import chdir_scope

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.protection.policy import ProtectionPolicy
    from maverick.protection.records import BlockCollector
    from maverick.protection.snapshot import SnapshotManifest
    from maverick.runtime.registry import CostSink

__all__ = ["SpecChainAgent"]


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
        protection_policy: ProtectionPolicy | None = None,
        block_collector: BlockCollector | None = None,
        workflow: str = "",
        baseline_manifest: SnapshotManifest | None = None,
    ) -> None:
        super().__init__(
            runtime=runtime,
            cwd=cwd,
            step_config=step_config,
            cost_sink=cost_sink,
            tag=tag,
            protection_policy=protection_policy,
            block_collector=block_collector,
            workflow=workflow,
            baseline_manifest=baseline_manifest,
        )

    async def run_step(self, prompt: str) -> StepReport:
        """Run one chain-step prompt and return its structured report.

        Binds the process working directory to this agent's ``cwd`` (the
        hidden workspace) for the duration of the call — see
        ``workspace.cwd_scope`` for why this is necessary and how it stays
        safe.
        """
        async with chdir_scope(self._cwd):
            report = await self._execute_via_runtime(prompt, timeout=STEP_TIMEOUT_SECONDS)
        assert isinstance(report, StepReport)
        return report
