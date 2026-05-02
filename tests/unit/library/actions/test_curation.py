"""Tests for ``maverick.library.actions.curation`` helpers.

The curator's persona / system prompt now lives at
``runtime/opencode/profile/agents/maverick.curator.md`` (loaded by
OpenCode via the ``agent=`` selector). The helpers tested here are
the deterministic Python wrapper around it: prompt assembly, JSON
plan parsing, bead-id extraction, and the ``Refs:`` trailer safety
net (FUTURE.md §3.9).
"""

from __future__ import annotations

import pytest

from maverick.library.actions.curation import (
    build_curator_prompt,
    ensure_refs_trailers,
    extract_bead_ids,
    parse_curation_plan,
)


class TestBuildCuratorPrompt:
    """Tests for ``build_curator_prompt``."""

    def test_empty_commits_lists_zero_total(self) -> None:
        prompt = build_curator_prompt({"commits": [], "log_summary": ""})
        assert isinstance(prompt, str)
        assert "0 total" in prompt

    def test_includes_change_id_and_description(self) -> None:
        commits = [
            {
                "change_id": "abc123",
                "description": "feat: add feature",
                "stats": "1 file changed",
            }
        ]
        prompt = build_curator_prompt({"commits": commits, "log_summary": "abc123 feat"})
        assert "abc123" in prompt
        assert "feat: add feature" in prompt
        assert "1 file changed" in prompt


class TestParseCurationPlan:
    """Tests for ``parse_curation_plan``."""

    def test_parse_valid_plan(self) -> None:
        raw = '[{"command": "squash", "args": ["-r", "abc123"], "reason": "Fix into parent"}]'
        plan = parse_curation_plan(raw)
        assert len(plan) == 1
        assert plan[0]["command"] == "squash"
        assert plan[0]["args"] == ["-r", "abc123"]
        assert plan[0]["reason"] == "Fix into parent"

    def test_parse_empty_plan(self) -> None:
        assert parse_curation_plan("[]") == []

    def test_parse_multiple_steps(self) -> None:
        raw = (
            "["
            '{"command":"squash","args":["-r","a1"],"reason":"fix"},'
            '{"command":"describe","args":["-r","b2","-m","feat: auth"],'
            '"reason":"better msg"},'
            '{"command":"rebase","args":["-r","c3","--after","a1"],'
            '"reason":"reorder"}'
            "]"
        )
        plan = parse_curation_plan(raw)
        assert [s["command"] for s in plan] == ["squash", "describe", "rebase"]

    def test_parse_handles_markdown_fences(self) -> None:
        raw = '```json\n[{"command": "squash", "args": ["-r", "x"], "reason": "fix"}]\n```'
        plan = parse_curation_plan(raw)
        assert len(plan) == 1
        assert plan[0]["command"] == "squash"

    def test_parse_handles_invalid_json(self) -> None:
        assert parse_curation_plan("this is not json at all") == []

    def test_parse_handles_non_array_json(self) -> None:
        assert parse_curation_plan('{"command": "squash"}') == []

    def test_parse_skips_invalid_commands(self) -> None:
        raw = """[
            {"command": "squash", "args": ["-r", "a1"], "reason": "ok"},
            {"command": "delete", "args": [], "reason": "not a valid command"},
            {"command": "describe", "args": ["-r", "b2", "-m", "x"], "reason": "ok"}
        ]"""
        plan = parse_curation_plan(raw)
        assert [s["command"] for s in plan] == ["squash", "describe"]

    def test_parse_skips_non_dict_entries(self) -> None:
        raw = '[{"command": "squash", "args": [], "reason": "ok"}, "not a dict", 42]'
        plan = parse_curation_plan(raw)
        assert len(plan) == 1

    def test_parse_adds_default_args_and_reason(self) -> None:
        plan = parse_curation_plan('[{"command": "squash"}]')
        assert plan[0]["args"] == []
        assert plan[0]["reason"] == ""


class TestExtractBeadIds:
    """Tests for ``extract_bead_ids`` helper."""

    def test_extracts_single_bead_id(self) -> None:
        desc = "bead(sample_maverick_project-e6c.8): implement auth"
        assert extract_bead_ids(desc) == ["sample_maverick_project-e6c.8"]

    def test_extracts_multiple_bead_ids_in_squashed_message(self) -> None:
        desc = "bead(proj-a.1): first part\n\nbead(proj-a.2): second part"
        assert extract_bead_ids(desc) == ["proj-a.1", "proj-a.2"]

    def test_dedupes_repeated_ids(self) -> None:
        desc = "bead(p-1.1): a\nbead(p-1.1): b\nbead(p-1.2): c"
        assert extract_bead_ids(desc) == ["p-1.1", "p-1.2"]

    def test_returns_empty_for_snapshot_commit(self) -> None:
        assert extract_bead_ids("snapshot: pre-flight uncommitted changes") == []

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
        assert "\n\nRefs:" in new_message

    def test_preserves_existing_trailer(self) -> None:
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
        assert _describe_message(out[0]) == existing

    def test_skips_when_source_has_no_bead_id(self) -> None:
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
        assert new_message == (
            "feat: complex change\n\nLong body explaining why.\n\nRefs: proj-1.5"
        )


def _describe_message(step: dict) -> str:
    """Return the ``-m`` arg value from a describe step (test helper)."""
    args = step["args"]
    for i, token in enumerate(args):
        if token == "-m" and i + 1 < len(args):
            return str(args[i + 1])
    raise AssertionError(f"describe step has no -m arg: {step}")


# ---------------------------------------------------------------------------
# Round-trip sanity check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_commands",
    [
        ("[]", []),
        ('[{"command": "squash"}]', ["squash"]),
        (
            '[{"command": "squash"}, {"command": "describe", "args": ["-r", "x"]}]',
            ["squash", "describe"],
        ),
    ],
)
def test_parse_round_trip(raw: str, expected_commands: list[str]) -> None:
    plan = parse_curation_plan(raw)
    assert [s["command"] for s in plan] == expected_commands
