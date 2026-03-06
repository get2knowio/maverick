# Data Model: ACP Integration

**Feature**: 042-acp-integration | **Date**: 2026-03-04

## Entity Overview

```
AgentProviderConfig ──1:N──> AgentProviderRegistry
                                    │
                                    │ resolves
                                    ▼
                            AcpStepExecutor ──uses──> MaverickAcpClient
                                    │                        │
                                    │ creates                │ receives
                                    ▼                        ▼
                          ClientSideConnection         SessionUpdate events
                                    │                        │
                                    │ manages                │ maps to
                                    ▼                        ▼
                               ACP Sessions          AgentStreamChunk
```

## Entities

### AgentProviderConfig (New)

**Location**: `src/maverick/config.py`
**Type**: Pydantic `BaseModel` (frozen)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `command` | `list[str]` | *required* | Subprocess command and arguments |
| `env` | `dict[str, str]` | `{}` | Environment variable overrides |
| `permission_mode` | `PermissionModeEnum` | `"auto_approve"` | Permission handling strategy |
| `default` | `bool` | `False` | Whether this is the default provider |

**Validation Rules**:
- `command` must be non-empty
- `permission_mode` must be one of: `auto_approve`, `deny_dangerous`, `interactive`

**State Transitions**: None (immutable configuration)

### AgentProviderRegistry (New)

**Location**: `src/maverick/executor/provider_registry.py`
**Type**: Plain class (not a model)

| Field | Type | Description |
|-------|------|-------------|
| `_providers` | `dict[str, AgentProviderConfig]` | Named provider configs |
| `_default_name` | `str` | Name of the default provider |

**Methods**:
- `get(name: str) -> AgentProviderConfig` — Raises `ConfigError` if not found
- `default() -> tuple[str, AgentProviderConfig]` — Returns `(name, config)` of the default
- `names() -> list[str]` — All registered provider names

**Validation Rules**:
- Exactly one provider must have `default=True`
- Provider names must be unique (enforced by dict keys)

**Factory**: `AgentProviderRegistry.from_config(providers: dict[str, AgentProviderConfig])` — validates and constructs

### AcpStepExecutor (New)

**Location**: `src/maverick/executor/acp.py`
**Type**: Class implementing `StepExecutor` protocol

| Field | Type | Description |
|-------|------|-------------|
| `_registry` | `AgentProviderRegistry` | Provider lookup |
| `_agent_registry` | `ComponentRegistry` | Agent prompt builder lookup |
| `_connections` | `dict[str, _CachedConnection]` | Cached connections by provider name |
| `_logger` | `BoundLogger` | structlog logger |

**Methods**:
- `execute(...)` → `ExecutorResult` — Protocol method
- `cleanup()` → None — Terminates all cached subprocess connections
- `_get_or_create_connection(provider_name)` → `_CachedConnection` — Lazy connection creation
- `_build_acp_prompt(prompt, instructions, agent)` → `list[ContentBlock]` — Convert prompt to ACP content
- `_extract_json_output(text, schema)` → `BaseModel` — Extract and validate structured output

**Internal Type**: `_CachedConnection` (frozen dataclass):
| Field | Type | Description |
|-------|------|-------------|
| `conn` | `ClientSideConnection` | ACP connection |
| `proc` | `asyncio.subprocess.Process` | Subprocess handle |
| `provider_name` | `str` | Provider name for logging |

### MaverickAcpClient (New)

**Location**: `src/maverick/executor/acp_client.py`
**Type**: Class extending `acp.Client`

| Field | Type | Description |
|-------|------|-------------|
| `_permission_mode` | `PermissionModeEnum` | How to handle permission requests |
| `_event_callback` | `EventCallback \| None` | Where to forward streaming events |
| `_step_name` | `str` | Current step name (for AgentStreamChunk) |
| `_agent_name` | `str` | Current agent name (for AgentStreamChunk) |
| `_text_accumulator` | `list[str]` | Accumulated agent text for output extraction |
| `_tool_call_counts` | `dict[str, int]` | Circuit breaker tracking |
| `_abort_event` | `asyncio.Event` | Set when circuit breaker triggers |
| `_allowed_tools` | `frozenset[str]` | Tools the agent is allowed to use (for deny_dangerous) |

**Methods**:
- `request_permission(options, session_id, tool_call)` → `RequestPermissionResponse`
- `session_update(session_id, update)` → None — Maps ACP events to Maverick events
- `get_accumulated_text()` → `str` — Returns joined text buffer
- `reset()` → None — Clears state for new session

### AgentPromptBuilder (Refactored from MaverickAgent)

**Location**: `src/maverick/agents/base.py`
**Type**: Abstract base class (replaces current `MaverickAgent`)

| Field | Type | Description |
|-------|------|-------------|
| `_name` | `str` | Agent identifier |
| `_instructions` | `str` | Agent role/behavioral guidelines |
| `_allowed_tools` | `list[str]` | Tools the agent may use |
| `_model` | `str` | Preferred model ID |

**Methods**:
- `build_prompt(context: TContext) -> str` — **New abstract method**: construct the prompt string from typed context
- `name`, `instructions`, `allowed_tools`, `model` — Read-only properties (preserved)

**Removed** (moved to executor):
- `query()` — SDK interaction
- `execute()` — Full execution lifecycle
- `_build_options()` — SDK options construction
- `_wrap_sdk_error()` — Error mapping
- `_extract_usage()` — Usage extraction
- `_extract_structured_output()` — Output extraction
- `_extract_tool_calls()` — Tool call tracking
- `_check_circuit_breaker()` — Circuit breaker
- `stream_callback` property — Streaming

### MaverickConfig Changes

**Location**: `src/maverick/config.py`

| Change | Description |
|--------|-------------|
| Add `agent_providers: dict[str, AgentProviderConfig]` | New field for ACP provider configs |
| Keep `agents: dict[str, AgentConfig]` | Unchanged — per-logical-agent overrides |
| Remove `claude-agent-sdk` references | Post-migration cleanup |

**Zero-Config Default**: When `agent_providers` is empty, `AgentProviderRegistry.from_config()` synthesizes:
```python
{"claude": AgentProviderConfig(
    command=["npx", "@anthropic-ai/claude-code@latest", "--acp"],
    permission_mode="auto_approve",
    default=True,
)}
```

### StepConfig Changes

**Location**: `src/maverick/executor/config.py`

| Change | Description |
|--------|-------------|
| `provider: Literal["claude"] \| None` → `provider: str \| None` | Allow any registered provider name |

### ExecutorResult (Unchanged)

Existing frozen dataclass — no changes needed. The `output` field accepts `Any` (validated Pydantic model or raw text). The `events` tuple holds `AgentStreamChunk` instances.

### UsageMetadata (Unchanged)

Existing frozen dataclass — no changes needed. ACP does not provide token usage; fields will be zero-initialized until ACP adds usage extensions.

## Relationships

1. **MaverickConfig** contains 0..N **AgentProviderConfig** entries
2. **AgentProviderRegistry** is constructed from **MaverickConfig.agent_providers**
3. **AcpStepExecutor** holds one **AgentProviderRegistry** and one **ComponentRegistry**
4. **AcpStepExecutor** creates/caches **_CachedConnection** per provider
5. Each **_CachedConnection** wraps one **ClientSideConnection** + **Process**
6. **MaverickAcpClient** is instantiated per-connection and handles streaming + permissions
7. **AgentPromptBuilder** (in ComponentRegistry) provides prompt text to **AcpStepExecutor**
