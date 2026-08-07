"""Tests for :class:`maverick.agents.base.Agent`'s session-based execution
and context-file-protection wiring (056-context-file-protection, T011).

Uses a fake runtime implementing the ``session(on_permission=...)``
protocol — no real airframe adapter/SDK involved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.base import Agent
from maverick.protection.policy import PermissionGate, ProtectionPolicy
from maverick.protection.records import BlockCollector
from maverick.protection.snapshot import SnapshotManifest


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="fake",
        model_id="fake-model",
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


class _FakeSession:
    """Minimal fake satisfying the ``AgentSession`` protocol surface Agent uses."""

    def __init__(
        self,
        *,
        on_permission: Any,
        result: RuntimeResult,
        side_effect: Any = None,
    ) -> None:
        self.id = "fake-session"
        self.on_permission = on_permission
        self._result = result
        self._side_effect = side_effect
        self.execute_calls: list[dict[str, Any]] = []
        self.closed = False

    async def execute(
        self, prompt: Any, *, schema: Any = None, timeout: float = 600.0, **kwargs: Any
    ) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, "schema": schema, "timeout": timeout})
        if self._side_effect is not None:
            self._side_effect()
        return self._result

    async def close(self) -> None:
        self.closed = True


class _FakeRuntime:
    """Minimal fake satisfying the ``AgentRuntime`` protocol surface Agent uses."""

    label = "fake"

    def __init__(
        self,
        *,
        supports_permission_callback: bool = True,
        result: RuntimeResult | None = None,
        session_side_effect: Any = None,
    ) -> None:
        self._supports_permission_callback = supports_permission_callback
        self._result = result or RuntimeResult(
            text="done", structured=None, cost=_cost(), finish="end_turn"
        )
        self._session_side_effect = session_side_effect
        self.sessions: list[_FakeSession] = []
        self.session_calls: list[dict[str, Any]] = []
        self.execute_calls: list[dict[str, Any]] = []
        self.reset_calls = 0
        self.close_calls = 0
        self.events: list[str] = []

    def supports(self, feature: Any, model: Any = None) -> bool:
        from airframe.features import Feature

        if feature == Feature.PERMISSION_CALLBACK:
            return self._supports_permission_callback
        return False

    def session(self, **kwargs: Any) -> _FakeSession:
        self.session_calls.append(kwargs)
        sess = _FakeSession(
            on_permission=kwargs.get("on_permission"),
            result=self._result,
            side_effect=self._session_side_effect,
        )
        self.sessions.append(sess)
        return sess

    async def execute(self, prompt: Any, **kwargs: Any) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        return self._result

    async def reset(self) -> None:
        self.reset_calls += 1

    async def close(self) -> None:
        self.events.append("runtime.close")
        self.close_calls += 1


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def policy(root: Path) -> ProtectionPolicy:
    return ProtectionPolicy.build(root)


class TestOpenAttachesGateOnlyWhenSupported:
    async def test_session_opened_with_gate_when_supported(self, policy: ProtectionPolicy) -> None:
        runtime = _FakeRuntime(supports_permission_callback=True)
        agent = Agent(runtime=runtime, cwd="/tmp", protection_policy=policy, workflow="fly-beads")
        await agent.open()
        assert len(runtime.session_calls) == 1
        gate = runtime.session_calls[0]["on_permission"]
        assert isinstance(gate, PermissionGate)
        assert gate.workflow == "fly-beads"

    async def test_session_opened_without_gate_when_unsupported(
        self, policy: ProtectionPolicy
    ) -> None:
        runtime = _FakeRuntime(supports_permission_callback=False)
        agent = Agent(runtime=runtime, cwd="/tmp", protection_policy=policy)
        await agent.open()
        assert len(runtime.session_calls) == 1
        assert runtime.session_calls[0]["on_permission"] is None

    async def test_no_session_opened_when_policy_none(self) -> None:
        runtime = _FakeRuntime(supports_permission_callback=True)
        agent = Agent(runtime=runtime, cwd="/tmp")  # protection_policy=None
        await agent.open()
        assert runtime.session_calls == []


class TestRotateSessionClosesAndReopens:
    async def test_rotate_closes_previous_and_opens_fresh_session(
        self, policy: ProtectionPolicy
    ) -> None:
        runtime = _FakeRuntime(supports_permission_callback=True)
        agent = Agent(runtime=runtime, cwd="/tmp", protection_policy=policy)
        await agent.open()
        first_session = runtime.sessions[0]
        await agent.rotate_session()
        assert first_session.closed is True
        assert len(runtime.sessions) == 2
        assert runtime.sessions[1].closed is False
        # runtime.reset() (the legacy path) is never called once sessions
        # are in play.
        assert runtime.reset_calls == 0

    async def test_rotate_reuses_the_same_permission_gate_instance(
        self, policy: ProtectionPolicy
    ) -> None:
        runtime = _FakeRuntime(supports_permission_callback=True)
        agent = Agent(runtime=runtime, cwd="/tmp", protection_policy=policy)
        await agent.open()
        await agent.rotate_session()
        gate_a = runtime.session_calls[0]["on_permission"]
        gate_b = runtime.session_calls[1]["on_permission"]
        assert gate_a is gate_b

    async def test_rotate_without_policy_calls_runtime_reset(self) -> None:
        runtime = _FakeRuntime()
        agent = Agent(runtime=runtime, cwd="/tmp")  # protection_policy=None
        await agent.open()
        await agent.rotate_session()
        assert runtime.reset_calls == 1
        assert runtime.session_calls == []


class TestCloseClosesSessionThenRuntime:
    async def test_close_order_session_before_runtime(self, policy: ProtectionPolicy) -> None:
        runtime = _FakeRuntime(supports_permission_callback=True)
        agent = Agent(runtime=runtime, cwd="/tmp", protection_policy=policy)
        await agent.open()
        session = runtime.sessions[0]
        await agent.close()
        assert session.closed is True
        assert runtime.close_calls == 1

    async def test_close_without_policy_only_closes_runtime(self) -> None:
        runtime = _FakeRuntime()
        agent = Agent(runtime=runtime, cwd="/tmp")
        await agent.open()
        await agent.close()
        assert runtime.close_calls == 1
        assert runtime.sessions == []


class TestPolicyNoneZeroBehaviorChange:
    async def test_execute_via_runtime_uses_legacy_execute_path(self) -> None:
        runtime = _FakeRuntime(
            result=RuntimeResult(
                text="", structured={"kind": "x"}, cost=_cost(), finish="end_turn"
            )
        )
        agent = Agent(runtime=runtime, cwd="/tmp")
        from pydantic import BaseModel

        class _Schema(BaseModel):
            kind: str

        async with agent:
            payload = await agent._execute_via_runtime("do it", schema=_Schema)
        assert isinstance(payload, _Schema)
        assert payload.kind == "x"
        assert len(runtime.execute_calls) == 1
        assert runtime.session_calls == []


class TestBackstopBracketsExecuteViaRuntime:
    async def test_protected_file_mutation_during_send_is_restored(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        target = root / "CLAUDE.md"
        original = "original protected content"
        target.write_text(original)

        def _mutate() -> None:
            target.write_text("agent overwrote this mid-send")

        runtime = _FakeRuntime(
            supports_permission_callback=True,
            result=RuntimeResult(
                text="", structured={"kind": "x"}, cost=_cost(), finish="end_turn"
            ),
            session_side_effect=_mutate,
        )
        collector = BlockCollector()
        agent = Agent(
            runtime=runtime,
            cwd=str(root),
            protection_policy=policy,
            block_collector=collector,
            workflow="fly-beads",
        )
        from pydantic import BaseModel

        class _Schema(BaseModel):
            kind: str

        async with agent:
            await agent._execute_via_runtime("do it", schema=_Schema)

        assert target.read_text() == original
        records = collector.drain()
        assert len(records) == 1
        assert records[0].layer == "backstop"
        assert records[0].path == "CLAUDE.md"

    async def test_backstop_restores_even_when_send_raises(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        target = root / "AGENTS.md"
        original = "keep me"
        target.write_text(original)

        def _mutate_then_boom() -> None:
            target.write_text("mutated before crash")

        class _RaisingSession(_FakeSession):
            async def execute(self, *args: Any, **kwargs: Any) -> RuntimeResult:
                _mutate_then_boom()
                raise RuntimeError("mid-turn crash")

        class _RaisingRuntime(_FakeRuntime):
            def session(self, **kwargs: Any) -> _FakeSession:
                sess = _RaisingSession(
                    on_permission=kwargs.get("on_permission"), result=self._result
                )
                self.sessions.append(sess)
                return sess

        runtime = _RaisingRuntime(supports_permission_callback=True)
        collector = BlockCollector()
        agent = Agent(
            runtime=runtime, cwd=str(root), protection_policy=policy, block_collector=collector
        )
        async with agent:
            with pytest.raises(RuntimeError, match="mid-turn crash"):
                await agent._execute_via_runtime("do it")

        assert target.read_text() == original
        records = collector.drain()
        assert len(records) == 1
        assert records[0].layer == "backstop"

    async def test_text_execute_also_bracketed(self, root: Path, policy: ProtectionPolicy) -> None:
        target = root / "AGENTS.md"
        target.write_text("stable")

        def _mutate() -> None:
            target.write_text("agent touched it")

        runtime = _FakeRuntime(
            supports_permission_callback=True,
            result=RuntimeResult(text="done", structured=None, cost=_cost(), finish="end_turn"),
            session_side_effect=_mutate,
        )
        collector = BlockCollector()
        agent = Agent(
            runtime=runtime, cwd=str(root), protection_policy=policy, block_collector=collector
        )
        async with agent:
            text = await agent._execute_text_via_runtime("do it")
        assert text == "done"
        assert target.read_text() == "stable"
        assert len(collector.drain()) == 1

    async def test_unprotected_mutation_survives(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        real_work = root / "src" / "real_work.py"
        real_work.parent.mkdir(parents=True)
        real_work.write_text("before")

        def _mutate() -> None:
            real_work.write_text("after — legitimate change")

        runtime = _FakeRuntime(
            supports_permission_callback=True,
            result=RuntimeResult(text="done", structured=None, cost=_cost(), finish="end_turn"),
            session_side_effect=_mutate,
        )
        collector = BlockCollector()
        agent = Agent(
            runtime=runtime, cwd=str(root), protection_policy=policy, block_collector=collector
        )
        async with agent:
            await agent._execute_text_via_runtime("do it")
        assert real_work.read_text() == "after — legitimate change"
        assert collector.drain() == []


class TestSnapshotCaptureFailureFallsBackToBaseline:
    async def test_capture_failure_falls_back_to_baseline_manifest(
        self, root: Path, policy: ProtectionPolicy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = root / "CLAUDE.md"
        original = "baseline content"
        target.write_text(original)
        baseline = await SnapshotManifest.capture(root, policy)

        async def _boom(*args: object, **kwargs: object) -> SnapshotManifest:
            raise OSError("simulated capture failure")

        monkeypatch.setattr(SnapshotManifest, "capture", _boom)

        def _mutate() -> None:
            target.write_text("mutated during the step whose own capture failed")

        runtime = _FakeRuntime(
            supports_permission_callback=True,
            result=RuntimeResult(text="done", structured=None, cost=_cost(), finish="end_turn"),
            session_side_effect=_mutate,
        )
        collector = BlockCollector()
        agent = Agent(
            runtime=runtime,
            cwd=str(root),
            protection_policy=policy,
            block_collector=collector,
            baseline_manifest=baseline,
        )
        async with agent:
            await agent._execute_text_via_runtime("do it")

        # The per-step capture failed, but the baseline still let the
        # post-step compare detect and undo the mutation.
        assert target.read_text() == original
        assert len(collector.drain()) == 1

    async def test_capture_failure_without_baseline_skips_this_step_only(
        self, root: Path, policy: ProtectionPolicy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = root / "CLAUDE.md"
        target.write_text("original")

        async def _boom(*args: object, **kwargs: object) -> SnapshotManifest:
            raise OSError("simulated capture failure")

        monkeypatch.setattr(SnapshotManifest, "capture", _boom)

        def _mutate() -> None:
            target.write_text("mutated, nothing to compare against")

        runtime = _FakeRuntime(
            supports_permission_callback=True,
            result=RuntimeResult(text="done", structured=None, cost=_cost(), finish="end_turn"),
            session_side_effect=_mutate,
        )
        agent = Agent(runtime=runtime, cwd=str(root), protection_policy=policy)
        async with agent:
            # Must not raise even though there's no baseline to fall back to.
            await agent._execute_text_via_runtime("do it")
        # No manifest to compare against -> this step's mutation isn't
        # caught (documented degrade — the very next successful step's
        # own snapshot resumes normal coverage).
        assert target.read_text() == "mutated, nothing to compare against"
