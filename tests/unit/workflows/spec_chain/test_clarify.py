"""Tests for the clarify answering-path policy seam
(`maverick.workflows.spec_chain.clarify`) — R2."""

from __future__ import annotations

from maverick.assumptions.models import Severity
from maverick.workflows.spec_chain.clarify import (
    assess_severity,
    decisions_from_interception,
    decisions_from_spec_md,
    supports_interception,
)


class TestSupportsInterception:
    def test_runtime_without_ask_question_does_not_support(self) -> None:
        class _PlainRuntime:
            pass

        assert supports_interception(_PlainRuntime()) is False

    def test_runtime_with_non_callable_ask_question_does_not_support(self) -> None:
        class _FakeRuntime:
            ask_question = "not-a-method"

        assert supports_interception(_FakeRuntime()) is False

    def test_runtime_with_ask_question_method_supports(self) -> None:
        class _InterceptingRuntime:
            async def ask_question(
                self, question: str, *, recommended: str | None, alternatives: list[str]
            ) -> str:
                return recommended or ""

        assert supports_interception(_InterceptingRuntime()) is True


class TestAssessSeverity:
    def test_unmatched_question_defaults_low(self) -> None:
        severity, defaulted = assess_severity("Should the button be blue or green?")
        assert severity is Severity.LOW
        assert defaulted is True

    def test_scope_keyword_escalates_medium(self) -> None:
        severity, defaulted = assess_severity("What is out of scope for this feature?")
        assert severity is Severity.MEDIUM
        assert defaulted is False

    def test_security_keyword_escalates_medium(self) -> None:
        severity, defaulted = assess_severity("How should we store the user's credential?")
        assert severity is Severity.MEDIUM
        assert defaulted is False

    def test_compliance_keyword_escalates_medium(self) -> None:
        severity, defaulted = assess_severity("Does this need GDPR compliance review?")
        assert severity is Severity.MEDIUM
        assert defaulted is False

    def test_data_integrity_keyword_escalates_medium(self) -> None:
        severity, defaulted = assess_severity("Is this migration irreversible?")
        assert severity is Severity.MEDIUM
        assert defaulted is False

    def test_case_insensitive_matching(self) -> None:
        severity, _ = assess_severity("What PERMISSION level is required?")
        assert severity is Severity.MEDIUM


class TestDecisionsFromInterception:
    def test_adopts_recommended_option(self) -> None:
        decisions, blocked = decisions_from_interception([("Should X?", "Yes", ["No", "Maybe"])])
        assert blocked is False
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.question == "Should X?"
        assert decision.adopted_answer == "Yes"
        assert decision.alternatives == ("No", "Maybe")
        assert decision.path == "interception"
        assert decision.ledger_bead_id is None

    def test_no_recommended_option_falls_back_to_first_alternative(self) -> None:
        decisions, blocked = decisions_from_interception(
            [("Should X?", None, ["Option A", "Option B"])]
        )
        assert blocked is False
        assert len(decisions) == 1
        assert decisions[0].adopted_answer == "Option A"
        assert decisions[0].alternatives == ("Option B",)

    def test_no_recommended_option_and_no_alternatives_blocks(self) -> None:
        decisions, blocked = decisions_from_interception([("Should X?", None, [])])
        assert blocked is True
        assert decisions == []

    def test_never_silently_skips_a_question_without_blocking(self) -> None:
        """Every question either produces a decision or trips `blocked` —
        never both absent (edge case: never silently skip)."""
        decisions, blocked = decisions_from_interception(
            [
                ("Q1 with recommendation", "A1", []),
                ("Q2 with no recommendation but alternatives", None, ["Alt"]),
                ("Q3 fully unresolvable", None, []),
            ]
        )
        assert blocked is True
        # Q1 and Q2 still produced decisions even though Q3 blocked.
        assert {d.question for d in decisions} == {
            "Q1 with recommendation",
            "Q2 with no recommendation but alternatives",
        }

    def test_severity_assessed_per_question(self) -> None:
        decisions, _ = decisions_from_interception([("What is in scope here?", "Everything", [])])
        assert decisions[0].severity is Severity.MEDIUM
        assert decisions[0].severity_defaulted is False

    def test_multiple_questions_preserve_order(self) -> None:
        decisions, _ = decisions_from_interception(
            [
                ("Q1?", "A1", []),
                ("Q2?", "A2", []),
                ("Q3?", "A3", []),
            ]
        )
        assert [d.question for d in decisions] == ["Q1?", "Q2?", "Q3?"]


class TestDecisionsFromSpecMd:
    def test_parses_single_clarification_bullet(self) -> None:
        content = (
            "## Clarifications\n\n"
            "### Session 2026-07-24\n\n"
            "- Q: Where should the chain execute? → A: Hidden workspace.\n"
        )
        decisions = decisions_from_spec_md(content)
        assert len(decisions) == 1
        assert decisions[0].question == "Where should the chain execute?"
        assert decisions[0].adopted_answer == "Hidden workspace."
        assert decisions[0].alternatives == ()
        assert decisions[0].path == "non_interactive"

    def test_parses_multiple_bullets_across_sessions(self) -> None:
        content = (
            "## Clarifications\n\n"
            "### Session 2026-07-24\n\n"
            "- Q: Q1? → A: A1.\n"
            "- Q: Q2? → A: A2.\n\n"
            "### Session 2026-07-25\n\n"
            "- Q: Q3? → A: A3.\n"
        )
        decisions = decisions_from_spec_md(content)
        assert [d.question for d in decisions] == ["Q1?", "Q2?", "Q3?"]
        assert [d.adopted_answer for d in decisions] == ["A1.", "A2.", "A3."]

    def test_no_clarifications_section_yields_no_decisions(self) -> None:
        content = "# Feature Specification: Foo\n\nNo clarifications here.\n"
        assert decisions_from_spec_md(content) == []

    def test_ignores_non_bullet_lines_in_clarifications_section(self) -> None:
        content = (
            "## Clarifications\n\n"
            "### Session 2026-07-24\n\n"
            "Some prose that is not a Q/A bullet.\n"
            "- Q: Real question? → A: Real answer.\n"
        )
        decisions = decisions_from_spec_md(content)
        assert len(decisions) == 1
        assert decisions[0].question == "Real question?"

    def test_severity_escalation_applies_to_parsed_questions(self) -> None:
        content = (
            "## Clarifications\n\n"
            "### Session 2026-07-24\n\n"
            "- Q: What data retention policy applies? → A: 30 days.\n"
        )
        decisions = decisions_from_spec_md(content)
        assert decisions[0].severity is Severity.MEDIUM
        assert decisions[0].severity_defaulted is False

    def test_unmatched_question_defaults_to_low_severity(self) -> None:
        content = (
            "## Clarifications\n\n"
            "### Session 2026-07-24\n\n"
            "- Q: What color should the button be? → A: Blue.\n"
        )
        decisions = decisions_from_spec_md(content)
        assert decisions[0].severity is Severity.LOW
        assert decisions[0].severity_defaulted is True


class TestAssumptionsFromSpecMd:
    """`## Assumptions` is where specify records what it decided unasked.

    From the first live Spec Kit walkthrough: specify resolved all three of
    the PRD's explicit Open Questions into this section and emitted zero
    `[NEEDS CLARIFICATION]` markers, so clarify had nothing left to ask.
    Six adopted decisions -- including "defer this feature entirely" --
    reached no ledger entry and therefore never reached the land gate.
    """

    LIVE = """\
# Feature Specification: Greet CLI

## Clarifications

### Session 2026-07-27

- Q: What is the minimum supported Python version? → A: Python 3.10+.

## Assumptions

- **`--random` behavior**: Selects exactly one language per invocation.
- **Grid/all-at-once layout**: Deferred entirely; output is always sequential.
- **RTL language rendering**: Banner rendered left-to-right; no bidi reflow.

## Success Criteria

- **SC-001**: A user sees output within 60 seconds.
"""

    def test_parses_each_assumption_bullet(self) -> None:
        from maverick.workflows.spec_chain.clarify import assumptions_from_spec_md

        decisions = assumptions_from_spec_md(self.LIVE)
        assert [d.question for d in decisions] == [
            "`--random` behavior",
            "Grid/all-at-once layout",
            "RTL language rendering",
        ]
        assert decisions[1].adopted_answer.startswith("Deferred entirely")

    def test_section_ends_at_the_next_heading(self) -> None:
        """SC-001 lives under Success Criteria and is not an assumption."""
        from maverick.workflows.spec_chain.clarify import assumptions_from_spec_md

        decisions = assumptions_from_spec_md(self.LIVE)
        assert all("SC-001" not in d.question for d in decisions)
        assert len(decisions) == 3

    def test_clarification_bullets_are_not_assumptions(self) -> None:
        from maverick.workflows.spec_chain.clarify import assumptions_from_spec_md

        decisions = assumptions_from_spec_md(self.LIVE)
        assert all("minimum supported Python" not in d.question for d in decisions)

    def test_path_records_how_the_decision_was_captured(self) -> None:
        from maverick.workflows.spec_chain.clarify import assumptions_from_spec_md

        decisions = assumptions_from_spec_md(self.LIVE)
        assert {d.path for d in decisions} == {"assumptions_section"}

    def test_severity_assessed_over_question_and_answer(self) -> None:
        """A scope signal in the *decision* must escalate, not just in the topic."""
        from maverick.workflows.spec_chain.clarify import assumptions_from_spec_md

        content = "## Assumptions\n\n- **Retry budget**: Out of scope for this release.\n"
        decisions = assumptions_from_spec_md(content)
        assert decisions[0].severity is Severity.MEDIUM
        assert decisions[0].severity_defaulted is False

    def test_no_assumptions_section_yields_nothing(self) -> None:
        from maverick.workflows.spec_chain.clarify import assumptions_from_spec_md

        assert assumptions_from_spec_md("# Spec\n\n## Requirements\n\n- FR-001\n") == []
