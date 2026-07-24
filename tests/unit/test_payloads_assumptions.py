"""Tests for AssumptionPayload and the assumptions field on submit payloads."""

from __future__ import annotations

from maverick.payloads import (
    AssumptionPayload,
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)


class TestAssumptionPayload:
    def test_requires_question_and_adopted_answer(self) -> None:
        payload = AssumptionPayload(
            question="Should retries be per bead?",
            adopted_answer="Per bead.",
        )
        assert payload.question == "Should retries be per bead?"
        assert payload.adopted_answer == "Per bead."

    def test_alternatives_default_empty(self) -> None:
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")
        assert payload.alternatives == ()

    def test_valid_severity_not_defaulted(self) -> None:
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="high")
        assert payload.severity == "high"
        assert payload.severity_defaulted is False

    def test_unknown_severity_coerced_to_medium(self) -> None:
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="critical")
        assert payload.severity == "medium"
        assert payload.severity_defaulted is True

    def test_absent_severity_defaults_to_medium(self) -> None:
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")
        assert payload.severity == "medium"
        assert payload.severity_defaulted is True

    def test_never_raises_on_bad_severity(self) -> None:
        # Should not raise ValidationError for any severity string.
        payload = AssumptionPayload(
            question="Q?", adopted_answer="A.", severity="not-a-real-severity"
        )
        assert payload.severity == "medium"


class TestSubmitPayloadsAssumptionsField:
    def test_submit_implementation_absent_field_defaults_empty(self) -> None:
        payload = SubmitImplementationPayload(summary="did stuff")
        assert payload.assumptions == ()

    def test_submit_implementation_with_assumptions(self) -> None:
        payload = SubmitImplementationPayload(
            summary="did stuff",
            assumptions=[{"question": "Q?", "adopted_answer": "A."}],
        )
        assert len(payload.assumptions) == 1
        assert payload.assumptions[0].question == "Q?"

    def test_submit_review_absent_field_defaults_empty(self) -> None:
        payload = SubmitReviewPayload(approved=True)
        assert payload.assumptions == ()

    def test_submit_fix_result_absent_field_defaults_empty(self) -> None:
        payload = SubmitFixResultPayload(summary="fixed")
        assert payload.assumptions == ()

    def test_existing_payload_dicts_still_validate(self) -> None:
        """Older agent prompts that never mention assumptions keep validating."""
        payload = SubmitImplementationPayload.model_validate(
            {"summary": "did stuff", "files_changed": ["a.py"]}
        )
        assert payload.assumptions == ()
        assert payload.files_changed == ("a.py",)

    def test_malformed_assumption_dropped_not_fatal(self) -> None:
        """A partially-filled assumption must not fail the whole load-bearing
        payload — it is pruned, the rest of the payload validates."""
        payload = SubmitImplementationPayload.model_validate(
            {
                "summary": "did stuff",
                "files_changed": ["a.py"],
                "assumptions": [
                    {"question": "Kept?", "adopted_answer": "Yes."},
                    {"question": "Missing answer"},  # dropped
                    {"adopted_answer": "Missing question"},  # dropped
                    {"question": "  ", "adopted_answer": "blank q"},  # dropped
                ],
            }
        )
        assert payload.summary == "did stuff"
        assert len(payload.assumptions) == 1
        assert payload.assumptions[0].question == "Kept?"

    def test_malformed_assumption_dropped_on_review_and_fix(self) -> None:
        review = SubmitReviewPayload.model_validate(
            {"approved": True, "assumptions": [{"question": "Q?"}]}
        )
        assert review.assumptions == ()
        fix = SubmitFixResultPayload.model_validate(
            {"summary": "fixed", "assumptions": [{"adopted_answer": "A."}]}
        )
        assert fix.assumptions == ()

    def test_assumptions_round_trip_through_dump_and_revalidate(self) -> None:
        """dump -> state dict -> re-validate preserves severity_defaulted."""
        from maverick.payloads import dump_supervisor_payload

        payload = SubmitImplementationPayload(
            summary="did stuff",
            assumptions=[{"question": "Q?", "adopted_answer": "A.", "severity": "bogus"}],
        )
        dumped = dump_supervisor_payload(payload)
        assumption_dict = dumped["assumptions"][0]
        assert assumption_dict["severity_defaulted"] is True

        rebuilt = AssumptionPayload.model_validate(assumption_dict)
        assert rebuilt.severity == "medium"
        assert rebuilt.severity_defaulted is True
