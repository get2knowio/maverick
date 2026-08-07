"""Unit tests for `SpecChainWorkflow` helper methods added by code review.

Covers two resume-path correctness fixes:

* ``_reseed_workspace_from_checkout`` — a freshly-recreated hidden
  workspace (the user cleared ``~/.maverick/workspaces`` between runs)
  gets its landed upstream artifacts restored from the checkout, so
  downstream steps don't run against an empty workspace.
* ``_file_clarify_decisions`` idempotency — a resume that re-runs clarify
  merges by normalized question instead of blindly appending, so the
  audit list (and its derived counts) don't double.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.models import ChainState, ClarifyDecision, StepRecord
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow


def _config() -> MaverickConfig:
    return MaverickConfig(
        agents=AgentsConfig(generate=AgentBindingConfig(provider="claude", model_id="stub-model"))
    )


def _workflow() -> SpecChainWorkflow:
    return SpecChainWorkflow(config=_config())


def _base_state(*, feature_dir: str | None, **overrides: object) -> ChainState:
    now = datetime.now(tz=UTC)
    defaults: dict[str, object] = {
        "run_id": "run-1",
        "feature": "widget-export",
        "feature_dir": feature_dir,
        "prd_path": "docs/prd.md",
        "prd_digest": "0" * 64,
        "workspace_path": "/tmp/ws",
        "status": "running",
        "started_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return ChainState(**defaults)  # type: ignore[arg-type]


class TestReseedWorkspaceFromCheckout:
    def _landed_steps(self) -> dict[ChainStep, StepRecord]:
        return {
            ChainStep.SPECIFY: StepRecord(
                step=ChainStep.SPECIFY,
                status="succeeded",
                landed=True,
                artifacts=["spec.md"],
            ),
            ChainStep.PLAN: StepRecord(
                step=ChainStep.PLAN,
                status="succeeded",
                landed=True,
                artifacts=["plan.md"],
            ),
        }

    def test_restores_landed_artifacts_into_empty_workspace(self, tmp_path: Path) -> None:
        checkout = tmp_path / "checkout"
        workspace = tmp_path / "workspace"
        feature_dir = "001-widget-export"
        checkout_feature = checkout / "specs" / feature_dir
        checkout_feature.mkdir(parents=True)
        (checkout_feature / "spec.md").write_text("spec body", encoding="utf-8")
        (checkout_feature / "plan.md").write_text("plan body", encoding="utf-8")
        (workspace / "specs").mkdir(parents=True)  # workspace exists but is empty

        state = _base_state(feature_dir=f"specs/{feature_dir}", steps=self._landed_steps())

        _workflow()._reseed_workspace_from_checkout(state, workspace=workspace, checkout=checkout)

        ws_feature = workspace / "specs" / feature_dir
        assert (ws_feature / "spec.md").read_text(encoding="utf-8") == "spec body"
        assert (ws_feature / "plan.md").read_text(encoding="utf-8") == "plan body"

    def test_noop_when_workspace_already_has_artifacts(self, tmp_path: Path) -> None:
        checkout = tmp_path / "checkout"
        workspace = tmp_path / "workspace"
        feature_dir = "001-widget-export"
        checkout_feature = checkout / "specs" / feature_dir
        checkout_feature.mkdir(parents=True)
        (checkout_feature / "spec.md").write_text("checkout spec", encoding="utf-8")
        (checkout_feature / "plan.md").write_text("checkout plan", encoding="utf-8")

        ws_feature = workspace / "specs" / feature_dir
        ws_feature.mkdir(parents=True)
        # Workspace already holds the landed artifacts (normal reuse path):
        # the reseed must not clobber them with the checkout copies.
        (ws_feature / "spec.md").write_text("workspace spec", encoding="utf-8")
        (ws_feature / "plan.md").write_text("workspace plan", encoding="utf-8")

        state = _base_state(feature_dir=f"specs/{feature_dir}", steps=self._landed_steps())

        _workflow()._reseed_workspace_from_checkout(state, workspace=workspace, checkout=checkout)

        assert (ws_feature / "spec.md").read_text(encoding="utf-8") == "workspace spec"
        assert (ws_feature / "plan.md").read_text(encoding="utf-8") == "workspace plan"

    def test_noop_when_no_feature_dir_yet(self, tmp_path: Path) -> None:
        checkout = tmp_path / "checkout"
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = _base_state(feature_dir=None)

        # Must not raise, must not create anything.
        _workflow()._reseed_workspace_from_checkout(state, workspace=workspace, checkout=checkout)
        assert not (workspace / "specs").exists()

    def test_noop_when_checkout_feature_dir_absent(self, tmp_path: Path) -> None:
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = _base_state(feature_dir="specs/001-widget-export", steps=self._landed_steps())

        _workflow()._reseed_workspace_from_checkout(state, workspace=workspace, checkout=checkout)
        assert not (workspace / "specs").exists()

    def test_reseeds_when_only_some_artifacts_present(self, tmp_path: Path) -> None:
        """A partially-populated workspace (e.g. plan.md restored but
        spec.md missing) still triggers a full reseed of the feature dir."""
        checkout = tmp_path / "checkout"
        workspace = tmp_path / "workspace"
        feature_dir = "001-widget-export"
        checkout_feature = checkout / "specs" / feature_dir
        checkout_feature.mkdir(parents=True)
        (checkout_feature / "spec.md").write_text("spec body", encoding="utf-8")
        (checkout_feature / "plan.md").write_text("plan body", encoding="utf-8")

        ws_feature = workspace / "specs" / feature_dir
        ws_feature.mkdir(parents=True)
        (ws_feature / "plan.md").write_text("stale plan", encoding="utf-8")  # spec.md missing

        state = _base_state(feature_dir=f"specs/{feature_dir}", steps=self._landed_steps())

        _workflow()._reseed_workspace_from_checkout(state, workspace=workspace, checkout=checkout)

        assert (ws_feature / "spec.md").read_text(encoding="utf-8") == "spec body"
        assert (ws_feature / "plan.md").read_text(encoding="utf-8") == "plan body"


class TestFileClarifyDecisionsIdempotency:
    def _spec_md(self) -> str:
        return (
            "# Spec\n\n## Clarifications\n\n### Session 2026-07-24\n\n"
            "- Q: Should exports include archived widgets? "
            "→ A: No, exclude archived widgets.\n"
        )

    def _existing_decision(self) -> ClarifyDecision:
        from maverick.assumptions.models import Severity

        return ClarifyDecision(
            question="Should exports include archived widgets?",
            adopted_answer="No, exclude archived widgets.",
            alternatives=(),
            severity=Severity.MEDIUM,
            severity_defaulted=False,
            path="non_interactive",
            ledger_bead_id="dea-existing",
        )

    async def test_resume_rerun_does_not_double_decisions(self, tmp_path: Path) -> None:
        feature_dir = "001-widget-export"
        workspace = tmp_path / "workspace"
        spec_dir = workspace / "specs" / feature_dir
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.md").write_text(self._spec_md(), encoding="utf-8")
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        # State already carries the decision from the pre-halt clarify run.
        state = _base_state(
            feature_dir=f"specs/{feature_dir}",
            clarify_decisions=[self._existing_decision()],
        )

        created = type("Record", (), {"bead_id": "dea-existing", "severity": None})()
        with patch(
            "maverick.workflows.spec_chain.workflow.record_standalone_assumption",
            new=AsyncMock(return_value=created),
        ):
            new_state = await _workflow()._file_clarify_decisions(
                state, workspace=workspace, checkout=checkout, feature_dir_name=feature_dir
            )

        # Same question re-parsed on resume must merge, not append.
        assert len(new_state.clarify_decisions) == 1
        questions = [d.question for d in new_state.clarify_decisions]
        assert questions == ["Should exports include archived widgets?"]

    async def test_fresh_run_records_the_decision(self, tmp_path: Path) -> None:
        feature_dir = "001-widget-export"
        workspace = tmp_path / "workspace"
        spec_dir = workspace / "specs" / feature_dir
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.md").write_text(self._spec_md(), encoding="utf-8")
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        state = _base_state(feature_dir=f"specs/{feature_dir}", clarify_decisions=[])

        created = type("Record", (), {"bead_id": "dea-1", "severity": None})()
        with patch(
            "maverick.workflows.spec_chain.workflow.record_standalone_assumption",
            new=AsyncMock(return_value=created),
        ):
            new_state = await _workflow()._file_clarify_decisions(
                state, workspace=workspace, checkout=checkout, feature_dir_name=feature_dir
            )

        assert len(new_state.clarify_decisions) == 1
        assert new_state.clarify_decisions[0].ledger_bead_id == "dea-1"


class TestFileClarifyDecisionsCallsAttachSuggestions:
    """055-learned-assumption-resolution T014 (US2): after filing each
    parsed clarify/assumptions-section decision as a standalone ledger
    entry, ``_file_clarify_decisions`` hands the newly filed entries to
    ``assumptions.suggestions.attach_suggestions`` — non-fatally, and
    against the user's checkout (never the hidden workspace), matching
    the existing ``BeadClient(cwd=checkout)`` construction (research R5,
    T020).
    """

    def _spec_md(self) -> str:
        return (
            "# Spec\n\n## Clarifications\n\n### Session 2026-07-24\n\n"
            "- Q: Should exports include archived widgets? "
            "→ A: No, exclude archived widgets.\n"
        )

    async def test_calls_attach_suggestions_with_filed_entries_against_checkout(
        self, tmp_path: Path
    ) -> None:
        feature_dir = "001-widget-export"
        workspace = tmp_path / "workspace"
        spec_dir = workspace / "specs" / feature_dir
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.md").write_text(self._spec_md(), encoding="utf-8")
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        state = _base_state(feature_dir=f"specs/{feature_dir}", clarify_decisions=[])

        created = type("Record", (), {"bead_id": "dea-1", "severity": None})()
        with (
            patch(
                "maverick.workflows.spec_chain.workflow.record_standalone_assumption",
                new=AsyncMock(return_value=created),
            ),
            patch(
                "maverick.workflows.spec_chain.workflow.attach_suggestions",
                new=AsyncMock(),
            ) as mock_attach,
        ):
            new_state = await _workflow()._file_clarify_decisions(
                state, workspace=workspace, checkout=checkout, feature_dir_name=feature_dir
            )

        assert len(new_state.clarify_decisions) == 1
        mock_attach.assert_awaited_once()
        call_args = list(mock_attach.await_args.args) + list(
            mock_attach.await_args.kwargs.values()
        )

        # The client/store passed must be rooted at the user's checkout,
        # never the hidden spec-chain workspace (Guardrail 0's one
        # exception still must not leak into where ledger/runway state is
        # written).
        client_like = next((a for a in call_args if hasattr(a, "_cwd")), None)
        assert client_like is not None, f"expected a BeadClient-like argument among {call_args!r}"
        assert Path(client_like._cwd) == checkout
        assert Path(client_like._cwd) != workspace

        store_like = next((a for a in call_args if hasattr(a, "path")), None)
        if store_like is not None:
            assert checkout in Path(store_like.path).parents or Path(store_like.path) == checkout
            assert workspace not in Path(store_like.path).parents

        records_arg = next((a for a in call_args if isinstance(a, (list, tuple))), None)
        assert records_arg is not None, (
            f"expected a list/tuple of newly filed entries among {call_args!r}"
        )
        # Must be `AssumptionReportEntry`s, not bare `AssumptionRecord`s:
        # `attach_suggestions` reads `entry.record.*`, so handing it a raw
        # record raises `AttributeError` inside its own best-effort handler
        # and silently disables suggestions on this path.
        assert {item.record.bead_id for item in records_arg} == {"dea-1"}

    async def test_attach_suggestions_failure_is_non_fatal(self, tmp_path: Path) -> None:
        feature_dir = "001-widget-export"
        workspace = tmp_path / "workspace"
        spec_dir = workspace / "specs" / feature_dir
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.md").write_text(self._spec_md(), encoding="utf-8")
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        state = _base_state(feature_dir=f"specs/{feature_dir}", clarify_decisions=[])

        created = type("Record", (), {"bead_id": "dea-1", "severity": None})()
        with (
            patch(
                "maverick.workflows.spec_chain.workflow.record_standalone_assumption",
                new=AsyncMock(return_value=created),
            ),
            patch(
                "maverick.workflows.spec_chain.workflow.attach_suggestions",
                new=AsyncMock(side_effect=RuntimeError("runway unavailable")),
            ),
        ):
            # Must not raise even though attach_suggestions blows up.
            new_state = await _workflow()._file_clarify_decisions(
                state, workspace=workspace, checkout=checkout, feature_dir_name=feature_dir
            )

        # The decision-filing result is unaffected by the suggestion
        # attachment failure.
        assert len(new_state.clarify_decisions) == 1
        assert new_state.clarify_decisions[0].ledger_bead_id == "dea-1"
