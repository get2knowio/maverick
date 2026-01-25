# Maverick Training Curriculum

A comprehensive learning path covering the third-party technologies and architecture of the Maverick AI-powered workflow orchestration system.

---

## Part 1: Foundational Technologies

### 1. Modern Python Development

- Python 3.10+ features (`from __future__ import annotations`, type hints)
- Async-first development with `asyncio` and `anyio`
- Type annotations and generic types (`TypeVar`, `Generic`)
- Dataclasses and Pydantic for structured data

**Proposed Slides:**

| #   | Slide Title             | Content                                                                              |
| --- | ----------------------- | ------------------------------------------------------------------------------------ |
| 1.1 | Why Python 3.10+?       | New syntax features, performance improvements, why Maverick requires 3.10+           |
| 1.2 | Future Annotations      | `from __future__ import annotations` - what it does, why every Maverick file uses it |
| 1.3 | Type Hints Fundamentals | Basic type hints: `str`, `int`, `list[str]`, `dict[str, Any]`, `Optional`, `Union`   |
| 1.4 | Advanced Type Hints     | `TypeVar`, `Generic[T]`, `Protocol`, `Literal` - with Maverick examples              |
| 1.5 | Async/Await Primer      | Coroutines, `async def`, `await`, event loops - why Maverick is async-first          |
| 1.6 | asyncio Patterns        | `asyncio.gather()`, `asyncio.create_task()`, `asyncio.to_thread()` for blocking code |
| 1.7 | anyio for Portability   | Why Maverick uses `anyio` alongside `asyncio`                                        |
| 1.8 | Dataclasses Overview    | `@dataclass`, frozen dataclasses, `field()`, when to use vs Pydantic                 |

### 2. Click - Building CLI Applications

- Command groups and subcommands
- Options, arguments, and flags
- Context passing between commands
- Custom decorators for async commands

**Key Files:**

- `src/maverick/main.py`
- `src/maverick/cli/commands/fly.py`

**Proposed Slides:**

| #   | Slide Title              | Content                                                                     |
| --- | ------------------------ | --------------------------------------------------------------------------- |
| 2.1 | What is Click?           | Click vs argparse vs typer - why Maverick chose Click                       |
| 2.2 | Your First Click Command | `@click.command()`, `@click.option()`, `@click.argument()` basics           |
| 2.3 | Command Groups           | `@click.group()` - building hierarchical CLIs like `maverick workflow list` |
| 2.4 | Options Deep Dive        | Types, defaults, multiple values, flags, required options                   |
| 2.5 | Click Context            | `@click.pass_context`, sharing state between commands                       |
| 2.6 | Custom Decorators        | Building `@async_command` to bridge Click with async functions              |
| 2.7 | Maverick CLI Tour        | Walkthrough of `maverick fly`, `maverick workflow`, `maverick config`       |

### 3. Pydantic - Data Validation & Configuration

- BaseModel and validation
- Field validators and model validators
- Settings management with `pydantic-settings`
- Configuration layering (project → user → defaults)

**Key Files:**

- `src/maverick/config.py`
- `src/maverick/dsl/serialization/schema.py`

**Proposed Slides:**

| #   | Slide Title                 | Content                                                                        |
| --- | --------------------------- | ------------------------------------------------------------------------------ |
| 3.1 | Why Pydantic?               | Runtime validation, serialization, IDE support - Pydantic v2 improvements      |
| 3.2 | BaseModel Basics            | Defining models, type coercion, accessing fields                               |
| 3.3 | Field Configuration         | `Field()`, defaults, aliases, descriptions, constraints (`gt`, `le`, etc.)     |
| 3.4 | Field Validators            | `@field_validator` - custom validation logic per field                         |
| 3.5 | Model Validators            | `@model_validator` - cross-field validation, `mode="before"` vs `mode="after"` |
| 3.6 | Nested Models               | Composing models, discriminated unions for step types                          |
| 3.7 | Pydantic Settings           | `BaseSettings`, environment variables, `.env` files                            |
| 3.8 | Config Layering in Maverick | How `MaverickConfig` merges project → user → defaults                          |

### 4. Textual - Terminal User Interfaces

- Textual app architecture and lifecycle
- Widgets, screens, and layouts
- CSS styling (TCSS files)
- Reactive attributes and message handling
- Command palette integration

**Key Files:**

- `src/maverick/tui/app.py`
- `src/maverick/tui/maverick.tcss`
- `src/maverick/tui/widgets/`

**Proposed Slides:**

| #    | Slide Title          | Content                                                              |
| ---- | -------------------- | -------------------------------------------------------------------- |
| 4.1  | What is Textual?     | Modern TUI framework, async-native, CSS styling in the terminal      |
| 4.2  | App Architecture     | `App` class, `compose()`, `on_mount()`, lifecycle methods            |
| 4.3  | Built-in Widgets     | `Static`, `Button`, `Input`, `DataTable`, `Tree`, `Log`              |
| 4.4  | Custom Widgets       | Creating widgets, `compose()`, `render()`, widget inheritance        |
| 4.5  | Layouts & Containers | `Container`, `Horizontal`, `Vertical`, `Grid` - arrangement patterns |
| 4.6  | TCSS Styling         | Textual CSS syntax, selectors, properties, the `maverick.tcss` file  |
| 4.7  | Reactive Attributes  | `reactive()`, `watch_*` methods, automatic UI updates                |
| 4.8  | Message System       | Custom messages, `post_message()`, `on_*` handlers                   |
| 4.9  | Screens & Navigation | Multiple screens, `push_screen()`, `pop_screen()`, modals            |
| 4.10 | Command Palette      | `Provider` class, `search()`, keyboard-driven commands               |
| 4.11 | Maverick TUI Tour    | Live demo of `MaverickApp` - screens, widgets, navigation            |

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
| 5.3 | structlog Basics           | `get_logger()`, `log.info("event", key=value)` pattern               |
| 5.4 | Context Binding            | `log.bind(workflow_id="123")` - carrying context through call stacks |
| 5.5 | Processors Pipeline        | How structlog transforms log events, built-in processors             |
| 5.6 | Output Formats             | Console (dev) vs JSON (prod), `MAVERICK_LOG_FORMAT` env var          |
| 5.7 | Maverick Logging Setup     | Tour of `maverick/logging.py`, `configure_logging()`                 |

### 6. GitPython - Git Operations

- Repository operations (status, add, commit, push)
- Branch management
- Diff and history analysis
- Async wrappers with `asyncio.to_thread`

**Key Files:**

- `src/maverick/git/repository.py`

**Proposed Slides:**

| #   | Slide Title           | Content                                                           |
| --- | --------------------- | ----------------------------------------------------------------- |
| 6.1 | Why GitPython?        | Programmatic git vs subprocess, type safety, error handling       |
| 6.2 | Opening a Repository  | `Repo()`, `Repo.init()`, detecting git repos                      |
| 6.3 | Status & Index        | `repo.is_dirty()`, `repo.untracked_files`, staging changes        |
| 6.4 | Commits               | `repo.index.commit()`, reading commit history, `repo.head.commit` |
| 6.5 | Branches              | Creating, switching, listing, deleting branches                   |
| 6.6 | Remotes & Push/Pull   | `repo.remotes`, `remote.push()`, `remote.pull()`                  |
| 6.7 | Diffs                 | `commit.diff()`, `repo.index.diff()`, parsing diff stats          |
| 6.8 | Async Git in Maverick | `AsyncGitRepository` wrapper, `asyncio.to_thread()` pattern       |
| 6.9 | Error Handling        | `GitCommandError`, custom exceptions like `MergeConflictError`    |

### 7. PyGithub - GitHub API Integration

- Authentication via `gh auth token`
- Issues and Pull Requests API
- Rate limiting with `aiolimiter`
- Async patterns for sync libraries

**Key Files:**

- `src/maverick/utils/github_client.py`

**Proposed Slides:**

| #   | Slide Title           | Content                                                      |
| --- | --------------------- | ------------------------------------------------------------ |
| 7.1 | GitHub API Overview   | REST API basics, authentication methods, rate limits         |
| 7.2 | PyGithub Setup        | Installing, creating `Github` client, token auth             |
| 7.3 | Auth via gh CLI       | `gh auth token` command, why Maverick uses this approach     |
| 7.4 | Working with Repos    | `github.get_repo()`, repo properties, permissions            |
| 7.5 | Issues API            | Creating, listing, updating, closing issues                  |
| 7.6 | Pull Requests API     | Creating PRs, getting PR details, merging                    |
| 7.7 | Rate Limiting         | GitHub limits (5000/hr), `aiolimiter.AsyncLimiter`           |
| 7.8 | Async Wrapper Pattern | `GitHubClient` class, `asyncio.to_thread()` for sync library |

### 8. Tenacity - Retry Logic

- Exponential backoff strategies
- Retry conditions and exceptions
- `AsyncRetrying` for async operations
- When to use retries in distributed systems

**Key Files:**

- `src/maverick/git/repository.py` (example usage)

**Proposed Slides:**

| #   | Slide Title       | Content                                                              |
| --- | ----------------- | -------------------------------------------------------------------- |
| 8.1 | Why Retry?        | Transient failures, network issues, rate limits                      |
| 8.2 | Tenacity Overview | Declarative retry logic, decorator and context manager styles        |
| 8.3 | Basic Retry       | `@retry` decorator, `stop_after_attempt()`, simple example           |
| 8.4 | Wait Strategies   | `wait_fixed`, `wait_exponential`, `wait_random`                      |
| 8.5 | Stop Conditions   | `stop_after_attempt`, `stop_after_delay`, combining conditions       |
| 8.6 | Retry Conditions  | `retry_if_exception_type`, `retry_if_result`, custom predicates      |
| 8.7 | AsyncRetrying     | Context manager for async code, `async for attempt in AsyncRetrying` |
| 8.8 | Maverick Examples | How `git push`, GitHub API calls use tenacity                        |

### 9. Lark - Parsing and DSLs

- Grammar files (`.lark` format)
- Building expression parsers
- AST transformation
- Expression evaluation

**Key Files:**

- `src/maverick/dsl/expressions/grammar.lark`
- `src/maverick/dsl/expressions/parser.py`
- `src/maverick/dsl/expressions/evaluator.py`

**Proposed Slides:**

| #   | Slide Title                 | Content                                              |
| --- | --------------------------- | ---------------------------------------------------- |
| 9.1 | What is Lark?               | Parser generator, EBNF grammars, Earley vs LALR      |
| 9.2 | Grammar Syntax              | Rules, terminals, operators (`*`, `+`, `?`, `\|`)    |
| 9.3 | Your First Grammar          | Simple expression grammar, testing with Lark         |
| 9.4 | Parse Trees                 | Understanding Lark's tree output, `Tree` and `Token` |
| 9.5 | Transformers                | `@v_args`, converting parse trees to custom objects  |
| 9.6 | Maverick Expression Grammar | `${{ inputs.x }}`, `${{ steps.y.output }}` syntax    |
| 9.7 | Expression Evaluation       | `ExpressionEvaluator` class, context resolution      |
| 9.8 | Template Interpolation      | Mixing literal text with expressions                 |

### 10. Claude Agent SDK - AI Agent Development

- MCP (Model Context Protocol) architecture
- Tool definitions with `@tool` decorator
- Creating MCP servers
- Agent execution and streaming

**Key Files:**

- `src/maverick/tools/validation.py`
- `src/maverick/agents/base.py`

**Proposed Slides:**

| #    | Slide Title               | Content                                                           |
| ---- | ------------------------- | ----------------------------------------------------------------- |
| 10.1 | What is MCP?              | Model Context Protocol, tools as capabilities, agent architecture |
| 10.2 | Claude Agent SDK Overview | Package structure, key classes, installation                      |
| 10.3 | Defining Tools            | `@tool` decorator, docstrings as descriptions, type hints         |
| 10.4 | Tool Parameters           | Input validation, optional parameters, complex types              |
| 10.5 | Tool Responses            | Success/error patterns, structured output, MCP format             |
| 10.6 | Creating MCP Servers      | `create_sdk_mcp_server()`, grouping related tools                 |
| 10.7 | Agent Execution           | Running agents, passing tools, handling responses                 |
| 10.8 | Streaming Responses       | Real-time output, `StreamCallback`, progress updates              |
| 10.9 | Built-in Tools            | Read, Write, Edit, Bash, Grep - what Claude can do                |

---

## Part 2: Maverick Architecture

### 11. Project Overview & Philosophy

- AI-powered workflow orchestration concept
- Separation of concerns: CLI → Workflows → Agents → Tools
- Async-first, dependency injection, fail gracefully principles
- The "full ownership" operating standard

**Key Files:**

- `README.md`
- `.github/copilot-instructions.md`
- `CONTRIBUTING.md`

**Proposed Slides:**

| #    | Slide Title             | Content                                                                 |
| ---- | ----------------------- | ----------------------------------------------------------------------- |
| 11.1 | What is Maverick?       | AI-powered workflow orchestration, automating development lifecycle     |
| 11.2 | The Problem We Solve    | Manual development tasks, inconsistent workflows, error-prone processes |
| 11.3 | Architecture Overview   | Four-layer diagram: CLI → Workflows → Agents → Tools                    |
| 11.4 | Separation of Concerns  | What each layer does, why boundaries matter                             |
| 11.5 | Core Principles         | Async-first, dependency injection, fail gracefully                      |
| 11.6 | Full Ownership Standard | "Fix what you find", no artificial scope minimization                   |
| 11.7 | Project Structure Tour  | `src/maverick/` directory walkthrough                                   |
| 11.8 | Key Configuration Files | `pyproject.toml`, `CLAUDE.md`, `maverick.yaml`                          |

### 12. The Workflow DSL

- YAML-based workflow definitions
- Step types: `python`, `agent`, `validate`, `parallel`, `branch`, `loop`, `checkpoint`
- Expression syntax: `${{ inputs.name }}`, `${{ steps.x.output }}`
- Workflow discovery (project → user → built-in)

**Key Files:**

- `src/maverick/library/workflows/feature.yaml`
- `src/maverick/dsl/serialization/schema.py`
- `src/maverick/dsl/discovery/`

**Proposed Slides:**

| #     | Slide Title             | Content                                                        |
| ----- | ----------------------- | -------------------------------------------------------------- |
| 12.1  | Why YAML Workflows?     | Declarative, shareable, version-controllable, no Python needed |
| 12.2  | Workflow File Structure | `version`, `name`, `description`, `inputs`, `steps`, `outputs` |
| 12.3  | Input Declarations      | Types (`string`, `integer`, `boolean`), `required`, `default`  |
| 12.4  | Step Types Overview     | Quick overview of all 8 step types                             |
| 12.5  | Python Steps            | `type: python`, `action`, `args`, `kwargs`                     |
| 12.6  | Agent Steps             | `type: agent`, `agent`, `context`, invoking AI                 |
| 12.7  | Validate Steps          | `type: validate`, `stages`, `retry`, validation pipeline       |
| 12.8  | Parallel Steps          | `type: parallel`, concurrent execution, `max_concurrent`       |
| 12.9  | Branch Steps            | `type: branch`, `condition`, conditional execution             |
| 12.10 | Loop Steps              | `type: loop`, `for_each`, `while`, iteration patterns          |
| 12.11 | Checkpoint Steps        | `type: checkpoint`, resumption points, `checkpoint_id`         |
| 12.12 | Subworkflow Steps       | `type: subworkflow`, composition, `workflow`, `inputs`         |
| 12.13 | Expression Syntax       | `${{ inputs.x }}`, `${{ steps.y.output }}`, `${{ not ... }}`   |
| 12.14 | Workflow Discovery      | Three locations: project → user → built-in, override order     |

### 13. Expression Evaluation Engine

- Grammar definition
- Parsing and AST generation
- Context resolution (inputs, step outputs, iteration context)
- Template string interpolation

**Key Files:**

- `src/maverick/dsl/expressions/grammar.lark`
- `src/maverick/dsl/expressions/parser.py`
- `src/maverick/dsl/expressions/evaluator.py`

**Proposed Slides:**

| #     | Slide Title                | Content                                                        |
| ----- | -------------------------- | -------------------------------------------------------------- |
| 13.1  | Expression System Overview | Why we need expressions, what they enable                      |
| 13.2  | Expression Syntax          | `${{ ... }}` delimiters, what goes inside                      |
| 13.3  | Input References           | `${{ inputs.name }}` - accessing workflow inputs               |
| 13.4  | Step Output References     | `${{ steps.x.output }}`, `${{ steps.x.output.field }}`         |
| 13.5  | Iteration Context          | `${{ item }}`, `${{ index }}` in loops                         |
| 13.6  | Boolean Operations         | `${{ not inputs.dry_run }}`, `${{ inputs.x and inputs.y }}`    |
| 13.7  | Ternary Expressions        | `${{ inputs.x if inputs.flag else inputs.y }}`                 |
| 13.8  | Template Strings           | `"Hello ${{ inputs.name }}"` - mixing literals and expressions |
| 13.9  | The Lark Grammar           | Walking through `grammar.lark`                                 |
| 13.10 | Parser Implementation      | `parse_expression()`, AST node types                           |
| 13.11 | Evaluator Implementation   | `ExpressionEvaluator`, context lookup, nested access           |

### 14. Step Execution Framework

- Base step protocol and step handlers
- Step lifecycle: start → execute → complete/error
- Context threading between steps
- Parallel step execution

**Key Files:**

- `src/maverick/dsl/steps/base.py`
- `src/maverick/dsl/steps/python.py`
- `src/maverick/dsl/steps/agent.py`
- `src/maverick/dsl/steps/parallel.py`

**Proposed Slides:**

| #     | Slide Title             | Content                                                  |
| ----- | ----------------------- | -------------------------------------------------------- |
| 14.1  | Step Execution Overview | How workflow steps become executed code                  |
| 14.2  | StepHandler Protocol    | Interface all step handlers implement                    |
| 14.3  | Step Lifecycle          | `StepStarted` → execute → `StepCompleted`/`StepFailed`   |
| 14.4  | Execution Context       | What context is passed to each step, how outputs flow    |
| 14.5  | PythonStepHandler       | Loading actions, resolving arguments, calling functions  |
| 14.6  | AgentStepHandler        | Instantiating agents, building context, streaming output |
| 14.7  | ParallelStepHandler     | `asyncio.gather()`, concurrency limits, error handling   |
| 14.8  | BranchStepHandler       | Evaluating conditions, selecting execution path          |
| 14.9  | Context Threading       | How step outputs become available to later steps         |
| 14.10 | Error Handling          | Step failures, retry logic, propagation                  |

### 15. Agent Architecture

- `MaverickAgent` base class (`Generic[TContext, TResult]`)
- Built-in tools (Read, Write, Edit, Bash, Grep, etc.)
- Agent types: Implementer, CodeReviewer, Fixer
- Streaming responses and callbacks

**Key Files:**

- `src/maverick/agents/base.py`
- `src/maverick/agents/registry.py`

**Proposed Slides:**

| #     | Slide Title               | Content                                                |
| ----- | ------------------------- | ------------------------------------------------------ |
| 15.1  | What is a Maverick Agent? | AI agents as autonomous workers, judgment vs execution |
| 15.2  | MaverickAgent Base Class  | `Generic[TContext, TResult]`, abstract methods         |
| 15.3  | Context Types             | What information agents receive, type safety           |
| 15.4  | Result Types              | What agents return, structured output                  |
| 15.5  | System Prompts            | `build_system_prompt()`, guiding agent behavior        |
| 15.6  | Tool Selection            | `allowed_tools`, principle of least privilege          |
| 15.7  | Built-in Tools            | Read, Write, Edit, Bash, Glob, Grep, WebFetch          |
| 15.8  | Agent Registry            | Registering agents, looking up by name                 |
| 15.9  | Streaming Output          | `StreamCallback`, real-time progress                   |
| 15.10 | Agent Execution Flow      | From invocation to result                              |

### 16. The ImplementerAgent

- Task file parsing and execution
- Phase-based implementation
- TDD approach prompts
- Conventional commits integration

**Key Files:**

- `src/maverick/agents/implementer.py`
- `src/maverick/models/implementation.py`

**Proposed Slides:**

| #    | Slide Title               | Content                                             |
| ---- | ------------------------- | --------------------------------------------------- |
| 16.1 | ImplementerAgent Overview | The agent that writes code                          |
| 16.2 | Task File Format          | `tasks.md` structure, phases, task markers          |
| 16.3 | Phase-Based Execution     | Why phases, how tasks are grouped                   |
| 16.4 | ImplementerContext        | What the agent receives: task file, phase, settings |
| 16.5 | System Prompt Design      | TDD guidance, convention adherence, tool usage      |
| 16.6 | Task Execution Loop       | Reading tasks, implementing, marking complete       |
| 16.7 | File Change Detection     | Tracking what the agent modified                    |
| 16.8 | ImplementationResult      | Output structure, status, files changed             |
| 16.9 | Conventional Commits      | How commit messages are formatted                   |

### 17. MCP Tools Layer

- Tool server creation with `create_sdk_mcp_server`
- Validation tools (format, lint, typecheck, test)
- Git and GitHub operation tools
- Response formatting patterns

**Key Files:**

- `src/maverick/tools/validation.py`
- `src/maverick/tools/git/`
- `src/maverick/tools/github/`

**Proposed Slides:**

| #    | Slide Title               | Content                                                 |
| ---- | ------------------------- | ------------------------------------------------------- |
| 17.1 | MCP Tools in Maverick     | How tools extend agent capabilities                     |
| 17.2 | Tool Server Architecture  | `create_sdk_mcp_server()`, grouping tools               |
| 17.3 | Validation Tools Overview | format, lint, typecheck, test operations                |
| 17.4 | run_validation Tool       | Input parameters, execution, output parsing             |
| 17.5 | Output Parsing            | Ruff pattern, Mypy pattern, structured errors           |
| 17.6 | Git Tools                 | Repository operations exposed to agents                 |
| 17.7 | GitHub Tools              | Issue/PR operations exposed to agents                   |
| 17.8 | Response Patterns         | `_success_response()`, `_error_response()`, consistency |
| 17.9 | Error Handling in Tools   | Graceful failures, informative messages                 |

### 18. Safety Hooks

- Bash command safety (dangerous pattern detection)
- Path protection (system directories, config files)
- Unicode normalization for security
- Secret detection integration

**Key Files:**

- `src/maverick/hooks/safety.py`
- `src/maverick/hooks/config.py`

**Proposed Slides:**

| #    | Slide Title             | Content                                                   |
| ---- | ----------------------- | --------------------------------------------------------- |
| 18.1 | Why Safety Hooks?       | AI agents can be dangerous, defense in depth              |
| 18.2 | Hook Architecture       | Where hooks run, what they can do                         |
| 18.3 | Dangerous Bash Patterns | `rm -rf /`, fork bombs, disk formatting                   |
| 18.4 | Pattern Detection       | Regex patterns, `DANGEROUS_BASH_PATTERNS` list            |
| 18.5 | Command Normalization   | Unicode tricks, escape sequences, `normalize_command()`   |
| 18.6 | Path Protection         | System directories, config files, protected paths         |
| 18.7 | SafetyConfig            | Configuring what's blocked, allowlists                    |
| 18.8 | Secret Detection        | `detect-secrets` integration, preventing credential leaks |
| 18.9 | Logging & Alerting      | What gets logged when hooks block actions                 |

### 19. Checkpointing & Resumption

- Checkpoint data models
- Checkpoint storage and retrieval
- Resume logic in workflow execution
- Idempotent step design

**Key Files:**

- `src/maverick/dsl/checkpoint/data.py`
- `src/maverick/dsl/checkpoint/store.py`

**Proposed Slides:**

| #    | Slide Title            | Content                                              |
| ---- | ---------------------- | ---------------------------------------------------- |
| 19.1 | Why Checkpointing?     | Long workflows fail, cost of re-running from scratch |
| 19.2 | Checkpoint Concept     | Saving state at safe points, resuming later          |
| 19.3 | CheckpointData Model   | What's stored: step outputs, completion status       |
| 19.4 | Checkpoint Storage     | File-based store, `.maverick/checkpoints/`           |
| 19.5 | Creating Checkpoints   | `type: checkpoint` step, automatic checkpoints       |
| 19.6 | Resume Detection       | How Maverick detects existing checkpoints            |
| 19.7 | Resume Logic           | Skipping completed steps, restoring context          |
| 19.8 | Idempotent Step Design | Why steps must be safe to re-run                     |
| 19.9 | Checkpoint CLI         | `--restart` flag, checkpoint inspection              |

### 20. The TUI Layer

- `MaverickApp` structure
- Screen navigation and history
- Widget composition
- Display-only principle (no business logic)

**Key Files:**

- `src/maverick/tui/app.py`
- `src/maverick/tui/screens/`
- `src/maverick/tui/widgets/`

**Proposed Slides:**

| #     | Slide Title                 | Content                                           |
| ----- | --------------------------- | ------------------------------------------------- |
| 20.1  | TUI Design Philosophy       | Display-only, no business logic, streaming-first  |
| 20.2  | MaverickApp Class           | Entry point, composition, bindings                |
| 20.3  | Application Layout          | Header, sidebar, content, log panel, footer       |
| 20.4  | Screen Inventory            | Home, Workflow, Review, Settings screens          |
| 20.5  | Widget Inventory            | LogPanel, Sidebar, ShortcutFooter, custom widgets |
| 20.6  | Navigation System           | `NavigationContext`, history, breadcrumbs         |
| 20.7  | Command Palette             | `MaverickCommands` provider, keyboard shortcuts   |
| 20.8  | Workflow Runner Integration | How TUI receives workflow events                  |
| 20.9  | Streaming Event Display     | Real-time agent output in the TUI                 |
| 20.10 | TCSS Theming                | `maverick.tcss`, color schemes, layout rules      |

---

## Part 3: Advanced Topics

### 21. Workflow Library & Actions

- Built-in workflows: `feature`, `cleanup`, `review`, `validate`
- Python actions for workflows
- Fragment composition
- Custom workflow creation

**Key Files:**

- `src/maverick/library/workflows/`
- `src/maverick/library/actions/`
- `src/maverick/library/fragments/`

**Proposed Slides:**

| #     | Slide Title               | Content                                                 |
| ----- | ------------------------- | ------------------------------------------------------- |
| 21.1  | Built-in Workflow Library | What ships with Maverick, where to find them            |
| 21.2  | feature Workflow          | Full walkthrough: preflight → implement → validate → PR |
| 21.3  | cleanup Workflow          | Tech-debt resolution, issue selection, parallel fixes   |
| 21.4  | review Workflow           | Code review orchestration, dual-agent approach          |
| 21.5  | validate Workflow         | Validation pipeline, fix loops, stages                  |
| 21.6  | quick-fix Workflow        | Single-issue rapid resolution                           |
| 21.7  | Python Actions Overview   | What actions are, how they're called from YAML          |
| 21.8  | Writing Custom Actions    | Function signature, return values, registration         |
| 21.9  | Actions Inventory         | Tour of `library/actions/` modules                      |
| 21.10 | Workflow Fragments        | Reusable YAML snippets, composition patterns            |
| 21.11 | Creating Custom Workflows | Best practices, starting from templates                 |

### 22. Runners & Command Execution

- `CommandRunner` for subprocess management
- Validation runner pipeline
- Output parsing (Ruff, Mypy patterns)
- Timeout and error handling

**Key Files:**

- `src/maverick/runners/command.py`
- `src/maverick/runners/validation.py`
- `src/maverick/runners/parsers/`

**Proposed Slides:**

| #     | Slide Title             | Content                                             |
| ----- | ----------------------- | --------------------------------------------------- |
| 22.1  | Why Runners?            | Encapsulating subprocess execution, async safety    |
| 22.2  | CommandRunner Class     | `run()`, `run_async()`, capturing output            |
| 22.3  | Timeout Handling        | Preventing runaway processes, graceful termination  |
| 22.4  | Error Handling          | Exit codes, stderr capture, exception mapping       |
| 22.5  | Validation Runner       | Orchestrating format → lint → typecheck → test      |
| 22.6  | Stage Execution         | Running each stage, collecting results              |
| 22.7  | Output Parsers          | Why parse output, structured error extraction       |
| 22.8  | Ruff Parser             | Pattern matching, extracting file/line/code/message |
| 22.9  | Mypy Parser             | Pattern matching, severity levels                   |
| 22.10 | Validation Result Model | Aggregating errors across stages                    |

### 23. Configuration Management

- Config file hierarchy (`maverick.yaml`)
- Environment variables
- Model configuration (Claude variants)
- Validation and notification settings

**Key Files:**

- `src/maverick/config.py`
- `src/maverick/constants.py`

**Proposed Slides:**

| #     | Slide Title              | Content                                                  |
| ----- | ------------------------ | -------------------------------------------------------- |
| 23.1  | Configuration Philosophy | Layered config, sensible defaults, easy overrides        |
| 23.2  | Config File Locations    | `./maverick.yaml`, `~/.config/maverick/config.yaml`      |
| 23.3  | Config Precedence        | CLI args > project > user > defaults                     |
| 23.4  | MaverickConfig Class     | Top-level config model, nested configs                   |
| 23.5  | GitHubConfig             | `owner`, `repo`, `default_branch`                        |
| 23.6  | ModelConfig              | `model_id`, `max_tokens`, `temperature`, Claude variants |
| 23.7  | ValidationConfig         | Commands for format, lint, typecheck, test               |
| 23.8  | NotificationConfig       | ntfy integration, push notifications                     |
| 23.9  | ParallelConfig           | Concurrency limits, `max_agents`, `max_tasks`            |
| 23.10 | Environment Variables    | `ANTHROPIC_API_KEY`, `MAVERICK_LOG_LEVEL`, etc.          |
| 23.11 | Loading & Merging Config | `load_config()` function, merge algorithm                |

### 24. Testing Strategies

- `pytest-asyncio` for async tests
- Mocking external services (Claude API, GitHub)
- TUI testing with Textual pilot
- Test markers: `@pytest.mark.slow`, `@pytest.mark.integration`

**Key Files:**

- `tests/`
- `pyproject.toml` (pytest configuration)

**Proposed Slides:**

| #     | Slide Title        | Content                                                             |
| ----- | ------------------ | ------------------------------------------------------------------- |
| 24.1  | Testing Philosophy | Test-first, high coverage, fast feedback                            |
| 24.2  | pytest Basics      | Test discovery, fixtures, assertions                                |
| 24.3  | pytest-asyncio     | `async def test_*`, `asyncio_mode = "auto"`                         |
| 24.4  | Test Fixtures      | Common fixtures in Maverick, `conftest.py`                          |
| 24.5  | Mocking Claude API | Avoiding real API calls, predictable responses                      |
| 24.6  | Mocking GitHub     | `unittest.mock`, fake responses                                     |
| 24.7  | Mocking Git        | In-memory repos, avoiding filesystem                                |
| 24.8  | TUI Testing        | Textual's `pilot`, simulating user input                            |
| 24.9  | Test Markers       | `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.tui` |
| 24.10 | Coverage           | `pytest-cov`, coverage reports, targets                             |
| 24.11 | Test Organization  | Directory structure, naming conventions                             |

### 25. Code Quality & Tooling

- Ruff for linting and formatting
- MyPy strict mode configuration
- Makefile commands for AI-friendly output
- Pre-commit and CI integration

**Key Files:**

- `pyproject.toml`
- `Makefile`

**Proposed Slides:**

| #     | Slide Title        | Content                                                  |
| ----- | ------------------ | -------------------------------------------------------- |
| 25.1  | Quality Philosophy | Automated checks, consistent style, type safety          |
| 25.2  | Ruff Overview      | Fast linter + formatter, replaces multiple tools         |
| 25.3  | Ruff Configuration | `pyproject.toml` settings, rule selection                |
| 25.4  | Ruff in Practice   | `ruff check`, `ruff format`, fixing issues               |
| 25.5  | MyPy Overview      | Static type checking, catching bugs early                |
| 25.6  | MyPy Strict Mode   | What `strict = true` enables, common errors              |
| 25.7  | MyPy Configuration | `pyproject.toml` settings, per-file overrides            |
| 25.8  | The Makefile       | Why Make, AI-friendly output, command reference          |
| 25.9  | Make Commands      | `make test`, `make lint`, `make typecheck`, `make check` |
| 25.10 | CI Integration     | GitHub Actions, running checks on PR                     |
| 25.11 | Pre-commit Hooks   | Optional local enforcement                               |

---

## Part 4: Practical Labs

### 26. Lab: Create a Custom Workflow

**Objectives:**

- Define inputs and outputs
- Add python steps calling library actions
- Add conditional logic with `when`
- Test with `maverick fly --dry-run`

**Starting Point:**

```yaml
version: "1.0"
name: my-custom-workflow
description: A custom workflow

inputs:
  target:
    type: string
    required: true

steps:
  - name: setup
    type: python
    action: my_setup_action
    kwargs:
      target: ${{ inputs.target }}
```

**Proposed Slides:**

| #     | Slide Title                   | Content                                              |
| ----- | ----------------------------- | ---------------------------------------------------- |
| 26.1  | Lab Introduction              | What we'll build: a custom workflow from scratch     |
| 26.2  | Workflow Requirements         | Define the problem, inputs needed, expected outputs  |
| 26.3  | Step 1: Create Workflow File  | File location, basic structure, metadata             |
| 26.4  | Step 2: Define Inputs         | Input types, required vs optional, defaults          |
| 26.5  | Step 3: Add Python Steps      | Calling library actions, passing arguments           |
| 26.6  | Step 4: Add Conditional Logic | `when` clause, expression syntax                     |
| 26.7  | Step 5: Add Outputs           | Declaring workflow outputs, referencing step results |
| 26.8  | Step 6: Dry Run Testing       | `maverick fly --dry-run`, interpreting output        |
| 26.9  | Step 7: Full Execution        | Running for real, debugging issues                   |
| 26.10 | Lab Wrap-up                   | Review, common mistakes, next steps                  |

### 27. Lab: Build a Custom Agent

**Objectives:**

- Extend `MaverickAgent` base class
- Define system prompt and tools
- Implement context and result types
- Integrate with workflow steps

**Starting Point:**

```python
from maverick.agents.base import MaverickAgent

class MyCustomAgent(MaverickAgent[MyContext, MyResult]):
    """Custom agent for specific task."""

    def build_system_prompt(self, context: MyContext) -> str:
        return "You are an expert at..."

    async def execute(self, context: MyContext) -> MyResult:
        # Implementation
        pass
```

**Proposed Slides:**

| #     | Slide Title                  | Content                                   |
| ----- | ---------------------------- | ----------------------------------------- |
| 27.1  | Lab Introduction             | What we'll build: a specialized AI agent  |
| 27.2  | Agent Requirements           | Define the task, what the agent should do |
| 27.3  | Step 1: Define Context Type  | Dataclass/Pydantic model for agent input  |
| 27.4  | Step 2: Define Result Type   | Dataclass/Pydantic model for agent output |
| 27.5  | Step 3: Create Agent Class   | Inheriting from `MaverickAgent`, generics |
| 27.6  | Step 4: Write System Prompt  | Guiding agent behavior, constraints       |
| 27.7  | Step 5: Select Tools         | Which built-in tools, `allowed_tools`     |
| 27.8  | Step 6: Implement Execute    | Calling Claude, processing response       |
| 27.9  | Step 7: Register Agent       | Adding to registry, name mapping          |
| 27.10 | Step 8: Workflow Integration | Using agent in `type: agent` step         |
| 27.11 | Step 9: Testing              | Unit tests, mocking Claude responses      |
| 27.12 | Lab Wrap-up                  | Review, common patterns, advanced topics  |

### 28. Lab: Add a New MCP Tool

**Objectives:**

- Create tool function with `@tool` decorator
- Define input/output schemas
- Register in tool server
- Test tool execution

**Starting Point:**

```python
from claude_agent_sdk import tool

@tool
def my_custom_tool(input_param: str) -> dict:
    """Tool description for the AI agent.

    Args:
        input_param: Description of the parameter.

    Returns:
        Result dictionary with operation outcome.
    """
    # Implementation
    return {"status": "success", "result": "..."}
```

**Proposed Slides:**

| #     | Slide Title                   | Content                                          |
| ----- | ----------------------------- | ------------------------------------------------ |
| 28.1  | Lab Introduction              | What we'll build: a new tool for agents          |
| 28.2  | Tool Requirements             | What capability to add, when agents would use it |
| 28.3  | Step 1: Design Tool Interface | Function name, parameters, return type           |
| 28.4  | Step 2: Write Tool Function   | `@tool` decorator, implementation                |
| 28.5  | Step 3: Write Docstring       | Description, args, returns - AI reads this!      |
| 28.6  | Step 4: Handle Errors         | Try/except, error responses                      |
| 28.7  | Step 5: Create Tool Server    | `create_sdk_mcp_server()`, grouping tools        |
| 28.8  | Step 6: Register Server       | Making server available to agents                |
| 28.9  | Step 7: Unit Testing          | Testing tool function directly                   |
| 28.10 | Step 8: Integration Testing   | Agent using the tool                             |
| 28.11 | Lab Wrap-up                   | Review, tool design best practices               |

### 29. Lab: Extend the TUI

**Objectives:**

- Create a new widget
- Add a screen with navigation
- Style with TCSS
- Handle user input

**Starting Point:**

```python
from textual.widgets import Static
from textual.app import ComposeResult

class MyCustomWidget(Static):
    """A custom widget for Maverick TUI."""

    def compose(self) -> ComposeResult:
        yield Static("Hello from custom widget!")
```

**Proposed Slides:**

| #     | Slide Title                 | Content                                    |
| ----- | --------------------------- | ------------------------------------------ |
| 29.1  | Lab Introduction            | What we'll build: a new TUI feature        |
| 29.2  | Feature Requirements        | UI element needed, user interaction        |
| 29.3  | Step 1: Create Widget Class | Inheriting from base widget, `compose()`   |
| 29.4  | Step 2: Add Child Widgets   | Building widget tree, layout               |
| 29.5  | Step 3: Add Reactive State  | `reactive()` attributes, `watch_*` methods |
| 29.6  | Step 4: Handle Messages     | `on_*` handlers, custom messages           |
| 29.7  | Step 5: Create Screen       | `Screen` class, using the widget           |
| 29.8  | Step 6: Add Navigation      | Registering screen, navigation methods     |
| 29.9  | Step 7: Write TCSS Styles   | Selectors, properties, theming             |
| 29.10 | Step 8: Add Keybindings     | `BINDINGS`, actions                        |
| 29.11 | Step 9: Testing with Pilot  | Simulating input, assertions               |
| 29.12 | Lab Wrap-up                 | Review, TUI patterns, accessibility        |

---

## Recommended Learning Path

| Week | Topics       | Focus                                | Est. Slides |
| ---- | ------------ | ------------------------------------ | ----------- |
| 1    | Topics 1-5   | Python fundamentals & CLI/TUI basics | ~45 slides  |
| 2    | Topics 6-10  | External integrations & AI SDK       | ~45 slides  |
| 3    | Topics 11-15 | Maverick core architecture           | ~55 slides  |
| 4    | Topics 16-20 | Agents, tools, and safety            | ~50 slides  |
| 5    | Topics 21-25 | Advanced patterns & quality          | ~55 slides  |
| 6    | Topics 26-29 | Hands-on labs                        | ~45 slides  |

**Total Estimated Slides: ~295**

---

## Slide Summary by Section

| Part       | Section                                       | Slides |
| ---------- | --------------------------------------------- | ------ |
| **Part 1** | 1. Modern Python Development                  | 8      |
|            | 2. Click - Building CLI Applications          | 7      |
|            | 3. Pydantic - Data Validation & Configuration | 8      |
|            | 4. Textual - Terminal User Interfaces         | 11     |
|            | 5. structlog - Structured Logging             | 7      |
|            | 6. GitPython - Git Operations                 | 9      |
|            | 7. PyGithub - GitHub API Integration          | 8      |
|            | 8. Tenacity - Retry Logic                     | 8      |
|            | 9. Lark - Parsing and DSLs                    | 8      |
|            | 10. Claude Agent SDK - AI Agent Development   | 9      |
| **Part 2** | 11. Project Overview & Philosophy             | 8      |
|            | 12. The Workflow DSL                          | 14     |
|            | 13. Expression Evaluation Engine              | 11     |
|            | 14. Step Execution Framework                  | 10     |
|            | 15. Agent Architecture                        | 10     |
|            | 16. The ImplementerAgent                      | 9      |
|            | 17. MCP Tools Layer                           | 9      |
|            | 18. Safety Hooks                              | 9      |
|            | 19. Checkpointing & Resumption                | 9      |
|            | 20. The TUI Layer                             | 10     |
| **Part 3** | 21. Workflow Library & Actions                | 11     |
|            | 22. Runners & Command Execution               | 10     |
|            | 23. Configuration Management                  | 11     |
|            | 24. Testing Strategies                        | 11     |
|            | 25. Code Quality & Tooling                    | 11     |
| **Part 4** | 26. Lab: Create a Custom Workflow             | 10     |
|            | 27. Lab: Build a Custom Agent                 | 12     |
|            | 28. Lab: Add a New MCP Tool                   | 11     |
|            | 29. Lab: Extend the TUI                       | 12     |

---

## Prerequisites

- Python 3.10+ installed
- Familiarity with async/await syntax
- Basic Git knowledge
- GitHub account with `gh` CLI installed
- Claude API access (`ANTHROPIC_API_KEY`)

## Resources

- [Maverick Documentation](https://get2knowio.github.io/maverick/)
- [Claude Agent SDK](https://github.com/anthropics/anthropic-agent-sdk)
- [Textual Documentation](https://textual.textualize.io/)
- [Click Documentation](https://click.palletsprojects.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [structlog Documentation](https://www.structlog.org/)
- [GitPython Documentation](https://gitpython.readthedocs.io/)
- [PyGithub Documentation](https://pygithub.readthedocs.io/)
- [Lark Documentation](https://lark-parser.readthedocs.io/)
