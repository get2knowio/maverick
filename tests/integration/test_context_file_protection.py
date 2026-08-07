"""Integration test: context-file protection end-to-end (056-context-file-protection).

Drives the real production seam — :class:`~maverick.squadron.fly.FlySquadron`
/ :class:`~maverick.squadron.spec_chain.SpecChainSquadron` building real
:class:`~maverick.agents.coding.CodingAgent` / :class:`~maverick.agents.spec_chain.SpecChainAgent`
instances with a real :class:`~maverick.protection.policy.ProtectionPolicy`
— against a stub airframe runtime (per
``tests/unit/workflows/conftest.py::stub_squadron_io``'s pattern: patch
``airframe.runtime_for``, never touch a real adapter SDK or network). The
stub's "model call" mutates protected + unprotected files as a side effect
before returning a canned typed payload — simulating a bead whose
implementer tried to rewrite ``CLAUDE.md``, plant ``sub/AGENTS.md``, delete
``.specify/memory/constitution.md``, and (legitimately) edit
``src/real_work.py``, all in one turn.

See quickstart.md §2 for the scenario this proves, and the Success
Criteria traceability table at its end for SC-001..SC-006.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.payloads import SubmitImplementationPayload
from maverick.protection.records import persist_blocks_artifact
from maverick.squadron.fly import DEFAULT_TIER, FlySquadron
from maverick.squadron.spec_chain import SpecChainSquadron
from maverick.workflows.spec_chain.models import StepReport


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="stub",
        model_id="stub-model",
        cost_usd=0.0,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


class _MutatingSession:
    """Simulates a model turn that mutates files as a side effect before
    returning its structured payload — no permission-callback gating
    (``supports_permission_callback`` returns False), so this exercises
    the universal Layer 2 backstop specifically.
    """

    def __init__(self, mutate: Any, result: RuntimeResult) -> None:
        self.id = "stub-session"
        self._mutate = mutate
        self._result = result

    async def execute(self, prompt: str, **kwargs: Any) -> RuntimeResult:
        if self._mutate is not None:
            self._mutate()
        return self._result

    async def close(self) -> None:
        return None


class _StubRuntime:
    label = "stub"

    def __init__(
        self,
        *,
        model: str | None = None,
        mutate: Any = None,
        result: RuntimeResult | None = None,
        **_kwargs: Any,
    ) -> None:
        self.model = model
        self._mutate = mutate
        self._result = result or RuntimeResult(
            text="", structured=None, cost=_cost(), finish="end_turn"
        )

    def validate_binding(self, _binding: Any) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _MutatingSession:
        return _MutatingSession(self._mutate, self._result)

    async def execute(self, *args: Any, **kwargs: Any) -> RuntimeResult:  # pragma: no cover
        raise NotImplementedError("stub runtime routes through session() only")

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _impl_payload_dict() -> dict[str, Any]:
    return {
        "kind": "submit_implementation",
        "summary": "did the work",
        "files_changed": ["src/real_work.py"],
        "commands_run": [],
        "verification": "tests pass",
        "next_step": "commit",
    }


def _make_config(**protection: Any) -> MaverickConfig:
    binding = AgentBindingConfig(provider="claude", model_id="stub-model")
    kwargs: dict[str, Any] = {
        "agents": AgentsConfig(
            implement=binding,
            review=binding,
            generate=binding,
        )
    }
    if protection:
        kwargs["protection"] = protection
    return MaverickConfig(**kwargs)


def _build_repo(cwd: Path) -> dict[str, str]:
    """Lay down a protected set + one real source file, return original contents."""
    (cwd / ".specify" / "memory").mkdir(parents=True)
    (cwd / "src").mkdir(parents=True)

    claude_md = "# CLAUDE.md\n\noriginal instructions\n"
    constitution = "# Constitution\n\nprinciple I\n"
    real_work = "def before():\n    return 1\n"

    (cwd / "CLAUDE.md").write_text(claude_md)
    (cwd / ".specify" / "memory" / "constitution.md").write_text(constitution)
    (cwd / "src" / "real_work.py").write_text(real_work)

    return {
        "CLAUDE.md": claude_md,
        ".specify/memory/constitution.md": constitution,
        "src/real_work.py": real_work,
    }


def _mutate_repo(cwd: Path) -> None:
    """The stub-runtime "model call" side effect: rewrite/plant/delete
    protected files, and make one legitimate edit."""
    (cwd / "CLAUDE.md").write_text("# CLAUDE.md\n\nAGENT OVERWROTE THIS\n")
    (cwd / "sub").mkdir(exist_ok=True)
    (cwd / "sub" / "AGENTS.md").write_text("agent planted this\n")
    (cwd / ".specify" / "memory" / "constitution.md").unlink()
    (cwd / "src" / "real_work.py").write_text("def after():\n    return 2\n")


class TestFlySquadronBackstopEndToEnd:
    async def test_protected_files_survive_bead_completes(self, tmp_path: Path) -> None:
        originals = _build_repo(tmp_path)
        config = _make_config()

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=lambda: _mutate_repo(tmp_path),
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                payload = await coder.implement("implement the bead")

        # The bead "completed" — the implementer's structured payload
        # came back despite the mid-turn protected-file mutation.
        assert isinstance(payload, SubmitImplementationPayload)
        assert payload.summary == "did the work"

        # Protected files: byte-identical to pre-step state (SC-001).
        assert (tmp_path / "CLAUDE.md").read_text() == originals["CLAUDE.md"]
        assert (tmp_path / ".specify" / "memory" / "constitution.md").read_text() == (
            originals[".specify/memory/constitution.md"]
        )
        assert not (tmp_path / "sub" / "AGENTS.md").exists()

        # The legitimate, unprotected change survives (SC-003, SC-005).
        assert (tmp_path / "src" / "real_work.py").read_text() == "def after():\n    return 2\n"

    async def test_blocks_recorded_in_collector(self, tmp_path: Path) -> None:
        _build_repo(tmp_path)
        config = _make_config()

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=lambda: _mutate_repo(tmp_path),
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                await coder.implement("implement the bead")

                records = squadron.block_collector.drain()  # type: ignore[union-attr]

        # Three restores: CLAUDE.md edit, constitution.md delete, AGENTS.md
        # create — src/real_work.py never appears (it isn't protected).
        paths = {r.path for r in records}
        assert paths == {
            "CLAUDE.md",
            ".specify/memory/constitution.md",
            "sub/AGENTS.md",
        }
        assert all(r.layer == "backstop" for r in records)
        assert all(r.operation == "restore" for r in records)
        assert all(r.agent_role == "implement" for r in records)
        assert all(r.workflow == "fly-beads" for r in records)

    async def test_no_blocks_on_clean_run(self, tmp_path: Path) -> None:
        """A bead that doesn't touch protected paths leaves the collector empty."""
        _build_repo(tmp_path)
        config = _make_config()

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=lambda: (tmp_path / "src" / "real_work.py").write_text(
                            "def clean():\n    return 3\n"
                        ),
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                await coder.implement("implement the bead")
                assert squadron.block_collector.drain() == []  # type: ignore[union-attr]


class TestAllowlistVariant:
    async def test_allowlisted_write_lands_others_still_blocked(self, tmp_path: Path) -> None:
        _build_repo(tmp_path)
        config = _make_config(allowlist=["CLAUDE.md"])

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=lambda: _mutate_repo(tmp_path),
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                await coder.implement("implement the bead")
                records = squadron.block_collector.drain()  # type: ignore[union-attr]

        # CLAUDE.md is allowlisted — the agent's rewrite lands, with no
        # block event recorded for it (SC-004).
        assert (tmp_path / "CLAUDE.md").read_text() == "# CLAUDE.md\n\nAGENT OVERWROTE THIS\n"
        assert not any(r.path == "CLAUDE.md" for r in records)
        # Everything else in the default protected set is still enforced,
        # in the same run.
        assert (tmp_path / ".specify" / "memory" / "constitution.md").is_file()
        assert not (tmp_path / "sub" / "AGENTS.md").exists()
        blocked_paths = {r.path for r in records}
        assert blocked_paths == {".specify/memory/constitution.md", "sub/AGENTS.md"}

    async def test_custom_glob_extends_protected_set(self, tmp_path: Path) -> None:
        _build_repo(tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "agent-rules.md").write_text("custom protected rules\n")
        config = _make_config(additional_globs=["docs/agent-rules.md"])

        def _mutate() -> None:
            (tmp_path / "docs" / "agent-rules.md").write_text("agent overwrote custom glob\n")
            (tmp_path / "src" / "real_work.py").write_text("def after():\n    return 2\n")

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=_mutate,
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                await coder.implement("implement the bead")
                records = squadron.block_collector.drain()  # type: ignore[union-attr]

        assert (tmp_path / "docs" / "agent-rules.md").read_text() == "custom protected rules\n"
        assert (tmp_path / "src" / "real_work.py").read_text() == "def after():\n    return 2\n"
        assert any(r.path == "docs/agent-rules.md" for r in records)


class TestNoAssumptionLedgerInteraction:
    async def test_protection_never_touches_bd(self, tmp_path: Path) -> None:
        """FR-005: block records never create assumption-ledger entries —
        proven by the fact nothing in this feature imports/calls
        ``maverick.assumptions`` or ``BeadClient`` at all."""
        import maverick.protection.policy as policy_mod
        import maverick.protection.records as records_mod
        import maverick.protection.snapshot as snapshot_mod

        for mod in (policy_mod, records_mod, snapshot_mod):
            source = Path(mod.__file__).read_text()  # type: ignore[arg-type]
            assert "assumptions" not in source
            assert "BeadClient" not in source


class TestWorkflowOwnedMutationOutsideAgentPathSurvives:
    async def test_mutation_between_agent_steps_is_never_reverted(self, tmp_path: Path) -> None:
        """FR-010: the backstop only brackets Agent execute calls — a
        workflow-owned write to a protected path *between* agent steps
        (not during one) is never the backstop's business."""
        _build_repo(tmp_path)
        config = _make_config()

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                await coder.implement("implement the bead")

                # A workflow action (not the agent) intentionally updates
                # CLAUDE.md between steps — outside any Agent execute call.
                (tmp_path / "CLAUDE.md").write_text("workflow-authored update\n")

                await coder.implement("a second, unrelated bead step")

        # The workflow-owned write survives — it was never inside a
        # snapshot/restore bracket.
        assert (tmp_path / "CLAUDE.md").read_text() == "workflow-authored update\n"


class TestSpecChainWorkspaceVariant:
    async def test_workspace_rooted_policy_protects_the_workspace(self, tmp_path: Path) -> None:
        """Spec-chain builds its agent with cwd=<hidden workspace> — the
        policy root follows, per research.md R10."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".specify" / "memory").mkdir(parents=True)
        (workspace / "AGENTS.md").write_text("workspace agents file\n")
        config = _make_config()

        report = StepReport(
            status="completed",
            artifacts=["specs/001-x/spec.md"],
            detail="done",
        )

        def _mutate() -> None:
            (workspace / "AGENTS.md").write_text("agent overwrote the workspace copy\n")

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=_mutate,
                        result=RuntimeResult(
                            text="",
                            structured=report.model_dump(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with SpecChainSquadron(cwd=workspace, config=config) as squadron:
                await squadron.chain_agent.run_step("run the specify step")

        assert (workspace / "AGENTS.md").read_text() == "workspace agents file\n"


class TestRepeatedRetriesIndividuallyRecordedSummarizedOnce:
    """Spec edge case: repeated blocked-write retries within a run are each
    individually recorded in the collector/artifact, but fly's loop-exit
    summary warning fires exactly once (proven separately in
    tests/unit/workflows/fly_beads/test_protection_backstop.py — this test
    proves the *recording* half at the squadron/agent seam)."""

    async def test_two_implement_calls_each_mutating_claude_md_yield_two_records(
        self, tmp_path: Path
    ) -> None:
        _build_repo(tmp_path)
        config = _make_config()

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=lambda: (tmp_path / "CLAUDE.md").write_text("mutated again\n"),
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                await coder.implement("attempt 1")
                await coder.implement("attempt 2")

                records = squadron.block_collector.drain()  # type: ignore[union-attr]

        # Each attempt is its own record — never deduplicated/merged —
        # even though both target the same path.
        assert len(records) == 2
        assert all(r.path == "CLAUDE.md" for r in records)
        assert (tmp_path / "CLAUDE.md").read_text() == "# CLAUDE.md\n\noriginal instructions\n"


class TestArtifactSchemaMatchesContract:
    async def test_persisted_artifact_matches_block_event_contract_shape(
        self, tmp_path: Path
    ) -> None:
        """contracts/block-event.md's protection-blocks.json shape:
        schema_version, run_id, workflow, generated_at, blocks[*] ==
        BlockRecord.to_dict() field-for-field."""
        _build_repo(tmp_path)
        config = _make_config()

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=lambda: _mutate_repo(tmp_path),
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        with patch("airframe.runtime_for", new=_factory):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                await coder.implement("implement the bead")
                records = squadron.block_collector.drain()  # type: ignore[union-attr]

        run_dir = tmp_path / ".maverick" / "runs" / "int-test-run"
        path = await persist_blocks_artifact(
            run_dir=run_dir, run_id="int-test-run", workflow="fly-beads", records=records
        )
        assert path is not None

        import json

        data = json.loads(path.read_text())
        assert set(data.keys()) == {
            "schema_version",
            "run_id",
            "workflow",
            "generated_at",
            "blocks",
        }
        assert data["schema_version"] == 1
        assert data["run_id"] == "int-test-run"
        assert data["workflow"] == "fly-beads"
        assert isinstance(data["generated_at"], str)
        assert len(data["blocks"]) == len(records)
        for block in data["blocks"]:
            assert set(block.keys()) == {
                "agent_role",
                "workflow",
                "operation",
                "path",
                "destination_path",
                "layer",
                "bead_id",
                "detail",
                "timestamp",
            }
            assert block["layer"] == "backstop"
            assert block["operation"] == "restore"


class TestNoAssumptionLedgerEntriesCreatedEndToEnd:
    async def test_bd_client_never_constructed_during_a_protected_run(
        self, tmp_path: Path
    ) -> None:
        """FR-005 behaviorally: run a full protected bead through the
        squadron/agent seam with ``BeadClient.__init__`` patched to raise
        — if anything in the protection path tried to touch the
        assumption ledger (which always goes through a BeadClient), this
        test would fail loudly instead of relying on a source grep."""
        _build_repo(tmp_path)
        config = _make_config()

        def _factory(_provider_id: str) -> type[_StubRuntime]:
            class _Bound(_StubRuntime):
                def __init__(self, **kwargs: Any) -> None:
                    super().__init__(
                        mutate=lambda: _mutate_repo(tmp_path),
                        result=RuntimeResult(
                            text="",
                            structured=_impl_payload_dict(),
                            cost=_cost(),
                            finish="end_turn",
                        ),
                        **kwargs,
                    )

            return _Bound

        def _bead_client_raises(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("BeadClient must never be constructed by the protection path")

        with (
            patch("airframe.runtime_for", new=_factory),
            patch("maverick.beads.client.BeadClient.__init__", new=_bead_client_raises),
        ):
            async with FlySquadron(cwd=tmp_path, config=config) as squadron:
                coder = squadron.coder_for(DEFAULT_TIER)
                payload = await coder.implement("implement the bead")

        assert isinstance(payload, SubmitImplementationPayload)
