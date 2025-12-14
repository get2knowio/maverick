# Feature Specification: Base Agent Abstraction Layer

**Feature Branch**: `002-base-agent`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for the base agent abstraction layer in Maverick, building on the project foundation."

## Clarifications

### Session 2025-12-12

- Q: When a second agent attempts to register with a name already in use, what should the registry do? → A: Raise exception immediately on duplicate registration (fail fast).
- Q: When an agent execution times out or encounters a network error, should the base class automatically retry? → A: No retries at base layer; return error immediately and let caller decide retry policy.
- Q: When a streaming response fails partway through, what should query() do with the partial content? → A: Yield partial content received so far, then raise exception.
- Q: When should validation of allowed_tools against available MCP servers occur? → A: Validate at agent construction time; raise error if any tool name is invalid.
- Q: How should malformed or unparseable responses from Claude be handled? → A: Wrap in MalformedResponseError with raw response attached for debugging.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a Simple Agent (Priority: P1)

A developer wants to create a new agent for a specific task (e.g., code review, documentation generation). They define a system prompt and implement the execute method, inheriting all common functionality from the base class.

**Why this priority**: This is the primary use case - the base abstraction exists to make agent creation trivial. Without this working, the entire abstraction has no value.

**Independent Test**: Can be fully tested by creating a minimal test agent with a system prompt and verifying it can execute and return structured results.

**Acceptance Scenarios**:

1. **Given** a developer defines a class inheriting from `MaverickAgent` with a name, system prompt, and allowed tools, **When** they implement the `execute()` method, **Then** the agent is fully functional and can interact with Claude.
2. **Given** a minimal agent implementation, **When** the developer calls `execute()` with a context, **Then** they receive a structured `AgentResult` with success status, output, metadata, errors, and usage statistics.

---

### User Story 2 - Stream Agent Responses (Priority: P2)

A developer wants to stream responses from an agent for real-time display in the TUI. They use the `query()` helper method to get an async iterator of messages as they arrive.

**Why this priority**: Streaming is essential for TUI responsiveness during long-running agent operations. This directly supports the async-first principle.

**Independent Test**: Can be tested by calling `query()` and verifying messages arrive incrementally as an async iterator.

**Acceptance Scenarios**:

1. **Given** an agent instance, **When** a developer calls `query()` with a prompt, **Then** they receive an async iterator yielding messages as they stream from Claude.
2. **Given** streaming is active, **When** the TUI consumes messages from the iterator, **Then** each message can be displayed immediately without waiting for full completion.

---

### User Story 3 - Discover and Instantiate Agents (Priority: P2)

A workflow orchestrator needs to dynamically discover available agents and instantiate them by name. They use the agent registry to look up and create agent instances with injected dependencies.

**Why this priority**: Workflows need to orchestrate multiple agents dynamically. The registry pattern enables loose coupling between workflows and specific agent implementations.

**Independent Test**: Can be tested by registering agents, then looking them up by name and instantiating them with provided configuration.

**Acceptance Scenarios**:

1. **Given** multiple agent classes registered with the registry, **When** a workflow requests an agent by name, **Then** the registry returns the corresponding agent class.
2. **Given** an agent class from the registry, **When** the workflow instantiates it with configuration and dependencies, **Then** a fully configured agent instance is created.

---

### User Story 4 - Extract Structured Output from Responses (Priority: P3)

A developer needs to extract text content from Claude's `AssistantMessage` responses for further processing. They use the provided utility methods to get clean text without manually parsing message structures.

**Why this priority**: While necessary, this is a convenience utility. Developers could manually extract content, but utilities reduce boilerplate and ensure consistency.

**Independent Test**: Can be tested by providing sample `AssistantMessage` objects and verifying correct text extraction.

**Acceptance Scenarios**:

1. **Given** an `AssistantMessage` with text content, **When** the developer calls the extraction utility, **Then** they receive the plain text content.
2. **Given** an `AssistantMessage` with mixed content types, **When** the developer calls the extraction utility, **Then** only text content is extracted and concatenated appropriately.

---

### User Story 5 - Handle Agent Errors Gracefully (Priority: P3)

An agent encounters an error during execution (CLI not found, process error, etc.). The error is caught, wrapped with context, and returned in a structured format that workflows can handle.

**Why this priority**: Error handling is essential for the fail-gracefully principle but is a cross-cutting concern built into the base functionality.

**Independent Test**: Can be tested by simulating error conditions and verifying structured error responses are returned.

**Acceptance Scenarios**:

1. **Given** the Claude CLI is not installed, **When** an agent attempts to execute, **Then** a clear error message explains the missing dependency.
2. **Given** a process error occurs during execution, **When** the error is caught, **Then** it is wrapped with context and included in the `AgentResult.errors` list.
3. **Given** an agent execution fails, **When** the result is returned, **Then** `success` is `False` and meaningful error information is available for logging and user feedback.

---

### Edge Cases

- What happens when the Claude CLI is not found in PATH? → Raises `CLINotFoundError` with actionable message (covered by User Story 5).
- How does the system handle network timeouts during agent execution? → Returns error immediately with no automatic retry; caller (workflow) decides retry policy.
- What happens when an agent's allowed_tools list references a tool that doesn't exist? → Raises `InvalidToolError` at construction time (fail fast).
- How are malformed responses from Claude handled? → Wraps in `MalformedResponseError` with raw response attached for debugging.
- What happens when the agent registry has duplicate name registrations? → Raises `DuplicateAgentError` immediately (fail fast).
- How does the system handle partial streaming failures mid-response? → Yields partial content received, then raises `StreamingError`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an abstract base class `MaverickAgent` that wraps Claude Agent SDK interactions.
- **FR-002**: `MaverickAgent` MUST accept a name, system prompt, allowed tools list, and model configuration at construction; MUST validate allowed tools against available MCP servers and raise `InvalidToolError` for unknown tool names.
- **FR-003**: `MaverickAgent` MUST build `ClaudeAgentOptions` with sensible defaults for common settings (e.g., timeout, max tokens).
- **FR-004**: `MaverickAgent` MUST provide an abstract async method `execute(context: AgentContext) -> AgentResult` for subclasses to implement.
- **FR-005**: `MaverickAgent` MUST provide a helper method `query(prompt: str) -> AsyncIterator[Message]` for streaming responses; on mid-stream failure, MUST yield partial content before raising `StreamingError`.
- **FR-006**: System MUST provide utility functions for extracting text content from `AssistantMessage` objects.
- **FR-007**: System MUST catch and wrap common errors (`CLINotFoundError`, `ProcessError`, `TimeoutError`, `NetworkError`, `StreamingError`, `MalformedResponseError`, `InvalidToolError`, `DuplicateAgentError`) with clear, actionable error messages; no automatic retries at the base layer.
- **FR-008**: System MUST provide an `AgentResult` dataclass containing: success (bool), output (str), metadata (dict), errors (list), and usage statistics (tokens, cost, duration). When `success` is `False`, the `errors` list MUST contain at least one error with actionable context.
- **FR-009**: System MUST provide an `AgentContext` dataclass for passing runtime context to agents including working directory, branch name, and configuration.
- **FR-010**: System MUST provide an agent registry for discovering and instantiating agents by name.
- **FR-011**: Agent registry MUST support registration of agent classes with unique names; duplicate registration attempts MUST raise `DuplicateAgentError` immediately.
- **FR-012**: Agent registry MUST support lookup of agent classes by name.
- **FR-013**: All agent methods involving I/O MUST be async following the async-first principle.
- **FR-014**: `AgentResult` MUST include usage statistics: input tokens, output tokens, total cost (if available), and execution duration.

### Key Entities

- **MaverickAgent**: Abstract base class representing an AI agent that can execute tasks via Claude. Contains name, system prompt, allowed tools, and model configuration. Provides common functionality for all concrete agents.
- **AgentResult**: Value object representing the outcome of an agent execution. Contains success status, output content, arbitrary metadata, error information, and usage statistics.
- **AgentContext**: Value object containing runtime context passed to agent execution. Includes working directory path, git branch name, configuration object, and any additional context needed by specific agents.
- **AgentRegistry**: Service for registering, discovering, and instantiating agents. Maps unique agent names to their implementing classes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can create a fully functional agent by implementing only the `execute()` method and defining a system prompt - no additional boilerplate required.
- **SC-002**: Agent execution returns structured results within 100ms overhead beyond Claude's actual response time. Measurement: `AgentResult.usage.duration_ms` minus time spent waiting for Claude API responses (logged separately). Validated via integration tests with mocked Claude responses.
- **SC-003**: Streaming responses begin arriving to consumers within 500ms of calling `query()`. Measurement: Time from `query()` invocation to first `yield` of a Message. Excludes Claude API latency; measures only internal processing overhead. Validated via integration tests with mocked streaming.
- **SC-004**: All common errors (missing CLI, process failures, network issues) are caught and reported with actionable error messages.
- **SC-005**: The agent registry can instantiate any registered agent by name without the caller knowing the concrete class.
- **SC-006**: Usage statistics (tokens, duration) are accurately captured for every agent execution for monitoring and cost tracking.
- **SC-007**: Zero business logic exists in concrete agents beyond their specific task implementation - all common functionality is in the base class.

## Assumptions

- The Claude Agent SDK is installed and available (`claude-agent-sdk` package).
- The `claude` CLI is installed and accessible in the system PATH for agents to function.
- Agents will primarily be instantiated by workflows, not directly by users.
- Model configuration (model ID, max tokens, etc.) can have sensible defaults that cover most use cases.
- The async generator pattern from the Claude SDK is the primary streaming mechanism.
- Cost tracking may not be available for all model interactions; the field should be optional.

## Dependencies

- Claude Agent SDK (`claude-agent-sdk`) - core AI interaction capability
- Pydantic - for configuration and data model validation
- Python 3.10+ - for async features and type hint support
