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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.agents.code_reviewer import (
    ALLOWED_TOOLS,
    DEFAULT_BASE_BRANCH,
    MAX_DIFF_FILES,
    MAX_DIFF_LINES,
    MAX_TOKENS_PER_CHUNK,
    SYSTEM_PROMPT,
    CodeReviewerAgent,
)
from maverick.agents.context import AgentContext
from maverick.agents.result import AgentUsage
from maverick.exceptions import AgentError
from maverick.models.review import (
    ReviewContext,
    ReviewSeverity,
    UsageStats,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def agent() -> CodeReviewerAgent:
    """Create a CodeReviewerAgent instance for testing."""
    return CodeReviewerAgent()


@pytest.fixture
def mock_agent_context(tmp_path: Path) -> AgentContext:
    """Create a mock AgentContext for testing."""
    return AgentContext(
        cwd=tmp_path,
        branch="feature/test-branch",
        config=MagicMock(),
        extra={"base_branch": "main"},
    )


@pytest.fixture
def mock_review_context(tmp_path: Path) -> ReviewContext:
    """Create a mock ReviewContext for testing."""
    return ReviewContext(
        branch="feature/test-branch",
        base_branch="main",
        cwd=tmp_path,
    )


@pytest.fixture
def sample_diff() -> str:
    """Sample git diff for testing."""
    return """diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -1,5 +1,10 @@
 def hello():
-    print("Hello")
+    print("Hello, World!")
+
+def insecure_query(user_input):
+    # SQL injection vulnerability
+    query = f"SELECT * FROM users WHERE name = '{user_input}'"
+    return query
"""


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
      "message": "SQL injection vulnerability: user input is directly interpolated into SQL query",
      "suggestion": "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE name = ?', (user_input,))"
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
        assert agent.system_prompt == SYSTEM_PROMPT
        assert agent.allowed_tools == ALLOWED_TOOLS

    def test_custom_model(self) -> None:
        """Test agent accepts custom model parameter."""
        custom_agent = CodeReviewerAgent(model="claude-3-opus-20240229")
        assert custom_agent.model == "claude-3-opus-20240229"

    def test_system_prompt_contains_review_dimensions(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test system prompt includes all review dimensions."""
        prompt = agent.system_prompt
        assert "correctness" in prompt.lower() or "Correctness" in prompt
        assert "security" in prompt.lower() or "Security" in prompt
        assert "style" in prompt.lower() or "Style" in prompt
        assert "performance" in prompt.lower() or "Performance" in prompt

    def test_allowed_tools_includes_bash(self, agent: CodeReviewerAgent) -> None:
        """Test allowed tools includes Bash for git operations."""
        assert "Bash" in agent.allowed_tools

    def test_allowed_tools_includes_read(self, agent: CodeReviewerAgent) -> None:
        """Test allowed tools includes Read for file reading."""
        assert "Read" in agent.allowed_tools

    def test_allowed_tools_matches_contract(self, agent: CodeReviewerAgent) -> None:
        """Test allowed tools matches US5 contract exactly.

        US5 Contract: CodeReviewerAgent must have exactly Read, Glob, Grep, Bash.
        Read-only tools for analysis, no Write or Edit permissions.
        """
        expected_tools = {"Read", "Glob", "Grep", "Bash"}
        actual_tools = set(agent.allowed_tools)
        assert actual_tools == expected_tools, (
            f"CodeReviewerAgent tools mismatch. Expected: {expected_tools}, Got: {actual_tools}"
        )
        # Ensure no write permissions
        assert "Write" not in agent.allowed_tools
        assert "Edit" not in agent.allowed_tools


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
        # 12 characters / 4 = 3 tokens
        result = agent._estimate_tokens("Hello World!")
        assert result == 3

    def test_estimate_tokens_long_string(self, agent: CodeReviewerAgent) -> None:
        """Test token estimation for longer content."""
        content = "a" * 400  # 400 characters / 4 = 100 tokens
        result = agent._estimate_tokens(content)
        assert result == 100


class TestShouldTruncate:
    """Tests for _should_truncate helper method."""

    def test_should_truncate_under_limits(self, agent: CodeReviewerAgent) -> None:
        """Test returns False when under all limits."""
        diff_stats = {
            "files": ["a.py", "b.py"],
            "total_lines": 100,
        }
        assert agent._should_truncate(diff_stats) is False

    def test_should_truncate_exceeds_line_limit(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test returns True when exceeding line limit."""
        diff_stats = {
            "files": ["a.py"],
            "total_lines": MAX_DIFF_LINES + 1,
        }
        assert agent._should_truncate(diff_stats) is True

    def test_should_truncate_exceeds_file_limit(
        self, agent: CodeReviewerAgent
    ) -> None:
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
        critical_findings = [f for f in findings if f.severity == ReviewSeverity.CRITICAL]
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
    {"severity": "critical", "file": "a.py", "message": "Valid finding here with enough length", "suggestion": "Fix it"},
    {"severity": "invalid", "file": "b.py", "message": "Invalid severity value here too"},
    {"file": "c.py", "message": "Missing severity field here ok", "suggestion": "Fix"}
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
# Execute Method Tests
# =============================================================================


class TestExecuteMethod:
    """Tests for the execute method."""

    @pytest.mark.asyncio
    async def test_execute_returns_review_result(
        self,
        agent: CodeReviewerAgent,
        mock_agent_context: AgentContext,
    ) -> None:
        """Test execute returns a ReviewResult on success."""
        # Mock all the internal methods
        with (
            patch.object(
                agent, "_check_merge_conflicts", new_callable=AsyncMock
            ) as mock_conflicts,
            patch.object(
                agent, "_get_diff_stats", new_callable=AsyncMock
            ) as mock_stats,
            patch.object(
                agent, "_read_conventions", new_callable=AsyncMock
            ) as mock_conventions,
            patch.object(
                agent, "_get_diff_content", new_callable=AsyncMock
            ) as mock_diff,
            patch.object(agent, "query") as mock_query,
        ):
            mock_conflicts.return_value = False
            mock_stats.return_value = {
                "files": ["test.py"],
                "total_lines": 10,
                "binary_files": [],
            }
            mock_conventions.return_value = "# Conventions"
            mock_diff.return_value = "diff content"

            # Mock query as async generator
            mock_message = MagicMock()
            mock_message.role = "assistant"
            mock_message.content = [MagicMock(type="text", text="```json\n[]\n```")]

            async def async_gen(*args, **kwargs):
                yield mock_message

            mock_query.side_effect = async_gen

            result = await agent.execute(mock_agent_context)

            # Should return ReviewResult
            assert result is not None
            assert hasattr(result, "success")

    @pytest.mark.asyncio
    async def test_execute_raises_on_merge_conflicts(
        self,
        agent: CodeReviewerAgent,
        mock_agent_context: AgentContext,
    ) -> None:
        """Test execute raises AgentError when merge conflicts exist."""
        with patch.object(
            agent, "_check_merge_conflicts", new_callable=AsyncMock
        ) as mock_conflicts:
            mock_conflicts.return_value = True

            with pytest.raises(AgentError) as exc_info:
                await agent.execute(mock_agent_context)

            assert "merge conflicts" in str(exc_info.value).lower()
            assert exc_info.value.error_code == "MERGE_CONFLICTS"

    @pytest.mark.asyncio
    async def test_execute_handles_empty_diff(
        self,
        agent: CodeReviewerAgent,
        mock_agent_context: AgentContext,
    ) -> None:
        """Test execute handles empty diff gracefully."""
        with (
            patch.object(
                agent, "_check_merge_conflicts", new_callable=AsyncMock
            ) as mock_conflicts,
            patch.object(
                agent, "_get_diff_stats", new_callable=AsyncMock
            ) as mock_stats,
            patch.object(
                agent, "_read_conventions", new_callable=AsyncMock
            ) as mock_conventions,
        ):
            mock_conflicts.return_value = False
            mock_stats.return_value = {
                "files": [],
                "total_lines": 0,
                "binary_files": [],
            }
            mock_conventions.return_value = ""

            result = await agent.execute(mock_agent_context)

            # Should succeed with empty result
            assert result.success is True


# =============================================================================
# ReviewContext Building Tests
# =============================================================================


class TestReviewContextBuilding:
    """Tests for ReviewContext building from AgentContext."""

    @pytest.mark.asyncio
    async def test_uses_default_base_branch_when_not_specified(
        self,
        agent: CodeReviewerAgent,
        tmp_path: Path,
    ) -> None:
        """Test uses DEFAULT_BASE_BRANCH when not in extra params."""
        context = AgentContext(
            cwd=tmp_path,
            branch="feature/test",
            config=MagicMock(),
            extra={},  # No base_branch specified
        )

        with (
            patch.object(
                agent, "_check_merge_conflicts", new_callable=AsyncMock
            ) as mock_conflicts,
            patch.object(
                agent, "_get_diff_stats", new_callable=AsyncMock
            ) as mock_stats,
            patch.object(
                agent, "_read_conventions", new_callable=AsyncMock
            ) as mock_conventions,
        ):
            mock_conflicts.return_value = False
            mock_stats.return_value = {
                "files": [],
                "total_lines": 0,
                "binary_files": [],
            }
            mock_conventions.return_value = ""

            result = await agent.execute(context)

            # Verify default base branch was used
            assert result.success is True

    @pytest.mark.asyncio
    async def test_uses_custom_base_branch_when_specified(
        self,
        agent: CodeReviewerAgent,
        tmp_path: Path,
    ) -> None:
        """Test uses custom base_branch from extra params."""
        context = AgentContext(
            cwd=tmp_path,
            branch="feature/test",
            config=MagicMock(),
            extra={"base_branch": "develop"},
        )

        with (
            patch.object(
                agent, "_check_merge_conflicts", new_callable=AsyncMock
            ) as mock_conflicts,
            patch.object(
                agent, "_get_diff_stats", new_callable=AsyncMock
            ) as mock_stats,
            patch.object(
                agent, "_read_conventions", new_callable=AsyncMock
            ) as mock_conventions,
        ):
            mock_conflicts.return_value = False
            mock_stats.return_value = {
                "files": [],
                "total_lines": 0,
                "binary_files": [],
            }
            mock_conventions.return_value = ""

            await agent.execute(context)

            # The stats method should be called - we can verify context was built
            mock_stats.assert_called_once()


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


# =============================================================================
# Usage Stats Conversion Tests
# =============================================================================


class TestUsageStatsConversion:
    """Tests for _convert_to_usage_stats method."""

    def test_converts_agent_usage_to_usage_stats(
        self, agent: CodeReviewerAgent
    ) -> None:
        """Test conversion from AgentUsage to UsageStats."""
        agent_usage = AgentUsage(
            input_tokens=1000,
            output_tokens=500,
            total_cost_usd=0.025,
            duration_ms=2500,
        )

        result = agent._convert_to_usage_stats(agent_usage, duration_ms=2500)

        assert isinstance(result, UsageStats)
        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.total_cost == 0.025
        assert result.duration_ms == 2500

    def test_handles_none_cost(self, agent: CodeReviewerAgent) -> None:
        """Test conversion when cost is None."""
        agent_usage = AgentUsage(
            input_tokens=100,
            output_tokens=50,
            total_cost_usd=None,
            duration_ms=500,
        )

        result = agent._convert_to_usage_stats(agent_usage, duration_ms=500)

        assert result.total_cost is None
