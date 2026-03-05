"""Unit tests for CodeReviewerAgent.

Tests the code review agent's functionality including:
- Initialization and configuration
- Diff retrieval and parsing
- Finding extraction and severity categorization
- Truncation and chunking behavior
- Error handling for git operations
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.agents.code_reviewer import (
    DEFAULT_BASE_BRANCH,
    MAX_DIFF_FILES,
    MAX_DIFF_LINES,
    MAX_TOKENS_PER_CHUNK,
    SYSTEM_PROMPT,
    CodeReviewerAgent,
)
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.models.review import (
    ReviewContext,
    ReviewSeverity,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def agent() -> CodeReviewerAgent:
    """Create a CodeReviewerAgent instance for testing."""
    return CodeReviewerAgent()


@pytest.fixture
def mock_review_context(tmp_path: Path) -> ReviewContext:
    """Create a mock ReviewContext for testing."""
    return ReviewContext(
        branch="feature/test-branch",
        base_branch="main",
        cwd=tmp_path,
    )


@pytest.fixture
def sample_findings_response() -> str:
    """Sample Claude response with findings JSON."""
    return """
I've reviewed the code and found the following issues:

```json
{
  "findings": [
    {
      "severity": "critical",
      "file": "src/example.py",
      "line": 5,
      "message": "SQL injection vulnerability: user input is directly interpolated",
      "suggestion": "Use parameterized queries with placeholders"
    },
    {
      "severity": "minor",
      "file": "src/example.py",
      "line": 2,
      "message": "Consider using f-string for greeting",
      "suggestion": "Use: print(f'Hello, {name}!')"
    }
  ]
}
```

Please address the critical SQL injection issue before merging.
"""


# =============================================================================
# Initialization Tests
# =============================================================================


class TestCodeReviewerAgentInitialization:
    """Tests for CodeReviewerAgent initialization."""

    def test_default_initialization(self, agent: CodeReviewerAgent) -> None:
        """Test agent initializes with correct defaults."""
        assert agent.name == "code-reviewer"
        assert agent.instructions == SYSTEM_PROMPT
        assert set(agent.allowed_tools) == set(REVIEWER_TOOLS)

    def test_custom_model(self) -> None:
        """Test agent accepts custom model parameter."""
        custom_agent = CodeReviewerAgent(model="claude-3-opus-20240229")
        assert custom_agent.model == "claude-3-opus-20240229"

    def test_instructions_contains_review_dimensions(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test instructions includes all review dimensions."""
        prompt = agent.instructions
        assert "correctness" in prompt.lower() or "Correctness" in prompt
        assert "security" in prompt.lower() or "Security" in prompt
        assert "style" in prompt.lower() or "Style" in prompt
        assert "performance" in prompt.lower() or "Performance" in prompt

    def test_instructions_mentions_pre_gathered_context(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test instructions mentions pre-gathered context (T025).

        Agent should understand that diffs and file contents are provided
        by the orchestration layer, not retrieved by the agent itself.
        """
        prompt = agent.instructions.lower()
        assert (
            "pre-gathered" in prompt
            or "provided" in prompt
            or "orchestration" in prompt
        )

    def test_allowed_tools_excludes_bash(self, agent: CodeReviewerAgent) -> None:
        """Test allowed tools excludes Bash (orchestration layer handles commands)."""
        assert "Bash" not in agent.allowed_tools

    def test_allowed_tools_includes_read(self, agent: CodeReviewerAgent) -> None:
        """Test allowed tools includes Read for file reading."""
        assert "Read" in agent.allowed_tools

    def test_allowed_tools_matches_contract(self, agent: CodeReviewerAgent) -> None:
        """Test allowed tools matches US1 contract exactly.

        US1 Contract: CodeReviewerAgent must have exactly Read, Glob, Grep (no Bash).
        Read-only tools for analysis, no Write or Edit permissions.
        Bash removed per orchestration pattern - workflows handle command execution.
        """
        expected_tools = {"Read", "Glob", "Grep"}
        actual_tools = set(agent.allowed_tools)
        assert actual_tools == expected_tools, (
            f"CodeReviewerAgent tools mismatch. "
            f"Expected: {expected_tools}, Got: {actual_tools}"
        )
        # Ensure no write permissions
        assert "Write" not in agent.allowed_tools
        assert "Edit" not in agent.allowed_tools
        # Ensure no Bash (orchestration handles commands)
        assert "Bash" not in agent.allowed_tools

    def test_allowed_tools_uses_centralized_constants(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test allowed tools uses REVIEWER_TOOLS from maverick.agents.tools.

        T011: Verify that CodeReviewerAgent uses the centralized REVIEWER_TOOLS
        constant from tools.py, not local definition. This enforces the orchestration
        pattern where tool permissions are centrally managed.
        """
        from maverick.agents.tools import REVIEWER_TOOLS as CENTRALIZED_TOOLS

        # Agent's allowed_tools should match the centralized constant
        expected_tools = set(CENTRALIZED_TOOLS)
        actual_tools = set(agent.allowed_tools)

        assert actual_tools == expected_tools, (
            f"CodeReviewerAgent must use centralized REVIEWER_TOOLS. "
            f"Expected: {expected_tools}, Got: {actual_tools}"
        )

        # Ensure Bash is NOT in the centralized tools (per US1 contract)
        assert "Bash" not in CENTRALIZED_TOOLS, (
            "Bash should be removed from REVIEWER_TOOLS per US1"
        )

        # Ensure no write tools (read-only agent)
        assert "Write" not in CENTRALIZED_TOOLS
        assert "Edit" not in CENTRALIZED_TOOLS


# =============================================================================
# Constants Tests
# =============================================================================


class TestCodeReviewerConstants:
    """Tests for CodeReviewerAgent constants."""

    def test_max_diff_lines_is_reasonable(self) -> None:
        """Test MAX_DIFF_LINES is set to spec value."""
        assert MAX_DIFF_LINES == 2000

    def test_max_diff_files_is_reasonable(self) -> None:
        """Test MAX_DIFF_FILES is set to spec value."""
        assert MAX_DIFF_FILES == 50

    def test_default_base_branch_is_main(self) -> None:
        """Test default base branch is 'main'."""
        assert DEFAULT_BASE_BRANCH == "main"

    def test_max_tokens_per_chunk_is_set(self) -> None:
        """Test MAX_TOKENS_PER_CHUNK is defined."""
        assert MAX_TOKENS_PER_CHUNK > 0


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestEstimateTokens:
    """Tests for _estimate_tokens helper method."""

    def test_estimate_tokens_empty_string(self, agent: CodeReviewerAgent) -> None:
        """Test token estimation for empty string returns 0."""
        result = agent._estimate_tokens("")
        assert result == 0

    def test_estimate_tokens_short_string(self, agent: CodeReviewerAgent) -> None:
        """Test token estimation for short string."""
        # tiktoken cl100k_base: "Hello World!" = 3 tokens
        result = agent._estimate_tokens("Hello World!")
        assert result == 3

    def test_estimate_tokens_long_string(self, agent: CodeReviewerAgent) -> None:
        """Test token estimation for longer content."""
        # tiktoken cl100k_base: 400 'a' characters = 50 tokens
        content = "a" * 400
        result = agent._estimate_tokens(content)
        assert result == 50


class TestShouldTruncate:
    """Tests for _should_truncate helper method."""

    def test_should_truncate_under_limits(self, agent: CodeReviewerAgent) -> None:
        """Test returns False when under all limits."""
        diff_stats = {
            "files": ["a.py", "b.py"],
            "total_lines": 100,
        }
        assert agent._should_truncate(diff_stats) is False

    def test_should_truncate_exceeds_line_limit(self, agent: CodeReviewerAgent) -> None:
        """Test returns True when exceeding line limit."""
        diff_stats = {
            "files": ["a.py"],
            "total_lines": MAX_DIFF_LINES + 1,
        }
        assert agent._should_truncate(diff_stats) is True

    def test_should_truncate_exceeds_file_limit(self, agent: CodeReviewerAgent) -> None:
        """Test returns True when exceeding file limit."""
        diff_stats = {
            "files": [f"file_{i}.py" for i in range(MAX_DIFF_FILES + 1)],
            "total_lines": 100,
        }
        assert agent._should_truncate(diff_stats) is True

    def test_should_truncate_at_exact_limits(self, agent: CodeReviewerAgent) -> None:
        """Test returns False when at exact limits."""
        diff_stats = {
            "files": [f"file_{i}.py" for i in range(MAX_DIFF_FILES)],
            "total_lines": MAX_DIFF_LINES,
        }
        assert agent._should_truncate(diff_stats) is False


class TestParseFindings:
    """Tests for _parse_findings helper method."""

    def test_parse_findings_valid_json(
        self, agent: CodeReviewerAgent, sample_findings_response: str
    ) -> None:
        """Test parsing findings from valid JSON response."""
        findings = agent._parse_findings(sample_findings_response)

        # Should parse at least the valid entries
        assert len(findings) >= 1
        # Check first finding (critical)
        critical_findings = [
            f for f in findings if f.severity == ReviewSeverity.CRITICAL
        ]
        assert len(critical_findings) >= 1
        assert critical_findings[0].file == "src/example.py"

    def test_parse_findings_empty_response(self, agent: CodeReviewerAgent) -> None:
        """Test parsing empty response returns empty list."""
        findings = agent._parse_findings("")
        assert findings == []

    def test_parse_findings_no_json(self, agent: CodeReviewerAgent) -> None:
        """Test parsing response without JSON returns empty list."""
        response = "The code looks good, no issues found."
        findings = agent._parse_findings(response)
        assert findings == []

    def test_parse_findings_invalid_json(self, agent: CodeReviewerAgent) -> None:
        """Test parsing invalid JSON returns empty list."""
        response = "```json\n{invalid json}\n```"
        findings = agent._parse_findings(response)
        assert findings == []

    def test_parse_findings_filters_invalid_entries(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test that invalid finding entries are filtered out."""
        response = """```json
{
  "findings": [
    {"severity": "critical", "file": "a.py", "message": "Valid finding"},
    {"severity": "invalid", "file": "b.py", "message": "Invalid severity value"},
    {"file": "c.py", "message": "Missing severity field"}
  ]
}
```"""
        findings = agent._parse_findings(response)
        # Valid entries should be parsed - invalid severity gets default
        assert len(findings) >= 1
        # The first one should be critical
        assert any(f.severity == ReviewSeverity.CRITICAL for f in findings)


# Note: Binary file detection is handled in _get_diff_stats via git diff --numstat
# which marks binary files with "-" for additions/deletions. No separate method exists.


# =============================================================================
# build_prompt Tests
# =============================================================================


class TestBuildPrompt:
    """Tests for the build_prompt method.

    execute() was removed in the ACP migration. The primary agent interface
    is now build_prompt(context) which constructs the prompt for the ACP executor.
    """

    def test_build_prompt_returns_string(
        self,
        agent: CodeReviewerAgent,
        mock_review_context: ReviewContext,
    ) -> None:
        """Test build_prompt returns a non-empty string."""
        result = agent.build_prompt(mock_review_context)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_prompt_contains_branch_name(
        self,
        agent: CodeReviewerAgent,
        mock_review_context: ReviewContext,
    ) -> None:
        """Test build_prompt includes the feature branch name."""
        result = agent.build_prompt(mock_review_context)

        assert "feature/test-branch" in result

    def test_build_prompt_contains_base_branch(
        self,
        agent: CodeReviewerAgent,
        mock_review_context: ReviewContext,
    ) -> None:
        """Test build_prompt includes the base branch name."""
        result = agent.build_prompt(mock_review_context)

        assert "main" in result

    def test_build_prompt_mentions_conventions(
        self,
        agent: CodeReviewerAgent,
        mock_review_context: ReviewContext,
    ) -> None:
        """Test build_prompt instructs agent to check CLAUDE.md conventions."""
        result = agent.build_prompt(mock_review_context)

        assert "CLAUDE.md" in result

    def test_build_prompt_with_file_list(
        self,
        agent: CodeReviewerAgent,
        tmp_path: Path,
    ) -> None:
        """Test build_prompt includes file list when specified."""
        context = ReviewContext(
            branch="feature/auth",
            base_branch="main",
            file_list=["src/auth.py", "tests/test_auth.py"],
            cwd=tmp_path,
        )
        result = agent.build_prompt(context)

        assert "src/auth.py" in result
        assert "tests/test_auth.py" in result

    def test_build_prompt_without_file_list(
        self,
        agent: CodeReviewerAgent,
        mock_review_context: ReviewContext,
    ) -> None:
        """Test build_prompt works when no file list is specified (review all files)."""
        assert mock_review_context.file_list is None
        result = agent.build_prompt(mock_review_context)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_prompt_requests_structured_findings(
        self,
        agent: CodeReviewerAgent,
        mock_review_context: ReviewContext,
    ) -> None:
        """Test build_prompt asks agent to return structured findings."""
        result = agent.build_prompt(mock_review_context)

        assert "findings" in result.lower() or "structured" in result.lower()


# =============================================================================
# ReviewContext Building Tests
# =============================================================================


class TestReviewContextBuilding:
    """Tests for ReviewContext building via build_prompt."""

    def test_uses_default_base_branch_when_not_specified(
        self,
        agent: CodeReviewerAgent,
        tmp_path: Path,
    ) -> None:
        """Test prompt uses DEFAULT_BASE_BRANCH when ReviewContext defaults apply."""
        context = ReviewContext(
            branch="feature/test",
            cwd=tmp_path,
            # base_branch not specified — defaults to "main" (DEFAULT_BASE_BRANCH)
        )
        result = agent.build_prompt(context)

        assert DEFAULT_BASE_BRANCH in result

    def test_uses_custom_base_branch_when_specified(
        self,
        agent: CodeReviewerAgent,
        tmp_path: Path,
    ) -> None:
        """Test prompt includes custom base_branch when provided."""
        context = ReviewContext(
            branch="feature/test",
            base_branch="develop",
            cwd=tmp_path,
        )
        result = agent.build_prompt(context)

        assert "develop" in result


# =============================================================================
# Truncation Tests
# =============================================================================


class TestTruncateFiles:
    """Tests for _truncate_files method."""

    def test_truncate_files_returns_subset(self, agent: CodeReviewerAgent) -> None:
        """Test truncation returns limited files."""
        files = [f"file_{i}.py" for i in range(100)]
        diff_stats = {
            "files": files,
            "total_lines": MAX_DIFF_LINES + 100,  # Force truncation
        }

        result, notice = agent._truncate_files(files, diff_stats)

        assert len(result) == MAX_DIFF_FILES
        assert notice != ""
        assert "skipped" in notice.lower()

    def test_truncate_files_no_change_when_under_limit(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test no truncation when under limit."""
        files = ["a.py", "b.py", "c.py"]
        diff_stats = {
            "files": files,
            "total_lines": 100,
        }

        result, notice = agent._truncate_files(files, diff_stats)

        assert result == files
        assert notice == ""
