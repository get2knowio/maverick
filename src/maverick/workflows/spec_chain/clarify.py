"""Clarify answering-path policy (R2): interception vs. non-interactive upgrade.

Both paths converge on :class:`ClarifyDecision` — filed as an
assumption-ledger entry by the *workflow* (never the agent) after the
clarify step completes (Guardrail X.3 / Principle II). See
specs/050-headless-spec-chain/research.md R2.

**Interception path**: activates when the runtime exposes a
question-interception hook (:func:`supports_interception`). No current
airframe adapter (0.9.0rc1) implements one — verified alongside the R1
cwd-binding gate — so this path is a forward-looking seam: it activates
automatically the moment an adapter adds the capability, with no further
workflow change needed. :func:`decisions_from_interception` adopts the
recommended option per question, or an informed default when none is
given, and reports ``blocked=True`` only when a question has neither a
recommended option nor any alternative to fall back on (no defensible
default exists — FR-009's edge case).

**Non-interactive path** (the one every provider takes today): the
clarify step prompt invokes Spec Kit's own non-interactive convention,
which records informed defaults as ``- Q: ... → A: ...`` bullets under
spec.md's ``## Clarifications`` section (verified against this
repository's own Spec Kit output — the more precise source than
research.md's original "Assumptions section" framing).
:func:`decisions_from_spec_md` parses that section back into
:class:`ClarifyDecision` instances.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from maverick.assumptions.models import Severity
from maverick.workflows.spec_chain.models import ClarifyDecision

__all__ = [
    "ESCALATION_SIGNALS",
    "assess_severity",
    "decisions_from_interception",
    "decisions_from_spec_md",
    "supports_interception",
]

#: Category -> keyword signals that escalate a clarify question's severity
#: to at least MEDIUM (R2, FR-007a). A question whose text matches any
#: keyword in any category escalates; unmatched questions default to LOW.
ESCALATION_SIGNALS: dict[str, tuple[str, ...]] = {
    "scope": ("scope", "in-scope", "out of scope", "user role", "permission", "boundary"),
    "security_privacy": (
        "auth",
        "credential",
        "password",
        "secret",
        "pii",
        "privacy",
        "data protection",
        "retention",
    ),
    "compliance": ("regulat", "legal", "compliance", "gdpr", "hipaa"),
    "data_integrity": ("irreversible", "migration", "delet", "data loss"),
}

_CLARIFICATION_BULLET_RE = re.compile(r"^-\s+Q:\s*(.+?)\s*\u2192\s*A:\s*(.+)$")


def assess_severity(question: str) -> tuple[Severity, bool]:
    """Assess a clarify question's severity per :data:`ESCALATION_SIGNALS`.

    Returns ``(severity, defaulted)`` — ``defaulted=True`` means no
    signal matched and LOW was the harness default (FR-007a), not an
    assessed MEDIUM.
    """
    lowered = question.casefold()
    for keywords in ESCALATION_SIGNALS.values():
        if any(keyword in lowered for keyword in keywords):
            return Severity.MEDIUM, False
    return Severity.LOW, True


def supports_interception(runtime: object) -> bool:
    """Capability probe: does *runtime* expose a question-interception hook?"""
    return callable(getattr(runtime, "ask_question", None))


def decisions_from_interception(
    questions: Sequence[tuple[str, str | None, Sequence[str]]],
) -> tuple[list[ClarifyDecision], bool]:
    """Interception path: adopt the recommended option per question, or an
    informed default (the first alternative) when none is given.

    Args:
        questions: ``(question, recommended_option, alternatives)``
            triples already collected by the runtime's question callback.

    Returns:
        ``(decisions, blocked)`` — ``blocked`` is ``True`` iff at least
        one question arrived with neither a recommended option nor any
        alternative (no defensible default exists — FR-009). Questions
        that block are excluded from *decisions*, not silently guessed
        at; the caller halts the chain when ``blocked`` is ``True``.
    """
    decisions: list[ClarifyDecision] = []
    blocked = False
    for question, recommended, raw_alternatives in questions:
        alternatives = tuple(raw_alternatives)
        if recommended:
            adopted = recommended
            remaining = tuple(a for a in alternatives if a != recommended)
        elif alternatives:
            adopted = alternatives[0]
            remaining = alternatives[1:]
        else:
            blocked = True
            continue

        severity, defaulted = assess_severity(question)
        decisions.append(
            ClarifyDecision(
                question=question,
                adopted_answer=adopted,
                alternatives=remaining,
                severity=severity,
                severity_defaulted=defaulted,
                path="interception",
                ledger_bead_id=None,
            )
        )
    return decisions, blocked


def decisions_from_spec_md(spec_md_content: str) -> list[ClarifyDecision]:
    """Non-interactive path: parse the clarify step's recorded defaults out
    of an updated spec.md's ``## Clarifications`` section (Spec Kit's own
    ``- Q: ... \u2192 A: ...`` convention) into :class:`ClarifyDecision`
    instances.

    Every parsed bullet becomes one decision — Spec Kit's own convention
    only records a question once it has adopted an answer for it, so
    there is no "no adopted answer" case to handle here.
    """
    decisions: list[ClarifyDecision] = []
    for line in spec_md_content.splitlines():
        m = _CLARIFICATION_BULLET_RE.match(line.strip())
        if not m:
            continue
        question, answer = m.group(1).strip(), m.group(2).strip()
        severity, defaulted = assess_severity(question)
        decisions.append(
            ClarifyDecision(
                question=question,
                adopted_answer=answer,
                alternatives=(),
                severity=severity,
                severity_defaulted=defaulted,
                path="non_interactive",
                ledger_bead_id=None,
            )
        )
    return decisions
