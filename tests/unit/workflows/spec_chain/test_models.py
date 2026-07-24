"""Tests for maverick.workflows.spec_chain constants and models.

T004: ChainStep ordering, ChainState/StepRecord/ClarifyDecision/StepReport/
AnalyzeFinding validation, and the "in_progress only after all prior steps
succeeded" state-transition invariant — per
specs/050-headless-spec-chain/data-model.md.

Written before implementation (TDD, Constitution Principle V):
``src/maverick/workflows/spec_chain/constants.py`` and
``.../models.py`` are still placeholder stubs, so every test in this
module MUST fail (ImportError / AttributeError) until T007 (constants.py)
and T008 (models.py) land.
"""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from maverick.workflows.spec_chain.models import ChainState, StepRecord


# ===========================================================================
# Shared fixtures / builders
# ===========================================================================


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)


def _make_step_record(step: Any, status: str = "pending", **overrides: Any) -> StepRecord:
    """Build a valid StepRecord for *step* with sensible fresh defaults."""
    from maverick.workflows.spec_chain.models import StepRecord

    defaults: dict[str, Any] = {
        "step": step,
        "status": status,
        "attempts": 0,
        "artifacts": [],
        "landed": False,
        "error": None,
        "started_at": None,
        "finished_at": None,
    }
    defaults.update(overrides)
    return StepRecord(**defaults)


def _make_chain_state(**overrides: Any) -> ChainState:
    """Build a valid ChainState from sample data."""
    from maverick.workflows.spec_chain.models import ChainState

    defaults: dict[str, Any] = {
        "run_id": "run-20260724-120000",
        "feature": "headless-spec-chain",
        "feature_dir": None,
        "prd_path": "docs/prd.md",
        "prd_digest": hashlib.sha256(b"prd content").hexdigest(),
        "workspace_path": ("/home/user/.maverick/workspaces/proj/spec-chain/headless-spec-chain/"),
        "status": "running",
        "steps": {},
        "clarify_decisions": [],
        "remediation_bead_ids": [],
        "started_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    return ChainState(**defaults)


# ===========================================================================
# ChainStep (enum) — constants.py
# ===========================================================================


class TestChainStepOrder:
    """ChainStep enum ordering: SPECIFY -> CLARIFY -> PLAN -> TASKS -> ANALYZE.

    "The order is the single source of truth for FR-002/FR-008 gating."
    """

    def test_members_exist(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        assert {member.name for member in ChainStep} == {
            "SPECIFY",
            "CLARIFY",
            "PLAN",
            "TASKS",
            "ANALYZE",
        }

    def test_string_values(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        assert ChainStep.SPECIFY == "specify"
        assert ChainStep.CLARIFY == "clarify"
        assert ChainStep.PLAN == "plan"
        assert ChainStep.TASKS == "tasks"
        assert ChainStep.ANALYZE == "analyze"

    def test_chain_step_order_sequence(self) -> None:
        from maverick.workflows.spec_chain.constants import CHAIN_STEP_ORDER, ChainStep

        assert CHAIN_STEP_ORDER == (
            ChainStep.SPECIFY,
            ChainStep.CLARIFY,
            ChainStep.PLAN,
            ChainStep.TASKS,
            ChainStep.ANALYZE,
        )

    def test_order_is_single_source_of_truth(self) -> None:
        from maverick.workflows.spec_chain.constants import CHAIN_STEP_ORDER, ChainStep

        assert len(CHAIN_STEP_ORDER) == len(list(ChainStep))
        assert set(CHAIN_STEP_ORDER) == set(ChainStep)
        assert len(set(CHAIN_STEP_ORDER)) == len(CHAIN_STEP_ORDER)  # no duplicates


class TestNextStep:
    """``next_step(...)`` derives the next step to run from CHAIN_STEP_ORDER
    (data-model.md: "next_step(state) derives from it"; contracts/chain-state.md:
    "continue from the first step whose status is not succeeded")."""

    def test_empty_steps_returns_first_step(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import next_step

        assert next_step({}) == ChainStep.SPECIFY

    def test_returns_first_non_succeeded_step(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import next_step

        steps = {ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded")}
        assert next_step(steps) == ChainStep.CLARIFY

    def test_skips_over_multiple_succeeded_steps(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import next_step

        steps = {
            ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded"),
            ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="succeeded"),
            ChainStep.PLAN: _make_step_record(ChainStep.PLAN, status="succeeded"),
        }
        assert next_step(steps) == ChainStep.TASKS

    def test_failed_step_is_the_next_step_to_retry(self) -> None:
        """A failed step is retried on resume, not skipped over."""
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import next_step

        steps = {
            ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded"),
            ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="failed"),
        }
        assert next_step(steps) == ChainStep.CLARIFY

    def test_all_succeeded_returns_none(self) -> None:
        from maverick.workflows.spec_chain.constants import CHAIN_STEP_ORDER
        from maverick.workflows.spec_chain.models import next_step

        steps = {s: _make_step_record(s, status="succeeded") for s in CHAIN_STEP_ORDER}
        assert next_step(steps) is None

    def test_works_from_a_chain_state_steps_mapping(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import next_step

        state = _make_chain_state(
            steps={ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded")}
        )
        assert next_step(state.steps) == ChainStep.CLARIFY


# ===========================================================================
# StepRecord — nested in ChainState
# ===========================================================================


class TestStepRecord:
    def test_minimal_construction_defaults(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import StepRecord

        record = StepRecord(step=ChainStep.SPECIFY, status="pending")
        assert record.step == ChainStep.SPECIFY
        assert record.status == "pending"
        assert record.attempts == 0
        assert list(record.artifacts) == []
        assert record.landed is False
        assert record.error is None
        assert record.started_at is None
        assert record.finished_at is None

    def test_all_fields_construction(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import StepRecord

        started = _now()
        record = StepRecord(
            step=ChainStep.PLAN,
            status="succeeded",
            attempts=2,
            artifacts=["specs/001-foo/plan.md"],
            landed=True,
            error=None,
            started_at=started,
            finished_at=started,
        )
        assert record.attempts == 2
        assert record.artifacts == ["specs/001-foo/plan.md"]
        assert record.landed is True
        assert record.started_at == started

    def test_artifacts_is_list(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        record = _make_step_record(ChainStep.SPECIFY, artifacts=["a.md", "b.md"])
        assert isinstance(record.artifacts, list)

    @pytest.mark.parametrize(
        "status", ["pending", "in_progress", "succeeded", "failed", "skipped"]
    )
    def test_valid_status_values(self, status: str) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import StepRecord

        record = StepRecord(step=ChainStep.SPECIFY, status=status)
        assert record.status == status

    def test_invalid_status_raises(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import StepRecord

        with pytest.raises(ValidationError):
            StepRecord(step=ChainStep.SPECIFY, status="not-a-real-status")

    def test_error_field_carries_failure_summary(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        record = _make_step_record(ChainStep.CLARIFY, status="failed", error="model timeout")
        assert record.error == "model timeout"

    def test_started_and_finished_at_accept_datetimes(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import StepRecord

        started = _now()
        record = StepRecord(step=ChainStep.SPECIFY, status="in_progress", started_at=started)
        assert record.started_at == started
        assert record.finished_at is None

    def test_invalid_step_raises(self) -> None:
        from maverick.workflows.spec_chain.models import StepRecord

        with pytest.raises(ValidationError):
            StepRecord(step="not-a-chain-step", status="pending")  # type: ignore[arg-type]


# ===========================================================================
# ChainState — schema_version, required fields, defaults
# ===========================================================================


class TestChainStateFields:
    def test_construction_all_fields(self) -> None:
        from maverick.workflows.spec_chain.models import ChainState

        state = _make_chain_state()
        assert isinstance(state, ChainState)

    def test_required_fields_accessible(self) -> None:
        state = _make_chain_state()
        assert state.run_id == "run-20260724-120000"
        assert state.feature == "headless-spec-chain"
        assert state.status == "running"
        assert state.prd_path == "docs/prd.md"

    def test_schema_version_defaults_to_1(self) -> None:
        state = _make_chain_state()
        assert state.schema_version == 1

    def test_schema_version_explicit(self) -> None:
        state = _make_chain_state(schema_version=1)
        assert state.schema_version == 1

    def test_feature_dir_defaults_to_none(self) -> None:
        """feature_dir is None until specify lands."""
        state = _make_chain_state()
        assert state.feature_dir is None

    def test_feature_dir_set_after_specify(self) -> None:
        state = _make_chain_state(feature_dir="specs/051-headless-spec-chain")
        assert state.feature_dir == "specs/051-headless-spec-chain"

    def test_clarify_decisions_defaults_to_empty_list(self) -> None:
        state = _make_chain_state()
        assert list(state.clarify_decisions) == []

    def test_remediation_bead_ids_defaults_to_empty_list(self) -> None:
        state = _make_chain_state()
        assert list(state.remediation_bead_ids) == []

    def test_remediation_bead_ids_is_list_of_str(self) -> None:
        state = _make_chain_state(remediation_bead_ids=["bd-1", "bd-2"])
        assert state.remediation_bead_ids == ["bd-1", "bd-2"]

    @pytest.mark.parametrize("status", ["running", "halted", "completed", "failed"])
    def test_valid_status_values(self, status: str) -> None:
        state = _make_chain_state(status=status)
        assert state.status == status

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_chain_state(status="not-a-status")

    def test_missing_required_field_raises(self) -> None:
        from maverick.workflows.spec_chain.models import ChainState

        with pytest.raises(ValidationError):
            ChainState(  # type: ignore[call-arg]
                feature="headless-spec-chain",
                prd_path="docs/prd.md",
                prd_digest=hashlib.sha256(b"x").hexdigest(),
                workspace_path="/tmp/ws",
                status="running",
                steps={},
                clarify_decisions=[],
                remediation_bead_ids=[],
                started_at=_now(),
                updated_at=_now(),
            )  # run_id omitted

    def test_steps_dict_keyed_by_chain_step(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        state = _make_chain_state(
            steps={ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded")}
        )
        assert ChainStep.SPECIFY in state.steps
        assert state.steps[ChainStep.SPECIFY].status == "succeeded"

    def test_json_round_trip_preserves_steps(self) -> None:
        """Persisted to .maverick/runs/<run-id>/spec-chain.json as JSON;
        dict[ChainStep, StepRecord] keys must serialise to plain strings
        and round-trip through model_validate."""
        from maverick.workflows.spec_chain.constants import ChainStep
        from maverick.workflows.spec_chain.models import ChainState

        state = _make_chain_state(
            steps={ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded")}
        )
        dumped = state.model_dump(mode="json")
        assert set(dumped["steps"].keys()) == {"specify"}
        assert dumped["steps"]["specify"]["status"] == "succeeded"

        restored = ChainState.model_validate(dumped)
        assert restored.steps[ChainStep.SPECIFY].status == "succeeded"
        assert restored == state


# ===========================================================================
# ChainState — Validation rules: feature name, non-empty, filesystem-safe slug
# ===========================================================================


class TestChainStateFeatureValidation:
    """Validation rules: "Feature name: non-empty, filesystem-safe slug."""

    def test_empty_feature_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_chain_state(feature="")

    def test_feature_with_parent_dir_traversal_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_chain_state(feature="../escape")

    def test_feature_with_slash_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_chain_state(feature="foo/bar")

    def test_valid_kebab_slug_accepted(self) -> None:
        state = _make_chain_state(feature="headless-spec-chain")
        assert state.feature == "headless-spec-chain"


# ===========================================================================
# ChainState — state-transition invariant: in_progress only after all
# prior steps have succeeded.
# ===========================================================================


class TestChainStateStepInvariant:
    """ "Invariant: a step may be in_progress only if all steps ordered
    before it are succeeded." (data-model.md "State transitions")."""

    def test_fresh_state_with_no_steps_is_valid(self) -> None:
        state = _make_chain_state(steps={})
        assert state.steps == {}

    def test_first_step_in_progress_is_valid(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        state = _make_chain_state(
            steps={ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="in_progress")}
        )
        assert state.steps[ChainStep.SPECIFY].status == "in_progress"

    def test_ascending_progress_is_valid(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        state = _make_chain_state(
            steps={
                ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded"),
                ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="succeeded"),
                ChainStep.PLAN: _make_step_record(ChainStep.PLAN, status="in_progress"),
            }
        )
        assert state.steps[ChainStep.PLAN].status == "in_progress"

    def test_last_step_in_progress_after_all_prior_succeeded_is_valid(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        steps = {
            s: _make_step_record(s, status="succeeded")
            for s in (
                ChainStep.SPECIFY,
                ChainStep.CLARIFY,
                ChainStep.PLAN,
                ChainStep.TASKS,
            )
        }
        steps[ChainStep.ANALYZE] = _make_step_record(ChainStep.ANALYZE, status="in_progress")
        state = _make_chain_state(steps=steps)
        assert state.steps[ChainStep.ANALYZE].status == "in_progress"

    def test_in_progress_step_with_missing_prior_step_raises(self) -> None:
        """CLARIFY in_progress but SPECIFY has no record at all (never
        attempted) violates the invariant just as much as an explicit
        pending/failed prior step."""
        from maverick.workflows.spec_chain.constants import ChainStep

        with pytest.raises(ValidationError):
            _make_chain_state(
                steps={
                    ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="in_progress")
                }
            )

    def test_in_progress_step_with_pending_prior_step_raises(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        with pytest.raises(ValidationError):
            _make_chain_state(
                steps={
                    ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="pending"),
                    ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="in_progress"),
                }
            )

    def test_in_progress_step_with_failed_prior_step_raises(self) -> None:
        from maverick.workflows.spec_chain.constants import ChainStep

        with pytest.raises(ValidationError):
            _make_chain_state(
                steps={
                    ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded"),
                    ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="failed"),
                    ChainStep.PLAN: _make_step_record(ChainStep.PLAN, status="in_progress"),
                }
            )

    def test_two_steps_in_progress_simultaneously_raises(self) -> None:
        """A second in_progress entry whose predecessor is itself only
        in_progress (not succeeded) violates the invariant."""
        from maverick.workflows.spec_chain.constants import ChainStep

        with pytest.raises(ValidationError):
            _make_chain_state(
                steps={
                    ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="in_progress"),
                    ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="in_progress"),
                }
            )

    def test_halted_chain_with_failed_step_and_skipped_tail_is_valid(self) -> None:
        """Contract (chain-state.md, FR-009): steps[CLARIFY].status ==
        "failed" => status == "halted" and plan/tasks/analyze remain
        pending/skipped. No step is in_progress here, so the invariant
        does not block it."""
        from maverick.workflows.spec_chain.constants import ChainStep

        state = _make_chain_state(
            status="halted",
            steps={
                ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded"),
                ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="failed"),
                ChainStep.PLAN: _make_step_record(ChainStep.PLAN, status="skipped"),
                ChainStep.TASKS: _make_step_record(ChainStep.TASKS, status="skipped"),
                ChainStep.ANALYZE: _make_step_record(ChainStep.ANALYZE, status="skipped"),
            },
        )
        assert state.status == "halted"

    def test_succeeded_then_untouched_pending_is_valid(self) -> None:
        """Steps may be succeeded up to some point with the rest untouched
        (pending) as long as nothing is in_progress out of order."""
        from maverick.workflows.spec_chain.constants import ChainStep

        state = _make_chain_state(
            steps={
                ChainStep.SPECIFY: _make_step_record(ChainStep.SPECIFY, status="succeeded"),
                ChainStep.CLARIFY: _make_step_record(ChainStep.CLARIFY, status="pending"),
            }
        )
        assert state.steps[ChainStep.CLARIFY].status == "pending"


# ===========================================================================
# ClarifyDecision — frozen dataclass
# ===========================================================================


class TestClarifyDecision:
    def _make(self, **overrides: Any) -> Any:
        from maverick.assumptions.models import Severity
        from maverick.workflows.spec_chain.models import ClarifyDecision

        defaults: dict[str, Any] = {
            "question": "Should the API support pagination?",
            "adopted_answer": "Yes, cursor-based pagination.",
            "alternatives": ("Offset-based pagination", "No pagination"),
            "severity": Severity.LOW,
            "severity_defaulted": False,
            "path": "interception",
            "ledger_bead_id": None,
        }
        defaults.update(overrides)
        return ClarifyDecision(**defaults)

    def test_construction_all_fields(self) -> None:
        from maverick.workflows.spec_chain.models import ClarifyDecision

        decision = self._make()
        assert isinstance(decision, ClarifyDecision)

    def test_fields_accessible(self) -> None:
        decision = self._make()
        assert decision.question == "Should the API support pagination?"
        assert decision.adopted_answer == "Yes, cursor-based pagination."
        assert decision.path == "interception"

    def test_severity_uses_shared_assumption_ledger_enum(self) -> None:
        """Field type is maverick.assumptions.models.Severity (spec 049) —
        not a locally-defined duplicate."""
        from maverick.assumptions.models import Severity

        decision = self._make(severity=Severity.HIGH)
        assert decision.severity is Severity.HIGH

    def test_severity_defaulted_flag_is_independent_of_severity_value(self) -> None:
        """FR-007a: default severity is LOW when the harness has no clear
        signal; severity_defaulted records that fact."""
        from maverick.assumptions.models import Severity

        decision = self._make(severity=Severity.LOW, severity_defaulted=True)
        assert decision.severity is Severity.LOW
        assert decision.severity_defaulted is True

    def test_alternatives_is_tuple(self) -> None:
        decision = self._make(alternatives=("a", "b"))
        assert isinstance(decision.alternatives, tuple)

    def test_alternatives_may_be_empty_on_fallback_path(self) -> None:
        decision = self._make(alternatives=(), path="non_interactive")
        assert decision.alternatives == ()

    def test_path_accepts_interception(self) -> None:
        decision = self._make(path="interception")
        assert decision.path == "interception"

    def test_path_accepts_non_interactive(self) -> None:
        decision = self._make(path="non_interactive")
        assert decision.path == "non_interactive"

    def test_ledger_bead_id_defaults_to_none(self) -> None:
        """ "ledger_bead_id | str | None | filled after filing" — absent
        at creation time, before record_standalone_assumption runs."""
        from maverick.workflows.spec_chain.models import ClarifyDecision

        decision = ClarifyDecision(
            question="Q",
            adopted_answer="A",
            alternatives=(),
            severity=self._make().severity,
            severity_defaulted=False,
            path="interception",
        )
        assert decision.ledger_bead_id is None

    def test_ledger_bead_id_filled_after_filing(self) -> None:
        decision = self._make(ledger_bead_id="bd-abc123")
        assert decision.ledger_bead_id == "bd-abc123"

    def test_frozen_immutability(self) -> None:
        decision = self._make()
        with pytest.raises(FrozenInstanceError):
            decision.question = "changed"  # type: ignore[misc]


# ===========================================================================
# StepReport (+ ReportedQuestion / ReportedFinding) — structured-output
# schema for SpecChainAgent.
# ===========================================================================


class TestReportedQuestion:
    def test_construction(self) -> None:
        from maverick.workflows.spec_chain.models import ReportedQuestion

        question = ReportedQuestion(
            question="Should X?",
            adopted_answer="Yes",
            alternatives=["No", "Maybe"],
        )
        assert question.question == "Should X?"
        assert question.adopted_answer == "Yes"
        assert question.alternatives == ["No", "Maybe"]

    def test_alternatives_defaults_to_empty(self) -> None:
        from maverick.workflows.spec_chain.models import ReportedQuestion

        question = ReportedQuestion(question="Q", adopted_answer="A")
        assert list(question.alternatives) == []


class TestReportedFinding:
    def test_construction_all_fields(self) -> None:
        from maverick.workflows.spec_chain.models import ReportedFinding

        finding = ReportedFinding(
            title="Ambiguous auth requirement",
            category="ambiguity",
            severity_hint="medium",
            location="spec.md#FR-003",
            summary="FR-003 doesn't specify token lifetime.",
        )
        assert finding.title == "Ambiguous auth requirement"
        assert finding.category == "ambiguity"
        assert finding.severity_hint == "medium"
        assert finding.location == "spec.md#FR-003"
        assert finding.summary == "FR-003 doesn't specify token lifetime."


class TestStepReport:
    def _make(self, **overrides: Any) -> Any:
        from maverick.workflows.spec_chain.models import StepReport

        defaults: dict[str, Any] = {
            "status": "completed",
            "artifacts": ["specs/001-foo/spec.md"],
            "questions": [],
            "findings": [],
            "detail": "Spec written from PRD.",
        }
        defaults.update(overrides)
        return StepReport(**defaults)

    def test_construction(self) -> None:
        from maverick.workflows.spec_chain.models import StepReport

        report = self._make()
        assert isinstance(report, StepReport)

    @pytest.mark.parametrize("status", ["completed", "blocked", "failed"])
    def test_valid_status_values(self, status: str) -> None:
        report = self._make(status=status)
        assert report.status == status

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make(status="not-a-real-status")

    def test_artifacts_is_list_of_str(self) -> None:
        report = self._make(artifacts=["specs/001-foo/spec.md", "specs/001-foo/plan.md"])
        assert isinstance(report.artifacts, list)

    def test_questions_default_empty(self) -> None:
        report = self._make(questions=[])
        assert list(report.questions) == []

    def test_findings_default_empty(self) -> None:
        report = self._make(findings=[])
        assert list(report.findings) == []

    def test_questions_carries_reported_question_instances(self) -> None:
        from maverick.workflows.spec_chain.models import ReportedQuestion

        report = self._make(
            status="blocked",
            questions=[
                ReportedQuestion(question="Q1", adopted_answer="A1", alternatives=["B1"]),
            ],
        )
        assert report.questions[0].question == "Q1"

    def test_findings_carries_reported_finding_instances(self) -> None:
        from maverick.workflows.spec_chain.models import ReportedFinding

        report = self._make(
            status="completed",
            findings=[
                ReportedFinding(
                    title="Missing edge case",
                    category="coverage-gap",
                    severity_hint="low",
                    location="spec.md#FR-010",
                    summary="No handling for empty PRD.",
                ),
            ],
        )
        assert report.findings[0].title == "Missing edge case"

    def test_questions_accept_plain_dicts(self) -> None:
        """StepReport backs SpecChainAgent's format=json_schema structured
        output — OpenCode responses arrive as parsed JSON and are validated
        via model_validate, so plain dicts must coerce to ReportedQuestion."""
        report = self._make(
            status="blocked",
            questions=[{"question": "Q?", "adopted_answer": "A", "alternatives": []}],
        )
        assert report.questions[0].question == "Q?"

    def test_findings_accept_plain_dicts(self) -> None:
        report = self._make(
            status="completed",
            findings=[
                {
                    "title": "Gap",
                    "category": "coverage-gap",
                    "severity_hint": "low",
                    "location": "spec.md",
                    "summary": "summary",
                }
            ],
        )
        assert report.findings[0].title == "Gap"

    def test_json_schema_has_expected_top_level_fields(self) -> None:
        """StepReport is the schema OpenCode's format=json_schema forces the
        model to satisfy — it must expose all five top-level fields."""
        from maverick.workflows.spec_chain.models import StepReport

        schema = StepReport.model_json_schema()
        assert set(schema["properties"]) >= {
            "status",
            "artifacts",
            "questions",
            "findings",
            "detail",
        }


# ===========================================================================
# AnalyzeFinding -> remediation bead
# ===========================================================================


class TestAnalyzeFinding:
    def _make(self, **overrides: Any) -> Any:
        from maverick.workflows.spec_chain.models import AnalyzeFinding

        defaults: dict[str, Any] = {
            "title": "Ambiguous auth requirement",
            "category": "ambiguity",
            "severity_hint": "medium",
            "location": "spec.md#FR-003",
            "summary": "FR-003 doesn't specify token lifetime.",
            "feature_dir": "specs/051-headless-spec-chain",
        }
        defaults.update(overrides)
        return AnalyzeFinding(**defaults)

    def test_construction_all_fields(self) -> None:
        from maverick.workflows.spec_chain.models import AnalyzeFinding

        finding = self._make()
        assert isinstance(finding, AnalyzeFinding)

    def test_fields_accessible(self) -> None:
        finding = self._make()
        assert finding.title == "Ambiguous auth requirement"
        assert finding.category == "ambiguity"
        assert finding.severity_hint == "medium"
        assert finding.location == "spec.md#FR-003"
        assert finding.summary == "FR-003 doesn't specify token lifetime."
        assert finding.feature_dir == "specs/051-headless-spec-chain"

    def test_frozen_immutability(self) -> None:
        finding = self._make()
        with pytest.raises(FrozenInstanceError):
            finding.title = "changed"  # type: ignore[misc]

    # --- speckit_feature / remediation_source bead-state keys ---

    def test_feature_dir_is_the_speckit_feature_key_value(self) -> None:
        """Bead state key "speckit_feature" = <NNN-feature> directory name
        (adoption key, matches refuel delta key)."""
        finding = self._make(feature_dir="specs/051-headless-spec-chain")
        assert finding.feature_dir == "specs/051-headless-spec-chain"

    # --- finding_fingerprint idempotency contract ---

    def test_fingerprint_is_sha256_hex_digest(self) -> None:
        finding = self._make()
        fingerprint = finding.fingerprint
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64
        int(fingerprint, 16)  # raises ValueError if not valid hex

    def test_fingerprint_is_deterministic(self) -> None:
        """Idempotency contract: rerunning analyze on the same finding must
        produce the same fingerprint so remediation beads don't duplicate."""
        first = self._make().fingerprint
        second = self._make().fingerprint
        assert first == second

    def test_fingerprint_differs_when_title_changes(self) -> None:
        base = self._make().fingerprint
        changed = self._make(title="A completely different finding title").fingerprint
        assert base != changed

    def test_fingerprint_differs_when_location_changes(self) -> None:
        base = self._make().fingerprint
        changed = self._make(location="tasks.md#T012").fingerprint
        assert base != changed

    def test_fingerprint_ignores_non_identity_fields(self) -> None:
        """Only title + location feed the fingerprint (data-model.md:
        "finding_fingerprint = sha256 of normalized title + location") —
        category/severity_hint/summary must not perturb it, otherwise the
        same underlying finding re-reported with slightly different prose
        would spuriously create a duplicate remediation bead."""
        base = self._make().fingerprint
        same_identity = self._make(
            category="different-category",
            severity_hint="high",
            summary="Completely different summary text.",
        ).fingerprint
        assert base == same_identity

    def test_fingerprint_normalizes_case_and_whitespace(self) -> None:
        """ "normalized" title/location means trivial formatting differences
        (case, surrounding whitespace) must not change the fingerprint —
        otherwise cosmetic wording drift across analyze runs would create
        duplicate remediation beads."""
        base = self._make(
            title="Ambiguous auth requirement", location="spec.md#FR-003"
        ).fingerprint
        cosmetic = self._make(
            title="  AMBIGUOUS auth REQUIREMENT  ",
            location="  SPEC.MD#FR-003  ",
        ).fingerprint
        assert base == cosmetic


# ===========================================================================
# constants.py: labels / state-key constants for the remediation bead
# (T007's contract — "AnalyzeFinding -> remediation bead" table).
# ===========================================================================


class TestSpecRemediationConstants:
    def test_spec_remediation_label(self) -> None:
        from maverick.workflows.spec_chain.constants import SPEC_REMEDIATION_LABEL

        assert SPEC_REMEDIATION_LABEL == "spec-remediation"

    def test_remediation_source_value(self) -> None:
        from maverick.workflows.spec_chain.constants import REMEDIATION_SOURCE_ANALYZE

        assert REMEDIATION_SOURCE_ANALYZE == "spec-chain:analyze"

    def test_state_key_names(self) -> None:
        from maverick.workflows.spec_chain.constants import (
            KEY_FINDING_FINGERPRINT,
            KEY_REMEDIATION_SOURCE,
            KEY_SPECKIT_FEATURE,
        )

        assert KEY_SPECKIT_FEATURE == "speckit_feature"
        assert KEY_REMEDIATION_SOURCE == "remediation_source"
        assert KEY_FINDING_FINGERPRINT == "finding_fingerprint"

    def test_analyze_finding_carries_enough_to_build_bead_state(self) -> None:
        """AnalyzeFinding + the constants above together must be enough to
        build the three bead state keys from the "AnalyzeFinding ->
        remediation bead" table without any other input."""
        from maverick.workflows.spec_chain.constants import REMEDIATION_SOURCE_ANALYZE
        from maverick.workflows.spec_chain.models import AnalyzeFinding

        finding = AnalyzeFinding(
            title="Ambiguous auth requirement",
            category="ambiguity",
            severity_hint="medium",
            location="spec.md#FR-003",
            summary="FR-003 doesn't specify token lifetime.",
            feature_dir="specs/051-headless-spec-chain",
        )
        state = {
            "speckit_feature": finding.feature_dir,
            "remediation_source": REMEDIATION_SOURCE_ANALYZE,
            "finding_fingerprint": finding.fingerprint,
        }
        assert state["speckit_feature"] == "specs/051-headless-spec-chain"
        assert state["remediation_source"] == "spec-chain:analyze"
        assert len(state["finding_fingerprint"]) == 64
