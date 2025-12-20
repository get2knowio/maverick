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
    IMPLEMENTER_SYSTEM_PROMPT,
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
        assert agent.system_prompt == IMPLEMENTER_SYSTEM_PROMPT
        # Compare as sets since allowed_tools is a list and IMPLEMENTER_TOOLS is a frozenset
        assert set(agent.allowed_tools) == set(IMPLEMENTER_TOOLS)

    def test_custom_model(self) -> None:
        """Test agent accepts custom model parameter."""
        custom_agent = ImplementerAgent(model="claude-3-opus-20240229")
        assert custom_agent.model == "claude-3-opus-20240229"

    def test_system_prompt_contains_tdd_approach(
        self, agent: ImplementerAgent
    ) -> None:
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
        """Test allowed tools matches US3 contract exactly.

        US3 Contract: ImplementerAgent must have exactly Read, Write, Edit, Glob, Grep.
        Bash removed - orchestration layer handles command execution.
        """
        expected_tools = {"Read", "Write", "Edit", "Glob", "Grep"}
        actual_tools = set(agent.allowed_tools)
        assert actual_tools == expected_tools, (
            f"ImplementerAgent tools mismatch. Expected: {expected_tools}, Got: {actual_tools}"
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

    def test_implementer_system_prompt_is_string(self) -> None:
        """Test IMPLEMENTER_SYSTEM_PROMPT is defined and non-empty."""
        assert isinstance(IMPLEMENTER_SYSTEM_PROMPT, str)
        assert len(IMPLEMENTER_SYSTEM_PROMPT) > 100

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


class TestDetectFileChanges:
    """Tests for _detect_file_changes helper method."""

    @pytest.mark.asyncio
    async def test_detect_file_changes_returns_list(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test returns list of FileChange objects."""
        with patch("maverick.utils.git.get_diff_stats", new_callable=AsyncMock) as mock_diff:
            mock_diff.return_value = {
                "src/file.py": (10, 2),
                "tests/test_file.py": (20, 0),
            }

            changes = await agent._detect_file_changes(tmp_path)

            assert isinstance(changes, list)
            assert len(changes) == 2
            assert all(isinstance(c, FileChange) for c in changes)

    @pytest.mark.asyncio
    async def test_detect_file_changes_parses_stats_correctly(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test correctly parses file stats into FileChange objects."""
        with patch("maverick.utils.git.get_diff_stats", new_callable=AsyncMock) as mock_diff:
            mock_diff.return_value = {
                "src/module.py": (15, 3),
            }

            changes = await agent._detect_file_changes(tmp_path)

            assert len(changes) == 1
            assert changes[0].file_path == "src/module.py"
            assert changes[0].lines_added == 15
            assert changes[0].lines_removed == 3
            assert changes[0].change_type == ChangeType.MODIFIED

    @pytest.mark.asyncio
    async def test_detect_file_changes_handles_errors_gracefully(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test returns empty list on git errors."""
        with patch("maverick.utils.git.get_diff_stats", new_callable=AsyncMock) as mock_diff:
            mock_diff.side_effect = Exception("Git command failed")

            changes = await agent._detect_file_changes(tmp_path)

            assert changes == []


class TestRunValidation:
    """Tests for _run_validation helper method."""

    @pytest.mark.asyncio
    async def test_run_validation_returns_list(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test returns list of ValidationResult objects."""
        with patch(
            "maverick.utils.validation.run_validation_pipeline", new_callable=AsyncMock
        ) as mock_validation:
            mock_validation.return_value = [
                ValidationResult(
                    step=ValidationStep.FORMAT,
                    success=True,
                    duration_ms=500,
                ),
            ]

            results = await agent._run_validation(tmp_path)

            assert isinstance(results, list)
            assert len(results) == 1
            assert isinstance(results[0], ValidationResult)

    @pytest.mark.asyncio
    async def test_run_validation_handles_errors_gracefully(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test returns empty list on validation errors."""
        with patch(
            "maverick.utils.validation.run_validation_pipeline", new_callable=AsyncMock
        ) as mock_validation:
            mock_validation.side_effect = Exception("Validation failed")

            results = await agent._run_validation(tmp_path)

            assert results == []


class TestCreateCommit:
    """Tests for _create_commit helper method."""

    @pytest.mark.asyncio
    async def test_create_commit_returns_sha(
        self, agent: ImplementerAgent, sample_task: Task, tmp_path: Path
    ) -> None:
        """Test returns commit SHA on success."""
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/test",
            cwd=tmp_path,
        )

        with (
            patch("maverick.utils.git.has_uncommitted_changes", new_callable=AsyncMock) as mock_changes,
            patch("maverick.utils.git.create_commit", new_callable=AsyncMock) as mock_commit,
        ):
            mock_changes.return_value = True
            mock_commit.return_value = "abc123def456"

            sha = await agent._create_commit(sample_task, context)

            assert sha == "abc123def456"
            mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_commit_returns_none_when_no_changes(
        self, agent: ImplementerAgent, sample_task: Task, tmp_path: Path
    ) -> None:
        """Test returns None when no uncommitted changes."""
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/test",
            cwd=tmp_path,
        )

        with patch("maverick.utils.git.has_uncommitted_changes", new_callable=AsyncMock) as mock_changes:
            mock_changes.return_value = False

            sha = await agent._create_commit(sample_task, context)

            assert sha is None

    @pytest.mark.asyncio
    async def test_create_commit_generates_conventional_message(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test generates conventional commit message format."""
        task = Task(
            id="T042",
            description="Create new authentication service",
            status=TaskStatus.PENDING,
        )
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/test",
            cwd=tmp_path,
        )

        with (
            patch("maverick.utils.git.has_uncommitted_changes", new_callable=AsyncMock) as mock_changes,
            patch("maverick.utils.git.create_commit", new_callable=AsyncMock) as mock_commit,
        ):
            mock_changes.return_value = True
            mock_commit.return_value = "abc123"

            await agent._create_commit(task, context)

            # Check the commit message contains conventional format
            call_args = mock_commit.call_args[0][0]
            assert "feat" in call_args or "chore" in call_args
            assert "t042" in call_args.lower()

    @pytest.mark.asyncio
    async def test_create_commit_handles_errors_gracefully(
        self, agent: ImplementerAgent, sample_task: Task, tmp_path: Path
    ) -> None:
        """Test returns None on commit errors."""
        context = ImplementerContext(
            task_description="This is a test task description",
            branch="feature/test",
            cwd=tmp_path,
        )

        with patch("maverick.utils.git.has_uncommitted_changes", new_callable=AsyncMock) as mock_changes:
            mock_changes.side_effect = Exception("Git error")

            sha = await agent._create_commit(sample_task, context)

            assert sha is None


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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock, return_value=[]
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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock, return_value=[]
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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
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

            result = await agent.execute(context)

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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
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
        """Test skips validation when skip_validation is True."""
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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock
            ) as mock_validation,
        ):
            result = await agent.execute(context)

            # Validation should not be called
            mock_validation.assert_not_called()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_handles_dry_run(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test skips commit creation in dry_run mode."""
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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                agent, "_create_commit", new_callable=AsyncMock
            ) as mock_commit,
        ):
            result = await agent.execute(context)

            # Commit should not be called in dry_run
            mock_commit.assert_not_called()
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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
            ),
        ):
            result = await agent.execute(single_task_context)

            assert "branch" in result.metadata
            assert result.metadata["branch"] == "feature/auth"
            assert "duration_ms" in result.metadata
            assert result.metadata["duration_ms"] > 0

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
            patch.object(
                agent,
                "_detect_file_changes",
                new_callable=AsyncMock,
                return_value=mock_file_changes,
            ),
        ):
            result = await agent.execute(context)

            # Should aggregate changes from both tasks
            assert len(result.files_changed) == 4  # 2 tasks × 2 files each
            assert result.total_lines_changed > 0

    @pytest.mark.asyncio
    async def test_result_tracks_commits(
        self, agent: ImplementerAgent, tmp_path: Path
    ) -> None:
        """Test result tracks commit SHAs."""
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
            patch.object(
                agent, "_detect_file_changes", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                agent, "_run_validation", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                agent,
                "_create_commit",
                new_callable=AsyncMock,
                return_value="abc123def456",
            ),
        ):
            result = await agent.execute(context)

            assert len(result.commits) == 1
            assert result.commits[0] == "abc123def456"
