# Feature Specification: ACP Integration

**Feature Branch**: `042-acp-integration`
**Created**: 2026-03-04
**Status**: Draft
**Input**: User description: "Replace Maverick's Claude Agent SDK integration with Agent Client Protocol (ACP) support, making ACP the execution layer between workflows and coding agents."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Workflow Executes Steps via ACP Agent (Priority: P1)

A Maverick user runs `maverick fly` to implement features from their bead queue. The workflow spawns a coding agent (Claude Code) via ACP, sends prompts for each step (implement, review, fix), collects streaming output in the TUI, and receives structured results. The user experience is identical to the current Claude Agent SDK path — the agent receives instructions, makes code changes, and returns results — but the underlying transport is now ACP over stdio JSON-RPC.

**Why this priority**: This is the core execution path. Without it, no workflow step can run.

**Independent Test**: Run a fly workflow with a single bead. Verify the ACP agent subprocess spawns, receives the prompt, streams output chunks to the TUI, and returns a result that the workflow can process.

**Acceptance Scenarios**:

1. **Given** a configured `maverick.yaml` with default ACP agent settings, **When** a workflow step executes, **Then** an ACP agent subprocess is spawned, initialized, and receives the prompt via a new ACP session.
2. **Given** an active ACP session, **When** the agent produces output, **Then** streaming chunks (text, thinking, tool calls) appear in the Maverick TUI in real time.
3. **Given** an active ACP session, **When** the agent completes its work, **Then** the executor returns an `ExecutorResult` with the agent's text output and any structured output parsed from it.
4. **Given** a step that requires structured output (e.g., decomposition), **When** the agent returns JSON text, **Then** the executor parses and validates it against the expected Pydantic schema.
5. **Given** an ACP agent subprocess is already running, **When** a subsequent workflow step executes for the same provider, **Then** the existing connection is reused (no redundant subprocess spawn).

---

### User Story 2 - Configurable Agent Providers (Priority: P2)

A Maverick user configures multiple ACP-compatible coding agents in their `maverick.yaml` (e.g., Claude Code as default, Gemini CLI for specific steps). Each agent provider has its own spawn command, environment variables, and permission mode. Workflow steps can select a specific provider via `StepConfig.provider`, or fall back to the default.

**Why this priority**: Multi-agent support is the architectural differentiator of the ACP migration. It must be designed correctly from the start, even if only one agent (Claude Code) ships initially.

**Independent Test**: Configure two agent entries in `maverick.yaml`. Run a step with `provider: "claude"` and another with `provider: "gemini"`. Verify each step spawns the correct agent subprocess.

**Acceptance Scenarios**:

1. **Given** a `maverick.yaml` with an `agent_providers` section containing one entry marked `default: true`, **When** a step has no explicit provider, **Then** the default agent is used.
2. **Given** a `maverick.yaml` with multiple `agent_providers` entries, **When** a step specifies `provider: "gemini"`, **Then** the gemini agent subprocess is spawned with its configured command and env.
3. **Given** a `maverick.yaml` without an `agent_providers` section, **When** a workflow runs, **Then** a sensible default (Claude Code via ACP) is used automatically.
4. **Given** a `maverick.yaml` with two `agent_providers` entries both marked `default: true`, **When** configuration loads, **Then** a validation error is raised.

---

### User Story 3 - Error Resilience and Safety (Priority: P2)

When an ACP agent subprocess crashes, times out, or enters a runaway loop, Maverick detects the failure and maps it to the appropriate error in its exception hierarchy. The circuit breaker prevents infinite tool-call loops. Retry logic re-attempts failed steps with fresh sessions. Safety validators gate dangerous tool calls before they execute.

**Why this priority**: Without resilience, a single agent failure can crash the entire workflow, violating the "fail gracefully" principle.

**Independent Test**: Simulate agent subprocess crash, timeout, and excessive tool calls. Verify each triggers the correct Maverick exception and the workflow continues or fails gracefully.

**Acceptance Scenarios**:

1. **Given** an ACP agent subprocess that exits unexpectedly, **When** the executor detects the exit, **Then** a `ProcessError` is raised and the workflow's error handling captures it.
2. **Given** a step with a configured timeout, **When** the agent does not respond within the timeout period, **Then** a timeout error is raised and the ACP session is cancelled.
3. **Given** an agent that makes more than 15 calls to the same tool, **When** the circuit breaker threshold is reached, **Then** a circuit breaker error is raised and the session is cancelled.
4. **Given** a step with retry configuration, **When** the first attempt fails, **Then** the executor retries with a fresh ACP session (reusing the connection) up to the configured maximum.
5. **Given** permission mode `"deny_dangerous"`, **When** an agent requests a tool call that matches a dangerous pattern, **Then** the permission is denied and the agent receives an error response.

---

### User Story 4 - Clean SDK Removal (Priority: P3)

After the migration, the `claude-agent-sdk` package is no longer a dependency. No imports, mocks, or references to the SDK remain anywhere in the codebase. The `MaverickAgent` base class is a pure prompt-construction container without any SDK coupling. All tests are updated to mock ACP interactions instead.

**Why this priority**: This is the cleanup story. It can only be completed after the ACP path is fully functional, but it must be done to avoid carrying dead code.

**Independent Test**: Remove `claude-agent-sdk` from the virtualenv and run `make check`. All tests pass, no import errors occur, and the full test suite is green.

**Acceptance Scenarios**:

1. **Given** the completed ACP migration, **When** `claude-agent-sdk` is removed from dependencies, **Then** dependency resolution succeeds and no runtime import errors occur.
2. **Given** the refactored `MaverickAgent`, **When** inspecting the source, **Then** no `claude_agent_sdk` imports exist (neither runtime nor type-checking).
3. **Given** the updated test suite, **When** running the full test suite, **Then** all tests pass without mocking any `claude_agent_sdk` types.

---

### Edge Cases

- What happens when Node.js is not installed and `npx` is not available? The executor raises a clear error about the Node.js prerequisite at the first workflow step, not at config load time.
- What happens when the ACP agent subprocess is killed by the OS (OOM, SIGKILL)? The executor detects the abnormal exit and raises the appropriate process error.
- What happens when `maverick.yaml` has no `agents` section and no Node.js is available? The default Claude Code agent fails to spawn at the first workflow step with a clear error.
- What happens when the agent returns malformed JSON for a structured output step? The executor raises a schema validation error with the raw text included for debugging.
- What happens when two workflow steps try to use different providers concurrently? Each provider has its own cached connection; concurrent sessions on different providers are independent.
- What happens when a configured agent command does not exist on the system? The executor raises a clear "command not found" error identifying the missing binary.
- What happens when a cached ACP connection drops mid-workflow (clean disconnect)? The executor transparently re-spawns the subprocess and re-initializes. If reconnect also fails, the error is raised to the workflow.
- What happens when parallel workflow steps need the same provider? Each parallel step uses its own connection (separate subprocess), since connections are one-session-at-a-time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST replace the `claude-agent-sdk` dependency with `agent-client-protocol` as the agent communication layer.
- **FR-002**: System MUST support an `agents` configuration section in `maverick.yaml` defining named ACP agent providers with spawn command, environment overrides, permission mode, and default flag.
- **FR-003**: System MUST provide a sensible default agent configuration (Claude Code via ACP) when no `agents` section is present in `maverick.yaml`.
- **FR-004**: System MUST implement a new step executor conforming to the existing `StepExecutor` protocol, managing ACP subprocess lifecycle (spawn, initialize, session creation, prompt, response collection, cleanup).
- **FR-005**: System MUST cache ACP connections per provider and reuse them across multiple step executions within the same workflow run. Each connection supports one session at a time; parallel execution requires separate provider connections.
- **FR-006**: System MUST convert prompt inputs (strings, objects with conversion methods) into ACP-compatible content before sending.
- **FR-007**: System MUST prepend agent instructions to prompts using a delimited framing format when instructions are provided.
- **FR-008**: System MUST map ACP streaming update events (message chunks, thinking chunks, tool call updates, tool result updates) to Maverick's existing streaming event types and forward them via the event callback.
- **FR-009**: System MUST implement permission handling on the ACP client, supporting auto-approve, deny-dangerous, and interactive modes.
- **FR-010**: System MUST extract structured output by accumulating all agent text chunks and extracting the last JSON block (fenced or raw brace-matched), then validating against the provided schema.
- **FR-011**: System MUST map ACP and subprocess errors to Maverick's existing exception hierarchy.
- **FR-012**: System MUST enforce step timeouts on the prompt-to-response cycle.
- **FR-013**: System MUST implement circuit breaker logic tracking tool call counts from ACP streaming events, with configurable thresholds.
- **FR-014**: System MUST implement retry logic, creating fresh ACP sessions on each retry while reusing the connection.
- **FR-015**: System MUST provide a registry that resolves provider names to configurations and validates exactly one default exists.
- **FR-016**: System MUST allow step configuration to specify any configured agent provider name, not just a single hardcoded value.
- **FR-017**: System MUST refactor the agent base class into a pure prompt-construction container, removing all SDK coupling. Concrete agents provide a method to construct prompts from typed context; the executor handles agent interaction.
- **FR-018**: System MUST remove all references to the previous SDK from source code, test code, and dependency declarations.
- **FR-019**: System MUST implement graceful cleanup that terminates all spawned agent subprocesses, wired into workflow teardown.
- **FR-020**: System MUST update all unit tests to mock ACP interactions instead of previous SDK types.
- **FR-021**: System MUST transparently reconnect (re-spawn subprocess, re-initialize) on ACP connection drop, with one reconnect attempt before raising an error.
- **FR-022**: System MUST pass cwd as an ACP session parameter per step, while also spawning the agent subprocess with the project/workspace root as the default working directory.
- **FR-023**: System MUST log ACP lifecycle events: spawn and cleanup at info level, per-session details (session create, prompt send, response complete) at debug level.

### Key Entities

- **AgentProviderConfig**: A named agent provider configuration with spawn command, environment overrides, permission mode, and default flag.
- **AgentProviderRegistry**: A lookup service that resolves provider names to their configurations and identifies the default provider.
- **AcpStepExecutor**: The executor that manages ACP subprocess lifecycle and implements the step executor protocol.
- **AgentPromptBuilder**: The new agent contract — a prompt-construction protocol replacing the SDK-coupled query pattern.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing workflow steps (implement, review, fix, decompose, curate) complete successfully using the ACP execution path with no behavioral regression.
- **SC-002**: The full validation suite passes with zero references to the previous SDK remaining in source or test code.
- **SC-003**: Agent subprocess connections are reused across steps — a workflow running multiple steps against the same provider spawns exactly 1 subprocess.
- **SC-004**: Circuit breaker triggers promptly upon exceeding the same-tool-call threshold, cancelling the ACP session.
- **SC-005**: Step timeout enforcement cancels the ACP session and raises an error within a few seconds of the configured timeout expiring.
- **SC-006**: A project configuration file without an `agents` section works out-of-the-box using the default Claude Code ACP agent.
- **SC-007**: Configuring a second agent provider and selecting it via step configuration routes execution to that agent's subprocess.
- **SC-008**: Structured output extraction successfully parses and validates agent JSON responses against schemas with the same reliability as the current path.

## Clarifications

### Session 2026-03-04

- Q: Can the executor run multiple ACP sessions concurrently on the same connection? → A: One session at a time per connection (sequential only). Parallel execution uses separate provider connections.
- Q: How should the executor extract JSON for structured output from multi-chunk agent responses? → A: Accumulate all text chunks, extract the last JSON block (fenced or raw brace-matched).
- Q: Should the executor transparently reconnect on mid-workflow ACP connection drop? → A: Yes, transparent reconnect with a single re-spawn and re-initialize attempt before raising an error.
- Q: How should cwd be passed to ACP sessions? → A: Both — spawn subprocess with project/workspace root as default cwd, and pass cwd as an ACP session parameter per step to support workspace isolation.
- Q: Should ACP lifecycle events be logged? → A: Info level for spawn/cleanup boundaries, debug level for per-session details (session create, prompt send, response complete).

## Assumptions

- Node.js 18+ is available on the host system for the Claude Code ACP adapter. This is a runtime prerequisite, not something Maverick installs.
- The `agent-client-protocol` Python package provides subprocess spawning, schema models, client interfaces, and content helpers as documented.
- ACP agents receive their system prompt internally (e.g., Claude Code uses its built-in preset). Maverick injects per-step instructions into the user prompt, not as a separate system prompt field.
- Token-level usage metrics are not available through ACP. Usage tracking will be deferred until ACP extensions provide this data.
- The `StepExecutor` protocol, `ExecutorResult`, `UsageMetadata`, workflow call sites, safety hooks, flight plan models, and workflow logic are all stable and must not change.

## Scope Boundaries

**In scope**:
- ACP executor implementation
- Agent provider configuration model and registry
- Agent base class refactoring to prompt-builder pattern
- Removal of previous SDK dependency and all references
- Test updates for ACP mocking
- Default configuration for zero-config Claude Code usage

**Out of scope**:
- Implementing additional ACP agents beyond Claude Code (architecture supports it; actual agents are future work)
- Token usage tracking via ACP (deferred until ACP provides usage extensions)
- Interactive permission mode implementation (stub only; auto-approve and deny-dangerous are implemented)
- Node.js installation or version management
- Changes to workflow logic, step ordering, checkpointing, or rollback
- Changes to safety hooks, flight plan models, or CLI command interfaces
