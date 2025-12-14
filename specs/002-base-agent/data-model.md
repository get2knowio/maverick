# Data Model: Base Agent Abstraction Layer

**Feature**: 002-base-agent | **Date**: 2025-12-12

---

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AgentRegistry                                  │
│  (singleton service for agent discovery and instantiation)               │
├─────────────────────────────────────────────────────────────────────────┤
│  _agents: dict[str, Type[MaverickAgent]]                                │
│  register(name, cls) → None           [raises DuplicateAgentError]      │
│  get(name) → Type[MaverickAgent]      [raises AgentNotFoundError]       │
│  list_agents() → list[str]                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ registers
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         MaverickAgent (ABC)                              │
│  (abstract base class for all agents)                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  name: str                                                               │
│  system_prompt: str                                                      │
│  allowed_tools: list[str]                                               │
│  model: str | None                                                       │
│  options: ClaudeAgentOptions         [SDK configuration]                │
├─────────────────────────────────────────────────────────────────────────┤
│  __init__(name, system_prompt, allowed_tools, model?, mcp_servers?)     │
│  @abstractmethod execute(context: AgentContext) → AgentResult           │
│  query(prompt, cwd?) → AsyncIterator[Message]                           │
│  _validate_tools(allowed_tools, mcp_servers) → None                     │
│  _build_options(cwd?) → ClaudeAgentOptions                              │
│  _wrap_sdk_error(error) → Exception                                      │
└─────────────────────────────────────────────────────────────────────────┘
                │                                        │
                │ receives                               │ returns
                ▼                                        ▼
┌───────────────────────────────┐    ┌───────────────────────────────────┐
│        AgentContext           │    │          AgentResult              │
│  (runtime context for exec)   │    │  (execution outcome)              │
├───────────────────────────────┤    ├───────────────────────────────────┤
│  cwd: Path                    │    │  success: bool                    │
│  branch: str                  │    │  output: str                      │
│  config: MaverickConfig       │    │  metadata: dict[str, Any]         │
│  extra: dict[str, Any]        │    │  errors: list[AgentError]         │
├───────────────────────────────┤    │  usage: AgentUsage                │
│  from_cwd(path) → cls         │    └───────────────────────────────────┘
└───────────────────────────────┘                    │
                                                     │ contains
                                                     ▼
                                    ┌───────────────────────────────────┐
                                    │          AgentUsage               │
                                    │  (usage statistics)               │
                                    ├───────────────────────────────────┤
                                    │  input_tokens: int                │
                                    │  output_tokens: int               │
                                    │  total_cost_usd: float | None     │
                                    │  duration_ms: int                 │
                                    └───────────────────────────────────┘
```

---

## Entity Definitions

### MaverickAgent

**Type**: Abstract Base Class
**Module**: `src/maverick/agents/base.py`
**Purpose**: Abstract base class wrapping Claude Agent SDK interactions (FR-001)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | Yes | - | Unique identifier for the agent |
| `system_prompt` | `str` | Yes | - | System prompt defining agent behavior |
| `allowed_tools` | `list[str]` | Yes | - | Tools the agent may use (validated at construction) |
| `model` | `str \| None` | No | `"claude-sonnet-4-5-20250929"` | Claude model ID |
| `options` | `ClaudeAgentOptions` | - | (built internally) | SDK configuration object |

**Validation Rules**:
- `name`: Non-empty string, unique within registry
- `allowed_tools`: Each tool must exist in BUILTIN_TOOLS or be a valid MCP tool pattern (`mcp__<server>__<tool>`)
- Raises `InvalidToolError` at construction if any tool is invalid (FR-002)

**Methods**:
| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(name, system_prompt, allowed_tools, model?, mcp_servers?)` | Constructor with tool validation |
| `execute` | `async (context: AgentContext) → AgentResult` | Abstract method - subclasses implement |
| `query` | `async (prompt, cwd?) → AsyncIterator[Message]` | Helper for streaming responses |

---

### AgentResult

**Type**: Dataclass (frozen, slots)
**Module**: `src/maverick/agents/result.py`
**Purpose**: Value object representing agent execution outcome (FR-008)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `success` | `bool` | Yes | - | Whether execution succeeded |
| `output` | `str` | Yes | - | Text output from agent |
| `metadata` | `dict[str, Any]` | No | `{}` | Arbitrary metadata (session_id, etc.) |
| `errors` | `list[AgentError]` | No | `[]` | Errors encountered during execution |
| `usage` | `AgentUsage` | Yes | - | Usage statistics (FR-014) |

**Validation Rules**:
- `success=False` MUST have at least one error in `errors` list with actionable context (per FR-008)
- `output` may be empty string but not None

**Factory Methods**:
| Method | Signature | Description |
|--------|-----------|-------------|
| `success_result` | `@classmethod (output, usage, metadata?) → AgentResult` | Create successful result |
| `failure_result` | `@classmethod (errors, usage, metadata?) → AgentResult` | Create failed result |

---

### AgentUsage

**Type**: Dataclass (frozen, slots)
**Module**: `src/maverick/agents/result.py`
**Purpose**: Usage statistics for agent execution (FR-014)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `input_tokens` | `int` | Yes | - | Input tokens consumed |
| `output_tokens` | `int` | Yes | - | Output tokens generated |
| `total_cost_usd` | `float \| None` | No | `None` | Total cost (may be unavailable) |
| `duration_ms` | `int` | Yes | - | Execution duration in milliseconds |

**Validation Rules**:
- `input_tokens >= 0`
- `output_tokens >= 0`
- `duration_ms >= 0`
- `total_cost_usd >= 0.0` if present

**Computed Properties**:
| Property | Type | Description |
|----------|------|-------------|
| `total_tokens` | `int` | `input_tokens + output_tokens` |

---

### AgentContext

**Type**: Dataclass (frozen, slots)
**Module**: `src/maverick/agents/context.py`
**Purpose**: Runtime context passed to agent execution (FR-009)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cwd` | `Path` | Yes | - | Working directory for agent execution |
| `branch` | `str` | Yes | - | Current git branch name |
| `config` | `MaverickConfig` | Yes | - | Application configuration |
| `extra` | `dict[str, Any]` | No | `{}` | Additional context for specific agents |

**Validation Rules**:
- `cwd`: Must be an existing directory
- `branch`: Non-empty string

**Factory Methods**:
| Method | Signature | Description |
|--------|-----------|-------------|
| `from_cwd` | `@classmethod (cwd: Path, config?: MaverickConfig) → AgentContext` | Create context detecting branch from git |

---

### AgentRegistry

**Type**: Service (singleton pattern)
**Module**: `src/maverick/agents/registry.py`
**Purpose**: Registry for discovering and instantiating agents (FR-010)

| Field | Type | Description |
|-------|------|-------------|
| `_agents` | `dict[str, Type[MaverickAgent]]` | Internal mapping of names to classes |

**Methods**:
| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `(name: str, cls: Type[MaverickAgent]) → None` | Register agent class (FR-011) |
| `get` | `(name: str) → Type[MaverickAgent]` | Look up agent class (FR-012) |
| `list_agents` | `() → list[str]` | List all registered agent names |
| `create` | `(name: str, **kwargs) → MaverickAgent` | Instantiate agent by name |

**Validation Rules**:
- `register()`: Raises `DuplicateAgentError` if name already registered
- `get()`: Raises `AgentNotFoundError` if name not found

**Usage Pattern**:
```python
# Module-level registry instance
registry = AgentRegistry()

# Decorator for registration
@registry.register("code_reviewer")
class CodeReviewerAgent(MaverickAgent):
    ...

# Or explicit registration
registry.register("code_reviewer", CodeReviewerAgent)

# Lookup and instantiation
cls = registry.get("code_reviewer")
agent = cls(mcp_servers={...})

# Or combined
agent = registry.create("code_reviewer", mcp_servers={...})
```

---

## Error Types

**Module**: `src/maverick/exceptions.py`

```
MaverickError (base)
├── AgentError (agent-related errors)
│   ├── CLINotFoundError      # Claude CLI not installed
│   ├── ProcessError          # Process execution failed
│   ├── TimeoutError          # Operation timed out
│   ├── NetworkError          # Network/connection error
│   ├── StreamingError        # Mid-stream failure
│   ├── MalformedResponseError # Unparseable response
│   ├── InvalidToolError      # Unknown tool in allowed_tools
│   ├── DuplicateAgentError   # Agent name already registered
│   └── AgentNotFoundError    # Agent name not in registry
├── WorkflowError
└── ConfigError
```

| Error | Fields | Raised By |
|-------|--------|-----------|
| `CLINotFoundError` | `cli_path: str \| None` | `MaverickAgent._wrap_sdk_error()` |
| `ProcessError` | `exit_code: int \| None`, `stderr: str \| None` | `MaverickAgent._wrap_sdk_error()` |
| `StreamingError` | `partial_messages: list[Message]` | `MaverickAgent.query()` |
| `MalformedResponseError` | `raw_response: str` | `MaverickAgent._wrap_sdk_error()` |
| `InvalidToolError` | `tool_name: str`, `available_tools: list[str]` | `MaverickAgent.__init__()` |
| `DuplicateAgentError` | `agent_name: str` | `AgentRegistry.register()` |
| `AgentNotFoundError` | `agent_name: str` | `AgentRegistry.get()` |

---

## Constants

**Module**: `src/maverick/agents/base.py`

```python
# Built-in tools available to all agents
BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "NotebookEdit", "WebFetch", "WebSearch", "TodoWrite",
    "BashOutput", "KillBash", "Task", "ExitPlanMode",
    "ListMcpResources", "ReadMcpResource"
})

# Default model for agents
DEFAULT_MODEL: str = "claude-sonnet-4-5-20250929"

# Default permission mode
DEFAULT_PERMISSION_MODE: str = "acceptEdits"
```

---

## Type Aliases

**Module**: `src/maverick/agents/__init__.py`

```python
from typing import TypeAlias
from claude_agent_sdk import Message

# SDK types re-exported for convenience
AgentMessage: TypeAlias = Message
```
