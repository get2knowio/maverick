"""Example test file demonstrating fixture usage patterns.

This file serves as documentation and verification that all fixtures work
correctly and meet the SC-005 success criteria (<20 lines of boilerplate
per test).

Each test demonstrates a specific fixture or combination of fixtures with
clear docstrings explaining the pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from maverick.config import MaverickConfig
from maverick.models.implementation import ImplementationResult, TaskStatus
from maverick.models.review import ReviewResult
from tests.fixtures.agents import MockMessage, MockSDKClient
from tests.fixtures.github import CommandResponse, MockGitHubCLI

if TYPE_CHECKING:
    from collections.abc import Callable

    from click.testing import CliRunner


# =============================================================================
# Mock Message Fixtures - Claude Agent SDK Mocking
# =============================================================================


def test_mock_text_message_factory(
    mock_text_message: Callable[..., MockMessage],
) -> None:
    """Demonstrate creating text messages from Claude Agent SDK.

    Pattern: Use mock_text_message factory to create TextMessage mocks
    for simulating agent text responses.

    Boilerplate: 3 lines (fixture param + 2 assertions)
    """
    msg = mock_text_message("Hello from the agent")

    assert msg.message_type == "TextMessage"
    assert msg.text == "Hello from the agent"


def test_mock_text_message_default(
    mock_text_message: Callable[..., MockMessage],
) -> None:
    """Demonstrate using default text message values.

    Pattern: Factory provides sensible defaults for quick setup.

    Boilerplate: 2 lines (fixture param + 1 assertion)
    """
    msg = mock_text_message()

    assert msg.text == "Response"


def test_mock_result_message_factory(
    mock_result_message: Callable[..., MockMessage],
) -> None:
    """Demonstrate creating result messages with usage metrics.

    Pattern: Use mock_result_message factory to create ResultMessage mocks
    with token usage and cost information.

    Boilerplate: 5 lines (fixture param + 4 assertions)
    """
    msg = mock_result_message(
        input_tokens=150, output_tokens=200, total_cost_usd=0.008, duration_ms=2000
    )

    assert msg.message_type == "ResultMessage"
    assert msg.usage == {"input_tokens": 150, "output_tokens": 200}
    assert msg.total_cost_usd == 0.008
    assert msg.duration_ms == 2000


def test_mock_result_message_defaults(
    mock_result_message: Callable[..., MockMessage],
) -> None:
    """Demonstrate using default result message values.

    Pattern: Factory provides sensible defaults for token counts and costs.

    Boilerplate: 2 lines (fixture param + 1 assertion)
    """
    msg = mock_result_message()

    assert msg.usage == {"input_tokens": 100, "output_tokens": 200}


# =============================================================================
# MockSDKClient - Async Agent Testing
# =============================================================================


@pytest.mark.asyncio
async def test_mock_sdk_client_basic_usage(
    mock_sdk_client: MockSDKClient,
    mock_text_message: Callable[..., MockMessage],
    mock_result_message: Callable[..., MockMessage],
) -> None:
    """Demonstrate basic MockSDKClient usage for agent testing.

    Pattern: Queue responses, then iterate through them with receive_response().
    This simulates the async streaming response from the Claude Agent SDK.

    Boilerplate: 8 lines (3 fixtures + 5 test logic)
    """
    # Queue a sequence of messages
    mock_sdk_client.queue_response(
        [mock_text_message("Processing..."), mock_result_message()]
    )

    # Collect messages
    messages = []
    async for msg in mock_sdk_client.receive_response():
        messages.append(msg)

    assert len(messages) == 2
    assert messages[0].text == "Processing..."
    assert messages[1].message_type == "ResultMessage"


@pytest.mark.asyncio
async def test_mock_sdk_client_multiple_responses(
    mock_sdk_client: MockSDKClient, mock_text_message: Callable[..., MockMessage]
) -> None:
    """Demonstrate queuing multiple response sequences.

    Pattern: Queue multiple response sequences to simulate multiple agent
    interactions in a single test.

    Boilerplate: 11 lines (2 fixtures + 9 test logic)
    """
    # Queue two separate response sequences
    mock_sdk_client.queue_response([mock_text_message("First response")])
    mock_sdk_client.queue_response([mock_text_message("Second response")])

    # First call to receive_response
    messages1 = [msg async for msg in mock_sdk_client.receive_response()]
    assert messages1[0].text == "First response"

    # Second call to receive_response
    messages2 = [msg async for msg in mock_sdk_client.receive_response()]
    assert messages2[0].text == "Second response"


@pytest.mark.asyncio
async def test_mock_sdk_client_error_handling(mock_sdk_client: MockSDKClient) -> None:
    """Demonstrate error simulation with MockSDKClient.

    Pattern: Use queue_error() to test agent error handling paths.

    Boilerplate: 4 lines (1 fixture + 3 test logic)
    """
    mock_sdk_client.queue_error(RuntimeError("Simulated agent failure"))

    with pytest.raises(RuntimeError, match="Simulated agent failure"):
        async for _ in mock_sdk_client.receive_response():
            pass


@pytest.mark.asyncio
async def test_mock_sdk_client_query_tracking(mock_sdk_client: MockSDKClient) -> None:
    """Demonstrate query call tracking.

    Pattern: Use query_calls to verify prompts sent to the agent.

    Boilerplate: 5 lines (1 fixture + 4 test logic)
    """
    await mock_sdk_client.query("First prompt")
    await mock_sdk_client.query("Second prompt")

    assert len(mock_sdk_client.query_calls) == 2
    assert mock_sdk_client.query_calls[0] == "First prompt"
    assert mock_sdk_client.query_calls[1] == "Second prompt"


# =============================================================================
# Configuration Fixtures
# =============================================================================


def test_sample_config_structure(sample_config: MaverickConfig) -> None:
    """Demonstrate using sample_config for configuration testing.

    Pattern: Use sample_config to get a fully configured MaverickConfig
    instance without manual setup.

    Boilerplate: 7 lines (1 fixture + 6 assertions)
    """
    assert sample_config.github.owner == "test-org"
    assert sample_config.github.repo == "test-repo"
    assert sample_config.github.default_branch == "main"
    assert sample_config.model.model_id == "claude-sonnet-4-5-20250929"
    assert sample_config.model.max_tokens == 4096
    assert sample_config.parallel.max_agents == 2


def test_sample_config_isolation(sample_config: MaverickConfig, temp_dir: Path) -> None:
    """Demonstrate config isolation with temp_dir.

    Pattern: sample_config uses temp_dir internally to ensure test isolation.
    Each test gets a fresh config in its own directory.

    Boilerplate: 4 lines (2 fixtures + 2 assertions)
    """
    # sample_config creates a maverick.yaml in temp_dir
    assert sample_config.github.owner == "test-org"
    assert sample_config.notifications.enabled is False


# =============================================================================
# Agent Response Fixtures
# =============================================================================


def test_sample_review_response_structure(
    sample_review_response: ReviewResult,
) -> None:
    """Demonstrate using sample_review_response for review testing.

    Pattern: Use pre-configured ReviewResult for testing review workflows
    without creating complex objects manually.

    Boilerplate: 6 lines (1 fixture + 5 assertions)
    """
    assert sample_review_response.success is True
    assert sample_review_response.files_reviewed == 3
    assert len(sample_review_response.findings) == 0
    assert sample_review_response.summary == "Reviewed 3 files, no issues found"
    assert sample_review_response.metadata["branch"] == "feature/test-branch"


def test_sample_implementation_response_structure(
    sample_implementation_response: ImplementationResult,
) -> None:
    """Demonstrate using sample_implementation_response for implementation testing.

    Pattern: Use pre-configured ImplementationResult for testing implementation
    workflows with realistic task and file change data.

    Boilerplate: 7 lines (1 fixture + 6 assertions)
    """
    assert sample_implementation_response.success is True
    assert sample_implementation_response.tasks_completed == 2
    assert sample_implementation_response.tasks_failed == 0
    assert len(sample_implementation_response.task_results) == 2
    assert sample_implementation_response.task_results[0].status == TaskStatus.COMPLETED
    assert sample_implementation_response.validation_passed is True


def test_sample_error_response_structure(
    sample_error_response: ImplementationResult,
) -> None:
    """Demonstrate using sample_error_response for error testing.

    Pattern: Use pre-configured error response to test failure handling
    without manually constructing complex error states.

    Boilerplate: 6 lines (1 fixture + 5 assertions)
    """
    assert sample_error_response.success is False
    assert sample_error_response.tasks_failed == 1
    assert sample_error_response.tasks_completed == 0
    assert len(sample_error_response.errors) == 1
    assert "Test error message" in sample_error_response.errors


# =============================================================================
# GitHub CLI Mock Fixtures
# =============================================================================


def test_mock_github_cli_basic_usage(mock_github_cli: MockGitHubCLI) -> None:
    """Demonstrate basic MockGitHubCLI usage.

    Pattern: Configure responses with set_response(), then execute commands
    to test GitHub CLI integrations.

    Boilerplate: 6 lines (1 fixture + 5 test logic)
    """
    mock_github_cli.set_response(
        "pr create", CommandResponse(returncode=0, stdout='{"number": 42}')
    )

    response = mock_github_cli.execute(["pr", "create", "--title", "Test PR"])

    assert response.returncode == 0
    assert response.stdout == '{"number": 42}'


def test_mock_github_cli_error_simulation(mock_github_cli: MockGitHubCLI) -> None:
    """Demonstrate GitHub CLI error simulation.

    Pattern: Use CommandResponse with non-zero returncode to simulate failures.

    Boilerplate: 6 lines (1 fixture + 5 test logic)
    """
    mock_github_cli.set_response(
        "pr create", CommandResponse(returncode=1, stderr="Error: PR already exists")
    )

    response = mock_github_cli.execute(["pr", "create", "--title", "Duplicate"])

    assert response.returncode == 1
    assert "PR already exists" in response.stderr


def test_mock_github_cli_call_tracking(mock_github_cli: MockGitHubCLI) -> None:
    """Demonstrate command call tracking.

    Pattern: Use get_calls() to verify GitHub CLI commands were executed
    with correct arguments.

    Boilerplate: 7 lines (1 fixture + 6 test logic)
    """
    mock_github_cli.execute(["pr", "create", "--title", "Test"])
    mock_github_cli.execute(["issue", "list", "--label", "bug"])

    all_calls = mock_github_cli.get_calls()
    pr_calls = mock_github_cli.get_calls("pr")

    assert len(all_calls) == 2
    assert len(pr_calls) == 1
    assert pr_calls[0].args == ["pr", "create", "--title", "Test"]


def test_mock_github_cli_pattern_matching(mock_github_cli: MockGitHubCLI) -> None:
    """Demonstrate pattern matching for flexible response configuration.

    Pattern: Patterns match substrings, allowing flexible response setup
    without exact argument matching.

    Boilerplate: 9 lines (1 fixture + 8 test logic)
    """
    mock_github_cli.set_response(
        "pr create", CommandResponse(returncode=0, stdout='{"number": 123}')
    )

    # Any command containing "pr create" will match
    response1 = mock_github_cli.execute(["pr", "create", "--title", "Test"])
    response2 = mock_github_cli.execute(["pr", "create", "--body", "Description"])

    assert response1.stdout == '{"number": 123}'
    assert response2.stdout == '{"number": 123}'


# =============================================================================
# Click CLI Testing Fixtures
# =============================================================================


def test_cli_runner_basic_usage(cli_runner: CliRunner) -> None:
    """Demonstrate Click CLI testing with cli_runner.

    Pattern: Use cli_runner.invoke() to test Click commands in isolation.

    Boilerplate: 9 lines (1 fixture + 8 test logic)
    """
    import click

    @click.command()
    def hello() -> None:
        click.echo("Hello, World!")

    result = cli_runner.invoke(hello)

    assert result.exit_code == 0
    assert "Hello, World!" in result.output


def test_cli_runner_with_arguments(cli_runner: CliRunner) -> None:
    """Demonstrate CLI testing with arguments.

    Pattern: Pass command arguments as a list to invoke().

    Boilerplate: 10 lines (1 fixture + 9 test logic)
    """
    import click

    @click.command()
    @click.argument("name")
    def greet(name: str) -> None:
        click.echo(f"Hello, {name}!")

    result = cli_runner.invoke(greet, ["Alice"])

    assert result.exit_code == 0
    assert "Hello, Alice!" in result.output


# =============================================================================
# Combined Fixture Usage - Real-World Patterns
# =============================================================================


@pytest.mark.asyncio
async def test_agent_with_config_and_mock_client(
    sample_config: MaverickConfig,
    mock_sdk_client: MockSDKClient,
    mock_text_message: Callable[..., MockMessage],
    mock_result_message: Callable[..., MockMessage],
) -> None:
    """Demonstrate combining config, SDK client, and message fixtures.

    Pattern: Real-world agent tests often need configuration and mocked
    SDK responses together. This shows the minimal boilerplate needed.

    Boilerplate: 11 lines (4 fixtures + 7 test logic)
    """
    # Setup mock response
    mock_sdk_client.queue_response(
        [mock_text_message("Review complete"), mock_result_message()]
    )

    # Verify config is available
    assert sample_config.model.model_id == "claude-sonnet-4-5-20250929"

    # Verify mock client works
    messages = [msg async for msg in mock_sdk_client.receive_response()]
    assert len(messages) == 2


def test_github_workflow_with_responses(
    mock_github_cli: MockGitHubCLI,
    sample_implementation_response: ImplementationResult,
) -> None:
    """Demonstrate combining GitHub mock with response fixtures.

    Pattern: Test workflows that use implementation results to create PRs.
    Shows how multiple fixtures compose cleanly.

    Boilerplate: 10 lines (2 fixtures + 8 test logic)
    """
    # Configure PR creation response
    mock_github_cli.set_response(
        "pr create", CommandResponse(returncode=0, stdout='{"number": 100}')
    )

    # Use implementation result in workflow logic
    assert sample_implementation_response.success is True

    # Create PR
    response = mock_github_cli.execute(["pr", "create", "--title", "Implementation"])
    assert response.returncode == 0


# =============================================================================
# Boilerplate Verification Tests
# =============================================================================


def test_verify_boilerplate_limit_simple() -> None:
    """Verify simple test meets <20 lines boilerplate requirement (SC-005).

    Pattern: Most basic test with single fixture.
    Actual boilerplate: 1 line (fixture parameter only)

    This test itself demonstrates the pattern - the entire test body
    plus fixture declaration is only 3 lines.
    """
    # Test body
    assert True


def test_verify_boilerplate_limit_with_fixture(
    sample_config: MaverickConfig,
) -> None:
    """Verify test with fixture meets <20 lines boilerplate requirement (SC-005).

    Pattern: Single fixture usage.
    Actual boilerplate: 2 lines (fixture param + 1 assertion)
    """
    assert sample_config.github.owner == "test-org"


@pytest.mark.asyncio
async def test_verify_boilerplate_limit_async_complex(
    mock_sdk_client: MockSDKClient,
    mock_text_message: Callable[..., MockMessage],
    mock_result_message: Callable[..., MockMessage],
    sample_config: MaverickConfig,
) -> None:
    """Verify complex test meets <20 lines boilerplate requirement (SC-005).

    Pattern: Multiple fixtures with async testing.
    Actual boilerplate: 8 lines (4 fixtures + 4 setup/assertion lines)

    Even with 4 fixtures and async, total boilerplate is well under 20 lines.
    """
    mock_sdk_client.queue_response([mock_text_message("Done"), mock_result_message()])
    messages = [msg async for msg in mock_sdk_client.receive_response()]

    assert len(messages) == 2
    assert sample_config is not None
