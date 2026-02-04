"""Unit tests for ImplementerAgent.

Tests the implementer agent's functionality including:
- Initialization and configuration
- Single task execution
- Task file parsing and execution
- Parallel task batch handling
- Helper methods (prompt building, file change detection, validation, commits)
- Error handling for parse errors and execution failures
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.agents.implementer import (
    IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE,
    ImplementerAgent,
)
from maverick.agents.tools import IMPLEMENTER_TOOLS
from maverick.exceptions import AgentError, TaskParseError
from maverick.models.implementation import (
    ChangeType,
    FileChange,
    ImplementationResult,
    ImplementerContext,
    Task,
    TaskResult,
    TaskStatus,
    ValidationResult,
    ValidationStep,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def agent() -> ImplementerAgent:
    """Create an ImplementerAgent instance for testing."""
    return ImplementerAgent()


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task for testing."""
    return Task(
        id="T001",
        description="Implement authentication module",
        status=TaskStatus.PENDING,
        parallel=False,
    )


@pytest.fixture
def sample_parallel_task() -> Task:
    """Create a sample parallel task for testing."""
    return Task(
        id="T002",
        description="Create unit tests",
        status=TaskStatus.PENDING,
        parallel=True,
    )


@pytest.fixture
def sample_task_with_dependencies() -> Task:
    """Create a sample task with dependencies."""
    return Task(
        id="T003",
        description="Integrate with API",
        status=TaskStatus.PENDING,
        parallel=False,
        dependencies=["T001"],
    )


@pytest.fixture
def single_task_context(tmp_path: Path) -> ImplementerContext:
    """Create context for single task execution."""
    return ImplementerContext(
        task_description="Create a new authentication module",
        branch="feature/auth",
        cwd=tmp_path,
        dry_run=True,
    )


@pytest.fixture
def task_file_context(tmp_path: Path) -> ImplementerContext:
    """Create context for task file execution."""
    task_file = tmp_path / "tasks.md"
    task_file.write_text("""## Phase 1
- [ ] T001 Create authentication module
- [ ] T002 [P] Add unit tests
- [ ] T003 [P] Add integration tests
""")
    return ImplementerContext(
        task_file=task_file,
        branch="feature/impl",
        cwd=tmp_path,
    )


@pytest.fixture
def mock_file_changes() -> list[FileChange]:
    """Create sample file changes."""
    return [
        FileChange(
            file_path="src/auth.py",
            change_type=ChangeType.ADDED,
            lines_added=150,
            lines_removed=0,
        ),
        FileChange(
            file_path="tests/test_auth.py",
            change_type=ChangeType.ADDED,
            lines_added=80,
            lines_removed=0,
        ),
    ]


@pytest.fixture
def mock_validation_results() -> list[ValidationResult]:
    """Create sample validation results."""
    return [
        ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
            output="",
            duration_ms=500,
            auto_fixed=True,
        ),
        ValidationResult(
            step=ValidationStep.LINT,
            success=True,
            output="All checks passed",
            duration_ms=800,
        ),
        ValidationResult(
            step=ValidationStep.TEST,
            success=True,
            output="10 tests passed",
            duration_ms=2000,
        ),
    ]


# =============================================================================
# Initialization Tests
# =============================================================================


class TestImplementerAgentInitialization:
    """Tests for ImplementerAgent initialization."""

    def test_default_initialization(self, agent: ImplementerAgent) -> None:
        """Test agent initializes with correct defaults."""
        assert agent.name == "implementer"
        # System prompt is rendered with skill guidance, so check key content
        assert "expert software engineer" in agent.system_prompt.lower()
        assert "test-driven" in agent.system_prompt.lower()
        # Compare as sets since allowed_tools is a list and
        # IMPLEMENTER_TOOLS is a frozenset
        assert set(agent.allowed_tools) == set(IMPLEMENTER_TOOLS)

    def test_custom_model(self) -> None:
        """Test agent accepts custom model parameter."""
        custom_agent = ImplementerAgent(model="claude-3-opus-20240229")
        assert custom_agent.model == "claude-3-opus-20240229"

    def test_system_prompt_contains_tdd_approach(self, agent: ImplementerAgent) -> None:
        """Test system prompt includes TDD methodology."""
        prompt = agent.system_prompt
        assert "TDD" in prompt or "test-driven" in prompt.lower()
        assert "test" in prompt.lower()

    def test_system_prompt_contains_conventional_commits(
        self, agent: ImplementerAgent
    ) -> None:
        """Test system prompt includes conventional commit format."""
        prompt = agent.system_prompt
        assert "conventional" in prompt.lower()
        assert "feat" in prompt.lower() or "fix" in prompt.lower()

    def test_system_prompt_mentions_orchestration(
        self, agent: ImplementerAgent
    ) -> None:
        """Test system prompt mentions orchestration layer (T024).

        Agent should understand it operates within an orchestration context
        and should not attempt to execute validation itself.
        """
        prompt = agent.system_prompt
        assert "orchestration" in prompt.lower() or "orchestrated" in prompt.lower()

    def test_allowed_tools_includes_required_tools(
        self, agent: ImplementerAgent
    ) -> None:
        """Test allowed tools includes all required tools."""
        assert "Read" in agent.allowed_tools
        assert "Write" in agent.allowed_tools
        assert "Edit" in agent.allowed_tools
        # Bash removed per US3 - agents don't execute commands, orchestration does
        assert "Glob" in agent.allowed_tools
        assert "Grep" in agent.allowed_tools

    def test_allowed_tools_matches_contract(self, agent: ImplementerAgent) -> None:
        """Test allowed tools matches contract exactly.

        ImplementerAgent has Read, Write, Edit, Glob, Grep, and Task
        (for subagent-based parallel task execution within phases).
        Bash removed - orchestration layer handles command execution.
        """
        expected_tools = {"Read", "Write", "Edit", "Glob", "Grep", "Task"}
        actual_tools = set(agent.allowed_tools)
        assert actual_tools == expected_tools, (
            f"ImplementerAgent tools mismatch. "
            f"Expected: {expected_tools}, Got: {actual_tools}"
        )

    def test_allowed_tools_uses_centralized_constants(
        self, agent: ImplementerAgent
    ) -> None:
        """Test allowed tools uses IMPLEMENTER_TOOLS from maverick.agents.tools.

        T010: Verify that ImplementerAgent uses the centralized IMPLEMENTER_TOOLS
        constant from tools.py, not local definition. This enforces the orchestration
        pattern where tool permissions are centrally managed.
        """
        from maverick.agents.tools import IMPLEMENTER_TOOLS as CENTRALIZED_TOOLS

        # Agent's allowed_tools should match the centralized constant
        expected_tools = set(CENTRALIZED_TOOLS)
        actual_tools = set(agent.allowed_tools)

        assert actual_tools == expected_tools, (
            f"ImplementerAgent must use centralized IMPLEMENTER_TOOLS. "
            f"Expected: {expected_tools}, Got: {actual_tools}"
        )

        # Ensure Bash is NOT in the centralized tools (per US1 contract)
        assert "Bash" not in CENTRALIZED_TOOLS, (
            "Bash should be removed from IMPLEMENTER_TOOLS per US1"
        )


# =============================================================================
# Constants Tests
# =============================================================================


class TestImplementerConstants:
    """Tests for ImplementerAgent constants."""

    def test_implementer_system_prompt_template_is_string(self) -> None:
        """Test IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE is defined and non-empty."""
        assert isinstance(IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE, str)
        assert len(IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE) > 100
        # Template should contain skill_guidance placeholder
        assert "$skill_guidance" in IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE

    def test_implementer_tools_is_frozenset(self) -> None:
        """Test IMPLEMENTER_TOOLS is a frozenset of strings (centralized, immutable)."""
        assert isinstance(IMPLEMENTER_TOOLS, frozenset)
        assert all(isinstance(tool, str) for tool in IMPLEMENTER_TOOLS)
        assert len(IMPLEMENTER_TOOLS) >= 5  # Without Bash

    def test_implementer_tools_contains_core_tools(self) -> None:
        """Test IMPLEMENTER_TOOLS contains core development tools (no Bash per US3)."""
        assert "Read" in IMPLEMENTER_TOOLS
        assert "Write" in IMPLEMENTER_TOOLS
        assert "Edit" in IMPLEMENTER_TOOLS
        # Bash removed - orchestration layer handles command execution
        assert "Bash" not in IMPLEMENTER_TOOLS


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestBuildTaskPrompt:
    """Tests for _build_task_prompt helper method."""

    def test_build_task_prompt_includes_task_id(
        self, agent: ImplementerAgent, sample_task: Task
    ) -> None:
        """Test prompt includes task ID."""
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/test",
        )
        prompt = agent._build_task_prompt(sample_task, context)
        assert sample_task.id in prompt

    def test_build_task_prompt_includes_description(
        self, agent: ImplementerAgent, sample_task: Task
    ) -> None:
        """Test prompt includes task description."""
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/test",
        )
        prompt = agent._build_task_prompt(sample_task, context)
        assert sample_task.description in prompt

    def test_build_task_prompt_includes_branch(
        self, agent: ImplementerAgent, sample_task: Task
    ) -> None:
        """Test prompt includes branch information."""
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/custom-branch",
        )
        prompt = agent._build_task_prompt(sample_task, context)
        assert "feature/custom-branch" in prompt

    def test_build_task_prompt_includes_tdd_instructions(
        self, agent: ImplementerAgent, sample_task: Task
    ) -> None:
        """Test prompt includes TDD approach instructions."""
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/test",
        )
        prompt = agent._build_task_prompt(sample_task, context)
        assert "TDD" in prompt or "test" in prompt.lower()


# NOTE: Tests for _detect_file_changes, _run_validation, and _create_commit
# have been moved to tests/unit/agents/test_utils.py as these are now
# shared utility functions in maverick.agents.utils (issue #147)


class TestGetParallelBatch:
    """Tests for _get_parallel_batch helper method."""

    def test_get_parallel_batch_returns_empty_for_sequential_task(
        self, agent: ImplementerAgent, sample_task: Task
    ) -> None:
        """Test returns empty list when first task is not parallel."""
        tasks = [sample_task]
        batch = agent._get_parallel_batch(tasks)
        assert batch == []

    def test_get_parallel_batch_returns_parallel_tasks(
        self, agent: ImplementerAgent
    ) -> None:
        """Test returns consecutive parallel tasks."""
        tasks = [
            Task(id="T001", description="Test 1", parallel=True),
            Task(id="T002", description="Test 2", parallel=True),
            Task(id="T003", description="Test 3", parallel=True),
        ]
        batch = agent._get_parallel_batch(tasks)
        assert len(batch) == 3
        assert all(t.parallel for t in batch)

    def test_get_parallel_batch_stops_at_non_parallel(
        self, agent: ImplementerAgent
    ) -> None:
        """Test stops collecting at first non-parallel task."""
        tasks = [
            Task(id="T001", description="Test 1", parallel=True),
            Task(id="T002", description="Test 2", parallel=True),
            Task(id="T003", description="Test 3", parallel=False),
            Task(id="T004", description="Test 4", parallel=True),
        ]
        batch = agent._get_parallel_batch(tasks)
        assert len(batch) == 2
        assert batch[0].id == "T001"
        assert batch[1].id == "T002"

    def test_get_parallel_batch_excludes_tasks_with_dependencies(
        self, agent: ImplementerAgent
    ) -> None:
        """Test excludes parallel tasks that have dependencies."""
        tasks = [
            Task(id="T001", description="Test 1", parallel=True, dependencies=["T000"]),
        ]
        batch = agent._get_parallel_batch(tasks)
        assert batch == []

    def test_get_parallel_batch_empty_list(self, agent: ImplementerAgent) -> None:
        """Test handles empty task list."""
        batch = agent._get_parallel_batch([])
        assert batch == []


class TestExecuteParallelBatch:
    """Tests for _execute_parallel_batch helper method."""

    @pytest.mark.asyncio
    async def test_execute_parallel_batch_runs_concurrently(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test executes multiple tasks concurrently."""
        tasks = [
            Task(id="T001", description="Test 1", parallel=True),
            Task(id="T002", description="Test 2", parallel=True),
        ]
        context = ImplementerContext(
            task_description="Parallel task batch execution test",
            branch="test",
            cwd=tmp_path,
            dry_run=True,
        )

        with patch.object(
            agent, "_execute_single_task", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = TaskResult(
                task_id="T001",
                status=TaskStatus.COMPLETED,
            )

            results = await agent._execute_parallel_batch(tasks, context)

            assert len(results) == 2
            assert mock_execute.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_parallel_batch_handles_exceptions(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test handles exceptions from individual tasks."""
        tasks = [
            Task(id="T001", description="Test 1", parallel=True),
            Task(id="T002", description="Test 2", parallel=True),
        ]
        context = ImplementerContext(
            task_description="Parallel task batch execution test",
            branch="test",
            cwd=tmp_path,
            dry_run=True,
        )

        with patch.object(
            agent, "_execute_single_task", new_callable=AsyncMock
        ) as mock_execute:
            # First task succeeds, second raises exception
            mock_execute.side_effect = [
                TaskResult(task_id="T001", status=TaskStatus.COMPLETED),
                Exception("Task execution failed"),
            ]

            results = await agent._execute_parallel_batch(tasks, context)

            assert len(results) == 2
            assert results[0].status == TaskStatus.COMPLETED
            assert results[1].status == TaskStatus.FAILED
            assert "Task execution failed" in (results[1].error or "")

    @pytest.mark.asyncio
    async def test_execute_parallel_batch_returns_results_in_order(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test returns results in same order as input tasks."""
        tasks = [
            Task(id=f"T{i:03d}", description=f"Test {i}", parallel=True)
            for i in range(1, 6)
        ]
        context = ImplementerContext(
            task_description="Parallel task batch execution test",
            branch="test",
            cwd=tmp_path,
            dry_run=True,
        )

        with patch.object(
            agent, "_execute_single_task", new_callable=AsyncMock
        ) as mock_execute:
            # Return results with task_id
            def create_result(task, ctx):
                return TaskResult(task_id=task.id, status=TaskStatus.COMPLETED)

            mock_execute.side_effect = create_result

            results = await agent._execute_parallel_batch(tasks, context)

            assert len(results) == 5
            for i, result in enumerate(results, start=1):
                assert result.task_id == f"T{i:03d}"


# =============================================================================
# Execute Method Tests
# =============================================================================


class TestExecuteMethod:
    """Tests for the execute method."""

    @pytest.mark.asyncio
    async def test_execute_returns_implementation_result(
        self, agent: ImplementerAgent, single_task_context: ImplementerContext
    ) -> None:
        """Test execute returns ImplementationResult on success."""
        # Mock the Claude query
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Task completed")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(single_task_context)

            assert isinstance(result, ImplementationResult)
            assert result.success is True
            assert result.tasks_completed == 1

    @pytest.mark.asyncio
    async def test_execute_handles_single_task_description(
        self, agent: ImplementerAgent, single_task_context: ImplementerContext
    ) -> None:
        """Test execute handles single task description correctly."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(single_task_context)

            assert result.tasks_completed == 1
            assert len(result.task_results) == 1
            assert result.task_results[0].task_id == "T000"

    @pytest.mark.asyncio
    async def test_execute_handles_task_file(
        self, agent: ImplementerAgent, task_file_context: ImplementerContext
    ) -> None:
        """Test execute parses and executes tasks from file."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(task_file_context)

            assert result.success is True
            # Should have executed 3 tasks
            assert result.tasks_completed == 3

    @pytest.mark.asyncio
    async def test_execute_raises_on_missing_task_file(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test execute raises TaskParseError when task file not found."""
        context = ImplementerContext(
            task_file=tmp_path / "nonexistent.md",
            branch="test",
        )

        with pytest.raises(TaskParseError) as exc_info:
            await agent.execute(context)

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_execute_handles_parallel_tasks(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test execute identifies and runs parallel tasks concurrently."""
        # Create task file with parallel tasks
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""## Phase 1
- [ ] T001 [P] Create module A
- [ ] T002 [P] Create module B
- [ ] T003 Create integration
""")
        context = ImplementerContext(
            task_file=task_file,
            branch="test",
            cwd=tmp_path,
            dry_run=True,
        )

        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                agent, "_execute_parallel_batch", new_callable=AsyncMock
            ) as mock_parallel,
        ):
            # Mock parallel batch execution
            mock_parallel.return_value = [
                TaskResult(task_id="T001", status=TaskStatus.COMPLETED),
                TaskResult(task_id="T002", status=TaskStatus.COMPLETED),
            ]

            await agent.execute(context)

            # Should have called parallel batch once for T001 and T002
            assert mock_parallel.call_count == 1
            # Check that it was called with 2 parallel tasks
            parallel_tasks = mock_parallel.call_args[0][0]
            assert len(parallel_tasks) == 2


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in ImplementerAgent."""

    @pytest.mark.asyncio
    async def test_handles_task_parse_error(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test raises TaskParseError on invalid task file."""
        task_file = tmp_path / "invalid.md"
        task_file.write_text("This is not a valid task file format")

        context = ImplementerContext(
            task_file=task_file,
            branch="test",
        )

        # Mock parse to raise TaskParseError
        with patch("maverick.models.implementation.TaskFile.parse") as mock_parse:
            mock_parse.side_effect = TaskParseError("Invalid format")

            with pytest.raises(TaskParseError):
                await agent.execute(context)

    @pytest.mark.asyncio
    async def test_failed_task_continues_to_next(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test continues executing remaining tasks when one fails."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""## Phase 1
- [ ] T001 Task 1
- [ ] T002 Task 2
- [ ] T003 Task 3
""")
        context = ImplementerContext(
            task_file=task_file,
            branch="test",
            cwd=tmp_path,
            dry_run=True,
        )

        call_count = 0

        async def failing_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Task 2 failed")
            mock_message = MagicMock()
            mock_message.role = "assistant"
            mock_message.content = [MagicMock(type="text", text="Done")]
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=failing_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(context)

            # Should have attempted all 3 tasks despite failure
            assert len(result.task_results) == 3
            # Task 2 should be failed
            assert result.task_results[1].status == TaskStatus.FAILED
            # Other tasks should complete
            assert result.tasks_failed == 1
            assert result.tasks_completed == 2

    @pytest.mark.asyncio
    async def test_handles_agent_error(
        self, agent: ImplementerAgent, single_task_context: ImplementerContext
    ) -> None:
        """Test handles AgentError gracefully."""
        with patch.object(agent, "query") as mock_query:
            mock_query.side_effect = AgentError(
                "Claude API error",
                error_code="API_ERROR",
            )

            result = await agent.execute(single_task_context)

            # Should return failed result, not raise
            assert result.success is False
            assert result.tasks_failed >= 1

    @pytest.mark.asyncio
    async def test_handles_validation_skip(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test executes successfully with skip_validation=True.

        Note: Agent no longer calls validation internally (workflow handles it).
        This test verifies the agent executes without issues when
        skip_validation is set.
        """
        context = ImplementerContext(
            task_description="Create module",
            branch="test",
            cwd=tmp_path,
            skip_validation=True,
            dry_run=True,
        )

        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(context)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_handles_dry_run(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test executes successfully in dry_run mode.

        Note: Agent no longer creates commits internally (workflow handles it).
        This test verifies the agent executes without issues in dry_run mode.
        """
        context = ImplementerContext(
            task_description="Create module",
            branch="test",
            cwd=tmp_path,
            dry_run=True,
        )

        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(context)

            assert result.success is True


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestImplementationResult:
    """Tests for ImplementationResult construction."""

    @pytest.mark.asyncio
    async def test_result_includes_metadata(
        self, agent: ImplementerAgent, single_task_context: ImplementerContext
    ) -> None:
        """Test result includes branch and duration metadata."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(single_task_context)

            assert "branch" in result.metadata
            assert result.metadata["branch"] == "feature/auth"
            assert "duration_ms" in result.metadata
            assert result.metadata["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_result_aggregates_file_changes(
        self,
        agent: ImplementerAgent,
        tmp_path: Path,
        mock_file_changes: list[FileChange],
    ) -> None:
        """Test result aggregates file changes from all tasks."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""## Phase 1
- [ ] T001 Task 1
- [ ] T002 Task 2
""")
        context = ImplementerContext(
            task_file=task_file,
            branch="test",
            cwd=tmp_path,
            dry_run=True,
        )

        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=mock_file_changes,
            ),
        ):
            result = await agent.execute(context)

            # Should aggregate changes from both tasks
            assert len(result.files_changed) == 4  # 2 tasks × 2 files each
            assert result.total_lines_changed > 0

    @pytest.mark.asyncio
    async def test_result_has_empty_commits_list_when_agent_does_not_create_commits(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test result has empty commits list since agent defers commits to workflow."""
        context = ImplementerContext(
            task_description="Create module",
            branch="test",
            cwd=tmp_path,
            dry_run=False,
        )

        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(context)

            assert len(result.commits) == 0


# =============================================================================
# Phase-Level Execution Tests
# =============================================================================


class TestPhaseLevelExecution:
    """Tests for phase-level task execution where Claude handles parallelization."""

    @pytest.fixture
    def phase_task_file(self, tmp_path: Path) -> Path:
        """Create a task file with multiple phases."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""## Phase 1: Setup
- [ ] T001 Create project structure
- [ ] T002 [P] Add configuration files
- [ ] T003 [P] Create utility modules

## Phase 2: Core
- [ ] T004 Implement main module
- [ ] T005 [P] Add logging
- [ ] T006 [P] Add error handling

## Phase 3: Testing
- [ ] T007 Write unit tests
- [ ] T008 Write integration tests
""")
        return task_file

    @pytest.fixture
    def phase_context(
        self, tmp_path: Path, phase_task_file: Path
    ) -> ImplementerContext:
        """Create context for phase-level execution."""
        return ImplementerContext(
            task_file=phase_task_file,
            phase_name="Phase 1: Setup",
            branch="feature/phase-test",
            cwd=tmp_path,
            dry_run=True,
        )

    def test_context_is_phase_mode(self, phase_context: ImplementerContext) -> None:
        """Test context correctly identifies phase mode."""
        assert phase_context.is_phase_mode is True
        assert phase_context.is_single_task is False

    def test_context_phase_mode_requires_task_file(self, tmp_path: Path) -> None:
        """Test phase_name without task_file raises validation error."""
        with pytest.raises(ValueError, match="phase_name requires task_file"):
            ImplementerContext(
                task_description="Some task description",
                phase_name="Phase 1",
                branch="test",
                cwd=tmp_path,
            )

    @pytest.mark.asyncio
    async def test_execute_routes_to_phase_mode(
        self, agent: ImplementerAgent, phase_context: ImplementerContext
    ) -> None:
        """Test execute routes to phase mode when phase_name is set."""
        with patch.object(
            agent, "_execute_phase_mode", new_callable=AsyncMock
        ) as mock_phase:
            mock_phase.return_value = ImplementationResult(
                success=True,
                tasks_completed=3,
                tasks_failed=0,
                tasks_skipped=0,
            )

            await agent.execute(phase_context)

            mock_phase.assert_called_once_with(phase_context)

    @pytest.mark.asyncio
    async def test_execute_routes_to_task_mode_without_phase(
        self, agent: ImplementerAgent, task_file_context: ImplementerContext
    ) -> None:
        """Test execute routes to task mode when phase_name is not set."""
        with patch.object(
            agent, "_execute_task_mode", new_callable=AsyncMock
        ) as mock_task:
            mock_task.return_value = ImplementationResult(
                success=True,
                tasks_completed=3,
                tasks_failed=0,
                tasks_skipped=0,
            )

            await agent.execute(task_file_context)

            mock_task.assert_called_once_with(task_file_context)

    @pytest.mark.asyncio
    async def test_phase_execution_sends_prompt_and_returns_result(
        self, agent: ImplementerAgent, phase_context: ImplementerContext
    ) -> None:
        """Test phase execution sends prompt to Claude and returns result."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Phase completed")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen) as mock_query,
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(phase_context)

            # Verify prompt was sent with phase-specific arguments
            mock_query.assert_called_once()
            prompt = mock_query.call_args[0][0]
            assert "Phase 1: Setup" in prompt
            assert result.metadata.get("phase") == "Phase 1: Setup"
            assert result.metadata.get("execution_mode") == "phase"
            assert result.success is True

    def test_build_phase_prompt_contains_phase_name(
        self, agent: ImplementerAgent, phase_context: ImplementerContext
    ) -> None:
        """Test phase prompt includes the phase name."""
        prompt = agent._build_phase_prompt("Phase 1: Setup", phase_context)

        assert "Phase 1: Setup" in prompt

    def test_build_phase_prompt_contains_task_file(
        self, agent: ImplementerAgent, phase_context: ImplementerContext
    ) -> None:
        """Test phase prompt includes the task file path."""
        prompt = agent._build_phase_prompt("Phase 1", phase_context)

        assert str(phase_context.task_file) in prompt

    def test_build_phase_prompt_instructs_write(
        self, agent: ImplementerAgent, phase_context: ImplementerContext
    ) -> None:
        """Test phase prompt instructs agent to use Write and Edit tools."""
        prompt = agent._build_phase_prompt("Phase 1", phase_context)

        assert "Write" in prompt
        assert "Edit" in prompt
        # Must emphasize actual code creation, not just reading
        assert "create" in prompt.lower() or "modify" in prompt.lower()

    def test_build_phase_prompt_mentions_parallel_tasks(
        self, agent: ImplementerAgent, phase_context: ImplementerContext
    ) -> None:
        """Test phase prompt mentions [P] parallel task markers."""
        prompt = agent._build_phase_prompt("Phase 1", phase_context)

        assert "[P]" in prompt
        assert "Task" in prompt  # Task tool for subagents

    # NOTE: test_phase_commit_message_format was removed as _create_phase_commit
    # was removed from the agent (issue #147). Commits are handled by workflow.


# =============================================================================
# Side-Effect Free Tests (Issue #160)
# =============================================================================


class TestSideEffectFree:
    """Tests verifying agents are side-effect free per issue #160.

    ImplementerAgent should NOT create commits or run validation internally.
    These are handled by the workflow layer.

    TaskResult should have:
    - Empty validation list
    - commit_sha=None
    """

    @pytest.mark.asyncio
    async def test_agent_has_no_validation_method(
        self, agent: ImplementerAgent
    ) -> None:
        """Test that agent does not have _run_validation method.

        The method has been removed as part of issue #147 - validation
        is now handled by the workflow layer.
        """
        assert not hasattr(agent, "_run_validation")

    @pytest.mark.asyncio
    async def test_agent_has_no_create_commit_method(
        self, agent: ImplementerAgent
    ) -> None:
        """Test that agent does not have _create_commit method.

        The method has been removed as part of issue #147 - commits
        are now handled by the workflow layer.
        """
        assert not hasattr(agent, "_create_commit")

    @pytest.mark.asyncio
    async def test_task_result_has_empty_validation(
        self, agent: ImplementerAgent, single_task_context: ImplementerContext
    ) -> None:
        """Test that task results have empty validation lists."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(single_task_context)

            # Verify task results have empty validation
            assert len(result.task_results) > 0
            for task_result in result.task_results:
                assert task_result.validation == []

    @pytest.mark.asyncio
    async def test_task_result_has_no_commit_sha(
        self, agent: ImplementerAgent, single_task_context: ImplementerContext
    ) -> None:
        """Test that task results have no commit_sha."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(single_task_context)

            # Verify task results have no commit_sha
            assert len(result.task_results) > 0
            for task_result in result.task_results:
                assert task_result.commit_sha is None

    @pytest.mark.asyncio
    async def test_implementation_result_has_empty_commits_list(
        self, agent: ImplementerAgent, single_task_context: ImplementerContext
    ) -> None:
        """Test that implementation result has empty commits list."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_message.content = [MagicMock(type="text", text="Done")]

        async def async_gen(*args, **kwargs):
            yield mock_message

        with (
            patch.object(agent, "query", side_effect=async_gen),
            patch(
                "maverick.agents.implementer.detect_file_changes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await agent.execute(single_task_context)

            # Verify commits list is empty (no commits created by agent)
            assert result.commits == []
