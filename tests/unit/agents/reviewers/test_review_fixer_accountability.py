"""Unit tests for ReviewFixerAgent accountability features.

This module tests the accountability-focused behavior of the ReviewFixerAgent:
- _build_prompt() includes all findings
- _build_prompt() includes previous attempt history
- _parse_output() extracts JSON from markdown
- _parse_output() handles raw JSON
- _parse_output() raises ValueError on invalid JSON
- _fill_missing() adds auto-defer entries
- _fill_missing() preserves existing entries
- System prompt includes accountability requirements
"""

from __future__ import annotations

import pytest

from maverick.agents.prompts.review_fixer import (
    INVALID_JUSTIFICATIONS,
    PREVIOUS_ATTEMPT_WARNING,
    REVIEW_FIXER_SYSTEM_PROMPT,
    VALID_BLOCKED_REASONS,
    format_system_prompt,
)
from maverick.agents.reviewers.review_fixer import (
    ReviewFixerAgent,
    build_fixer_input,
    build_fixer_input_from_legacy,
)
from maverick.models.fixer_io import (
    FixerInput,
    FixerInputItem,
    FixerOutput,
    FixerOutputItem,
)


class TestBuildPrompt:
    """Tests for _build_prompt() method."""

    def test_build_prompt_includes_all_findings(self) -> None:
        """Test that _build_prompt includes all findings."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="critical",
                    title="Security vulnerability",
                    description="SQL injection possible",
                    file_path="src/db.py",
                    line_range=(10, 15),
                    suggested_fix="Use parameterized queries",
                    previous_attempts=(),
                ),
                FixerInputItem(
                    finding_id="RT002",
                    severity="major",
                    title="Missing error handling",
                    description="No exception handling",
                    file_path="src/api.py",
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
            ),
            context="PR context here",
        )

        prompt = agent._build_prompt(fixer_input)

        # Check that all finding IDs are present
        assert "RS001" in prompt
        assert "RT002" in prompt

        # Check that all titles are present
        assert "Security vulnerability" in prompt
        assert "Missing error handling" in prompt

        # Check that descriptions are present
        assert "SQL injection possible" in prompt
        assert "No exception handling" in prompt

        # Check that file paths are present
        assert "src/db.py" in prompt
        assert "src/api.py" in prompt

        # Check iteration header
        assert "Iteration 1" in prompt

        # Check context is included
        assert "PR context here" in prompt

    def test_build_prompt_includes_line_range(self) -> None:
        """Test that _build_prompt includes line range when present."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="major",
                    title="Test issue",
                    description="Test description",
                    file_path="src/test.py",
                    line_range=(42, 50),
                    suggested_fix=None,
                    previous_attempts=(),
                ),
            ),
            context="",
        )

        prompt = agent._build_prompt(fixer_input)

        assert "42-50" in prompt or "42" in prompt

    def test_build_prompt_includes_suggested_fix(self) -> None:
        """Test that _build_prompt includes suggested fix when present."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="major",
                    title="Test issue",
                    description="Test description",
                    file_path=None,
                    line_range=None,
                    suggested_fix="Use a different approach",
                    previous_attempts=(),
                ),
            ),
            context="",
        )

        prompt = agent._build_prompt(fixer_input)

        assert "Use a different approach" in prompt

    def test_build_prompt_includes_previous_attempt_history(self) -> None:
        """Test that _build_prompt includes previous attempt history."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=2,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="critical",
                    title="Recurring issue",
                    description="This keeps coming back",
                    file_path="src/problem.py",
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(
                        {
                            "iteration": 1,
                            "outcome": "deferred",
                            "justification": "Too complex for now",
                        },
                    ),
                ),
            ),
            context="",
        )

        prompt = agent._build_prompt(fixer_input)

        # Check previous attempt info is included
        assert "Previous Attempts" in prompt
        assert "deferred" in prompt
        assert "Too complex for now" in prompt
        assert "iteration 1" in prompt.lower()

    def test_build_prompt_includes_multiple_previous_attempts(self) -> None:
        """Test that _build_prompt handles multiple previous attempts."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=3,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="critical",
                    title="Persistent issue",
                    description="Still not fixed",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(
                        {
                            "iteration": 1,
                            "outcome": "deferred",
                            "justification": "First attempt failed",
                        },
                        {
                            "iteration": 2,
                            "outcome": "deferred",
                            "justification": "Second attempt also failed",
                        },
                    ),
                ),
            ),
            context="",
        )

        prompt = agent._build_prompt(fixer_input)

        assert "First attempt failed" in prompt
        assert "Second attempt also failed" in prompt

    def test_build_prompt_includes_accountability_reminder(self) -> None:
        """Test that _build_prompt includes accountability reminder."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="major",
                    title="Test",
                    description="Test",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
            ),
            context="",
        )

        prompt = agent._build_prompt(fixer_input)

        assert "MUST report" in prompt or "must provide" in prompt.lower()
        assert "auto-deferred" in prompt.lower()


class TestParseOutput:
    """Tests for _parse_output() method."""

    def test_parse_output_extracts_json_from_markdown(self) -> None:
        """Test that _parse_output extracts JSON from markdown code block."""
        agent = ReviewFixerAgent()

        response = """
I analyzed the issues and made the following fixes.

Here is my report:

```json
{
  "items": [
    {
      "finding_id": "RS001",
      "status": "fixed",
      "justification": null,
      "changes_made": "Updated the code"
    }
  ],
  "summary": "Fixed 1 issue"
}
```

Let me know if you need anything else.
"""

        output = agent._parse_output(response)

        assert len(output.items) == 1
        assert output.items[0].finding_id == "RS001"
        assert output.items[0].status == "fixed"
        assert output.items[0].changes_made == "Updated the code"
        assert output.summary == "Fixed 1 issue"

    def test_parse_output_handles_raw_json(self) -> None:
        """Test that _parse_output handles raw JSON without markdown."""
        agent = ReviewFixerAgent()

        json_obj = (
            '{"items": [{"finding_id": "RT001", "status": "blocked", '
            '"justification": "File not found", "changes_made": null}], '
            '"summary": "1 blocked"}'
        )
        response = f"""
Here is my response:

{json_obj}
"""

        output = agent._parse_output(response)

        assert len(output.items) == 1
        assert output.items[0].finding_id == "RT001"
        assert output.items[0].status == "blocked"
        assert output.items[0].justification == "File not found"

    def test_parse_output_uses_last_json_block(self) -> None:
        """Test that _parse_output uses the last JSON block if multiple exist."""
        agent = ReviewFixerAgent()

        response = """
First I tried this:

```json
{
  "items": [{"finding_id": "RS001", "status": "deferred", "justification": "old"}]
}
```

But then I fixed it properly:

```json
{
  "items": [{"finding_id": "RS001", "status": "fixed", "changes_made": "Fixed it"}],
  "summary": "Done"
}
```
"""

        output = agent._parse_output(response)

        assert len(output.items) == 1
        assert output.items[0].status == "fixed"
        assert output.items[0].changes_made == "Fixed it"

    def test_parse_output_handles_multiple_items(self) -> None:
        """Test that _parse_output handles multiple items."""
        agent = ReviewFixerAgent()

        response = """
```json
{
  "items": [
    {"finding_id": "RS001", "status": "fixed", "changes_made": "Fixed A"},
    {"finding_id": "RS002", "status": "blocked", "justification": "Cannot fix"},
    {"finding_id": "RS003", "status": "deferred", "justification": "Later"}
  ],
  "summary": "Processed 3 items"
}
```
"""

        output = agent._parse_output(response)

        assert len(output.items) == 3
        assert output.items[0].finding_id == "RS001"
        assert output.items[0].status == "fixed"
        assert output.items[1].finding_id == "RS002"
        assert output.items[1].status == "blocked"
        assert output.items[2].finding_id == "RS003"
        assert output.items[2].status == "deferred"

    def test_parse_output_raises_on_no_json(self) -> None:
        """Test that _parse_output raises ValueError when no JSON found."""
        agent = ReviewFixerAgent()

        response = "I fixed everything but forgot to output JSON."

        with pytest.raises(ValueError, match="No JSON output found"):
            agent._parse_output(response)

    def test_parse_output_raises_on_invalid_json(self) -> None:
        """Test that _parse_output raises ValueError on invalid JSON."""
        agent = ReviewFixerAgent()

        response = """
```json
{
  "items": [
    {"finding_id": "RS001", status: "fixed"}
  ]
}
```
"""

        with pytest.raises(ValueError, match="Invalid JSON"):
            agent._parse_output(response)

    def test_parse_output_raises_on_missing_items_key(self) -> None:
        """Test that _parse_output raises ValueError when items key missing."""
        agent = ReviewFixerAgent()

        response = """
```json
{
  "findings": [{"id": "RS001"}]
}
```
"""

        with pytest.raises(ValueError, match="missing 'items' key"):
            agent._parse_output(response)

    def test_parse_output_skips_items_without_finding_id(self) -> None:
        """Test that _parse_output skips items missing finding_id."""
        agent = ReviewFixerAgent()

        response = """
```json
{
  "items": [
    {"finding_id": "RS001", "status": "fixed"},
    {"status": "fixed"},
    {"finding_id": "RS002", "status": "blocked", "justification": "test"}
  ]
}
```
"""

        output = agent._parse_output(response)

        # Should only have 2 items (the one without finding_id is skipped)
        assert len(output.items) == 2
        assert output.items[0].finding_id == "RS001"
        assert output.items[1].finding_id == "RS002"


class TestFillMissing:
    """Tests for _fill_missing() method."""

    def test_fill_missing_adds_auto_defer_entries(self) -> None:
        """Test that _fill_missing adds auto-defer for missing items."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="major",
                    title="First",
                    description="Desc 1",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
                FixerInputItem(
                    finding_id="RS002",
                    severity="minor",
                    title="Second",
                    description="Desc 2",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
            ),
            context="",
        )

        # Output only has RS001, missing RS002
        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed it",
                ),
            ),
            summary="Fixed 1",
        )

        result = agent._fill_missing(fixer_output, fixer_input)

        assert len(result.items) == 2
        # First item preserved
        assert result.items[0].finding_id == "RS001"
        assert result.items[0].status == "fixed"
        # Second item auto-deferred
        assert result.items[1].finding_id == "RS002"
        assert result.items[1].status == "deferred"
        assert "did not provide status" in result.items[1].justification.lower()

    def test_fill_missing_preserves_existing_entries(self) -> None:
        """Test that _fill_missing preserves existing entries."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="major",
                    title="First",
                    description="Desc",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
            ),
            context="",
        )

        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="blocked",
                    justification="Cannot fix - external dependency",
                    changes_made=None,
                ),
            ),
            summary="1 blocked",
        )

        result = agent._fill_missing(fixer_output, fixer_input)

        assert len(result.items) == 1
        assert result.items[0].finding_id == "RS001"
        assert result.items[0].status == "blocked"
        assert result.items[0].justification == "Cannot fix - external dependency"

    def test_fill_missing_handles_empty_output(self) -> None:
        """Test that _fill_missing handles completely empty output."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="major",
                    title="First",
                    description="Desc 1",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
                FixerInputItem(
                    finding_id="RS002",
                    severity="critical",
                    title="Second",
                    description="Desc 2",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
            ),
            context="",
        )

        fixer_output = FixerOutput(items=(), summary=None)

        result = agent._fill_missing(fixer_output, fixer_input)

        assert len(result.items) == 2
        assert all(item.status == "deferred" for item in result.items)
        assert "auto-deferred" in result.summary.lower()

    def test_fill_missing_updates_summary(self) -> None:
        """Test that _fill_missing updates summary with auto-defer count."""
        agent = ReviewFixerAgent()

        fixer_input = FixerInput(
            iteration=1,
            items=(
                FixerInputItem(
                    finding_id="RS001",
                    severity="major",
                    title="Issue 1",
                    description="Desc",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
                FixerInputItem(
                    finding_id="RS002",
                    severity="major",
                    title="Issue 2",
                    description="Desc",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
                FixerInputItem(
                    finding_id="RS003",
                    severity="major",
                    title="Issue 3",
                    description="Desc",
                    file_path=None,
                    line_range=None,
                    suggested_fix=None,
                    previous_attempts=(),
                ),
            ),
            context="",
        )

        fixer_output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Done",
                ),
            ),
            summary="Fixed 1 issue",
        )

        result = agent._fill_missing(fixer_output, fixer_input)

        assert "2 items auto-deferred" in result.summary


class TestSystemPrompt:
    """Tests for system prompt accountability requirements."""

    def test_system_prompt_includes_accountability_requirements(self) -> None:
        """Test that system prompt includes accountability requirements."""
        prompt = format_system_prompt(has_previous_attempts=False)

        # Check for accountability language
        assert "MUST report on EVERY issue" in prompt
        assert "No silent skipping" in prompt

    def test_system_prompt_includes_output_format(self) -> None:
        """Test that system prompt includes the JSON output format."""
        prompt = format_system_prompt(has_previous_attempts=False)

        assert "```json" in prompt
        assert '"items"' in prompt
        assert '"finding_id"' in prompt
        assert '"status"' in prompt

    def test_system_prompt_includes_status_definitions(self) -> None:
        """Test that system prompt includes status definitions."""
        prompt = format_system_prompt(has_previous_attempts=False)

        assert "fixed" in prompt.lower()
        assert "blocked" in prompt.lower()
        assert "deferred" in prompt.lower()

    def test_system_prompt_includes_deferred_warning(self) -> None:
        """Test that system prompt warns about deferred items returning."""
        prompt = format_system_prompt(has_previous_attempts=False)

        assert "deferred" in prompt.lower()
        assert "sent back" in prompt.lower() or "return" in prompt.lower()

    def test_system_prompt_includes_invalid_justifications(self) -> None:
        """Test that system prompt includes invalid justification patterns."""
        prompt = format_system_prompt(has_previous_attempts=False)

        # Check for some invalid justification patterns
        assert "unrelated" in prompt.lower() or "out of scope" in prompt.lower()
        assert "rejected" in prompt.lower()

    def test_system_prompt_includes_valid_blocked_reasons(self) -> None:
        """Test that system prompt includes valid blocked reasons."""
        prompt = format_system_prompt(has_previous_attempts=False)

        # Check for some valid blocked reasons
        assert "external" in prompt.lower() or "credentials" in prompt.lower()
        assert "blocked" in prompt.lower()

    def test_system_prompt_with_previous_attempts_includes_warning(self) -> None:
        """Test that system prompt with previous attempts includes warning."""
        prompt = format_system_prompt(has_previous_attempts=True)

        assert "Previous" in prompt
        assert "progress" in prompt.lower()

    def test_system_prompt_constants_are_defined(self) -> None:
        """Test that all prompt constants are properly defined."""
        assert REVIEW_FIXER_SYSTEM_PROMPT
        assert INVALID_JUSTIFICATIONS
        assert VALID_BLOCKED_REASONS
        assert PREVIOUS_ATTEMPT_WARNING


class TestBuildFixerInput:
    """Tests for build_fixer_input helper function."""

    def test_build_fixer_input_from_dicts(self) -> None:
        """Test building FixerInput from dictionary list."""
        findings = [
            {
                "finding_id": "RS001",
                "severity": "critical",
                "title": "Test Issue",
                "description": "A test issue",
                "file_path": "src/test.py",
                "line_start": 10,
                "line_end": 15,
                "suggested_fix": "Fix it",
            },
            {
                "id": "RT001",  # Alternative key
                "severity": "major",
                "title": "Another Issue",
                "description": "Another test issue",
            },
        ]

        result = build_fixer_input(findings, iteration=2, context="Test context")

        assert result.iteration == 2
        assert result.context == "Test context"
        assert len(result.items) == 2

        assert result.items[0].finding_id == "RS001"
        assert result.items[0].severity == "critical"
        assert result.items[0].file_path == "src/test.py"
        assert result.items[0].line_range == (10, 15)
        assert result.items[0].suggested_fix == "Fix it"

        assert result.items[1].finding_id == "RT001"
        assert result.items[1].severity == "major"

    def test_build_fixer_input_handles_missing_fields(self) -> None:
        """Test that build_fixer_input handles missing optional fields."""
        findings = [
            {
                "finding_id": "RS001",
                "severity": "minor",
                "title": "Simple Issue",
                "description": "Simple description",
            }
        ]

        result = build_fixer_input(findings, iteration=1)

        assert len(result.items) == 1
        assert result.items[0].file_path is None
        assert result.items[0].line_range is None
        assert result.items[0].suggested_fix is None
        assert result.items[0].previous_attempts == ()

    def test_build_fixer_input_includes_previous_attempts(self) -> None:
        """Test that build_fixer_input includes previous attempts."""
        findings = [
            {
                "finding_id": "RS001",
                "severity": "major",
                "title": "Issue",
                "description": "Desc",
                "previous_attempts": [
                    {"iteration": 1, "outcome": "deferred", "justification": "Later"},
                ],
            }
        ]

        result = build_fixer_input(findings, iteration=2)

        assert len(result.items[0].previous_attempts) == 1
        assert result.items[0].previous_attempts[0]["outcome"] == "deferred"


class TestBuildFixerInputFromLegacy:
    """Tests for build_fixer_input_from_legacy helper function."""

    def test_converts_structured_issues(self) -> None:
        """Test converting legacy context with structured issues."""
        legacy_context = {
            "review_report": "Some review findings",
            "issues": [
                {
                    "finding_id": "RS001",
                    "severity": "critical",
                    "title": "Security Issue",
                    "description": "SQL injection vulnerability",
                    "file_path": "src/db.py",
                    "line_start": 10,
                    "line_end": 15,
                },
                {
                    "id": "RT001",  # Alternative key
                    "severity": "major",
                    "title": "Missing Error Handling",
                    "description": "No exception handling",
                    "file_path": "src/api.py",
                    "line_number": 42,  # Alternative line field
                },
            ],
            "changed_files": ["src/db.py", "src/api.py"],
            "recommendation": "request_changes",
        }

        result = build_fixer_input_from_legacy(legacy_context, iteration=2)

        assert result.iteration == 2
        assert len(result.items) == 2

        # Check first item
        assert result.items[0].finding_id == "RS001"
        assert result.items[0].severity == "critical"
        assert result.items[0].file_path == "src/db.py"
        assert result.items[0].line_range == (10, 15)

        # Check second item (uses alternative keys)
        assert result.items[1].finding_id == "RT001"
        assert result.items[1].severity == "major"
        assert result.items[1].line_range == (42, 42)  # line_number becomes range

        # Check context includes changed files and recommendation
        assert "src/db.py" in result.context
        assert "request_changes" in result.context

    def test_creates_synthetic_finding_from_report(self) -> None:
        """Test creating synthetic finding when no structured issues present."""
        legacy_context = {
            "review_report": "Found several issues with error handling",
            "issues": [],
            "changed_files": [],
            "recommendation": "comment",
        }

        result = build_fixer_input_from_legacy(legacy_context)

        assert result.iteration == 1  # Default iteration
        assert len(result.items) == 1
        assert result.items[0].finding_id == "LEGACY001"
        assert result.items[0].severity == "major"
        assert "error handling" in result.items[0].description

    def test_handles_missing_optional_fields(self) -> None:
        """Test handling of missing optional fields in issues."""
        legacy_context = {
            "issues": [
                {
                    "description": "Some issue without title or ID",
                }
            ],
        }

        result = build_fixer_input_from_legacy(legacy_context)

        assert len(result.items) == 1
        # Should generate an ID
        assert result.items[0].finding_id == "L001"
        # Title should be derived from description
        assert "Some issue" in result.items[0].title
        # File path should be None
        assert result.items[0].file_path is None

    def test_skips_non_dict_issues(self) -> None:
        """Test that non-dict items in issues list are skipped."""
        legacy_context = {
            "issues": [
                {"finding_id": "RS001", "description": "Valid issue"},
                "not a dict",  # Should be skipped
                None,  # Should be skipped
                {"finding_id": "RS002", "description": "Another valid issue"},
            ],
        }

        result = build_fixer_input_from_legacy(legacy_context)

        # Only dict items should be included
        assert len(result.items) == 2
        assert result.items[0].finding_id == "RS001"
        assert result.items[1].finding_id == "RS002"

    def test_empty_context_produces_empty_items(self) -> None:
        """Test that empty context with no report produces empty items."""
        legacy_context = {
            "issues": [],
            "review_report": "",
        }

        result = build_fixer_input_from_legacy(legacy_context)

        assert len(result.items) == 0


class TestReviewFixerAgentInit:
    """Tests for ReviewFixerAgent initialization."""

    def test_agent_has_correct_name(self) -> None:
        """Test that agent has the correct name."""
        agent = ReviewFixerAgent()
        assert agent.name == "review-fixer"

    def test_agent_has_accountability_system_prompt(self) -> None:
        """Test that agent uses accountability-focused system prompt."""
        agent = ReviewFixerAgent()

        # Check for accountability requirements in the system prompt
        assert "MUST report on EVERY issue" in agent.system_prompt
        assert "No silent skipping" in agent.system_prompt

    def test_agent_has_allowed_tools(self) -> None:
        """Test that agent has allowed tools configured."""
        agent = ReviewFixerAgent()
        assert len(agent.allowed_tools) > 0
