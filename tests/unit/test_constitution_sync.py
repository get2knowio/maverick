"""Tests for governance-doc sync (057-isolated-bead-workspaces, T110, SC-010).

Guardrail 0 (single-repo CWD model) was redefined by
057-isolated-bead-workspaces: the "one documented exception" framing (which
implied `maverick spec` was the sole permitted case of isolated execution)
was removed in favor of stating the invariant that actually matters —
bd/ledger/commit-graph writes must target the checkout, never an isolated
workspace — directly, now that it is structurally enforced
(`assert_checkout`/`CheckoutPath`) rather than merely documented. This test
guards against that phrasing creeping back in, and against the constitution
and CLAUDE.md's guardrail numbering drifting apart, per Guardrail X.9's
"Guardrail numbers here match CLAUDE.md's guardrail numbers" contract.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSTITUTION = REPO_ROOT / ".specify" / "memory" / "constitution.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def _strip_sync_impact_report(text: str) -> str:
    """Drop the leading `<!-- Sync Impact Report ... -->` HTML comment —
    it's a changelog and legitimately *names* retired phrasing (including
    "one documented exception") when describing what changed. The checks
    below care about the live guardrail/appendix text, not the changelog."""
    return re.sub(r"^<!--.*?-->\n", "", text, count=1, flags=re.DOTALL)


def test_constitution_no_longer_states_one_documented_exception() -> None:
    text = _strip_sync_impact_report(CONSTITUTION.read_text(encoding="utf-8"))
    assert "one documented exception" not in text.lower()


def test_claude_md_no_longer_states_one_documented_exception() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "one documented exception" not in text.lower()


def test_guardrail_zero_states_the_bd_stays_out_invariant() -> None:
    """The redefined guardrail states the real invariant directly, not just
    "no hidden workspace exists" — both documents must say so."""
    constitution_text = CONSTITUTION.read_text(encoding="utf-8")
    claude_text = CLAUDE_MD.read_text(encoding="utf-8")

    assert "bd stays out of isolation" in claude_text.lower() or (
        "bd" in claude_text and "never target" in claude_text.lower()
    )
    assert "bd" in constitution_text.lower()
    assert "assert_checkout" in constitution_text
    assert "assert_checkout" in claude_text


def test_guardrail_zero_numbering_matches_between_files() -> None:
    """Guardrail X.9's own contract: 'Guardrail numbers here match
    CLAUDE.md's guardrail numbers; cite them as X.<n>' — Guardrail 0 must
    exist, by that number, in both."""
    constitution_text = CONSTITUTION.read_text(encoding="utf-8")
    claude_text = CLAUDE_MD.read_text(encoding="utf-8")

    constitution_match = re.search(
        r"^0\. \*\*Single-repo.*?workflow model", constitution_text, re.MULTILINE
    )
    claude_match = re.search(r"^### 0\. Single-repo.*?workflow model", claude_text, re.MULTILINE)

    assert constitution_match is not None, "Guardrail 0 not found in constitution.md"
    assert claude_match is not None, "Guardrail 0 not found in CLAUDE.md"


def test_constitution_version_was_bumped_major() -> None:
    """A guardrail redefinition is a backward-incompatible governance
    change (Amendment Process: 'MAJOR: backward-incompatible principle
    changes, removals, or redefinitions')."""
    text = CONSTITUTION.read_text(encoding="utf-8")
    match = re.search(r"\*\*Version\*\*:\s*(\d+)\.\d+\.\d+", text)
    assert match is not None, "Version footer not found"
    major = int(match.group(1))
    assert major >= 3, (
        f"expected a MAJOR bump (>=3.0.0) for the guardrail redefinition, got {major}"
    )
