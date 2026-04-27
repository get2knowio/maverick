"""Unit tests for CuratorAgent.

Tests the curator agent including:
- Initialization and tool set
- Plan parsing (valid, empty, invalid JSON)
- System prompt content
- Refs trailer post-processing (FUTURE.md §3.9)
"""

from __future__ import annotations

from maverick.agents.curator import (
    SYSTEM_PROMPT,
    CuratorAgent,
    ensure_refs_trailers,
    extract_bead_ids,
)
from maverick.agents.tools import CURATOR_TOOLS


class TestCuratorInit:
    """Tests for CuratorAgent initialization."""

    def test_curator_name(self) -> None:
        """Curator has the correct name."""
        agent = CuratorAgent()
        assert agent.name == "curator"

    def test_curator_system_prompt(self) -> None:
        """Curator system prompt mentions jj and JSON."""
        agent = CuratorAgent()
        assert "jj" in agent.system_prompt.lower() or "jj" in agent.system_prompt
        assert "JSON" in agent.system_prompt

    def test_curator_uses_generator_tools(self) -> None:
        """Curator tool set is empty (CURATOR_TOOLS)."""
        assert frozenset() == CURATOR_TOOLS
        agent = CuratorAgent()
        # Generator-based agent — tools come via base class
        assert agent.allowed_tools == []

    def test_system_prompt_constant(self) -> None:
        """SYSTEM_PROMPT module constant matches agent's prompt."""
        agent = CuratorAgent()
        assert agent.system_prompt == SYSTEM_PROMPT


class TestCuratorParsePlan:
    """Tests for CuratorAgent.parse_plan()."""

    def test_parse_valid_plan(self) -> None:
        """Parses a well-formed JSON plan."""
        agent = CuratorAgent()
        raw = '[{"command": "squash", "args": ["-r", "abc123"], "reason": "Fix into parent"}]'
        plan = agent.parse_plan(raw)
        assert len(plan) == 1
        assert plan[0]["command"] == "squash"
        assert plan[0]["args"] == ["-r", "abc123"]
        assert plan[0]["reason"] == "Fix into parent"

    def test_parse_empty_plan(self) -> None:
        """Parses an empty JSON array as no-op."""
        agent = CuratorAgent()
        plan = agent.parse_plan("[]")
        assert plan == []

    def test_parse_multiple_steps(self) -> None:
        """Parses a multi-step plan."""
        agent = CuratorAgent()
        raw = (
            "["
            '{"command":"squash","args":["-r","a1"],"reason":"fix"},'
            '{"command":"describe","args":["-r","b2","-m","feat: auth"],'
            '"reason":"better msg"},'
            '{"command":"rebase","args":["-r","c3","--after","a1"],'
            '"reason":"reorder"}'
            "]"
        )
        plan = agent.parse_plan(raw)
        assert len(plan) == 3
        assert plan[0]["command"] == "squash"
        assert plan[1]["command"] == "describe"
        assert plan[2]["command"] == "rebase"

    def test_parse_handles_markdown_fences(self) -> None:
        """Strips markdown code fences from LLM output."""
        agent = CuratorAgent()
        raw = '```json\n[{"command": "squash", "args": ["-r", "x"], "reason": "fix"}]\n```'
        plan = agent.parse_plan(raw)
        assert len(plan) == 1
        assert plan[0]["command"] == "squash"

    def test_parse_handles_invalid_json(self) -> None:
        """Returns empty list on malformed JSON."""
        agent = CuratorAgent()
        plan = agent.parse_plan("this is not json at all")
        assert plan == []

    def test_parse_handles_non_array_json(self) -> None:
        """Returns empty list when JSON is an object instead of array."""
        agent = CuratorAgent()
        plan = agent.parse_plan('{"command": "squash"}')
        assert plan == []

    def test_parse_skips_invalid_commands(self) -> None:
        """Skips steps with unrecognized commands."""
        agent = CuratorAgent()
        raw = """[
            {"command": "squash", "args": ["-r", "a1"], "reason": "ok"},
            {"command": "delete", "args": [], "reason": "not a valid command"},
            {"command": "describe", "args": ["-r", "b2", "-m", "x"], "reason": "ok"}
        ]"""
        plan = agent.parse_plan(raw)
        assert len(plan) == 2
        assert plan[0]["command"] == "squash"
        assert plan[1]["command"] == "describe"

    def test_parse_skips_non_dict_entries(self) -> None:
        """Skips entries that are not dicts."""
        agent = CuratorAgent()
        raw = '[{"command": "squash", "args": [], "reason": "ok"}, "not a dict", 42]'
        plan = agent.parse_plan(raw)
        assert len(plan) == 1

    def test_parse_adds_default_args_and_reason(self) -> None:
        """Missing args/reason default to empty."""
        agent = CuratorAgent()
        raw = '[{"command": "squash"}]'
        plan = agent.parse_plan(raw)
        assert len(plan) == 1
        assert plan[0]["args"] == []
        assert plan[0]["reason"] == ""


class TestCuratorRefsTrailerPrompt:
    """SYSTEM_PROMPT instructs the curator to preserve bead provenance
    via a ``Refs:`` trailer (FUTURE.md §3.9). The prompt remains the
    primary mechanism — ``ensure_refs_trailers`` is a safety net.
    """

    def test_prompt_describes_refs_trailer_format(self) -> None:
        assert "Refs:" in SYSTEM_PROMPT
        # Mentions the input bead-prefix format so the LLM knows where
        # to extract IDs from.
        assert "bead(" in SYSTEM_PROMPT

    def test_prompt_explains_squash_attribution(self) -> None:
        """Squash combines multiple beads into one commit — the trailer
        must list every contributing bead."""
        assert "squash" in SYSTEM_PROMPT.lower()
        # Mentions trailer plurality ("comma-separated", "every bead")
        assert "comma-separated" in SYSTEM_PROMPT or "comma" in SYSTEM_PROMPT


class TestExtractBeadIds:
    """Tests for ``extract_bead_ids`` helper."""

    def test_extracts_single_bead_id(self) -> None:
        desc = "bead(sample_maverick_project-e6c.8): implement auth"
        assert extract_bead_ids(desc) == ["sample_maverick_project-e6c.8"]

    def test_extracts_multiple_bead_ids_in_squashed_message(self) -> None:
        desc = (
            "bead(proj-a.1): first part\n"
            "\n"
            "bead(proj-a.2): second part"
        )
        assert extract_bead_ids(desc) == ["proj-a.1", "proj-a.2"]

    def test_dedupes_repeated_ids(self) -> None:
        desc = "bead(p-1.1): a\nbead(p-1.1): b\nbead(p-1.2): c"
        assert extract_bead_ids(desc) == ["p-1.1", "p-1.2"]

    def test_returns_empty_for_snapshot_commit(self) -> None:
        desc = "snapshot: pre-flight uncommitted changes"
        assert extract_bead_ids(desc) == []

    def test_does_not_match_bead_inside_body_text(self) -> None:
        """``bead(...)`` must be at line start to count as a prefix —
        casual mentions in a body shouldn't generate a trailer."""
        desc = "feat: add bug fix\n\nThis fixes the bead(legacy.3) issue"
        assert extract_bead_ids(desc) == []


class TestEnsureRefsTrailers:
    """Tests for ``ensure_refs_trailers`` post-processing safety net."""

    def test_appends_trailer_when_missing(self) -> None:
        plan = [
            {
                "command": "describe",
                "args": ["-r", "abc1", "-m", "feat: add auth"],
                "reason": "clarify",
            }
        ]
        commits = [
            {
                "change_id": "abc1",
                "description": "bead(proj-1.5): wire up login",
            }
        ]
        out = ensure_refs_trailers(plan, commits)
        assert len(out) == 1
        new_message = _describe_message(out[0])
        assert new_message.endswith("Refs: proj-1.5")
        # Blank line between body and trailer (git convention).
        assert "\n\nRefs:" in new_message

    def test_preserves_existing_trailer(self) -> None:
        """If the curator already followed the prompt and emitted a
        ``Refs:`` trailer, don't double-inject."""
        existing = "feat: add auth\n\nRefs: proj-1.5, proj-1.6"
        plan = [
            {
                "command": "describe",
                "args": ["-r", "abc1", "-m", existing],
                "reason": "ok",
            }
        ]
        commits = [
            {
                "change_id": "abc1",
                "description": "bead(proj-1.5): initial",
            }
        ]
        out = ensure_refs_trailers(plan, commits)
        # Message unchanged.
        assert _describe_message(out[0]) == existing

    def test_skips_when_source_has_no_bead_id(self) -> None:
        """Snapshot commits and other non-bead source commits don't
        produce a trailer — eval tooling should see no ``Refs:`` for
        those commits, distinguishing them from bead work."""
        plan = [
            {
                "command": "describe",
                "args": ["-r", "abc1", "-m", "chore: snapshot pre-fly"],
                "reason": "ok",
            }
        ]
        commits = [
            {
                "change_id": "abc1",
                "description": "snapshot: pre-flight uncommitted changes",
            }
        ]
        out = ensure_refs_trailers(plan, commits)
        assert _describe_message(out[0]) == "chore: snapshot pre-fly"
        assert "Refs:" not in _describe_message(out[0])

    def test_leaves_non_describe_commands_untouched(self) -> None:
        """``squash`` and ``rebase`` commands have no message to rewrite."""
        plan = [
            {
                "command": "squash",
                "args": ["-r", "abc1"],
                "reason": "fix into parent",
            },
            {
                "command": "rebase",
                "args": ["-r", "abc1", "--after", "def2"],
                "reason": "reorder",
            },
        ]
        out = ensure_refs_trailers(plan, [])
        assert out == plan

    def test_unknown_change_id_is_ignored(self) -> None:
        """A describe targeting a change_id we don't have context for
        is left as-is — better to land an untrailed commit than to
        inject incorrect provenance."""
        plan = [
            {
                "command": "describe",
                "args": ["-r", "unknown", "-m", "feat: x"],
                "reason": "ok",
            }
        ]
        commits = [
            {"change_id": "abc1", "description": "bead(proj-1.5): a"},
        ]
        out = ensure_refs_trailers(plan, commits)
        assert _describe_message(out[0]) == "feat: x"

    def test_handles_multi_paragraph_body(self) -> None:
        """The trailer goes after the body with one blank line; existing
        body whitespace is normalised."""
        existing = "feat: complex change\n\nLong body explaining why.\n"
        plan = [
            {
                "command": "describe",
                "args": ["-r", "abc1", "-m", existing],
                "reason": "ok",
            }
        ]
        commits = [
            {"change_id": "abc1", "description": "bead(proj-1.5): something"},
        ]
        out = ensure_refs_trailers(plan, commits)
        new_message = _describe_message(out[0])
        # Body preserved, trailer appended with single blank-line separator.
        assert new_message == (
            "feat: complex change\n\nLong body explaining why.\n\nRefs: proj-1.5"
        )


def _describe_message(step: dict) -> str:
    """Return the ``-m`` arg value from a describe step. Test helper."""
    args = step["args"]
    for i, token in enumerate(args):
        if token == "-m" and i + 1 < len(args):
            return str(args[i + 1])
    raise AssertionError(f"describe step has no -m arg: {step}")


class TestCuratorGenerate:
    """Tests for CuratorAgent.build_prompt()."""

    def test_build_prompt_empty_commits(self) -> None:
        """build_prompt with no commits produces a prompt mentioning 0 total."""
        agent = CuratorAgent()
        result = agent.build_prompt({"commits": [], "log_summary": ""})
        assert isinstance(result, str)
        assert "0 total" in result

    def test_build_prompt_with_commits(self) -> None:
        """build_prompt includes commit details in the prompt."""
        agent = CuratorAgent()
        commits = [
            {
                "change_id": "abc123",
                "description": "feat: add feature",
                "stats": "1 file changed",
            }
        ]
        result = agent.build_prompt({"commits": commits, "log_summary": "abc123 feat"})
        assert isinstance(result, str)
        assert "abc123" in result
        assert "feat: add feature" in result
