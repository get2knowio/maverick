# Research: ACP Integration

**Feature**: 042-acp-integration | **Date**: 2026-03-04

## R-001: ACP Python SDK API Surface

**Decision**: Use `agent-client-protocol` (PyPI) v0.8.1+ as the ACP client library.

**Rationale**: Official Python SDK maintained by the ACP project (originally Zed Industries). Pydantic 2.x models, async-first, Python 3.10+ — matches Maverick's stack exactly.

**Alternatives considered**:
- Raw JSON-RPC over stdio: Too low-level; would duplicate connection management, schema parsing, and error handling that the SDK provides.
- Claude Agent SDK's ACP shim (if any): None exists; the SDK is its own protocol.

### Key API Patterns

**Subprocess Spawn** (`spawn_agent_process`):
```python
from acp import spawn_agent_process, PROTOCOL_VERSION, text_block
from acp.schema import ClientCapabilities, Implementation

async with spawn_agent_process(
    client_impl,         # Client subclass (handles permissions, streaming)
    command,             # e.g., "npx" or "claude"
    *args,               # e.g., "--acp"
    cwd=project_root,    # Subprocess working directory
    env=env_overrides,   # Optional env dict
) as (conn, proc):
    await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(),
        client_info=Implementation(name="maverick", title="Maverick", version="..."),
    )
    session = await conn.new_session(cwd=str(workspace_path), mcp_servers=[])
    response = await conn.prompt(session_id=session.session_id, prompt=[text_block("...")])
```

**Streaming**: All streaming events arrive via `Client.session_update()` callback — not from the `prompt()` return value. `prompt()` blocks until the agent completes the turn.

**Session Update Types**:
| Type | Maps To (Maverick) |
|------|-------------------|
| `AgentMessageChunk` (TextContentBlock) | `AgentStreamChunk(chunk_type="output")` |
| `AgentThoughtChunk` (TextContentBlock) | `AgentStreamChunk(chunk_type="thinking")` |
| `ToolCallStart` | `AgentStreamChunk(chunk_type="output", text="[TOOL] ...")` |
| `ToolCallProgress` | `AgentStreamChunk(chunk_type="output", text="...")` |

**Permission Handling**: `Client.request_permission()` receives `PermissionOption` list and `ToolCall` context. Returns `RequestPermissionResponse` with outcome.

**No Built-in Reconnect**: If the subprocess dies, you must spawn a new one and re-initialize. `load_session(session_id=...)` can resume a previous session if the agent supports it.

---

## R-002: Mapping ACP to Existing StepExecutor Protocol

**Decision**: Implement `AcpStepExecutor` as a new `StepExecutor` implementation, replacing `ClaudeStepExecutor`. The `StepExecutor` protocol is already provider-agnostic (zero SDK imports).

**Rationale**: The protocol's `execute()` signature already accepts all parameters needed for ACP: `prompt` (converted to ACP content), `cwd` (passed to `new_session`), `instructions` (prepended to prompt), `output_schema` (post-processed from accumulated text), `config` (timeout, retry). No protocol changes needed.

**Key Mapping**:
| StepExecutor Parameter | ACP Equivalent |
|----------------------|----------------|
| `prompt` | Converted to `[text_block(...)]` via `_build_acp_prompt()` |
| `instructions` | Prepended to prompt with delimiter |
| `cwd` | `conn.new_session(cwd=str(cwd))` |
| `output_schema` | Post-process: accumulate text chunks → extract last JSON block → validate |
| `config.timeout` | `asyncio.wait_for(conn.prompt(...), timeout=config.timeout)` |
| `config.max_retries` | `tenacity.AsyncRetrying` around execute, fresh session per retry |
| `event_callback` | Called from `Client.session_update()` with mapped `AgentStreamChunk` |

---

## R-003: Agent Provider Configuration Model

**Decision**: Add `AgentProviderConfig` Pydantic model and `agents_acp` section to `MaverickConfig`. Separate from the existing `agents` dict (which holds per-agent model/token overrides).

**Rationale**: The existing `AgentConfig` holds per-logical-agent overrides (implementer, reviewer, etc.). The new `AgentProviderConfig` holds per-ACP-provider settings (Claude Code, Gemini CLI, etc.). These are orthogonal: a logical agent (implementer) selects a provider (claude) which determines the subprocess command.

**Schema**:
```yaml
# maverick.yaml
agent_providers:
  claude:
    command: ["npx", "@anthropic-ai/claude-code@latest", "--acp"]
    env:
      ANTHROPIC_API_KEY: "..."
    permission_mode: "auto_approve"  # auto_approve | deny_dangerous | interactive
    default: true
  gemini:
    command: ["gemini", "--acp"]
    env: {}
    permission_mode: "auto_approve"
    default: false
```

**Default (zero-config)**: When no `agent_providers` section exists, a default Claude Code entry is synthesized:
```python
AgentProviderConfig(
    command=["npx", "@anthropic-ai/claude-code@latest", "--acp"],
    permission_mode="auto_approve",
    default=True,
)
```

---

## R-004: Structured Output Extraction Strategy

**Decision**: Accumulate all `AgentMessageChunk` text content during streaming. After `prompt()` completes, extract the last JSON block from the accumulated text. Validate against `output_schema` via `model.model_validate_json()`.

**Rationale**: ACP agents return free-form text (they are coding agents, not API models). Structured output must be extracted from the text stream. The "last JSON block" heuristic matches the current `ClaudeStepExecutor` behavior and handles agents that emit explanatory text before/after JSON.

**Extraction Algorithm**:
1. Accumulate all `AgentMessageChunk` text into a buffer
2. Search for the last fenced code block (` ```json ... ``` `) — extract content
3. If no fenced block, search for the last top-level `{...}` using brace matching
4. Parse extracted string as JSON
5. Validate via `output_schema.model_validate(parsed_dict)`

**Alternatives considered**:
- Rely on ACP `structured_output` extension: Not available in ACP v0.8.x.
- Require agents to only output JSON: Too restrictive for coding agents that need to explain their work.

---

## R-005: MaverickAgent Refactoring Strategy

**Decision**: Refactor `MaverickAgent` into a prompt-construction-only base class. Remove `query()`, `_build_options()`, `_wrap_sdk_error()`, `_extract_usage()`, `_extract_structured_output()`, `_extract_tool_calls()`, `_check_circuit_breaker()` — all SDK-coupled methods. Replace `execute(context) -> TResult` with `build_prompt(context) -> str` as the single abstract method.

**Rationale**: The spec requires agents to become pure prompt containers (FR-017). The executor owns all interaction concerns (spawning, streaming, retry, circuit breaking). This cleanly separates "what to say" (agents) from "how to say it" (executor).

**Migration Path for Concrete Agents**:
Each agent's `execute()` currently: (1) builds a prompt string from context, (2) calls `self.query()`, (3) processes messages, (4) returns typed result. After refactoring:
- Step (1) becomes `build_prompt()` — the new abstract method
- Steps (2-4) move to `AcpStepExecutor`
- Typed result construction moves to executor's output processing

**Impact**: All concrete agents (implementer, code_reviewer, fixer, issue_fixer, decomposer, curator, flight_plan_generator) must be updated. Each is relatively small — the `execute()` method is typically 20-40 lines of prompt building + `self.query()` call.

---

## R-006: Connection Lifecycle and Caching

**Decision**: `AcpStepExecutor` caches one `(ClientSideConnection, Process)` tuple per provider name. Connections are created lazily on first use and reused across step executions. Each step execution creates a fresh session on the cached connection. Parallel steps use separate connections (one per parallel task).

**Rationale**: ACP connections are one-session-at-a-time. Sequential steps within a workflow can share a connection (creating a new session each time), but parallel steps need separate connections. Caching avoids redundant subprocess spawns for sequential execution (SC-003).

**Lifecycle**:
1. `execute()` → `_get_or_create_connection(provider_name)` → returns cached or spawns new
2. `conn.new_session(cwd=...)` → fresh session for this step
3. `conn.prompt(...)` → execute the prompt
4. Session completes → connection stays cached for next step
5. `cleanup()` → terminates all cached subprocesses (wired into workflow teardown)

**Reconnect on Drop**: If `prompt()` raises a transport error, attempt one reconnect: close old connection, spawn fresh subprocess, re-initialize, create new session, retry the prompt. If the retry also fails, raise the error.

---

## R-007: Circuit Breaker in ACP Context

**Decision**: Track tool call counts from `ToolCallStart` events in `Client.session_update()`. When count for any single tool exceeds `MAX_SAME_TOOL_CALLS` (15), call `conn.cancel(session_id)` to abort, then raise `CircuitBreakerError`.

**Rationale**: The current circuit breaker in `MaverickAgent.query()` tracks tool calls from SDK messages. In ACP, tool calls are visible via `ToolCallStart` streaming events. The logic is identical but the observation point moves from message iteration to the `session_update` callback.

**Implementation**: The `MaverickAcpClient` (our `Client` subclass) maintains a `tool_call_counts` dict per session. `session_update()` increments counts on `ToolCallStart`. When threshold is exceeded, it sets an `_abort` flag and calls `conn.cancel()`. The `prompt()` await in the executor then completes (or raises), and the executor checks the abort flag to raise `CircuitBreakerError`.

---

## R-008: Permission Mode Mapping

**Decision**: Map Maverick permission modes to ACP `request_permission` outcomes:

| Maverick Mode | ACP Behavior |
|---------------|-------------|
| `auto_approve` | Always select the "allow_once" option |
| `deny_dangerous` | Allow read/search tools, deny write/bash/destructive tools based on pattern matching |
| `interactive` | Stub — raise `NotImplementedError` (out of scope per spec) |

**Rationale**: The spec explicitly states interactive mode is a stub. `auto_approve` and `deny_dangerous` cover the current Maverick usage (agents run with `acceptEdits` permission mode, which is effectively auto-approve for the tools they're allowed).

**Dangerous Tool Patterns** (for `deny_dangerous`):
- `Bash` (any shell execution)
- `Write` (file creation)
- `Edit` (file modification — allowed in `acceptEdits` but denied in strict mode)
- Any tool not in the agent's `allowed_tools` list

---

## R-009: Error Mapping ACP → Maverick

**Decision**: Map ACP errors to the existing Maverick exception hierarchy:

| ACP Error | Maverick Exception |
|-----------|-------------------|
| `RequestError` (code -32601, method not found) | `AgentError` |
| `RequestError` (code -32602, invalid params) | `AgentError` |
| `RequestError` (code -32603, internal error) | `AgentError` |
| Subprocess exit (non-zero) | `ProcessError(exit_code=...)` |
| Subprocess not found (FileNotFoundError) | `CLINotFoundError` |
| `asyncio.TimeoutError` (from `wait_for`) | `MaverickTimeoutError` |
| Connection/transport error | `NetworkError` |
| JSON decode error from output extraction | `MalformedResponseError` |
| Circuit breaker threshold | `CircuitBreakerError` |

**Rationale**: Preserves the existing exception hierarchy so workflows don't need to change their error handling.

---

## R-010: Claude Code ACP Invocation

**Decision**: Claude Code is invoked via `npx @anthropic-ai/claude-code@latest --acp` for ACP mode.

**Rationale**: This is the documented way to run Claude Code as an ACP agent. The `npx` approach ensures the latest version and doesn't require a global install. Requires Node.js 18+ as a runtime prerequisite.

**Alternative considered**: `claude --acp` (global install) — rejected because it requires a separate installation step and version management.

**Environment Variables**: Claude Code in ACP mode respects `ANTHROPIC_API_KEY`, `CLAUDE_CODE_MAX_TURNS`, and other standard env vars. The `AgentProviderConfig.env` dict allows per-provider overrides.
