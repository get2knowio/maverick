"""Tests for spec-chain's protection-blocks wiring (056-context-file-protection T024).

Covers: ``ChainState.protection_blocks`` defaults/round-trips through
checkpointing (survive-resume); ``SpecChainWorkflow._drain_protection_blocks``
drains the squadron collector into state + emits one event per record;
``_persist_protection_blocks_artifact`` writes ``protection-blocks.json``
only when non-empty; the CLI summary renders a blocks line when present.
"""

from __future__ import annotations

import asyncio
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.events import ContextFileWriteBlocked, ProgressEvent
from maverick.protection.records import BlockCollector, BlockRecord
from maverick.workflows.spec_chain.models import ChainState
from maverick.workflows.spec_chain.state import load_chain_state, save_chain_state
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow


def _config() -> MaverickConfig:
    return MaverickConfig(
        agents=AgentsConfig(generate=AgentBindingConfig(provider="claude", model_id="stub-model"))
    )


def _workflow() -> SpecChainWorkflow:
    wf = SpecChainWorkflow(config=_config())
    wf._event_queue = asyncio.Queue()
    return wf


def _base_state(**overrides: Any) -> ChainState:
    now = datetime.now(tz=UTC)
    defaults: dict[str, Any] = {
        "run_id": "run-1",
        "feature": "widget-export",
        "feature_dir": None,
        "prd_path": "docs/prd.md",
        "prd_digest": "0" * 64,
        "workspace_path": "/tmp/ws",
        "status": "running",
        "started_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return ChainState(**defaults)


class _SquadronWithCollector:
    def __init__(self) -> None:
        self.block_collector = BlockCollector()


class _SquadronWithoutCollector:
    """Simulates degraded protection setup (no block_collector attribute)."""


def _block(path: str = "AGENTS.md") -> BlockRecord:
    return BlockRecord(
        agent_role="generate",
        workflow="spec-chain",
        operation="restore",
        path=path,
        layer="backstop",
        detail="restored after backstop-detected mutation",
    )


async def _drain_queue(queue: asyncio.Queue[ProgressEvent | None]) -> list[ProgressEvent]:
    events: list[ProgressEvent] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


class TestChainStateDefaultsAndRoundTrip:
    def test_defaults_to_empty_list(self) -> None:
        state = _base_state()
        assert state.protection_blocks == []

    async def test_survives_save_and_load(self, tmp_path: Path) -> None:
        state = _base_state(protection_blocks=[_block("CLAUDE.md").to_dict()])
        await save_chain_state(state, tmp_path)
        loaded = await load_chain_state("run-1", tmp_path)
        assert loaded is not None
        assert loaded.protection_blocks == state.protection_blocks

    async def test_survives_a_simulated_resume_cycle(self, tmp_path: Path) -> None:
        """The same pattern a mid-chain crash + resume exercises: save after
        step N, reload as if freshly started, confirm blocks persisted."""
        state = _base_state(protection_blocks=[_block("AGENTS.md").to_dict()])
        await save_chain_state(state, tmp_path)

        resumed = await load_chain_state("run-1", tmp_path)
        assert resumed is not None
        assert len(resumed.protection_blocks) == 1
        assert resumed.protection_blocks[0]["path"] == "AGENTS.md"


class TestDrainProtectionBlocks:
    async def test_drains_collector_into_state(self) -> None:
        wf = _workflow()
        squadron = _SquadronWithCollector()
        squadron.block_collector.append(_block("CLAUDE.md"))
        state = _base_state()

        new_state = await wf._drain_protection_blocks(state, squadron=squadron)  # type: ignore[arg-type]

        assert len(new_state.protection_blocks) == 1
        assert new_state.protection_blocks[0]["path"] == "CLAUDE.md"
        assert squadron.block_collector.drain() == []

    async def test_emits_one_event_per_record(self) -> None:
        wf = _workflow()
        squadron = _SquadronWithCollector()
        squadron.block_collector.append(_block("CLAUDE.md"))
        squadron.block_collector.append(_block("AGENTS.md"))
        state = _base_state()

        await wf._drain_protection_blocks(state, squadron=squadron)  # type: ignore[arg-type]

        emitted = await _drain_queue(wf._event_queue)
        blocked = [e for e in emitted if isinstance(e, ContextFileWriteBlocked)]
        assert len(blocked) == 2
        assert {e.path for e in blocked} == {"CLAUDE.md", "AGENTS.md"}

    async def test_accumulates_across_multiple_calls(self) -> None:
        """Successive steps each drain into the same growing list."""
        wf = _workflow()
        squadron = _SquadronWithCollector()

        squadron.block_collector.append(_block("CLAUDE.md"))
        state = await wf._drain_protection_blocks(_base_state(), squadron=squadron)  # type: ignore[arg-type]
        assert len(state.protection_blocks) == 1

        squadron.block_collector.append(_block("AGENTS.md"))
        state = await wf._drain_protection_blocks(state, squadron=squadron)  # type: ignore[arg-type]
        assert len(state.protection_blocks) == 2

    async def test_no_op_when_collector_empty(self) -> None:
        wf = _workflow()
        squadron = _SquadronWithCollector()
        state = _base_state()

        new_state = await wf._drain_protection_blocks(state, squadron=squadron)  # type: ignore[arg-type]

        assert new_state.protection_blocks == []
        assert new_state is state  # no-op returns the same object

    async def test_degraded_squadron_without_collector_is_a_no_op(self) -> None:
        wf = _workflow()
        squadron = _SquadronWithoutCollector()
        state = _base_state()

        new_state = await wf._drain_protection_blocks(state, squadron=squadron)  # type: ignore[arg-type]

        assert new_state is state
        assert (await _drain_queue(wf._event_queue)) == []


class TestPersistProtectionBlocksArtifact:
    async def test_writes_artifact_when_blocks_present(self, tmp_path: Path) -> None:
        wf = _workflow()
        state = _base_state(protection_blocks=[_block("CLAUDE.md").to_dict()])

        await wf._persist_protection_blocks_artifact(state, cwd=tmp_path)

        artifact_path = tmp_path / ".maverick" / "runs" / "run-1" / "protection-blocks.json"
        assert artifact_path.is_file()
        data = json.loads(artifact_path.read_text())
        assert data["workflow"] == "spec-chain"
        assert data["run_id"] == "run-1"
        assert data["blocks"][0]["path"] == "CLAUDE.md"

    async def test_no_artifact_written_when_clean(self, tmp_path: Path) -> None:
        wf = _workflow()
        state = _base_state()

        await wf._persist_protection_blocks_artifact(state, cwd=tmp_path)

        artifact_path = tmp_path / ".maverick" / "runs" / "run-1" / "protection-blocks.json"
        assert not artifact_path.exists()


class TestCliSummaryRendersBlocksLine:
    def _render(self, state: ChainState) -> str:
        from maverick.cli.commands.spec import _render_summary_and_exit

        buf = io.StringIO()
        import maverick.cli.commands.spec as spec_module

        original = spec_module.console
        spec_module.console = Console(file=buf, width=200, no_color=True)  # type: ignore[assignment]
        try:
            with pytest.raises(SystemExit):
                _render_summary_and_exit(state, "widget-export")
        finally:
            spec_module.console = original
        return buf.getvalue()

    def test_blocks_line_present_when_nonzero(self) -> None:
        state = _base_state(status="completed", protection_blocks=[_block("CLAUDE.md").to_dict()])
        out = self._render(state)
        assert "Context-file protection events: 1" in out

    def test_blocks_line_absent_when_zero(self) -> None:
        state = _base_state(status="completed")
        out = self._render(state)
        assert "Context-file protection events" not in out
