# Data Model: Testing Infrastructure

**Feature Branch**: `015-testing-infrastructure`
**Date**: 2025-12-17
**Status**: Complete

## Overview

This document defines the key entities and data structures for the Testing Infrastructure feature. Since this feature primarily provides test fixtures and utilities rather than persistent data, the entities are focused on mock objects and test helper classes.

---

## Entities

### 1. MockSDKClient

**Purpose**: Simulates Claude Agent SDK's `ClaudeSDKClient` for testing agents without real API calls.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `_responses` | `list[list[MockMessage]]` | FIFO queue of response sequences |
| `_response_index` | `int` | Current position in response queue |
| `query_calls` | `list[str]` | Record of prompts sent to query() |
| `options_used` | `ClaudeAgentOptions \| None` | Last options passed to client |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `queue_response` | `(messages: list[MockMessage]) -> None` | Add response sequence to queue |
| `queue_error` | `(error: Exception) -> None` | Queue an error to be raised |
| `query` | `async (prompt: str) -> None` | Record prompt, prepare for streaming |
| `receive_response` | `async () -> AsyncGenerator[MockMessage]` | Yield queued messages |
| `reset` | `() -> None` | Clear all state for test isolation |

**Relationships**:
- Contains `MockMessage` objects
- Used by agent test fixtures

---

### 2. MockMessage

**Purpose**: Represents a message from the Claude Agent SDK (TextMessage or ResultMessage).

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `message_type` | `str` | "TextMessage" or "ResultMessage" |
| `text` | `str \| None` | Message content (TextMessage only) |
| `usage` | `dict[str, int] \| None` | Token usage (ResultMessage only) |
| `total_cost_usd` | `float \| None` | Cost in USD (ResultMessage only) |
| `duration_ms` | `int \| None` | Duration in milliseconds (ResultMessage only) |

**Validation Rules**:
- `message_type` must be one of: "TextMessage", "ResultMessage"
- `usage` must contain `input_tokens` and `output_tokens` keys if present
- `total_cost_usd` must be non-negative if present

**State Transitions**: N/A (immutable value object)

---

### 3. MockGitHubCLI

**Purpose**: Simulates GitHub CLI (`gh`) command responses for testing GitHub integrations.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `_command_responses` | `dict[str, CommandResponse]` | Map of command patterns to responses |
| `_call_history` | `list[CommandCall]` | Record of all commands executed |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `set_response` | `(pattern: str, response: CommandResponse) -> None` | Configure response for command pattern |
| `execute` | `(args: list[str]) -> CommandResponse` | Simulate gh command execution |
| `get_calls` | `(pattern: str \| None) -> list[CommandCall]` | Get recorded calls, optionally filtered |

**Nested Types**:

```python
@dataclass
class CommandResponse:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

@dataclass
class CommandCall:
    args: list[str]
    timestamp: datetime
```

---

### 4. AsyncGeneratorCapture

**Purpose**: Utility to collect all items from an async generator for assertion.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `items` | `list[T]` | Collected items from generator |
| `error` | `Exception \| None` | Error if generator raised |
| `completed` | `bool` | Whether generator finished normally |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `capture` | `async (gen: AsyncGenerator[T]) -> AsyncGeneratorCapture[T]` | Collect all items |
| `__len__` | `() -> int` | Number of captured items |
| `__iter__` | `() -> Iterator[T]` | Iterate captured items |

---

### 5. AgentResultAssertion

**Purpose**: Helper for asserting on `AgentResult` contents with clear error messages.

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `assert_success` | `(result: AgentResult) -> None` | Assert result.success is True |
| `assert_failure` | `(result: AgentResult, error_type: type \| None) -> None` | Assert failure with optional error type |
| `assert_output_contains` | `(result: AgentResult, expected: str) -> None` | Assert output contains string |
| `assert_usage` | `(result: AgentResult, min_tokens: int \| None, max_cost: float \| None) -> None` | Assert usage within bounds |

---

### 6. MCPToolValidator

**Purpose**: Validates MCP tool responses against expected schemas.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `_schemas` | `dict[str, dict]` | Registered tool response schemas |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_schema` | `(tool_name: str, schema: dict) -> None` | Register expected schema |
| `validate` | `(tool_name: str, response: Any) -> ValidationResult` | Validate response against schema |
| `assert_valid` | `(tool_name: str, response: Any) -> None` | Raise if invalid |

---

### 7. TestWorkflowRunner

**Purpose**: Utility for running workflows with mocked agents and capturing progress events.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `events` | `list[WorkflowEvent]` | Captured progress events |
| `result` | `WorkflowResult \| None` | Final workflow result |
| `duration_ms` | `int` | Total execution time |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `run` | `async (workflow: Workflow) -> WorkflowResult` | Execute and capture events |
| `get_events` | `(event_type: type \| None) -> list[WorkflowEvent]` | Filter captured events |
| `assert_stage_passed` | `(stage_name: str) -> None` | Assert specific stage passed |

---

## Test Fixture Scopes

| Fixture | Scope | Description |
|---------|-------|-------------|
| `mock_sdk_client` | function | Fresh mock client per test |
| `mock_text_message` | function | Factory for text messages |
| `mock_result_message` | function | Factory for result messages |
| `mock_github_cli` | function | Fresh GitHub CLI mock per test |
| `sample_config` | function | Sample MaverickConfig |
| `temp_dir` | function | Temporary directory (existing) |
| `clean_env` | function | Clean environment vars (existing) |
| `cli_runner` | function | Click CliRunner instance |

---

## Entity Relationships

```
MockSDKClient
    └── contains → MockMessage[]
    └── uses → ClaudeAgentOptions (mocked)

MockGitHubCLI
    └── returns → CommandResponse
    └── records → CommandCall[]

AsyncGeneratorCapture[T]
    └── captures from → AsyncGenerator[T]

AgentResultAssertion
    └── asserts on → AgentResult

MCPToolValidator
    └── validates → MCP tool responses

TestWorkflowRunner
    └── captures → WorkflowEvent[]
    └── uses → mocked agents
```

---

## Validation Rules Summary

| Entity | Rule | Enforcement |
|--------|------|-------------|
| MockMessage | Valid message_type | Constructor validation |
| MockMessage | Non-negative cost | Pydantic/dataclass validation |
| MockSDKClient | Response queue not empty for receive | Graceful empty iteration |
| MockGitHubCLI | Valid returncode range | No enforcement (test flexibility) |
| AsyncGeneratorCapture | Generator must be async | Type hints + runtime check |

---

## Usage Examples

### Agent Testing

```python
@pytest.fixture
def mock_sdk_client() -> MockSDKClient:
    return MockSDKClient()

@pytest.fixture
def mock_text_message():
    def _create(text: str = "Response") -> MockMessage:
        return MockMessage("TextMessage", text=text)
    return _create

@pytest.mark.asyncio
async def test_agent_query(mock_sdk_client, mock_text_message, mock_result_message):
    mock_sdk_client.queue_response([
        mock_text_message("Here's the result"),
        mock_result_message(),
    ])

    agent = MyAgent(name="test", system_prompt="...", allowed_tools=[])

    with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk()}):
        messages = []
        async for msg in agent.query("Test prompt"):
            messages.append(msg)

    assert len(messages) == 2
    assert mock_sdk_client.query_calls == ["Test prompt"]
```

### Async Generator Capture

```python
@pytest.mark.asyncio
async def test_workflow_events():
    workflow = ValidationWorkflow(stages=[...])

    capture = await AsyncGeneratorCapture.capture(workflow.run())

    assert capture.completed
    assert len(capture) >= 3  # At least start, progress, complete
    assert any(isinstance(e, WorkflowCompleted) for e in capture)
```

### MCP Tool Validation

```python
def test_github_tool_response():
    validator = MCPToolValidator()
    validator.register_schema("create_pr", {
        "type": "object",
        "required": ["url", "number"],
        "properties": {
            "url": {"type": "string"},
            "number": {"type": "integer"},
        }
    })

    response = {"url": "https://github.com/...", "number": 123}
    validator.assert_valid("create_pr", response)
```
