"""Success-criteria refs forwarded to the decomposition validator.

Found by the first live walkthrough (#135 subtask 5). The extraction read
``sc.id`` / ``sc.description``, neither of which exists on
:class:`~maverick.flight.models.SuccessCriterion` — it has ``text`` and
``checked``. Every criterion therefore produced an empty string.

The damage was not the empty strings themselves but that a tuple of them
is *truthy*: ``validate_decomposition`` treats a non-empty
``expected_sc_refs`` as authoritative and skips its ``SC-001..SC-NNN``
fallback. So the validator compared ``""`` against every ``trace_ref``,
matched nothing, and reported all criteria uncovered on every run —
which burned the entire fix budget on an unfixable gap and let the fixer
invent redundant work units chasing criteria it could not name.

A live run turned 7 work units into 18, with confirmed duplicates.

Fixing the extraction alone was *not* enough, and made this workload
worse before it made it better: with a precise-but-impossible target
(``SC-015: total source lines stay under 500``) the fixer tried harder
and produced 33 units instead of 18. See
:class:`TestUntracedCriteriaAreAdvisory` for the second half of the fix.
"""

from __future__ import annotations

from maverick.workflows.refuel_maverick.workflow import (
    success_criteria_refs as _extract,
)


class TestSuccessCriteriaRefExtraction:
    def test_prose_criteria_yield_no_refs_but_a_real_count(self) -> None:
        """The shape the markdown flight-plan format actually produces.

        ``SuccessCriterion`` carries prose, not identifiers — so refs must
        come back empty (letting the validator fall back to SC-001..N)
        while the count still reflects every criterion.
        """
        from maverick.flight.models import SuccessCriterion

        class _Plan:
            success_criteria = tuple(
                SuccessCriterion(text=f"criterion {i}", checked=False) for i in range(1, 17)
            )

        refs, count = _extract(_Plan())

        assert refs == ()
        assert count == 16

    def test_empty_refs_do_not_suppress_the_validator_fallback(self) -> None:
        """The actual defect, stated as the validator sees it.

        A tuple of empty strings is truthy; an empty tuple is not. That
        single distinction is what decides whether ``SC-001..N`` is used.
        """
        from maverick.flight.models import SuccessCriterion

        class _Plan:
            success_criteria = (SuccessCriterion(text="does a thing", checked=False),)

        refs, _ = _extract(_Plan())

        # The pre-fix expression produced ("",) here — truthy, so the
        # validator skipped its fallback and compared "" to every ref.
        assert refs == ()
        assert not refs, "a falsy refs tuple is what lets SC-001..N apply"

    def test_real_ref_ids_are_forwarded(self) -> None:
        """Plans that *do* carry ref ids must still override the fallback."""

        class _Criterion:
            def __init__(self, id_: str) -> None:
                self.id = id_

        class _Plan:
            success_criteria = (_Criterion("SC-B1-default"), _Criterion("SC-B1-linux"))

        refs, count = _extract(_Plan())

        assert refs == ("SC-B1-default", "SC-B1-linux")
        assert count == 2

    def test_blank_and_whitespace_refs_are_dropped_not_forwarded(self) -> None:
        """A half-populated plan must not poison the fallback either."""

        class _Criterion:
            def __init__(self, id_: str) -> None:
                self.id = id_

        class _Plan:
            success_criteria = (_Criterion("SC-01"), _Criterion("   "), _Criterion(""))

        refs, count = _extract(_Plan())

        assert refs == ("SC-01",)
        # Count stays honest even though two criteria contributed no ref.
        assert count == 3

    def test_no_criteria_at_all(self) -> None:
        class _Plan:
            success_criteria = ()

        assert _extract(_Plan()) == ((), 0)

    def test_missing_attribute_is_tolerated(self) -> None:
        """Older/partial plan objects must not raise here."""

        class _Plan:
            pass

        assert _extract(_Plan()) == ((), 0)


class TestValidatorFallbackContract:
    """The half of the contract that lives in ``validate_decomposition``."""

    def test_empty_refs_select_sequential_fallback(self) -> None:
        """Pin the truthiness behaviour the extraction depends on."""
        expected_sc_refs: tuple[str, ...] = ()
        success_criteria_count = 3

        expected = (
            list(expected_sc_refs)
            if expected_sc_refs
            else [f"SC-{i:03d}" for i in range(1, success_criteria_count + 1)]
        )

        assert expected == ["SC-001", "SC-002", "SC-003"]

    def test_tuple_of_blanks_would_have_suppressed_it(self) -> None:
        """Documents why the old expression was harmful, not merely wrong.

        If this ever starts returning the fallback, the extraction fix
        stops being load-bearing and this whole class can go.
        """
        expected_sc_refs = ("", "", "")
        success_criteria_count = 3

        expected = (
            list(expected_sc_refs)
            if expected_sc_refs
            else [f"SC-{i:03d}" for i in range(1, success_criteria_count + 1)]
        )

        assert expected == ["", "", ""]
        assert "SC-001" not in expected


class TestUntracedCriteriaAreAdvisory:
    """Untraced criteria must not drive the fix loop (#135 subtask 5).

    A criterion goes untraced for two incompatible reasons and the check
    cannot distinguish them: the decomposition genuinely missed a
    feature, or the criterion is a cross-cutting constraint no single
    work unit can carry ("total LOC <= 500", "ruff check passes",
    "the package installs"). Failing on the second kind is unrecoverable
    — and expensive. Two live runs each spent their whole 3-round fix
    budget on it, and the fixer, told to make a work unit cover a
    codebase-wide LOC budget, invented units trying: 7 became 18 on one
    run and 33 on the other.
    """

    def test_traceability_error_is_distinguishable_from_overload(self) -> None:
        """Both used to be one exception type, so callers could not tell
        the uncloseable case from the one the fixer can act on."""
        from maverick.library.actions.decompose import (
            SCCoverageError,
            SCTraceabilityError,
        )

        assert issubclass(SCTraceabilityError, SCCoverageError)
        # Overload still raises the base class, so `except
        # SCTraceabilityError` cannot swallow it.
        assert not issubclass(SCCoverageError, SCTraceabilityError)

    def test_untraced_criteria_raise_traceability_error(self) -> None:
        from maverick.library.actions.decompose import (
            SCTraceabilityError,
            validate_decomposition,
        )
        from maverick.workflows.refuel_maverick.models import WorkUnitSpec

        spec = WorkUnitSpec.model_validate(
            {
                "id": "u-1",
                "task": "do a thing",
                "sequence": 1,
                "depends_on": [],
                "file_scope": {},
                "complexity": "simple",
                "instructions": "go",
                "acceptance_criteria": [{"text": "ac", "trace_ref": "SC-001"}],
                "verification": ["pytest"],
                "test_specification": "",
            }
        )

        try:
            validate_decomposition([spec], success_criteria_count=2)
        except SCTraceabilityError as exc:
            # SC-002 is uncovered; SC-001 is fine.
            assert any("SC-002" in g for g in exc.gaps)
        else:  # pragma: no cover - the gap must be detected
            raise AssertionError("expected SCTraceabilityError")

    def test_overload_still_raises_the_hard_error(self) -> None:
        """The fixer *can* split an overloaded unit, so it must keep
        failing validation."""
        from maverick.library.actions.decompose import (
            SCCoverageError,
            SCTraceabilityError,
            validate_decomposition,
        )
        from maverick.workflows.refuel_maverick.models import WorkUnitSpec

        spec = WorkUnitSpec.model_validate(
            {
                "id": "u-1",
                "task": "do everything",
                "sequence": 1,
                "depends_on": [],
                "file_scope": {},
                "complexity": "complex",
                "instructions": "go",
                "acceptance_criteria": [
                    {"text": f"ac-{i}", "trace_ref": f"SC-{i:03d}"} for i in range(1, 14)
                ],
                "verification": ["pytest"],
                "test_specification": "",
            }
        )

        try:
            validate_decomposition([spec], success_criteria_count=13)
        except SCCoverageError as exc:
            assert not isinstance(exc, SCTraceabilityError), (
                "overload must stay hard-failing, or the fixer never splits the unit"
            )
            assert "Split into smaller units" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected SCCoverageError for the overloaded unit")


class TestArtifactsColocateWithThePlan:
    """Refuel writes next to the flight plan, not to ``<frontmatter name>``.

    ``plan generate <name>`` writes ``plans/<name>/flight-plan.md``, but
    the generator chooses the frontmatter ``name:`` freely — a plan
    generated as ``greet-cli`` came back named ``greet-cli-mvp``. Refuel
    used to key its work-unit and cache directories off that frontmatter
    name, so a live run left the flight plan in ``plans/greet-cli/`` and
    everything refuel produced in ``plans/greet-cli-mvp/`` (#135
    subtask 5).
    """

    def test_work_units_and_cache_derive_from_the_plan_path(self) -> None:
        """Pin the derivation as source, since exercising the real
        workflow needs a squadron and a live Burr app."""
        import inspect

        from maverick.workflows.refuel_maverick import workflow as wf

        src = inspect.getsource(wf.RefuelMaverickWorkflow)

        assert "work_units_dir = flight_plan_path.parent" in src, (
            "work units must colocate with the flight plan"
        )
        assert 'cache_dir = str(plan_dir / "refuel-cache")' in src, (
            "the refuel cache must colocate with the flight plan"
        )
        # The frontmatter name must not reappear as a directory key.
        assert '"plans" / flight_plan.name' not in src
        assert '"plans" / plan_name' not in src


class TestBriefingFailuresAreSurvivable:
    """A failed briefing agent costs its brief, not the run (#135 subtask 5).

    A live refuel died outright when the contrarian could not produce
    valid structured output after 5 attempts. Navigator, Structuralist
    and Recon had all already succeeded — 290 seconds of agent work —
    and every bit of it was discarded, because the only briefings cache
    write sat downstream of the contrarian.

    Two separate defects, both fixed here: the failure was fatal, and the
    cache could not help with the one failure mode it most needed to.
    """

    def test_all_briefs_are_optional_downstream(self) -> None:
        """The premise the graceful path relies on."""
        import inspect

        from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

        sig = inspect.signature(serialize_briefs_to_markdown)
        for name in ("scope", "analysis", "criteria", "challenge"):
            assert sig.parameters[name].default is None, (
                f"{name} must be optional for a missing brief to be survivable"
            )

    def test_briefing_actions_do_not_let_one_agent_kill_the_run(self) -> None:
        import inspect

        from maverick.workflows.refuel_maverick import actions as acts

        for fn in (acts.parallel_briefings, acts.contrarian_briefing):
            src = inspect.getsource(getattr(fn, "_action", fn) if hasattr(fn, "_action") else fn)
            assert "_briefing_failed" in src, (
                f"{fn} must degrade on agent failure, not propagate it"
            )

    def test_cache_is_written_before_the_contrarian_runs(self) -> None:
        """The ordering that made the cache useless for this failure."""
        import inspect

        from maverick.workflows.refuel_maverick import actions as acts

        src = inspect.getsource(acts)
        parallel_at = src.index("async def parallel_briefings")
        contrarian_at = src.index("async def contrarian_briefing")
        first_write = src.index("_write_briefings_cache(", parallel_at)

        assert parallel_at < first_write < contrarian_at, (
            "the parallel phase must persist its briefs before the "
            "contrarian gets a chance to fail"
        )
