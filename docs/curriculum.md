# Maverick Training Curriculum

A comprehensive learning path covering the technologies, architectural boundaries, and implementation patterns used in the current Maverick system.

---

## Part 1: Foundational Technologies

### 1. Modern Python Development

- Python 3.10+ features (`from __future__ import annotations`, type hints)
- Async-first development with `asyncio` and `anyio`
- Type annotations and generic types (`TypeVar`, `Generic`, `Protocol`)
- Dataclasses and Pydantic for structured data

**Proposed Slides:**

| #   | Slide Title             | Content                                                                              |
| --- | ----------------------- | ------------------------------------------------------------------------------------ |
| 1.1 | Why Python 3.10+?       | New syntax features, performance improvements, why Maverick requires 3.10+           |
| 1.2 | Future Annotations      | `from __future__ import annotations` - what it does, why Maverick uses it widely     |
| 1.3 | Type Hints Fundamentals | Basic type hints: `str`, `int`, `list[str]`, `dict[str, Any]`, optionals             |
| 1.4 | Advanced Type Hints     | `TypeVar`, `Generic[T]`, `Protocol`, `Literal` - with Maverick examples              |
| 1.5 | Async/Await Primer      | Coroutines, `async def`, `await`, event loops - why Maverick is async-first          |
| 1.6 | asyncio Patterns        | `asyncio.gather()`, task groups, `asyncio.to_thread()` for blocking code             |
| 1.7 | anyio for Portability   | Why Maverick uses `anyio` alongside `asyncio` in selected boundaries                 |
| 1.8 | Dataclasses Overview    | `@dataclass`, frozen dataclasses, `field()`, when to use vs Pydantic                 |

### 2. Click - Building CLI Applications

- Command groups and subcommands
- Options, arguments, and flags
- Context passing between commands
- Custom decorators for async commands

**Key Files:**

- `src/maverick/main.py`
- `src/maverick/cli/commands/fly/_group.py`
- `src/maverick/cli/commands/refuel/_group.py`
- `src/maverick/cli/commands/workspace/_group.py`

**Proposed Slides:**

| #   | Slide Title              | Content                                                                 |
| --- | ------------------------ | ----------------------------------------------------------------------- |
| 2.1 | What is Click?           | Click vs argparse vs typer - why Maverick chose Click                   |
| 2.2 | Your First Click Command | `@click.command()`, `@click.option()`, `@click.argument()` basics       |
| 2.3 | Command Groups           | Hierarchical CLIs like `maverick refuel speckit` and `maverick workspace status` |
| 2.4 | Options Deep Dive        | Types, defaults, multiple values, flags, required options               |
| 2.5 | Click Context            | `@click.pass_context`, sharing state between commands                   |
| 2.6 | Custom Decorators        | Building `@async_command` to bridge Click with async functions          |
| 2.7 | Maverick CLI Tour        | Walkthrough of `maverick fly`, `land`, `refuel`, `workspace`, `flight-plan` |

### 3. Pydantic - Data Validation & Configuration

- BaseModel and validation
- Field validators and model validators
- Settings management with `pydantic-settings`
- Configuration layering (environment → project → user → defaults)

**Key Files:**

- `src/maverick/config.py`
- `src/maverick/executor/config.py`
- `src/maverick/models/`

**Proposed Slides:**

| #   | Slide Title                 | Content                                                                        |
| --- | --------------------------- | ------------------------------------------------------------------------------ |
| 3.1 | Why Pydantic?               | Runtime validation, serialization, IDE support - Pydantic v2 improvements      |
| 3.2 | BaseModel Basics            | Defining models, type coercion, accessing fields                               |
| 3.3 | Field Configuration         | `Field()`, defaults, aliases, descriptions, constraints                        |
| 3.4 | Field Validators            | `@field_validator` - custom validation logic per field                         |
| 3.5 | Model Validators            | `@model_validator` - cross-field validation, before vs after                   |
| 3.6 | Nested Models               | Composing config and result models across Maverick                             |
| 3.7 | Pydantic Settings           | `BaseSettings`, environment variables, YAML-backed configuration               |
| 3.8 | Config Layering in Maverick | How `MaverickConfig` merges env, project, user, and built-in defaults          |

### 4. Textual - Terminal User Interfaces

- Textual app architecture and lifecycle
- Widgets, screens, and layouts
- CSS styling (TCSS files)
- Reactive state and event-driven rendering
- Display-only UI boundaries

**Key Files / Directories:**

- `src/maverick/tui/`
- `src/maverick/cli/workflow_executor.py`
- `src/maverick/events.py`

**Proposed Slides:**

| #   | Slide Title            | Content                                                                  |
| --- | ---------------------- | ------------------------------------------------------------------------ |
| 4.1 | What is Textual?       | Modern TUI framework, async-native, CSS styling in the terminal          |
| 4.2 | App Architecture       | Apps, screens, widgets, and composition patterns                         |
| 4.3 | Layouts & Containers   | `Container`, horizontal/vertical layouts, responsive composition         |
| 4.4 | TCSS Styling           | Textual CSS syntax, selectors, properties, theming patterns              |
| 4.5 | Reactive State         | `reactive()` attributes, watchers, and redraw behavior                   |
| 4.6 | Message Handling       | Custom messages, event handlers, and decoupled widget updates            |
| 4.7 | Streaming Interfaces   | Rendering long-running workflow output without embedding business logic  |
| 4.8 | Display-Only Boundary  | Why workflow orchestration belongs outside the UI layer                  |
| 4.9 | Maverick UI Direction  | How the CLI/TUI surfaces consume shared workflow events                  |

### 5. structlog - Structured Logging

- Structured logging vs traditional logging
- Context binding and processors
- JSON vs console output formats
- Log levels and filtering

**Key Files:**

- `src/maverick/logging.py`

**Proposed Slides:**

| #   | Slide Title                | Content                                                              |
| --- | -------------------------- | -------------------------------------------------------------------- |
| 5.1 | Logging Pain Points        | Why traditional logging falls short for complex applications         |
| 5.2 | Structured Logging Concept | Key-value pairs, machine-parseable logs, benefits for debugging      |
| 5.3 | structlog Basics           | `get_logger()`, `log.info("event", key=value)` pattern             |
| 5.4 | Context Binding            | `log.bind(workflow_id="123")` - carrying context through call stacks |
| 5.5 | Processors Pipeline        | How structlog transforms log events, built-in processors             |
| 5.6 | Output Formats             | Console vs JSON, environment-sensitive configuration                 |
| 5.7 | Maverick Logging Setup     | Tour of `maverick/logging.py`, `configure_logging()`                 |

### 6. GitPython & Jujutsu - Repository Access Patterns

- GitPython for read-only repository inspection
- Jujutsu (`jj`) for write-path version control operations
- The `VcsRepository` protocol as an abstraction boundary
- Async wrappers and workspace-safe repository access

**Key Files:**

- `src/maverick/git/repository.py`
- `src/maverick/jj/client.py`
- `src/maverick/vcs/protocol.py`
- `src/maverick/workspace/manager.py`

**Proposed Slides:**

| #   | Slide Title            | Content                                                                  |
| --- | ---------------------- | ------------------------------------------------------------------------ |
| 6.1 | Why Two VCS APIs?      | Maverick uses GitPython for reads and Jujutsu for mutations              |
| 6.2 | GitPython for Reads    | Status, diff, blame, history, and lightweight repository inspection      |
| 6.3 | Jujutsu for Writes     | Commit, push, bookmark, merge, and history curation                      |
| 6.4 | The VCS Protocol       | `VcsRepository` as a typed read abstraction                              |
| 6.5 | Async Repository Access| Wrapping blocking repo operations safely                                 |
| 6.6 | Hidden Workspaces      | Why Maverick clones into `~/.maverick/workspaces/<project>/`             |
| 6.7 | Colocated Repositories | How jj and git share `.git` state                                        |
| 6.8 | Error Handling         | Repository exceptions, recovery, and safe cleanup                        |
| 6.9 | Maverick VCS Tour      | Walking a typical `fly` flow through read-path and write-path layers     |

### 7. PyGithub - GitHub API Integration

- Authentication and client setup
- Issues and Pull Requests API
- Async patterns for sync libraries
- Repository-level automation boundaries

**Key Files:**

- `src/maverick/utils/github_client.py`

**Proposed Slides:**

| #   | Slide Title           | Content                                                      |
| --- | --------------------- | ------------------------------------------------------------ |
| 7.1 | GitHub API Overview   | REST API basics, authentication methods, rate limits         |
| 7.2 | PyGithub Setup        | Creating a `Github` client and loading credentials           |
| 7.3 | Authentication Flow   | Token sourcing, CLI integration, environment expectations    |
| 7.4 | Working with Repos    | `get_repo()`, repo metadata, permissions                     |
| 7.5 | Issues API            | Creating, listing, updating, closing issues                  |
| 7.6 | Pull Requests API     | Creating PRs, reading PR details, status checks              |
| 7.7 | Async Wrapper Pattern | `GitHubClient` and `asyncio.to_thread()` for sync library use |
| 7.8 | Maverick Usage        | Where GitHub automation fits in `land`, review, and issue workflows |

### 8. Tenacity - Retry Logic

- Exponential backoff strategies
- Retry conditions and exceptions
- `AsyncRetrying` for async operations
- When to use retries in distributed systems

**Key Files:**

- `src/maverick/executor/acp.py`
- `src/maverick/runners/preflight.py`
- `src/maverick/utils/github_client.py`

**Proposed Slides:**

| #   | Slide Title       | Content                                                              |
| --- | ----------------- | -------------------------------------------------------------------- |
| 8.1 | Why Retry?        | Transient failures, network issues, provider hiccups                 |
| 8.2 | Tenacity Overview | Declarative retry logic, decorator and context manager styles        |
| 8.3 | Basic Retry       | `@retry`, `stop_after_attempt()`, simple example                     |
| 8.4 | Wait Strategies   | `wait_fixed`, `wait_exponential`, jittered backoff                   |
| 8.5 | Stop Conditions   | `stop_after_attempt`, `stop_after_delay`, combining conditions       |
| 8.6 | Retry Conditions  | `retry_if_exception_type`, custom predicates                         |
| 8.7 | AsyncRetrying     | `async for attempt in AsyncRetrying`                                 |
| 8.8 | Maverick Examples | ACP reconnects, GitHub retries, preflight resilience                 |

### 9. Agent Client Protocol (ACP)

- ACP as the transport layer for agent execution
- Subprocess + stdio communication model
- Sessions, prompts, and streamed events
- Provider abstraction and permission modes

**Key Files:**

- `src/maverick/executor/acp.py`
- `src/maverick/executor/acp_client.py`
- `src/maverick/executor/provider_registry.py`

**Proposed Slides:**

| #   | Slide Title            | Content                                                             |
| --- | ---------------------- | ------------------------------------------------------------------- |
| 9.1 | What is ACP?           | Standard protocol for communicating with agent subprocesses         |
| 9.2 | Process Model          | Spawning an agent binary and talking over stdio                    |
| 9.3 | Sessions & Prompts     | Request/response flow, session lifecycle                           |
| 9.4 | Streaming Events       | Output chunks, thoughts, and tool activity                         |
| 9.5 | Provider Registry      | Choosing default vs named providers                                |
| 9.6 | Permission Modes       | `auto_approve`, `deny_dangerous`, and future interactive mode      |
| 9.7 | Connection Management  | Caching, reconnects, and cleanup                                   |
| 9.8 | Maverick Integration   | Where ACP sits between workflows, agents, and provider processes   |

### 10. MCP Tools & Agent Capabilities

- MCP-style tool surfaces exposed to agents
- Tool allowlists and least-privilege design
- Built-in tool concepts vs Maverick-specific tool packages
- The distinction between prompt construction and tool execution

**Key Files:**

- `src/maverick/agents/base.py`
- `src/maverick/agents/tools.py`
- `src/maverick/tools/`
- `src/maverick/executor/acp.py`

**Proposed Slides:**

| #    | Slide Title              | Content                                                                 |
| ---- | ------------------------ | ----------------------------------------------------------------------- |
| 10.1 | MCP in Practice          | Tools as capabilities the agent can invoke while solving a task         |
| 10.2 | Tool Allowlists          | `allowed_tools` and the principle of least privilege                    |
| 10.3 | Built-in Tool Families   | Read/edit/shell/search/web-style tool categories                        |
| 10.4 | Maverick Tool Packages   | Git, GitHub, validation, and notification tool surfaces                 |
| 10.5 | Tool Response Contracts  | Returning structured, machine-consumable results                        |
| 10.6 | Prompt-to-Tool Flow      | Agent prompt design drives when tools are selected                      |
| 10.7 | Tool Safety Boundaries   | Permission modes, guarded commands, and scoped file access              |
| 10.8 | Legacy vs Current Runtime| Tool definitions may remain MCP-shaped, but execution is ACP-based      |
| 10.9 | Designing Good Tools     | Small surface area, predictable output, and clear failure modes         |

---

## Part 2: Maverick Architecture

### 11. Project Overview & Philosophy

- AI-powered workflow orchestration concept
- Separation of concerns: CLI → Python workflows → agents/actions → ACP/tools
- Async-first, dependency injection, fail gracefully principles
- The "full ownership" operating standard

**Key Files:**

- `README.md`
- `docs/architecture.md`
- `CONTRIBUTING.md`
- `maverick.yaml`

**Proposed Slides:**

| #    | Slide Title             | Content                                                                  |
| ---- | ----------------------- | ------------------------------------------------------------------------ |
| 11.1 | What is Maverick?       | AI-powered workflow orchestration for development tasks                  |
| 11.2 | The Problem We Solve    | Manual handoffs, inconsistent workflows, error-prone repetition          |
| 11.3 | Architecture Overview   | Current execution path: CLI → PythonWorkflow → Actions/AcpStepExecutor   |
| 11.4 | Separation of Concerns  | What each layer owns and why boundaries matter                           |
| 11.5 | Core Principles         | Async-first, typed contracts, dependency injection, graceful failure     |
| 11.6 | Full Ownership Standard | "Fix what you find", no artificial scope minimization                    |
| 11.7 | Project Structure Tour  | `src/maverick/` walkthrough by architectural layer                       |
| 11.8 | What Changed Recently   | YAML DSL removal (041) and ACP migration (042)                           |

### 12. Python Workflow Engine

- `PythonWorkflow` as the orchestration base class
- Async generator execution and event emission
- Deterministic actions vs ACP-backed agent steps
- Rollbacks, checkpointing, and step config resolution

**Key Files:**

- `src/maverick/workflows/base.py`
- `src/maverick/workflows/fly_beads/workflow.py`
- `src/maverick/workflows/refuel_speckit/workflow.py`
- `src/maverick/cli/workflow_executor.py`

**Proposed Slides:**

| #     | Slide Title               | Content                                                              |
| ----- | ------------------------- | -------------------------------------------------------------------- |
| 12.1  | Why Python Workflows?     | Why Maverick removed the YAML DSL and now uses Python classes        |
| 12.2  | `PythonWorkflow` Overview | Constructor dependencies, abstract `_run()`, public `execute()`      |
| 12.3  | Async Generator Model     | Yielding `ProgressEvent` values while work proceeds                  |
| 12.4  | Step Config Resolution    | Default config plus per-step overrides from `MaverickConfig`         |
| 12.5  | Event Emission Helpers    | `emit_step_started`, `emit_output`, `emit_step_completed`, failures  |
| 12.6  | Rollback Registration     | LIFO cleanup actions on failure                                      |
| 12.7  | Checkpoint Integration    | Saving workflow state without a dedicated DSL step type              |
| 12.8  | Deterministic Actions     | Running Python actions for git, validation, beads, and setup         |
| 12.9  | Agent Steps via Executor  | Delegating AI work to `StepExecutor`                                 |
| 12.10 | Concrete Workflows        | `FlyBeadsWorkflow`, `RefuelSpeckitWorkflow`, `RefuelMaverickWorkflow` |
| 12.11 | Fly Beads Walkthrough     | Preflight → workspace → bead loop → validate/review → commit         |
| 12.12 | Workflow Composition      | Reusing shared helpers and library actions instead of YAML fragments |

### 13. ACP Integration Layer

- `AcpStepExecutor` as the primary step executor
- `MaverickAcpClient` for streaming and permissions
- `AgentProviderRegistry` for provider lookup
- Structured output extraction and validation

**Key Files:**

- `src/maverick/executor/acp.py`
- `src/maverick/executor/acp_client.py`
- `src/maverick/executor/provider_registry.py`
- `src/maverick/executor/result.py`

**Proposed Slides:**

| #     | Slide Title              | Content                                                              |
| ----- | ------------------------ | -------------------------------------------------------------------- |
| 13.1  | ACP Layer Overview       | How Maverick talks to agent subprocesses                             |
| 13.2  | `AcpStepExecutor`        | Resolving providers, agents, prompts, retries, and results           |
| 13.3  | Provider Configuration   | Zero-config defaults and explicit `agent_providers` config           |
| 13.4  | Streaming via ACP Client | Mapping streamed events to Maverick event types                      |
| 13.5  | Permission Handling      | Safe defaults and runtime enforcement                                |
| 13.6  | Circuit Breaker          | Preventing runaway repeated tool calls                               |
| 13.7  | Connection Caching       | Reusing subprocesses across steps                                    |
| 13.8  | Reconnect Strategy       | Transparent recovery after connection loss                           |
| 13.9  | Output Extraction        | JSON blocks, schema validation, and `ExecutorResult`                 |
| 13.10 | Cleanup Semantics        | Releasing sessions and terminating provider processes cleanly        |

### 14. Event-Driven Execution Model

- `ProgressEvent` as the shared runtime contract
- `StepResult` and `WorkflowResult` aggregation
- Step lifecycle modeled in events instead of handler classes
- Rendering from CLI/TUI without embedding workflow logic in the UI

**Key Files:**

- `src/maverick/events.py`
- `src/maverick/results.py`
- `src/maverick/types.py`
- `src/maverick/cli/workflow_executor.py`

**Proposed Slides:**

| #     | Slide Title             | Content                                                               |
| ----- | ----------------------- | --------------------------------------------------------------------- |
| 14.1  | Execution Model Overview| Work progresses through events, not a YAML step dispatcher            |
| 14.2  | `ProgressEvent` Union   | The shared type consumed by renderers and observers                   |
| 14.3  | Core Lifecycle Events   | `WorkflowStarted`, `StepStarted`, `StepCompleted`, `WorkflowCompleted` |
| 14.4  | Informational Output    | `StepOutput`, validation events, preflight progress                   |
| 14.5  | Agent Streaming Events  | `AgentStreamChunk` for output, thinking, and tool activity            |
| 14.6  | Result Models           | `StepResult` and `WorkflowResult` as durable summaries                |
| 14.7  | `StepType` Enum         | Modeling deterministic, agent, validate, generate, loop, checkpoint  |
| 14.8  | Workflow Rendering      | How CLI/TUI consumers turn events into human-readable output          |
| 14.9  | Error and Rollback Flow | Failures, cleanup, and final reporting                                |
| 14.10 | Why This Model Matters  | Easier testing, UI decoupling, and provider independence              |

### 15. Agent Architecture

- `MaverickAgent` as a prompt-building abstraction
- Typed context and output contracts
- Allowed tools and prompt overrides
- Registry-based lookup and execution through the executor

**Key Files:**

- `src/maverick/agents/base.py`
- `src/maverick/agents/context.py`
- `src/maverick/agents/contracts.py`
- `src/maverick/agents/registry.py`

**Proposed Slides:**

| #    | Slide Title               | Content                                                            |
| ---- | ------------------------- | ------------------------------------------------------------------ |
| 15.1 | What is a Maverick Agent? | Judgment-only component: agents describe work, workflows execute   |
| 15.2 | `MaverickAgent` Base Class| Names, instructions, tool allowlists, and typed prompt building    |
| 15.3 | Context Models            | Passing structured data into agents                                |
| 15.4 | Output Contracts          | Typed responses and schema validation at the executor boundary     |
| 15.5 | Prompt Construction       | Translating domain context into effective ACP prompts              |
| 15.6 | Tool Selection            | Designing `allowed_tools` for least privilege                      |
| 15.7 | Agent Registry            | Registering and resolving agents by name                           |
| 15.8 | Prompt Overrides          | Per-agent and per-step prompt customization via configuration      |
| 15.9 | Execution Flow            | Workflow → registry → executor → ACP provider → typed result       |

### 16. The ImplementerAgent and Its Peers

- The ImplementerAgent in the `fly` bead loop
- Reviewer, fixer, curator, and decomposer roles
- Prompt design aligned with workflow phase and repository context
- Typed result handling across major agent families

**Key Files:**

- `src/maverick/agents/implementer.py`
- `src/maverick/agents/code_reviewer.py`
- `src/maverick/agents/fixer.py`
- `src/maverick/agents/curator.py`

**Proposed Slides:**

| #    | Slide Title                 | Content                                                            |
| ---- | --------------------------- | ------------------------------------------------------------------ |
| 16.1 | ImplementerAgent Overview   | The agent used for implementation work inside `fly`                |
| 16.2 | Bead Context                | What implementation prompts need: task, workspace, conventions     |
| 16.3 | Prompt Design for Coding    | Tests first, repository conventions, safe tool usage               |
| 16.4 | Reviewer Agents             | Code review and unified review roles                               |
| 16.5 | Fixer Agents                | Validation fixes and issue remediation                             |
| 16.6 | Curator Agent               | History curation during `land`                                     |
| 16.7 | Decomposer & Generators     | Flight-plan decomposition and content generation                    |
| 16.8 | Result Handling             | Turning agent output into actionable workflow decisions            |
| 16.9 | Choosing the Right Agent    | Matching intent, tools, and contract to the workflow step          |

### 17. Tools, Actions, and the Component Registry

- `ComponentRegistry` as the dispatch hub
- Actions for deterministic Python work
- Agents and generators as registry-managed components
- Tool packages as capabilities consumed by ACP-executed agents

**Key Files:**

- `src/maverick/registry/component_registry.py`
- `src/maverick/library/actions/`
- `src/maverick/library/agents/`
- `src/maverick/library/generators/`
- `src/maverick/tools/`

**Proposed Slides:**

| #    | Slide Title                | Content                                                            |
| ---- | -------------------------- | ------------------------------------------------------------------ |
| 17.1 | Why a Component Registry?  | Late binding, pluggability, and consistent lookup                  |
| 17.2 | `ComponentRegistry`        | Actions, agents, generators, and strict vs non-strict lookup       |
| 17.3 | Action Registry            | Deterministic Python functions for workflow orchestration          |
| 17.4 | Agent Registry             | Mapping names like `implementer` to agent classes                  |
| 17.5 | Generator Registry         | Specialized content generation components                          |
| 17.6 | Library Actions            | Beads, jj, preflight, validation, review, dependency sync          |
| 17.7 | Tool Packages              | Git, GitHub, validation, and notification tool surfaces            |
| 17.8 | Action vs Tool             | When logic belongs in a deterministic action vs an agent capability |
| 17.9 | Startup Registration       | `create_registered_registry()` and application bootstrapping       |

### 18. Safety, Permissions, and Guardrails

- ACP permission modes as the primary runtime safety boundary
- Circuit breakers, preflight checks, and conservative tool exposure
- Secret detection and path safety utilities
- Hook modules as transitional support rather than the main execution model

**Key Files:**

- `src/maverick/executor/acp_client.py`
- `src/maverick/runners/preflight.py`
- `src/maverick/hooks/`
- `src/maverick/utils/secrets.py`

**Proposed Slides:**

| #    | Slide Title             | Content                                                             |
| ---- | ----------------------- | ------------------------------------------------------------------- |
| 18.1 | Why Guardrails Matter   | AI-assisted execution needs layered safety                          |
| 18.2 | Permission Modes        | `auto_approve`, `deny_dangerous`, and how tool access is filtered   |
| 18.3 | Circuit Breakers        | Detecting runaway repeated tool use                                 |
| 18.4 | Preflight Validation    | Checking prerequisites before costly workflows begin                |
| 18.5 | Secret Detection        | Preventing accidental credential exposure                           |
| 18.6 | Path & Command Safety   | Limiting dangerous command shapes and protected files               |
| 18.7 | Hooks in Transition     | What remains in `hooks/` after the ACP migration                    |
| 18.8 | Defense in Depth        | Combining config, tools, permissions, and workflow design           |

### 19. Checkpointing & Resumption

- Checkpoint data models and stores
- Resume logic in `PythonWorkflow`
- File-based vs in-memory persistence
- Idempotent workflow design

**Key Files:**

- `src/maverick/checkpoint/data.py`
- `src/maverick/checkpoint/store.py`
- `src/maverick/workflows/base.py`

**Proposed Slides:**

| #    | Slide Title              | Content                                                             |
| ---- | ------------------------ | ------------------------------------------------------------------- |
| 19.1 | Why Checkpointing?       | Long-running workflows fail; resumption saves time and context      |
| 19.2 | Checkpoint Concepts      | Safe persistence points and restart semantics                       |
| 19.3 | Data Models              | What gets stored: workflow state, outputs, metadata                 |
| 19.4 | FileCheckpointStore      | Disk-backed checkpoint persistence                                  |
| 19.5 | MemoryCheckpointStore    | Fast in-memory store for tests and ephemeral runs                   |
| 19.6 | Workflow Integration     | `save_checkpoint()` and `load_checkpoint()` in `PythonWorkflow`     |
| 19.7 | Resume Strategies        | Restoring context without replaying every step                      |
| 19.8 | Idempotent Design        | Why steps must be safe to rerun or skip                             |

### 20. The TUI and Streaming Event Surface

- Shared event model for CLI and TUI rendering
- Display-only UI principle
- Real-time agent streaming and workflow progress visualization
- Future-facing UI composition built on stable workflow events

**Key Files / Directories:**

- `src/maverick/cli/workflow_executor.py`
- `src/maverick/events.py`
- `src/maverick/tui/`

**Proposed Slides:**

| #    | Slide Title               | Content                                                            |
| ---- | ------------------------- | ------------------------------------------------------------------ |
| 20.1 | UI Philosophy             | Display-only, event-driven, streaming-friendly surfaces            |
| 20.2 | Shared Event Feed         | One workflow event model for CLI and TUI consumers                 |
| 20.3 | Rendering Step Progress   | Step start/completion, validation progress, checkpoints            |
| 20.4 | Rendering Agent Streams   | Showing output and thinking without coupling to workflow logic     |
| 20.5 | Workflow Executor Bridge  | How CLI helpers consume and render `ProgressEvent` values          |
| 20.6 | TUI Composition           | Screens, widgets, and layout layers built on shared data           |
| 20.7 | Keeping UI Thin           | Why orchestration and subprocesses stay outside the UI layer       |
| 20.8 | Extending the Surface     | Adding new event renderers without changing workflow semantics     |

---

## Part 3: Advanced Topics

### 21. Workflow Library & Composition

- Built-in Python workflows and their responsibilities
- Reusing library actions and helper modules
- Workflow-specific model packages and constants
- Extending the system without a YAML DSL

**Key Files:**

- `src/maverick/workflows/`
- `src/maverick/library/actions/`
- `src/maverick/library/agents/`
- `src/maverick/library/generators/`

**Proposed Slides:**

| #     | Slide Title                 | Content                                                            |
| ----- | --------------------------- | ------------------------------------------------------------------ |
| 21.1  | Built-in Workflow Library   | What ships with Maverick today                                     |
| 21.2  | `FlyBeadsWorkflow`          | Bead-driven development loop and workspace orchestration           |
| 21.3  | `RefuelSpeckitWorkflow`     | Creating beads from SpecKit `tasks.md`                             |
| 21.4  | `RefuelMaverickWorkflow`    | Turning flight plans into executable work                          |
| 21.5  | `GenerateFlightPlanWorkflow`| Generating plans from PRDs                                         |
| 21.6  | Workflow Packages           | `workflow.py`, `models.py`, `constants.py` package pattern         |
| 21.7  | Shared Helpers              | Review-fix utilities and common workflow support code              |
| 21.8  | Actions as Building Blocks  | Reusing deterministic functions across workflows                   |
| 21.9  | Generators and Agents       | Specialized components used by workflows                           |
| 21.10 | Extending Without YAML      | Creating new Python workflows instead of DSL definitions           |

### 22. Runners & Command Execution

- `CommandRunner` for subprocess management
- Validation and preflight runners
- Output parsing and structured diagnostics
- Timeout, cancellation, and error handling

**Key Files:**

- `src/maverick/runners/command.py`
- `src/maverick/runners/validation.py`
- `src/maverick/runners/preflight.py`
- `src/maverick/runners/parsers/`

**Proposed Slides:**

| #    | Slide Title            | Content                                                            |
| ---- | ---------------------- | ------------------------------------------------------------------ |
| 22.1 | Why Runners?           | Encapsulating subprocess execution and external integrations        |
| 22.2 | `CommandRunner`        | Async command execution, output capture, and cancellation           |
| 22.3 | Timeout Handling       | Preventing runaway processes and surfacing failures clearly         |
| 22.4 | Validation Runner      | Format/lint/typecheck/test orchestration                           |
| 22.5 | Preflight Runner       | Checking environment requirements before workflow start             |
| 22.6 | Output Parsers         | Turning tool output into structured issues                          |
| 22.7 | Error Modeling         | Result objects vs exceptions across runner boundaries              |
| 22.8 | Runner Reuse           | Shared subprocess infrastructure across modules                     |
| 22.9 | Testing Runners        | Faking subprocess behavior and asserting timeouts                   |

### 23. Configuration Management

- Config file hierarchy (`maverick.yaml`)
- Environment variables and nested overrides
- Agent providers, per-agent config, and per-step config
- Validation, workspace, notifications, and metrics settings

**Key Files:**

- `src/maverick/config.py`
- `src/maverick/executor/config.py`
- `maverick.yaml`

**Proposed Slides:**

| #     | Slide Title              | Content                                                            |
| ----- | ------------------------ | ------------------------------------------------------------------ |
| 23.1  | Configuration Philosophy | Layered config, sensible defaults, easy overrides                  |
| 23.2  | Config File Locations    | `./maverick.yaml` and `~/.config/maverick/config.yaml`             |
| 23.3  | Config Precedence        | Environment > project > user > built-in defaults                   |
| 23.4  | `MaverickConfig`         | Top-level config model and nested settings                         |
| 23.5  | ValidationConfig         | Commands, limits, and timeouts                                     |
| 23.6  | WorkspaceConfig          | Hidden workspace root, setup, teardown, reuse                      |
| 23.7  | Agent Overrides          | Per-agent model and prompt customization                           |
| 23.8  | StepConfig               | Timeout, retries, provider, and autonomy settings                  |
| 23.9  | Agent Providers          | ACP binaries, env injection, permission modes                      |
| 23.10 | Operational Settings     | Parallelism, notifications, session logs, TUI metrics              |
| 23.11 | Loading & Validation     | How config is parsed, merged, and validated at startup             |

### 24. Testing Strategies

- `pytest-asyncio` for async tests
- Mocking ACP clients, subprocesses, GitHub, and filesystem boundaries
- Workflow, executor, and runner tests
- Event-driven assertions and TUI-friendly testing

**Key Files:**

- `tests/unit/executor/test_acp_executor.py`
- `tests/unit/executor/test_acp_client.py`
- `tests/unit/workflows/test_python_workflow_base.py`
- `tests/unit/workflows/test_fly_beads_workflow.py`

**Proposed Slides:**

| #     | Slide Title             | Content                                                            |
| ----- | ----------------------- | ------------------------------------------------------------------ |
| 24.1  | Testing Philosophy      | Test-first, high signal, confidence in async systems               |
| 24.2  | pytest Basics           | Discovery, fixtures, assertions, parametrization                   |
| 24.3  | Async Test Patterns     | `async def test_*`, event-loop-aware fixtures                      |
| 24.4  | Workflow Testing        | Verifying emitted events and final results                         |
| 24.5  | Executor Testing        | Mocking ACP providers and validating retries/output schemas        |
| 24.6  | Runner Testing          | Simulating subprocess results and timeouts                         |
| 24.7  | GitHub and VCS Mocks    | Isolating external systems safely                                  |
| 24.8  | Event Assertions        | Checking streamed output without brittle snapshots                 |
| 24.9  | Integration Boundaries  | What to cover with slower end-to-end tests                         |
| 24.10 | Test Organization       | Directory layout, fixture reuse, and scenario-focused modules      |

### 25. Code Quality & Tooling

- Ruff for linting and formatting
- MyPy for static type checking
- Makefile commands for low-noise validation
- CI-oriented local workflows

**Key Files:**

- `pyproject.toml`
- `Makefile`

**Proposed Slides:**

| #    | Slide Title        | Content                                                          |
| ---- | ------------------ | ---------------------------------------------------------------- |
| 25.1 | Quality Philosophy | Automated checks, consistent style, and typed contracts          |
| 25.2 | Ruff Overview      | Fast linting and formatting with one tool                        |
| 25.3 | Ruff in Practice   | `make lint`, `make format`, and autofix workflows               |
| 25.4 | MyPy Overview      | Catching interface and contract problems early                   |
| 25.5 | MyPy in Practice   | `make typecheck`, strictness, and common failure patterns        |
| 25.6 | The Makefile       | Why Maverick standardizes on `make` commands                     |
| 25.7 | Core Validation Cmds | `make test`, `make check`, `make ci`, `make clean`             |
| 25.8 | CI Alignment       | Matching local validation to repository automation               |
| 25.9 | Keeping the Tree Green | Fixing failures immediately instead of deferring them       |

---

## Part 4: Practical Labs

### 26. Lab: Create a Python Workflow

**Objectives:**

- Define workflow inputs and outputs in Python
- Emit progress events during execution
- Call deterministic actions and ACP-backed agent steps
- Exercise the workflow with existing CLI execution helpers

**Starting Point:**

```python
from __future__ import annotations

from typing import Any

from maverick.workflows.base import PythonWorkflow


class MyCustomWorkflow(PythonWorkflow):
    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.emit_output("setup", "Starting custom workflow")
        return {"ok": True, "inputs": inputs}
```

**Proposed Slides:**

| #    | Slide Title                | Content                                                           |
| ---- | -------------------------- | ----------------------------------------------------------------- |
| 26.1 | Lab Introduction           | What we'll build: a small Python workflow                         |
| 26.2 | Workflow Requirements      | Define the problem, inputs, outputs, and success criteria         |
| 26.3 | Step 1: Create the Class   | Subclassing `PythonWorkflow` and wiring constructor dependencies  |
| 26.4 | Step 2: Emit Events        | Using workflow helpers to report progress                         |
| 26.5 | Step 3: Call an Action     | Reusing a deterministic library action                            |
| 26.6 | Step 4: Add an Agent Step  | Executing an ACP-backed agent through the step executor           |
| 26.7 | Step 5: Add Checkpointing  | Persisting and restoring workflow state                           |
| 26.8 | Step 6: Run via CLI Helper | Executing and rendering events                                    |
| 26.9 | Lab Wrap-up                | Review, debugging tips, and extension ideas                       |

### 27. Lab: Build a Custom Agent

**Objectives:**

- Extend `MaverickAgent`
- Define context and output contracts
- Implement `build_prompt()` and tool allowlists
- Register the agent for execution through ACP

**Starting Point:**

```python
from __future__ import annotations

from dataclasses import dataclass

from maverick.agents.base import MaverickAgent


@dataclass(frozen=True)
class MyContext:
    task: str


class MyCustomAgent(MaverickAgent[MyContext, dict[str, str]]):
    def build_prompt(self, context: MyContext) -> str:
        return f"Complete this task carefully: {context.task}"
```

**Proposed Slides:**

| #     | Slide Title                | Content                                                            |
| ----- | -------------------------- | ------------------------------------------------------------------ |
| 27.1  | Lab Introduction           | What we'll build: a specialized prompt-building agent              |
| 27.2  | Agent Requirements         | Define task, inputs, outputs, and safe tool access                |
| 27.3  | Step 1: Define Context     | Dataclass or Pydantic model for agent input                       |
| 27.4  | Step 2: Define Output      | Typed result contract and schema expectations                     |
| 27.5  | Step 3: Create Agent Class | Inheriting from `MaverickAgent`                                   |
| 27.6  | Step 4: Write the Prompt   | Translating context into a strong ACP prompt                      |
| 27.7  | Step 5: Choose Tools       | Selecting `allowed_tools` for least privilege                     |
| 27.8  | Step 6: Register the Agent | Adding it to the registry                                         |
| 27.9  | Step 7: Execute via Workflow| Invoking the agent through `StepExecutor`                         |
| 27.10 | Lab Wrap-up                | Review, testing ideas, and production hardening                   |

### 28. Lab: Add a New Tool or Action Surface

**Objectives:**

- Decide whether new capability belongs in an action or a tool
- Implement a small capability with predictable output
- Register it in the appropriate package/registry path
- Verify it can be used safely from a workflow or agent

**Starting Point:**

```python
from __future__ import annotations


async def my_custom_action(target: str) -> dict[str, str]:
    return {"status": "ok", "target": target}
```

**Proposed Slides:**

| #    | Slide Title                  | Content                                                            |
| ---- | ---------------------------- | ------------------------------------------------------------------ |
| 28.1 | Lab Introduction             | What we'll build: a new capability for Maverick                    |
| 28.2 | Action vs Tool Decision      | Deterministic workflow logic vs agent-invoked capability           |
| 28.3 | Step 1: Design the Contract  | Inputs, outputs, and failure modes                                 |
| 28.4 | Step 2: Implement the Logic  | Writing a small, testable capability                               |
| 28.5 | Step 3: Register It          | Wiring into actions, tools, or server creation                     |
| 28.6 | Step 4: Scope Safety         | Permissions, path boundaries, and predictable behavior             |
| 28.7 | Step 5: Test It              | Unit tests and integration points                                  |
| 28.8 | Step 6: Expose It to Agents  | Updating allowlists or workflow call sites                         |
| 28.9 | Lab Wrap-up                  | Review, trade-offs, and refactoring opportunities                  |

### 29. Lab: Extend the TUI or Event Renderer

**Objectives:**

- Add a new event presentation or UI component
- Keep orchestration outside the UI layer
- Render streaming workflow progress clearly
- Validate the experience with event-focused tests

**Starting Point:**

```python
from __future__ import annotations

from maverick.events import StepOutput


def render_custom_event(event: StepOutput) -> str:
    return f"[{event.step_name}] {event.message}"
```

**Proposed Slides:**

| #     | Slide Title                   | Content                                                           |
| ----- | ----------------------------- | ----------------------------------------------------------------- |
| 29.1  | Lab Introduction              | What we'll build: a new UI or renderer enhancement               |
| 29.2  | UX Requirements               | Clarify what the user should see and when                        |
| 29.3  | Step 1: Choose the Surface    | CLI renderer, TUI component, or shared formatter                  |
| 29.4  | Step 2: Model the Input       | Which `ProgressEvent` types the surface will consume              |
| 29.5  | Step 3: Render Step Progress  | Started/completed/output events                                   |
| 29.6  | Step 4: Render Agent Streams  | Showing streaming text without blocking                           |
| 29.7  | Step 5: Keep UI Thin          | Avoiding workflow logic and subprocess calls in the UI            |
| 29.8  | Step 6: Test the Output       | Snapshot or semantic assertions on rendered output                |
| 29.9  | Step 7: Refine the UX         | Reduce noise, improve readability, add context                    |
| 29.10 | Lab Wrap-up                   | Review, accessibility, and future extensions                      |

---

## Recommended Learning Path

| Week | Topics       | Focus                                      | Est. Slides |
| ---- | ------------ | ------------------------------------------ | ----------- |
| 1    | Topics 1-5   | Python fundamentals, configuration, and UI basics | ~39 slides  |
| 2    | Topics 6-10  | VCS, GitHub, retries, ACP, and tool concepts     | ~42 slides  |
| 3    | Topics 11-15 | Core Maverick architecture and execution model   | ~49 slides  |
| 4    | Topics 16-20 | Agents, registry, safety, checkpoints, rendering | ~42 slides  |
| 5    | Topics 21-25 | Advanced workflow extension and quality practices | ~49 slides  |
| 6    | Topics 26-29 | Hands-on labs                                      | ~38 slides  |

**Total Estimated Slides: ~259**

---

## Slide Summary by Section

| Part       | Section                                         | Slides |
| ---------- | ----------------------------------------------- | ------ |
| **Part 1** | 1. Modern Python Development                    | 8      |
|            | 2. Click - Building CLI Applications            | 7      |
|            | 3. Pydantic - Data Validation & Configuration   | 8      |
|            | 4. Textual - Terminal User Interfaces           | 9      |
|            | 5. structlog - Structured Logging               | 7      |
|            | 6. GitPython & Jujutsu - Repository Access Patterns | 9   |
|            | 7. PyGithub - GitHub API Integration            | 8      |
|            | 8. Tenacity - Retry Logic                       | 8      |
|            | 9. Agent Client Protocol (ACP)                  | 8      |
|            | 10. MCP Tools & Agent Capabilities              | 9      |
| **Part 2** | 11. Project Overview & Philosophy               | 8      |
|            | 12. Python Workflow Engine                      | 12     |
|            | 13. ACP Integration Layer                       | 10     |
|            | 14. Event-Driven Execution Model                | 10     |
|            | 15. Agent Architecture                          | 9      |
|            | 16. The ImplementerAgent and Its Peers          | 9      |
|            | 17. Tools, Actions, and the Component Registry  | 9      |
|            | 18. Safety, Permissions, and Guardrails         | 8      |
|            | 19. Checkpointing & Resumption                  | 8      |
|            | 20. The TUI and Streaming Event Surface         | 8      |
| **Part 3** | 21. Workflow Library & Composition              | 10     |
|            | 22. Runners & Command Execution                 | 9      |
|            | 23. Configuration Management                    | 11     |
|            | 24. Testing Strategies                          | 10     |
|            | 25. Code Quality & Tooling                      | 9      |
| **Part 4** | 26. Lab: Create a Python Workflow               | 9      |
|            | 27. Lab: Build a Custom Agent                   | 10     |
|            | 28. Lab: Add a New Tool or Action Surface       | 9      |
|            | 29. Lab: Extend the TUI or Event Renderer       | 10     |

---

## Prerequisites

- Python 3.10+ installed
- Familiarity with async/await syntax
- Basic Git knowledge
- `gh`, `jj`, and `bd` available for hands-on workflow labs
- Access to an ACP-compatible agent provider (default Maverick setup uses `claude-agent-acp`)
- Required credentials configured for the chosen provider (for Claude, `ANTHROPIC_API_KEY`)

## Resources

- `docs/architecture.md`
- `README.md`
- [Textual Documentation](https://textual.textualize.io/)
- [Click Documentation](https://click.palletsprojects.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [structlog Documentation](https://www.structlog.org/)
- [GitPython Documentation](https://gitpython.readthedocs.io/)
- [PyGithub Documentation](https://pygithub.readthedocs.io/)
- [Jujutsu Documentation](https://jj-vcs.github.io/jj/latest/)
- `agent-client-protocol` package documentation
