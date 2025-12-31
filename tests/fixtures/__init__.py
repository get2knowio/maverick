"""Shared test fixtures for Maverick test suite.

This module contains reusable pytest fixtures for testing Maverick components.
Fixtures are organized by concern and shared across test modules to ensure
consistent test data and setup/teardown behavior.

Available Fixtures
==================

Agent SDK Mocks (from tests/fixtures/agents.py)
-----------------------------------------------

Classes:
    MockMessage: Simulates TextMessage and ResultMessage from Claude Agent SDK.
        Use for testing agent interactions without real API calls.

    MockSDKClient: Mock client with response queue for testing agent workflows.
        Maintains FIFO queue of responses and records all interactions.

Fixtures:
    mock_text_message: Factory fixture for creating TextMessage mocks.
        Returns a callable that creates MockMessage("TextMessage", text=...)

    mock_result_message: Factory fixture for creating ResultMessage mocks.
        Returns a callable that creates MockMessage("ResultMessage", usage=...)

    mock_sdk_client: Provides a fresh MockSDKClient instance for each test.

    mock_implementer_agent: Mock ImplementerAgent for workflow testing.
        Returns MagicMock with AsyncMock execute() returning ImplementationResult.

    mock_commit_generator: Mock CommitMessageGenerator for workflow testing.
        Returns MagicMock with AsyncMock generate() returning commit messages.

Runner Mocks (from tests/fixtures/runners.py)
----------------------------------------------

Fixtures:
    mock_git_runner: Mock GitRunner for testing git operations.
        Returns MagicMock with AsyncMock methods returning GitResult instances.
        Supports: create_branch, checkout, commit, push, add, status, diff.

    mock_validation_runner: Mock ValidationRunner for testing validation stages.
        Returns MagicMock with AsyncMock run() returning ValidationOutput.
        Default behavior: all stages pass successfully.

    mock_github_runner: Mock GitHubCLIRunner for testing GitHub operations.
        Returns MagicMock with AsyncMock methods for PR and issue management.
        Supports: create_pr, update_pr, get_pr, list_issues, get_issue, close_issue.

Example:
    >>> @pytest.mark.asyncio
    ... async def test_agent(mock_sdk_client, mock_text_message, mock_result_message):
    ...     # Queue a conversation: text message followed by result
    ...     mock_sdk_client.queue_response([
    ...         mock_text_message("Agent is thinking..."),
    ...         mock_result_message(input_tokens=150, output_tokens=200),
    ...     ])
    ...     async for msg in mock_sdk_client.receive_response():
    ...         if msg.message_type == "TextMessage":
    ...             print(msg.text)

Configuration (from tests/fixtures/config.py)
---------------------------------------------

Fixtures:
    sample_config: Creates a MaverickConfig with typical test values.
        Sets up temporary directory with maverick.yaml and loads config.
        Configured with test GitHub repo, disabled notifications, etc.

Example:
    >>> def test_config_usage(sample_config):
    ...     assert sample_config.github.owner == "test-org"
    ...     assert sample_config.model.model_id == "claude-sonnet-4-5-20250929"

Sample Responses (from tests/fixtures/responses.py)
---------------------------------------------------

Fixtures:
    sample_review_response: Typical successful code review response.
        Returns ReviewResult with no findings, 3 files reviewed.

    sample_implementation_response: Typical successful implementation response.
        Returns ImplementationResult with 2 completed tasks, file changes.

    sample_error_response: Error response with failure details.
        Returns ImplementationResult with failed task and error messages.

Example:
    >>> def test_review_handling(sample_review_response):
    ...     result = sample_review_response
    ...     assert result.success is True
    ...     assert result.files_reviewed == 3
    ...     assert len(result.findings) == 0

GitHub CLI Mocks (from tests/fixtures/github.py)
------------------------------------------------

Classes:
    CommandResponse: Simulates result of gh command (returncode, stdout, stderr).

    CommandCall: Records details of a gh command invocation (args, timestamp).

    MockGitHubCLI: Mock GitHub CLI with configurable responses and call history.
        Supports pattern-based response configuration and call verification.

Fixtures:
    mock_github_cli: Provides a fresh MockGitHubCLI instance for each test.

Example:
    >>> def test_pr_creation(mock_github_cli):
    ...     # Configure response for PR creation
    ...     mock_github_cli.set_response(
    ...         "pr create",
    ...         CommandResponse(returncode=0, stdout='{"number": 42}')
    ...     )
    ...     # Execute command
    ...     response = mock_github_cli.execute(["pr", "create", "--title", "Test"])
    ...     assert response.returncode == 0
    ...     # Verify command was called
    ...     pr_calls = mock_github_cli.get_calls("pr create")
    ...     assert len(pr_calls) == 1

Usage Notes
===========

1. Import fixtures directly in test function signatures:
   >>> def test_something(mock_sdk_client, sample_config):
   ...     pass

2. Factory fixtures (mock_text_message, mock_result_message) return callables:
   >>> def test_messages(mock_text_message):
   ...     msg1 = mock_text_message("First message")
   ...     msg2 = mock_text_message("Second message")

3. For test isolation, fixtures are reset/recreated for each test automatically.

4. Combine fixtures to test complex scenarios:
   >>> def test_workflow(mock_sdk_client, mock_github_cli, sample_config):
   ...     # Test workflow using both mocked SDK client and GitHub CLI
   ...     pass
"""

from __future__ import annotations

# Import classes and fixtures from submodules for easy access
from tests.fixtures.agents import (
    MockMessage,
    MockSDKClient,
    mock_commit_generator,
    mock_implementer_agent,
    mock_result_message,
    mock_sdk_client,
    mock_text_message,
)
from tests.fixtures.config import sample_config
from tests.fixtures.github import (
    CommandCall,
    CommandResponse,
    MockGitHubCLI,
    mock_github_cli,
)
from tests.fixtures.responses import (
    sample_error_response,
    sample_implementation_response,
    sample_review_response,
)
from tests.fixtures.runners import (
    mock_git_runner,
    mock_github_runner,
    mock_validation_runner,
)

__all__ = [
    # Agent SDK mocks
    "MockMessage",
    "MockSDKClient",
    "mock_text_message",
    "mock_result_message",
    "mock_sdk_client",
    "mock_implementer_agent",
    "mock_commit_generator",
    # Configuration
    "sample_config",
    # Sample responses
    "sample_review_response",
    "sample_implementation_response",
    "sample_error_response",
    # GitHub CLI mocks
    "CommandResponse",
    "CommandCall",
    "MockGitHubCLI",
    "mock_github_cli",
    # Runner mocks
    "mock_git_runner",
    "mock_validation_runner",
    "mock_github_runner",
]
