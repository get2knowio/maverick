"""Mock fixtures for Claude Agent SDK testing.

This module provides mock implementations of Claude Agent SDK components
for testing agents without real API calls.

Provides:
- MockMessage: Simulates TextMessage and ResultMessage
- MockSDKClient: Mock client with response queue for testing
- Factory fixtures for creating mock messages
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@dataclass
class MockMessage:
    """Represents a mock message from the Claude Agent SDK.

    Simulates either TextMessage or ResultMessage from the SDK.

    Args:
        message_type: Either "TextMessage" or "ResultMessage"
        text: Message content (for TextMessage)
        usage: Token usage dict with input_tokens and output_tokens (for ResultMessage)
        total_cost_usd: Cost in USD (for ResultMessage)
        duration_ms: Duration in milliseconds (for ResultMessage)

    Example:
        >>> text_msg = MockMessage("TextMessage", text="Hello world")
        >>> usage = {"input_tokens": 100, "output_tokens": 50}
        >>> result_msg = MockMessage("ResultMessage", usage=usage)
    """

    message_type: str
    text: str | None = None
    usage: dict[str, int] | None = None
    total_cost_usd: float | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        """Validate message_type after initialization."""
        valid_types = {"TextMessage", "ResultMessage"}
        if self.message_type not in valid_types:
            raise ValueError(
                f"message_type must be one of {valid_types}, got '{self.message_type}'"
            )
        if self.total_cost_usd is not None and self.total_cost_usd < 0:
            raise ValueError("total_cost_usd must be non-negative")
        if self.usage is not None:
            required_keys = {"input_tokens", "output_tokens"}
            if not required_keys.issubset(self.usage.keys()):
                raise ValueError(f"usage must contain keys: {required_keys}")
        if self.message_type == "TextMessage" and self.text is None:
            raise ValueError("TextMessage must have text")
        if self.message_type == "ResultMessage" and self.usage is None:
            raise ValueError("ResultMessage must have usage")

    @property
    def __class_name__(self) -> str:
        """Return the message type for isinstance-like checks."""
        return self.message_type


@dataclass
class MockSDKClient:
    """Mock Claude Agent SDK client with response queue for testing.

    Simulates the ClaudeSDKClient from claude-agent-sdk. Maintains a FIFO
    queue of response sequences that are yielded when receive_response() is called.

    Attributes:
        query_calls: List of prompts sent via query()
        options_used: Last ClaudeAgentOptions passed to client
        _responses: Internal queue of response sequences
        _errors: Internal queue of errors to raise
        _response_index: Current position in response queue

    Example:
        >>> client = MockSDKClient()
        >>> client.queue_response([MockMessage("TextMessage", text="Hello")])
        >>> async for msg in client.receive_response():
        ...     print(msg.text)
        Hello
    """

    query_calls: list[str] = field(default_factory=list)
    options_used: Any | None = None
    _responses: list[list[MockMessage]] = field(default_factory=list)
    _errors: list[Exception] = field(default_factory=list)
    _response_index: int = 0

    def queue_response(self, messages: list[MockMessage]) -> None:
        """Add a response sequence to the queue.

        Args:
            messages: List of MockMessage objects to yield in sequence
        """
        self._responses.append(messages)

    def queue_error(self, error: Exception) -> None:
        """Queue an error to be raised during receive_response.

        Args:
            error: Exception to raise
        """
        self._errors.append(error)

    async def query(self, prompt: str) -> None:
        """Record a query prompt.

        Args:
            prompt: The prompt sent to the agent
        """
        self.query_calls.append(prompt)

    async def receive_response(self) -> AsyncGenerator[MockMessage, None]:
        """Yield queued messages from the response queue.

        Yields messages from the current response sequence, then advances
        to the next sequence. If an error is queued, raises it after
        yielding any messages in the current sequence.

        Yields:
            MockMessage objects from the queued response

        Raises:
            Exception: If an error was queued via queue_error()
        """
        if self._response_index < len(self._responses):
            for msg in self._responses[self._response_index]:
                yield msg
            self._response_index += 1

        if self._errors:
            error = self._errors.pop(0)
            raise error

    def reset(self) -> None:
        """Clear all state for test isolation."""
        self.query_calls.clear()
        self.options_used = None
        self._responses.clear()
        self._errors.clear()
        self._response_index = 0

    async def __aenter__(self) -> MockSDKClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        pass


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def mock_text_message() -> Callable[..., MockMessage]:
    """Factory fixture for creating TextMessage mocks.

    Returns:
        A factory function that creates MockMessage with type "TextMessage"

    Example:
        >>> def test_something(mock_text_message):
        ...     msg = mock_text_message("Hello world")
        ...     assert msg.text == "Hello world"
    """

    def _create(text: str = "Response") -> MockMessage:
        return MockMessage("TextMessage", text=text)

    return _create


@pytest.fixture
def mock_result_message() -> Callable[..., MockMessage]:
    """Factory fixture for creating ResultMessage mocks.

    Returns:
        A factory function that creates MockMessage with type "ResultMessage"

    Example:
        >>> def test_something(mock_result_message):
        ...     msg = mock_result_message(input_tokens=150, output_tokens=200)
        ...     assert msg.usage["input_tokens"] == 150
    """

    def _create(
        input_tokens: int = 100,
        output_tokens: int = 200,
        total_cost_usd: float = 0.005,
        duration_ms: int = 1500,
    ) -> MockMessage:
        return MockMessage(
            "ResultMessage",
            usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            total_cost_usd=total_cost_usd,
            duration_ms=duration_ms,
        )

    return _create


@pytest.fixture
def mock_sdk_client() -> MockSDKClient:
    """Fixture providing a fresh MockSDKClient instance.

    Returns:
        A new MockSDKClient for testing agent interactions

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_agent(
        ...     mock_sdk_client, mock_text_message, mock_result_message
        ... ):
        ...     mock_sdk_client.queue_response([
        ...         mock_text_message("Hello"),
        ...         mock_result_message(),
        ...     ])
        ...     # Use mock_sdk_client in your agent test
    """
    return MockSDKClient()


# =============================================================================
# Agent Mocks for Workflow Testing
# =============================================================================


@pytest.fixture
def mock_implementer_agent() -> MagicMock:
    """Fixture providing a mock ImplementerAgent instance.

    Returns:
        MagicMock configured with AsyncMock execute() that returns ImplementationResult.
        Default behavior: successful task completion with minimal file changes.

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_workflow(mock_implementer_agent):
        ...     from maverick.models.implementation import ImplementerContext
        ...     # Default: implementation succeeds
        ...     context = ImplementerContext(branch="test-branch")
        ...     result = await mock_implementer_agent.execute(context)
        ...     assert result.success
        ...
        ...     # Configure specific behavior
        ...     from maverick.models.implementation import ImplementationResult
        ...     mock_implementer_agent.execute.return_value = ImplementationResult(
        ...         success=False,
        ...         tasks_completed=2,
        ...         tasks_failed=1,
        ...         tasks_skipped=0,
        ...         task_results=[],
        ...         files_changed=[],
        ...         commits=[],
        ...         validation_passed=False,
        ...         errors=["Task T003 failed"],
        ...     )
    """
    from maverick.models.implementation import (
        ChangeType,
        FileChange,
        ImplementationResult,
        TaskResult,
        TaskStatus,
    )

    agent = MagicMock()

    # Configure default successful implementation
    agent.execute = AsyncMock(
        return_value=ImplementationResult(
            success=True,
            tasks_completed=3,
            tasks_failed=0,
            tasks_skipped=0,
            task_results=[
                TaskResult(
                    task_id="T001",
                    status=TaskStatus.COMPLETED,
                    files_changed=[
                        FileChange(
                            file_path="src/module.py",
                            change_type=ChangeType.MODIFIED,
                            lines_added=15,
                            lines_removed=3,
                        )
                    ],
                    tests_added=["tests/test_module.py"],
                    commit_sha="abc1234567890",
                    duration_ms=5000,
                    validation=[],
                ),
                TaskResult(
                    task_id="T002",
                    status=TaskStatus.COMPLETED,
                    files_changed=[
                        FileChange(
                            file_path="tests/test_module.py",
                            change_type=ChangeType.ADDED,
                            lines_added=25,
                            lines_removed=0,
                        )
                    ],
                    tests_added=["tests/test_module.py"],
                    commit_sha="def4567890123",
                    duration_ms=3000,
                    validation=[],
                ),
                TaskResult(
                    task_id="T003",
                    status=TaskStatus.COMPLETED,
                    files_changed=[
                        FileChange(
                            file_path="README.md",
                            change_type=ChangeType.MODIFIED,
                            lines_added=5,
                            lines_removed=1,
                        )
                    ],
                    tests_added=[],
                    commit_sha="ghi7890123456",
                    duration_ms=1500,
                    validation=[],
                ),
            ],
            files_changed=[
                FileChange(
                    file_path="src/module.py",
                    change_type=ChangeType.MODIFIED,
                    lines_added=15,
                    lines_removed=3,
                ),
                FileChange(
                    file_path="tests/test_module.py",
                    change_type=ChangeType.ADDED,
                    lines_added=25,
                    lines_removed=0,
                ),
                FileChange(
                    file_path="README.md",
                    change_type=ChangeType.MODIFIED,
                    lines_added=5,
                    lines_removed=1,
                ),
            ],
            commits=["abc1234567890", "def4567890123", "ghi7890123456"],
            validation_passed=True,
            metadata={
                "branch": "test-branch",
                "duration_ms": 9500,
                "dry_run": False,
            },
            errors=[],
        )
    )

    # Set agent properties
    agent.name = "implementer"
    agent.system_prompt = "Mock implementer agent"
    agent.allowed_tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    return agent


@pytest.fixture
def mock_commit_generator() -> MagicMock:
    """Fixture providing a mock CommitMessageGenerator instance.

    Returns:
        MagicMock configured with AsyncMock generate() that returns commit messages.
        Default behavior: generates conventional commit messages based on context.

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_commit_generation(mock_commit_generator):
        ...     # Default: generates conventional commit message
        ...     context = {
        ...         "diff": "diff --git a/auth.py...",
        ...         "file_stats": {"auth.py": {"additions": 10, "deletions": 2}},
        ...         "scope_hint": "auth",
        ...     }
        ...     message = await mock_commit_generator.generate(context)
        ...     assert message.startswith("feat(")
        ...
        ...     # Configure specific behavior
        ...     mock_commit_generator.generate.return_value = "fix(api): null user"
        ...     message = await mock_commit_generator.generate(context)
        ...     assert message == "fix(api): null user"
    """
    generator = MagicMock()

    # Configure generate method to return context-aware commit messages
    def generate_commit_message(context: dict) -> str:
        """Generate a mock commit message based on context."""
        scope_hint = context.get("scope_hint", "core")
        file_stats = context.get("file_stats", {})

        # Determine type based on file changes (simple heuristic)
        if file_stats:
            first_file = next(iter(file_stats.keys()), "")
            if "test" in first_file.lower():
                return f"test({scope_hint}): add test coverage"
            elif "README" in first_file or "docs/" in first_file:
                return f"docs({scope_hint}): update documentation"
            else:
                return f"feat({scope_hint}): implement new functionality"
        return f"chore({scope_hint}): update codebase"

    generator.generate = AsyncMock(side_effect=generate_commit_message)

    # Set generator properties
    generator.name = "commit-message-generator"
    generator.system_prompt = "Mock commit message generator"

    return generator
