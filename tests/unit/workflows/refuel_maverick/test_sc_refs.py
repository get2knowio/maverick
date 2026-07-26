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
