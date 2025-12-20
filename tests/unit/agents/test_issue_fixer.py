"""Unit tests for IssueFixerAgent.

Tests the issue fixer agent's functionality including:
- Initialization and configuration
- Issue fetching (from GitHub or pre-fetched data)
- Fix analysis and implementation
- Verification and validation
- Commit creation
- Error handling
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.agents.issue_fixer import (
    ISSUE_FIXER_SYSTEM_PROMPT,
    IssueFixerAgent,
)
from maverick.agents.tools import ISSUE_FIXER_TOOLS
from maverick.exceptions import AgentError, GitHubError
from maverick.models.implementation import (
    ChangeType,
    FileChange,
    ValidationResult,
    ValidationStep,
)
from maverick.models.issue_fix import FixResult, IssueFixerContext

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def agent() -> IssueFixerAgent:
    """Create an IssueFixerAgent instance for testing."""
    return IssueFixerAgent()


@pytest.fixture
def issue_context(tmp_path: Path) -> IssueFixerContext:
    """Create a basic IssueFixerContext for testing."""
    return IssueFixerContext(
        issue_number=42,
        cwd=tmp_path,
    )


@pytest.fixture
def issue_context_with_data(tmp_path: Path) -> IssueFixerContext:
    """Create an IssueFixerContext with pre-fetched issue data."""
    return IssueFixerContext(
        issue_data={
            "number": 42,
            "title": "Bug: NullPointerException in UserService",
            "body": "When calling getUserById with null, app crashes.",
            "url": "https://github.com/test/repo/issues/42",
            "labels": [{"name": "bug"}, {"name": "high-priority"}],
        },
        cwd=tmp_path,
    )


@pytest.fixture
def sample_issue_data() -> dict:
    """Sample issue data from GitHub API."""
    return {
        "number": 42,
        "title": "Bug: NullPointerException in UserService",
        "body": """## Description
When calling getUserById with null parameter, the application crashes with NullPointerException.

## Steps to Reproduce
1. Call `userService.getUserById(null)`
2. Observe crash

## Expected Behavior
Should return empty Optional or throw IllegalArgumentException.
""",
        "url": "https://github.com/test/repo/issues/42",
        "labels": [{"name": "bug"}, {"name": "high-priority"}],
        "state": "open",
    }


@pytest.fixture
def sample_file_changes() -> list[FileChange]:
    """Sample file changes for testing."""
    return [
        FileChange(
            file_path="src/services/user_service.py",
            change_type=ChangeType.MODIFIED,
            lines_added=5,
            lines_removed=2,
        ),
        FileChange(
            file_path="tests/test_user_service.py",
            change_type=ChangeType.MODIFIED,
            lines_added=10,
            lines_removed=0,
        ),
    ]


# =============================================================================
# Initialization Tests
# =============================================================================


class TestIssueFixerAgentInitialization:
    """Tests for IssueFixerAgent initialization."""

    def test_default_initialization(self, agent: IssueFixerAgent) -> None:
        """Test agent initializes with correct defaults."""
        assert agent.name == "issue-fixer"
        assert agent.system_prompt == ISSUE_FIXER_SYSTEM_PROMPT
        # Compare as sets since allowed_tools is a list and ISSUE_FIXER_TOOLS is a frozenset
        assert set(agent.allowed_tools) == set(ISSUE_FIXER_TOOLS)

    def test_custom_model(self) -> None:
        """Test agent accepts custom model parameter."""
        custom_agent = IssueFixerAgent(model="claude-3-opus-20240229")
        assert custom_agent.model == "claude-3-opus-20240229"

    def test_mcp_servers_passthrough(self) -> None:
        """Test MCP servers are passed through to base class."""
        mcp_config = {"server1": {"command": "test"}}
        agent = IssueFixerAgent(mcp_servers=mcp_config)
        assert agent.mcp_servers == mcp_config

    def test_system_prompt_emphasizes_minimal_changes(
        self, agent: IssueFixerAgent
    ) -> None:
        """Test system prompt emphasizes minimal, targeted fixes."""
        prompt = agent.system_prompt
        assert "minimal" in prompt.lower() or "MINIMUM" in prompt
        assert "root cause" in prompt.lower()
        assert "target <100 lines" in prompt or "100 lines" in prompt

    def test_system_prompt_includes_verification_steps(
        self, agent: IssueFixerAgent
    ) -> None:
        """Test system prompt includes verification requirements."""
        prompt = agent.system_prompt
        assert "verification" in prompt.lower() or "Verification" in prompt
        assert "test" in prompt.lower()

    def test_system_prompt_includes_commit_format(
        self, agent: IssueFixerAgent
    ) -> None:
        """Test system prompt specifies commit message format."""
        prompt = agent.system_prompt
        assert "fix(" in prompt.lower() or "Fixes #" in prompt
        assert "issue_number" in prompt.lower()


# =============================================================================
# Constants Tests
# =============================================================================


class TestIssueFixerConstants:
    """Tests for IssueFixerAgent constants."""

    def test_system_prompt_is_non_empty(self) -> None:
        """Test ISSUE_FIXER_SYSTEM_PROMPT is defined."""
        assert ISSUE_FIXER_SYSTEM_PROMPT
        assert len(ISSUE_FIXER_SYSTEM_PROMPT) > 100

    def test_allowed_tools_includes_essential_tools(self) -> None:
        """Test ISSUE_FIXER_TOOLS includes essential file tools (no Bash per US3)."""
        assert "Read" in ISSUE_FIXER_TOOLS
        assert "Write" in ISSUE_FIXER_TOOLS
        assert "Edit" in ISSUE_FIXER_TOOLS
        # Bash removed - orchestration layer handles command execution
        assert "Bash" not in ISSUE_FIXER_TOOLS

    def test_allowed_tools_includes_search_tools(self) -> None:
        """Test ISSUE_FIXER_TOOLS includes search tools."""
        assert "Glob" in ISSUE_FIXER_TOOLS
        assert "Grep" in ISSUE_FIXER_TOOLS

    def test_allowed_tools_count(self) -> None:
        """Test ISSUE_FIXER_TOOLS has expected number of tools."""
        assert len(ISSUE_FIXER_TOOLS) == 5  # Without Bash

    def test_allowed_tools_matches_contract(self) -> None:
        """Test ISSUE_FIXER_TOOLS matches US3 contract exactly.

        US3 Contract: IssueFixerAgent must have exactly Read, Write, Edit, Glob, Grep.
        Same as ImplementerAgent - full code manipulation for targeted bug fixes.
        Bash removed - orchestration layer handles command execution.
        """
        expected_tools = {"Read", "Write", "Edit", "Glob", "Grep"}
        actual_tools = set(ISSUE_FIXER_TOOLS)
        assert actual_tools == expected_tools, (
            f"IssueFixerAgent tools mismatch. Expected: {expected_tools}, Got: {actual_tools}"
        )

    def test_allowed_tools_uses_centralized_constants(
        self, agent: IssueFixerAgent
    ) -> None:
        """Test allowed tools uses ISSUE_FIXER_TOOLS from maverick.agents.tools.

        T012: Verify that IssueFixerAgent uses the centralized ISSUE_FIXER_TOOLS
        constant from tools.py, not local definition. This enforces the orchestration
        pattern where tool permissions are centrally managed.
        """
        from maverick.agents.tools import ISSUE_FIXER_TOOLS as CENTRALIZED_TOOLS

        # Agent's allowed_tools should match the centralized constant
        expected_tools = set(CENTRALIZED_TOOLS)
        actual_tools = set(agent.allowed_tools)

        assert actual_tools == expected_tools, (
            f"IssueFixerAgent must use centralized ISSUE_FIXER_TOOLS. "
            f"Expected: {expected_tools}, Got: {actual_tools}"
        )

        # Ensure Bash is NOT in the centralized tools (per US1 contract)
        assert "Bash" not in CENTRALIZED_TOOLS, (
            "Bash should be removed from ISSUE_FIXER_TOOLS per US1"
        )


# =============================================================================
# Execute Method Tests
# =============================================================================


class TestExecuteMethod:
    """Tests for the execute method."""

    @pytest.mark.asyncio
    async def test_execute_returns_fix_result(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test execute returns a FixResult on success."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock
            ) as mock_validate,
            patch.object(
                agent, "_create_commit", new_callable=AsyncMock
            ) as mock_commit,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.return_value = ("output", "root cause", "fix description")
            mock_detect.return_value = []
            mock_verify.return_value = True
            mock_validate.return_value = [
                ValidationResult(
                    step=ValidationStep.TEST,
                    success=True,
                    output="All tests passed",
                )
            ]
            mock_commit.return_value = "abc123"

            result = await agent.execute(issue_context)

            assert isinstance(result, FixResult)
            assert result.success is True
            assert result.issue_number == 42
            assert result.issue_title == "Bug: NullPointerException in UserService"

    @pytest.mark.asyncio
    async def test_execute_handles_issue_number_context(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test execute fetches issue when given issue_number."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.return_value = ("output", "cause", "fix")
            mock_detect.return_value = []
            mock_verify.return_value = True

            result = await agent.execute(issue_context)

            # Should have called _fetch_issue with context
            mock_fetch.assert_called_once_with(issue_context)
            assert result.issue_number == 42

    @pytest.mark.asyncio
    async def test_execute_handles_prefetched_issue_data(
        self,
        agent: IssueFixerAgent,
        issue_context_with_data: IssueFixerContext,
    ) -> None:
        """Test execute uses pre-fetched issue_data when provided."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
        ):
            mock_fetch.return_value = issue_context_with_data.issue_data
            mock_analyze.return_value = ("output", "cause", "fix")
            mock_detect.return_value = []
            mock_verify.return_value = True

            result = await agent.execute(issue_context_with_data)

            # Should still call _fetch_issue (which returns the pre-fetched data)
            mock_fetch.assert_called_once()
            assert result.issue_number == 42

    @pytest.mark.asyncio
    async def test_execute_handles_dry_run_mode(
        self,
        agent: IssueFixerAgent,
        tmp_path: Path,
        sample_issue_data: dict,
    ) -> None:
        """Test execute respects dry_run flag and doesn't commit."""
        context = IssueFixerContext(
            issue_number=42,
            cwd=tmp_path,
            dry_run=True,
        )

        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
            patch.object(
                agent, "_create_commit", new_callable=AsyncMock
            ) as mock_commit,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.return_value = ("output", "cause", "fix")
            mock_detect.return_value = [
                FileChange(
                    file_path="test.py",
                    change_type=ChangeType.MODIFIED,
                    lines_added=1,
                    lines_removed=1,
                )
            ]
            mock_verify.return_value = True

            result = await agent.execute(context)

            # Should NOT create commit in dry_run mode
            mock_commit.assert_not_called()
            assert result.commit_sha is None
            assert result.metadata["dry_run"] is True

    @pytest.mark.asyncio
    async def test_execute_handles_skip_validation_mode(
        self,
        agent: IssueFixerAgent,
        tmp_path: Path,
        sample_issue_data: dict,
    ) -> None:
        """Test execute skips validation when skip_validation is True."""
        context = IssueFixerContext(
            issue_number=42,
            cwd=tmp_path,
            skip_validation=True,
        )

        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock
            ) as mock_validate,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.return_value = ("output", "cause", "fix")
            mock_detect.return_value = []
            mock_verify.return_value = True

            result = await agent.execute(context)

            # Should NOT run validation
            mock_validate.assert_not_called()
            assert result.validation_passed is True

    @pytest.mark.asyncio
    async def test_execute_includes_duration_metadata(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test execute includes duration in metadata."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.return_value = ("output", "cause", "fix")
            mock_detect.return_value = []
            mock_verify.return_value = True

            result = await agent.execute(issue_context)

            assert "duration_ms" in result.metadata
            assert isinstance(result.metadata["duration_ms"], int)
            assert result.metadata["duration_ms"] >= 0


# =============================================================================
# Fetch Issue Tests
# =============================================================================


class TestFetchIssue:
    """Tests for _fetch_issue helper method."""

    @pytest.mark.asyncio
    async def test_fetch_issue_from_github(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test _fetch_issue fetches from GitHub when issue_number provided."""
        with patch(
            "maverick.utils.github.fetch_issue", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = sample_issue_data

            result = await agent._fetch_issue(issue_context)

            mock_fetch.assert_called_once_with(42, issue_context.cwd)
            assert result == sample_issue_data

    @pytest.mark.asyncio
    async def test_fetch_issue_uses_prefetched_data(
        self,
        agent: IssueFixerAgent,
        issue_context_with_data: IssueFixerContext,
    ) -> None:
        """Test _fetch_issue returns pre-fetched data when available."""
        with patch(
            "maverick.utils.github.fetch_issue", new_callable=AsyncMock
        ) as mock_fetch:
            result = await agent._fetch_issue(issue_context_with_data)

            # Should NOT call GitHub fetch
            mock_fetch.assert_not_called()
            assert result == issue_context_with_data.issue_data

    @pytest.mark.asyncio
    async def test_fetch_issue_raises_github_error_on_failure(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
    ) -> None:
        """Test _fetch_issue raises GitHubError on fetch failure."""
        with patch(
            "maverick.utils.github.fetch_issue", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.side_effect = GitHubError("Issue not found")

            with pytest.raises(GitHubError):
                await agent._fetch_issue(issue_context)


# =============================================================================
# Analyze and Fix Tests
# =============================================================================


class TestAnalyzeAndFix:
    """Tests for _analyze_and_fix helper method."""

    @pytest.mark.asyncio
    async def test_analyze_and_fix_returns_tuple(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test _analyze_and_fix returns (output, root_cause, fix_description)."""
        with patch.object(agent, "query") as mock_query:
            # Mock query as async generator with proper type name for extract_all_text
            mock_text_block = MagicMock()
            mock_text_block.text = "Fixed the null pointer issue"
            type(mock_text_block).__name__ = "TextBlock"

            mock_message = MagicMock()
            mock_message.content = [mock_text_block]
            type(mock_message).__name__ = "AssistantMessage"

            async def async_gen(*args, **kwargs):
                yield mock_message

            mock_query.side_effect = async_gen

            output, root_cause, fix_description = await agent._analyze_and_fix(
                sample_issue_data, issue_context
            )

            assert isinstance(output, str)
            assert isinstance(root_cause, str)
            assert isinstance(fix_description, str)
            assert len(output) > 0

    @pytest.mark.asyncio
    async def test_analyze_and_fix_builds_proper_prompt(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test _analyze_and_fix builds prompt with issue details."""
        with (
            patch.object(agent, "_build_fix_prompt") as mock_build_prompt,
            patch.object(agent, "query") as mock_query,
        ):
            mock_build_prompt.return_value = "test prompt"

            async def async_gen(*args, **kwargs):
                yield MagicMock(
                    role="assistant",
                    content=[MagicMock(type="text", text="output")],
                )

            mock_query.side_effect = async_gen

            await agent._analyze_and_fix(sample_issue_data, issue_context)

            mock_build_prompt.assert_called_once_with(sample_issue_data)

    def test_build_fix_prompt_includes_issue_details(
        self, agent: IssueFixerAgent, sample_issue_data: dict
    ) -> None:
        """Test _build_fix_prompt includes issue number, title, and body."""
        prompt = agent._build_fix_prompt(sample_issue_data)

        assert "42" in prompt
        assert "NullPointerException" in prompt
        assert "getUserById" in prompt or "Description" in prompt

    def test_build_fix_prompt_includes_labels(
        self, agent: IssueFixerAgent, sample_issue_data: dict
    ) -> None:
        """Test _build_fix_prompt includes issue labels."""
        prompt = agent._build_fix_prompt(sample_issue_data)

        assert "bug" in prompt or "high-priority" in prompt

    def test_build_fix_prompt_handles_empty_labels(
        self, agent: IssueFixerAgent
    ) -> None:
        """Test _build_fix_prompt handles issues without labels."""
        issue_data = {
            "number": 1,
            "title": "Test",
            "body": "Test body",
            "labels": [],
        }

        prompt = agent._build_fix_prompt(issue_data)

        assert "None" in prompt or "Labels" in prompt


# =============================================================================
# Verify Fix Tests
# =============================================================================


class TestVerifyFix:
    """Tests for _verify_fix helper method."""

    @pytest.mark.asyncio
    async def test_verify_fix_runs_tests(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test _verify_fix runs validation tests."""
        with patch(
            "maverick.utils.validation.run_validation_step", new_callable=AsyncMock
        ) as mock_run_step:
            mock_run_step.return_value = ValidationResult(
                step=ValidationStep.TEST,
                success=True,
                output="Tests passed",
            )

            result = await agent._verify_fix(sample_issue_data, issue_context)

            mock_run_step.assert_called_once_with(
                ValidationStep.TEST, issue_context.cwd
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_verify_fix_returns_false_on_failure(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test _verify_fix returns False when tests fail."""
        with patch(
            "maverick.utils.validation.run_validation_step", new_callable=AsyncMock
        ) as mock_run_step:
            mock_run_step.return_value = ValidationResult(
                step=ValidationStep.TEST,
                success=False,
                output="Tests failed",
            )

            result = await agent._verify_fix(sample_issue_data, issue_context)

            assert result is False

    @pytest.mark.asyncio
    async def test_verify_fix_handles_exceptions(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test _verify_fix handles exceptions gracefully."""
        with patch(
            "maverick.utils.validation.run_validation_step", new_callable=AsyncMock
        ) as mock_run_step:
            mock_run_step.side_effect = Exception("Validation error")

            result = await agent._verify_fix(sample_issue_data, issue_context)

            assert result is False


# =============================================================================
# Detect File Changes Tests
# =============================================================================


class TestDetectFileChanges:
    """Tests for _detect_file_changes helper method."""

    @pytest.mark.asyncio
    async def test_detect_file_changes_returns_file_changes(
        self, agent: IssueFixerAgent, tmp_path: Path
    ) -> None:
        """Test _detect_file_changes returns FileChange list."""
        with patch(
            "maverick.utils.git.get_diff_stats", new_callable=AsyncMock
        ) as mock_diff:
            mock_diff.return_value = {
                "src/file.py": (10, 5),
                "tests/test_file.py": (5, 0),
            }

            result = await agent._detect_file_changes(tmp_path)

            assert len(result) == 2
            assert all(isinstance(fc, FileChange) for fc in result)
            assert result[0].file_path == "src/file.py"
            assert result[0].lines_added == 10
            assert result[0].lines_removed == 5

    @pytest.mark.asyncio
    async def test_detect_file_changes_handles_no_changes(
        self, agent: IssueFixerAgent, tmp_path: Path
    ) -> None:
        """Test _detect_file_changes handles empty diff stats."""
        with patch(
            "maverick.utils.git.get_diff_stats", new_callable=AsyncMock
        ) as mock_diff:
            mock_diff.return_value = {}

            result = await agent._detect_file_changes(tmp_path)

            assert result == []

    @pytest.mark.asyncio
    async def test_detect_file_changes_handles_exceptions(
        self, agent: IssueFixerAgent, tmp_path: Path
    ) -> None:
        """Test _detect_file_changes handles exceptions gracefully."""
        with patch(
            "maverick.utils.git.get_diff_stats", new_callable=AsyncMock
        ) as mock_diff:
            mock_diff.side_effect = Exception("Git error")

            result = await agent._detect_file_changes(tmp_path)

            assert result == []


# =============================================================================
# Validation Tests
# =============================================================================


class TestRunValidation:
    """Tests for _run_validation helper method."""

    @pytest.mark.asyncio
    async def test_run_validation_returns_results(
        self, agent: IssueFixerAgent, tmp_path: Path
    ) -> None:
        """Test _run_validation returns list of ValidationResult."""
        with patch(
            "maverick.utils.validation.run_validation_pipeline",
            new_callable=AsyncMock,
        ) as mock_pipeline:
            mock_pipeline.return_value = [
                ValidationResult(
                    step=ValidationStep.FORMAT,
                    success=True,
                    output="Formatted",
                ),
                ValidationResult(
                    step=ValidationStep.LINT,
                    success=True,
                    output="Linted",
                ),
            ]

            result = await agent._run_validation(tmp_path)

            mock_pipeline.assert_called_once_with(tmp_path)
            assert len(result) == 2
            assert all(isinstance(r, ValidationResult) for r in result)

    @pytest.mark.asyncio
    async def test_run_validation_handles_exceptions(
        self, agent: IssueFixerAgent, tmp_path: Path
    ) -> None:
        """Test _run_validation handles exceptions gracefully."""
        with patch(
            "maverick.utils.validation.run_validation_pipeline",
            new_callable=AsyncMock,
        ) as mock_pipeline:
            mock_pipeline.side_effect = Exception("Validation error")

            result = await agent._run_validation(tmp_path)

            assert result == []


# =============================================================================
# Create Commit Tests
# =============================================================================


class TestCreateCommit:
    """Tests for _create_commit helper method."""

    @pytest.mark.asyncio
    async def test_create_commit_creates_conventional_commit(
        self, agent: IssueFixerAgent, issue_context: IssueFixerContext
    ) -> None:
        """Test _create_commit creates commit with conventional format."""
        with (
            patch(
                "maverick.utils.git.has_uncommitted_changes",
                new_callable=AsyncMock,
            ) as mock_has_changes,
            patch(
                "maverick.utils.git.create_commit", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_has_changes.return_value = True
            mock_create.return_value = "abc123def456"

            result = await agent._create_commit(
                42, "resolve null pointer issue", issue_context
            )

            assert result == "abc123def456"
            # Check commit message format
            call_args = mock_create.call_args[0]
            commit_message = call_args[0]
            assert "fix:" in commit_message
            assert "Fixes #42" in commit_message

    @pytest.mark.asyncio
    async def test_create_commit_includes_issue_number(
        self, agent: IssueFixerAgent, issue_context: IssueFixerContext
    ) -> None:
        """Test _create_commit includes 'Fixes #N' in commit body."""
        with (
            patch(
                "maverick.utils.git.has_uncommitted_changes",
                new_callable=AsyncMock,
            ) as mock_has_changes,
            patch(
                "maverick.utils.git.create_commit", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_has_changes.return_value = True
            mock_create.return_value = "abc123"

            await agent._create_commit(123, "fix description", issue_context)

            call_args = mock_create.call_args[0]
            commit_message = call_args[0]
            assert "Fixes #123" in commit_message

    @pytest.mark.asyncio
    async def test_create_commit_returns_none_without_changes(
        self, agent: IssueFixerAgent, issue_context: IssueFixerContext
    ) -> None:
        """Test _create_commit returns None when no uncommitted changes."""
        with (
            patch(
                "maverick.utils.git.has_uncommitted_changes",
                new_callable=AsyncMock,
            ) as mock_has_changes,
            patch(
                "maverick.utils.git.create_commit", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_has_changes.return_value = False

            result = await agent._create_commit(42, "fix", issue_context)

            assert result is None
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_commit_truncates_long_descriptions(
        self, agent: IssueFixerAgent, issue_context: IssueFixerContext
    ) -> None:
        """Test _create_commit truncates long fix descriptions."""
        with (
            patch(
                "maverick.utils.git.has_uncommitted_changes",
                new_callable=AsyncMock,
            ) as mock_has_changes,
            patch(
                "maverick.utils.git.create_commit", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_has_changes.return_value = True
            mock_create.return_value = "abc123"
            long_description = "a" * 100

            await agent._create_commit(42, long_description, issue_context)

            call_args = mock_create.call_args[0]
            commit_message = call_args[0]
            # First line should be truncated to 50 chars + "fix: "
            first_line = commit_message.split("\n")[0]
            assert len(first_line) <= 60  # "fix: " + 50 chars + some buffer

    @pytest.mark.asyncio
    async def test_create_commit_handles_exceptions(
        self, agent: IssueFixerAgent, issue_context: IssueFixerContext
    ) -> None:
        """Test _create_commit handles exceptions gracefully."""
        with (
            patch(
                "maverick.utils.git.has_uncommitted_changes",
                new_callable=AsyncMock,
            ) as mock_has_changes,
            patch(
                "maverick.utils.git.create_commit", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_has_changes.return_value = True
            mock_create.side_effect = Exception("Git error")

            result = await agent._create_commit(42, "fix", issue_context)

            assert result is None


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in IssueFixerAgent."""

    @pytest.mark.asyncio
    async def test_execute_raises_github_error_on_fetch_failure(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
    ) -> None:
        """Test execute raises GitHubError when issue fetch fails."""
        with patch.object(
            agent, "_fetch_issue", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.side_effect = GitHubError("Issue #42 not found")

            with pytest.raises(GitHubError) as exc_info:
                await agent.execute(issue_context)

            assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_execute_returns_failed_result_on_agent_error(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test execute returns failed FixResult on AgentError."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.side_effect = AgentError("Analysis failed")

            result = await agent.execute(issue_context)

            assert isinstance(result, FixResult)
            assert result.success is False
            assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_execute_returns_failed_result_on_general_exception(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test execute returns failed FixResult on unexpected exceptions."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.side_effect = RuntimeError("Unexpected error")

            result = await agent.execute(issue_context)

            assert isinstance(result, FixResult)
            assert result.success is False
            assert result.issue_number == 42
            assert any("Unexpected error" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_execute_returns_partial_results_on_verification_failure(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
        sample_file_changes: list[FileChange],
    ) -> None:
        """Test execute returns partial FixResult when verification fails."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.return_value = ("output", "cause", "fix")
            mock_detect.return_value = sample_file_changes
            mock_verify.return_value = False

            result = await agent.execute(issue_context)

            # Should have partial results
            assert result.success is False
            assert result.verification_passed is False
            assert len(result.files_changed) > 0
            assert result.root_cause == "cause"
            assert result.fix_description == "fix"

    @pytest.mark.asyncio
    async def test_execute_returns_partial_results_on_validation_failure(
        self,
        agent: IssueFixerAgent,
        issue_context: IssueFixerContext,
        sample_issue_data: dict,
    ) -> None:
        """Test execute returns partial FixResult when validation fails."""
        with (
            patch.object(
                agent, "_fetch_issue", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                agent, "_analyze_and_fix", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock
            ) as mock_detect,
            patch.object(
                agent, "_verify_fix", new_callable=AsyncMock
            ) as mock_verify,
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock
            ) as mock_validate,
        ):
            mock_fetch.return_value = sample_issue_data
            mock_analyze.return_value = ("output", "cause", "fix")
            mock_detect.return_value = []
            mock_verify.return_value = True
            mock_validate.return_value = [
                ValidationResult(
                    step=ValidationStep.LINT,
                    success=False,
                    output="Lint errors",
                )
            ]

            result = await agent.execute(issue_context)

            assert result.success is False
            assert result.verification_passed is True
            assert result.validation_passed is False
