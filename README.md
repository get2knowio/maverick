# Maverick

Point your AI agents at a task list and let them fly. Maverick orchestrates
implementation, code review, fixes, and PR creation — the full development
lifecycle on autopilot.

## What is Maverick?

Maverick is a Python CLI application that orchestrates AI-powered development
workflows using the Agent Client Protocol (ACP). It automates the complete
development lifecycle — from PRD decomposition through implementation,
validation, code review, and commit management — using a **bead-driven**
execution model.

**Core idea**: Everything is a bead. A bead is a unit of work managed by the
`bd` CLI tool. The implementer agent doesn't know or care whether it's building
a feature, fixing a lint error, or addressing a review finding — the bead
description tells it what to do.

### Key Features

- **Full PRD-to-code pipeline** — Generate flight plans from PRDs, decompose
  into work units, create beads, implement, review, and ship
- **Spec-derived verification properties** — Executable test assertions are
  derived from acceptance criteria at plan time and locked before implementation.
  A deterministic spec compliance gate verifies correctness mechanically —
  no reviewer opinion needed for functional correctness
- **SOP-driven decomposition** — Work units contain step-by-step procedures
  with RFC 2119 keywords (MUST, SHOULD, MAY), not abstract goal descriptions.
  Agents follow procedures rather than interpreting goals
- **Multi-provider routing** — Distribute work across Claude, Copilot, and
  Gemini with per-step provider/model configuration in `maverick.yaml`
- **Bead-driven workflows** — All work is tracked as beads with dependencies,
  priorities, and lifecycle management via `bd`
- **Autonomous AI agents** — Agents make decisions, implement code, review
  changes, and recover from failures via ACP subprocess communication
- **Pre-Flight Briefing Room** — Parallel AI analysis (scopist, codebase
  analyst, criteria writer, contrarian) before plan generation and refueling
- **Jujutsu (jj) VCS** — Write-path VCS operations use jj in colocated mode for
  snapshot/rollback safety; GitPython handles read-only operations
- **Workspace isolation** — All fly work happens in a hidden
  `~/.maverick/workspaces/` clone; your working directory stays untouched
- **Runway knowledge store** — Episodic records of bead outcomes, review
  findings, and fix attempts build project-specific context over time
- **Thespian actor system** — All workflows use Thespian `multiprocTCPBase`
  for true cross-process actor messaging. Each actor runs in its own OS
  process. Supervisors route messages via policy. Agent actors hold persistent
  ACP sessions. The MCP server delivers schema-validated tool calls directly
  to the supervisor's Thespian inbox — no files, no polling, no parsing.
- **MCP supervisor inbox** — Agents communicate results via MCP tool calls
  (`submit_outline`, `submit_review`, etc.). The `maverick serve-inbox`
  subcommand runs an MCP server with jsonschema validation that delivers
  to the Thespian supervisor. Built-in tools (Read/Write) are for work;
  MCP tools are for messaging.
- **Three information types** — Clean separation between beads (domain work
  units on the project board), files (durable context surviving restarts),
  and messages (ephemeral process coordination between actors)
- **Fly reports** — Structured JSON capturing the complete message exchange
  per bead, feeding into runway for process-level learning

## Quick Start

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) — Fast Python package manager (recommended)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- [Jujutsu](https://martinvonz.github.io/jj/) (`jj`) for VCS write operations
- [bd](https://beads.dev/) for bead/work-item management
- [claude-agent-acp](https://www.npmjs.com/package/@anthropic-ai/claude-agent-acp) — ACP agent subprocess
- Claude API access (set `ANTHROPIC_API_KEY` environment variable)
- Git repository with remote origin (jj runs in colocated mode)

### Installation

```bash
uv tool install maverick-cli
```

That's it. `maverick` lands on your PATH in its own isolated environment.

Alternatively, install from the repository:

```bash
uv tool install git+https://github.com/get2knowio/maverick.git
```

### Basic Usage

```bash
# Full PRD-to-code pipeline:
# 1. Generate a flight plan from a PRD
maverick plan generate my-feature --from-prd specs/my-feature/spec.md

# 2. Validate the generated plan
maverick plan validate my-feature

# 3. Decompose into work units and create beads
maverick refuel my-feature

# 4. Implement beads (in isolated workspace)
maverick fly --epic <epic-id> --max-beads 5

# 5. Curate history and merge into local repo
maverick land

# Alternative: create beads from a SpecKit specification
maverick refuel --from speckit 001-my-feature

# Other commands
maverick fly --skip-review --max-beads 5
maverick land --dry-run
maverick brief                  # Review queued beads
maverick brief --watch          # Live polling while fly runs
maverick runway seed            # Analyze codebase for runway context
maverick init                   # Initialize a new project
```

## Workflows

Maverick uses a beads-only workflow model. All development is driven by beads
(units of work managed by the `bd` CLI tool). Workflows are implemented as
Python async classes under `src/maverick/workflows/`.

### The PRD-to-Code Pipeline

The full pipeline takes a product requirements document and turns it into
shipped code:

```
PRD ──▶ plan generate ──▶ refuel ──▶ fly ──▶ land
         (+ derive          (SOP-style     (spec compliance
          verification       procedures)     replaces review
          properties)                        for correctness)
```

1. **Plan** — A Pre-Flight Briefing Room runs parallel AI analysts, then a
   generator synthesizes the output into a flight plan with verification
   properties (executable test assertions derived from acceptance criteria)
2. **Refuel** — Decomposes the plan into beads with SOP-style procedures
   (MUST/SHOULD/MAY steps) and threads verification properties
3. **Fly** — Actor-mailbox supervisor per bead: implementer and reviewer
   collaborate via persistent sessions with deterministic gate/AC/spec
   actors validating between rounds
4. **Land** — AI curator reorganizes commits (stripping internal bead
   references), merges clean conventional-commit history into your local repo

### `maverick plan generate` — Plan from PRD

Generates a flight plan from a product requirements document (PRD). Runs a
**Pre-Flight Briefing Room** — four parallel AI agents analyze the PRD before
a generator agent synthesizes the plan:

| Agent | Role |
|-------|------|
| **Scopist** | Defines scope boundaries, in/out decisions |
| **Codebase Analyst** | Maps relevant modules, patterns, dependencies |
| **Criteria Writer** | Drafts acceptance criteria and test scenarios |
| **Contrarian** | Identifies risks, blind spots, and over-engineering |

```bash
maverick plan generate my-feature --from-prd specs/my-feature/spec.md
```

### `maverick plan validate` — Validate Plan

Validates a generated flight plan for structural correctness.

```bash
maverick plan validate my-feature
```

### `maverick plan create` — Create Plan from Template

Creates a new flight plan file from a template for manual authoring.

```bash
maverick plan create my-feature
```

### `maverick refuel` — Decompose into Beads

Decomposes a flight plan into work units and creates beads. All artifacts
are stored in `.maverick/plans/<name>/`. Also runs a briefing room to
inform the decomposition.

Use `--from speckit` to load from a SpecKit specification instead.

```bash
maverick refuel my-feature
maverick refuel my-feature --dry-run
maverick refuel my-feature --skip-briefing
maverick refuel --from speckit 001-my-feature
```

### `maverick fly` — Bead-Driven Development

The primary execution command. Iterates over ready beads until done:

```
preflight ──▶ baseline_gate ──▶ create_workspace ──▶ bead loop
                                                        │
  ┌── select next ready bead ◄──────────────────────────┘
  │
  └── BeadSupervisor (actor-mailbox per bead)
      ├── ImplementerActor (persistent ACP session)
      │   ├── receives IMPLEMENT_REQUEST → writes code
      │   └── receives FIX_REQUEST → targeted fixes (same session)
      ├── GateActor (deterministic: build/lint/test)
      ├── AcceptanceCriteriaActor (deterministic: verification commands)
      ├── SpecComplianceActor (deterministic: VP tests)
      ├── ReviewerActor (persistent ACP session)
      │   ├── first review → full diff review
      │   └── follow-up → checks prior findings addressed (same session)
      └── CommitActor (jj commit + runway recording)

      Message flow:
      Implement → Gate → AC → Spec → Review ──┐
                                               │
      ┌── if approved ──────────── Commit ◄────┘
      └── if findings ── Fix → Gate → Review (up to 3 rounds)
```

The supervisor routes messages between actors. The implementer and reviewer
maintain persistent ACP sessions — the implementer remembers its decisions,
the reviewer checks its own prior findings. This eliminates review oscillation
(previously 11→10→12 per bead, now 0-1 rounds) and follow-up bead
proliferation (review negotiation stays within the bead as messages).

After `fly` finishes, run `maverick land` to curate history and merge.

| Flag | Default | Description |
|------|---------|-------------|
| `--epic <id>` | (any) | Filter to beads under this epic |
| `--max-beads <n>` | 30 | Maximum beads to process |
| `--dry-run` | false | Preview mode — skip git and bd mutations |
| `--skip-review` | false | Skip code review step |
| `--auto-commit` | false | Auto-commit uncommitted changes before cloning workspace |
| `--list-steps` | false | List workflow steps and exit |
| `--session-log <path>` | (none) | Write session journal (JSONL) |

### `maverick land` — Finalize and Ship

Curate commit history and merge into your local repo after `maverick fly`
completes. Uses an AI agent to intelligently reorganize commits (squash fix
commits, improve messages, reorder for logical flow), with user approval
before applying changes.

```bash
maverick land                    # Agent-curated history + merge
maverick land --dry-run          # Show plan without applying
maverick land --heuristic-only   # Heuristic curation (no agent)
maverick land --no-curate        # Skip curation, just merge
maverick land --yes              # Auto-approve the plan
maverick land --base develop     # Custom base revision
```

Three modes of operation:

| Mode | Command | Behavior |
|------|---------|----------|
| **Approve** (default) | `maverick land` | Curate → user approval → merge into local repo → cleanup workspace |
| **Eject** | `maverick land --eject` | Curate → create local preview branch → keep workspace |
| **Finalize** | `maverick land --finalize` | Merge preview branch → cleanup workspace |

| Flag | Default | Description |
|------|---------|-------------|
| `--no-curate` | false | Skip curation, just merge |
| `--dry-run` | false | Show plan without executing |
| `--yes` / `-y` | false | Auto-approve curation plan |
| `--base <rev>` | main | Base revision for curation scope |
| `--heuristic-only` | false | Use heuristic curation (no agent) |
| `--eject` | false | Create local preview branch, keep workspace |
| `--finalize` | false | Merge preview branch, cleanup workspace |
| `--no-consolidate` | false | Skip runway consolidation |
| `--branch <name>` | `maverick/<project>` | Custom branch name |

### `maverick brief` — Bead Dashboard

Review ready and blocked beads before starting a fly session. Use `--watch` for
live polling while `maverick fly` runs in another terminal.

### `maverick runway` — Knowledge Store

Manage the runway knowledge store — episodic records of bead outcomes, review
findings, and fix attempts that build project-specific context over time.

```bash
maverick runway init             # Initialize the runway store
maverick runway status           # Show store status and metrics
maverick runway seed             # AI-generated codebase analysis
maverick runway seed --dry-run   # Preview what would be generated
maverick runway consolidate      # Distill old records into summaries
maverick runway consolidate --force  # Run even if below thresholds
```

The `seed` command analyzes a brownfield codebase and pre-populates the runway
with architectural insights, making agents more effective from the first bead.

The `consolidate` command distills old episodic records into a semantic
`consolidated-insights.md` summary using an AI agent, then prunes the JSONL
files to keep only recent records. This runs automatically during
`maverick land` (disable with `--no-consolidate`) and can also be triggered
manually.

### `maverick init` — Project Setup

Initialize a new Maverick project with configuration files.

### `maverick workspace` — Workspace Management

Manage the hidden workspace used by `maverick fly`. The workspace lives in
`~/.maverick/workspaces/<project>/` and is a jj-colocated clone of your repo.

```bash
maverick workspace status           # Show workspace state for current project
maverick workspace clean            # Remove workspace for current project
maverick workspace clean --yes      # Skip confirmation prompt
```

## Architecture

Maverick follows a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer (Click + Rich)                                   │
│  maverick fly, refuel, plan, init, brief, land, runway,     │
│  serve-inbox                                                │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Workflow Layer (Python async)                              │
│  FlyBeadsWorkflow, GenerateFlightPlanWorkflow,              │
│  RefuelMaverickWorkflow                                     │
│  Starts Thespian ActorSystem, creates actors, sends "start" │
│  to supervisor, waits for "complete"                        │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Thespian Actor Layer (multiprocTCPBase)                    │
│  Each actor runs in its own OS process                      │
│                                                             │
│  Supervisors (routing policy in receiveMessage):            │
│  - RefuelSupervisorActor (outline → detail → validate)      │
│  - BeadSupervisor (implement → gate → review → commit)      │
│  - PlanSupervisor (briefing fan-out → generate → validate)  │
│                                                             │
│  Agent actors (persistent ACP sessions):                    │
│  - DecomposerActor, ImplementerActor, ReviewerActor         │
│  - BriefingActor (generic, parameterized per agent)         │
│                                                             │
│  Deterministic actors (pure Python):                        │
│  - ValidatorActor, GateActor, BeadCreatorActor,             │
│    CommitActor, SynthesisActor, PlanWriterActor             │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  MCP Supervisor Inbox (maverick serve-inbox)                │
│  Agent → MCP tool call → jsonschema validation →            │
│  Thespian tell() → supervisor's receiveMessage              │
│                                                             │
│  Built-in tools (Read/Write/Edit) = workspace work          │
│  MCP tools (submit_outline/review) = supervisor messages    │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  ACP Executor Layer (Agent Client Protocol)                 │
│  AcpStepExecutor — spawns agent subprocesses, supports      │
│  single-turn (execute) and multi-turn (create_session +     │
│  prompt_session) modes for persistent conversations         │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Agent Layer (prompt builders)                              │
│  ImplementerAgent, Reviewers, DecomposerAgent, CuratorAgent │
│  Briefing agents (Scopist, Analyst, CriteriaWriter)         │
│  FlightPlanGenerator                                        │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Tool & Runner Layer                                        │
│  CommandRunner, jj actions, GitPython, PyGithub,            │
│  validation runners, bd CLI, notifications                  │
└─────────────────────────────────────────────────────────────┘
```

### Separation of Concerns

- **Supervisors** are Thespian actors that own routing policy. Their `receiveMessage`
  is the inbox. MCP tool calls from agents arrive here directly. The supervisor
  routes to the next actor based on message type — no scattered control flow.
- **Agent actors** are Thespian actors that hold persistent ACP sessions. They
  receive prompts from the supervisor, send them to the LLM via ACP, and the
  LLM delivers results back to the supervisor via MCP tool calls.
- **Deterministic actors** are Thespian actors that wrap pure Python functions
  (validation, bead creation, gate checks). No ACP session needed.
- **MCP Supervisor Inbox** (`maverick serve-inbox`) bridges agents and supervisors.
  The agent calls MCP tools; the server validates via jsonschema and delivers
  via Thespian `tell()` to the supervisor's inbox.
- **Workflows** create the Thespian ActorSystem, instantiate actors, send "start"
  to the supervisor, and wait for "complete". They own the outer lifecycle.
- **ACP Executor** bridges agent actors and LLM subprocesses — supports both
  single-turn (`execute`) and multi-turn (`create_session` + `prompt_session`)
  modes for persistent conversations.
- **Agents** (prompt builders) know HOW to do a task — system prompts, tool
  selection. They build prompts; they don't own orchestration or state.

### Agent Execution via ACP

Agents run as `claude-agent-acp` subprocesses communicating over stdio via the
[Agent Client Protocol](https://github.com/anthropics/agent-client-protocol).
The executor handles:

- **Prompt construction** — Merges agent instructions, context, and output
  schema directives into a single prompt
- **Streaming output** — Agent text is streamed to the console in real-time
- **File-based structured output** — Reviewer and decomposer agents write
  JSON findings to disk files, avoiding text-stream truncation. The executor
  reads files first, falling back to text extraction if no file exists
- **Text extraction fallback** — When agents don't write files, the last
  JSON block in conversational output is extracted and validated against
  a Pydantic schema with schema coercion and truncation repair

### VCS: Jujutsu + Git

Maverick uses a dual-VCS approach in colocated mode (jj and git share the same
`.git` directory):

| Operation | Tool | Module |
|-----------|------|--------|
| Commit, push, branch, snapshot, rollback | **jj** | `maverick.jj.client.JjClient` |
| Diff, status, log, blame (read-only) | **GitPython** | `maverick.git` |

**Why jj?** Jujutsu provides snapshot/restore operations that enable safe
rollback when a bead fails verification. The `fly` workflow snapshots
before each bead, and restores to the snapshot if the verification gate fails.

### Runway Knowledge Store

The runway records episodic data as beads are processed:

- **Fly reports** — Complete message exchange per bead (the actor-mailbox
  conversation log), including findings trajectory, review rounds, timing,
  and implementation decisions
- **Bead outcomes** — Success/failure status, implementation details, error context
- **Review findings** — What reviewers flagged, severity, resolution status
- **Fix attempts** — What was tried, what worked, what didn't

This data is stored as JSONL files and per-bead JSON fly reports with
BM25-based retrieval. Over time, agents
can query the runway for context on past decisions, recurring patterns, and
known pitfalls. The `maverick runway seed` command bootstraps this store by
analyzing a brownfield codebase with an AI agent. Periodic consolidation
(automatic during `maverick land`, or manual via `maverick runway consolidate`)
distills old episodic records into semantic summaries, keeping the store bounded
in size and improving retrieval quality.

### Project Structure

See [CONTRIBUTING.md](CONTRIBUTING.md#directory-structure) for the full directory layout.

## Configuration

Maverick uses YAML configuration files with layered precedence:

1. Project config: `./maverick.yaml`
2. User config: `~/.config/maverick/config.yaml`
3. CLI arguments (highest precedence)

```yaml
# Project identity — used for skill guidance and prompt injection
project_type: python

# Project-specific conventions injected into agent prompts at runtime.
# Agents run as ACP subprocesses without access to CLAUDE.md, so any
# project-specific standards (canonical libraries, language style, async
# rules) must be declared here.
project_conventions: |
  ### Canonical Libraries
  - **Logging**: `structlog` via `get_logger()`
  - **Retry logic**: `tenacity` (`@retry`, `AsyncRetrying`)
  - **Validation**: Pydantic `BaseModel`

  ### Async-First
  - All workflows MUST be async.
  - Never call `subprocess.run` from `async def`.

github:
  owner: your-org
  repo: your-repo
  default_branch: main

model:
  model_id: claude-sonnet-4-5-20250929

validation:
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
  test_cmd: ["pytest", "-x", "--tb=short"]
  timeout_seconds: 300

notifications:
  enabled: false
  server: https://ntfy.sh
  topic: maverick-notifications

# Multi-provider routing — distribute work across providers
agent_providers:
  claude:
    default: true
    default_model: sonnet
  copilot:
    default: false
    default_model: gpt-5.3-codex
  gemini:
    default: false
    default_model: gemini-3.1-pro-preview

# Per-step provider/model overrides
steps:
  implement:
    provider: claude
    model_id: sonnet
    timeout: 1800
  completeness_review:
    provider: gemini
    model_id: gemini-3.1-pro-preview
  gate_remediation:
    provider: copilot
    model_id: gpt-5.3-codex
```

### Agent Convention Injection

Agents run as ACP subprocesses and do **not** see CLAUDE.md at runtime.
Convention guidance is injected into prompts via a two-tier model:

| Tier | Source | Scope |
|------|--------|-------|
| **Framework conventions** | Hardcoded in `FRAMEWORK_CONVENTIONS` | Universal orchestration principles (separation of concerns, hardening, testing, type safety, modularization) — always present |
| **Project conventions** | `project_conventions` field in `maverick.yaml` | Language-specific and project-specific standards (canonical libraries, async rules, naming, docstring style) — injected by `render_prompt()` |

This means Maverick works on any project type — Python, Rust, Node.js, Go,
Ansible — without baking language-specific assumptions into the agent core.
See [Agent Prompts Reference](docs/agent-prompts.md) for details.

## Technology Stack

| Category | Technology | Notes |
|----------|-----------|-------|
| Language | Python 3.11+ | `from __future__ import annotations` |
| Package Manager | uv | Fast, reproducible builds via `uv.lock` |
| Build System | Make | AI-friendly commands with minimal output |
| AI/Agents | Agent Client Protocol (ACP) | `agent-client-protocol` SDK + `claude-agent-acp` subprocess |
| Actor Framework | Thespian | `multiprocTCPBase` — each actor in its own OS process |
| MCP Tools | MCP SDK | Supervisor inbox server with jsonschema validation |
| CLI | Click + Rich | Auto TTY detection for output |
| Validation | Pydantic | Configuration and data models |
| VCS (writes) | Jujutsu (jj) | Colocated mode; `maverick.jj.client.JjClient` |
| VCS (reads) | GitPython | `maverick.git` (read-only) |
| GitHub API | PyGithub | `maverick.utils.github_client` |
| Logging | structlog | `maverick.logging.get_logger()` |
| Retry Logic | tenacity | `@retry` or `AsyncRetrying` |
| Knowledge Store | rank-bm25 | BM25-based retrieval for runway queries |
| Secret Detection | detect-secrets | Pre-commit secret scanning |
| Testing | pytest + pytest-asyncio | Parallel via xdist (`-n auto`) |
| Linting | Ruff | Fast, comprehensive Python linter |
| Type Checking | MyPy | Strict mode |

## Development

### Setup

```bash
git clone https://github.com/get2knowio/maverick.git
cd maverick
uv sync
uv run maverick --help
```

### Commands

```bash
make test           # Run all tests in parallel (errors only)
make test-fast      # Unit tests only, no slow tests (fastest)
make test-cov       # Run tests with coverage report
make lint           # Run ruff linter
make typecheck      # Run mypy
make format-fix     # Apply formatting fixes
make check          # Run all checks (lint, typecheck, test)
make ci             # CI mode: fail fast on any error
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

## Documentation

- [Agent Prompts Reference](docs/agent-prompts.md) — Complete catalog of all agent system prompts
- [Training Slides](https://get2knowio.github.io/maverick/slides/) — Technology and architecture deep dives
- [Training Curriculum](docs/curriculum.md) — Structured learning path

## License

MIT

## Links

- [Documentation Site](https://get2knowio.github.io/maverick/)
- [Contributing Guide](CONTRIBUTING.md)
- [Issue Tracker](https://github.com/get2knowio/maverick/issues)
- [Agent Client Protocol](https://github.com/anthropics/agent-client-protocol)
