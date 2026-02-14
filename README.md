# Maverick

AI-powered development workflow orchestration with autonomous agent execution.

## What is Maverick?

Maverick is a Python CLI application that orchestrates AI-powered development
workflows using the Claude Agent SDK. It automates the complete development
lifecycle — from task creation through implementation, validation, code review,
and commit management — using a **bead-driven** execution model.

**Core idea**: Everything is a bead. A bead is a unit of work managed by the
`bd` CLI tool. The implementer agent doesn't know or care whether it's building
a feature, fixing a lint error, or addressing a review finding — the bead
description tells it what to do.

### Key Features

- **Bead-driven workflows** — All work is tracked as beads with dependencies,
  priorities, and lifecycle management via `bd`
- **Autonomous AI agents** — Agents make decisions, implement code, review
  changes, and recover from failures
- **YAML-based workflow DSL** — Declarative, shareable workflow definitions with
  conditional logic, parallel execution, loops, and checkpoints
- **Jujutsu (jj) VCS** — Write-path VCS operations use jj in colocated mode for
  snapshot/rollback safety; GitPython handles read-only operations
- **Resilient operation** — Automatic retries, validation-fix loops,
  review-fix cycles, and bead-level rollback on failure
- **Extensible architecture** — Custom workflows, agents, and MCP tools with
  three-location discovery (project, user, built-in)

## Quick Start

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) — Fast Python package manager (recommended)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- [Jujutsu](https://martinvonz.github.io/jj/) (`jj`) for VCS write operations
- [bd](https://beads.dev/) for bead/work-item management
- Claude API access (set `ANTHROPIC_API_KEY` environment variable)
- Git repository with remote origin (jj runs in colocated mode)

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install with uv (uses uv.lock for reproducible builds)
uv sync

# Run maverick
uv run maverick --help
```

### Basic Usage

```bash
# Fly: implement the next ready beads under an epic
maverick fly
maverick fly --epic my-epic
maverick fly --epic my-epic --dry-run
maverick fly --skip-review --max-beads 5

# Refuel: create beads from a SpecKit specification
maverick refuel speckit .specify/specs/my-feature/

# Initialize a new Maverick project
maverick init

# Review queued beads before flying
maverick briefing
```

## Workflows

Maverick uses a beads-only workflow model. All development is driven by beads
(units of work managed by the `bd` CLI tool).

### `maverick fly` — Bead-Driven Development

The primary command. Iterates over ready beads until done, running the
`fly-beads` YAML workflow:

```
preflight ──▶ bead loop ──▶ curate history ──▶ push
                 │
                 ├── select next ready bead
                 ├── snapshot (jj operation for rollback)
                 ├── implement (ImplementerAgent)
                 ├── validate & fix (format/lint/typecheck/test, 3 attempts)
                 ├── create fix beads (for remaining failures)
                 ├── review & fix (UnifiedReviewerAgent, 2 cycles)
                 ├── create review beads (for remaining findings)
                 ├── verify completion gate
                 ├── rollback on failure / commit on success
                 └── close bead
```

**Options**:

| Flag | Default | Description |
|------|---------|-------------|
| `--epic <id>` | (any) | Filter to beads under this epic |
| `--max-beads <n>` | 30 | Maximum beads to process |
| `--dry-run` | false | Preview mode — skip git and bd mutations |
| `--skip-review` | false | Skip code review step |
| `--list-steps` | false | List workflow steps and exit |
| `--session-log <path>` | (none) | Write session journal (JSONL) |

**How failures become beads**: When validation or review finds issues that can't
be auto-fixed, new beads are created under the same epic with high priority.
The outer loop picks them up on the next iteration — no inline fix loops needed.

### `maverick refuel speckit` — Bead Creation

Creates beads from a SpecKit specification directory containing `tasks.md`:

1. **Parse** — Extract phases and tasks from `tasks.md`
2. **Create** — Generate epic and work beads via `bd`
3. **Enrich** — Add acceptance criteria and context to bead descriptions
4. **Wire** — Set up dependencies between beads

```bash
maverick refuel speckit .specify/specs/my-feature/
maverick refuel speckit .specify/specs/my-feature/ --dry-run
```

### `maverick init` — Project Setup

Initialize a new Maverick project with configuration files.

### `maverick briefing` — Bead Queue Review

Review queued beads before starting a fly session.

## Architecture

Maverick follows a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer (Click + Rich)                                   │
│  maverick fly, refuel, init, briefing                       │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Workflow DSL Layer                                         │
│  YAML parsing, step execution (python, agent, validate,     │
│  parallel, loop, subworkflow, checkpoint), bead lifecycle   │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Agent Layer (Claude Agent SDK)                             │
│  ImplementerAgent, UnifiedReviewerAgent, FixerAgent,        │
│  SimpleFixerAgent, IssueFixerAgent, Generators              │
│  (system prompts, tool selection, autonomous decisions)      │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Tool & Runner Layer                                        │
│  MCP tools, CommandRunner, jj actions, GitPython,           │
│  PyGithub, validation runners, notifications                │
└─────────────────────────────────────────────────────────────┘
```

### Separation of Concerns

- **Agents** know HOW to do a task — system prompts, tool selection, Claude SDK
  interaction. They provide judgment (implementation, review, fix suggestions).
- **Workflows** know WHAT to do and WHEN — orchestration, state management,
  sequencing. They own deterministic side effects (commits, validation, retries).
- **Tools** wrap external systems — GitHub API, VCS, notifications.

### VCS: Jujutsu + Git

Maverick uses a dual-VCS approach in colocated mode (jj and git share the same
`.git` directory):

| Operation | Tool | Module |
|-----------|------|--------|
| Commit, push, branch, snapshot, rollback | **jj** | `maverick.library.actions.jj` |
| Diff, status, log, blame (read-only) | **GitPython** | `maverick.git` |

**Why jj?** Jujutsu provides snapshot/restore operations that enable safe
rollback when a bead fails verification. The `fly-beads` workflow snapshots
before each bead, and restores to the snapshot if the verification gate fails.

### Project Structure

```
src/maverick/
├── cli/                 # Click CLI commands
│   └── commands/        # fly, refuel, init, briefing, uninstall
├── dsl/                 # Workflow DSL implementation
│   ├── serialization/   # YAML parsing, schema, executor
│   ├── discovery/       # Workflow discovery from locations
│   ├── steps/           # Step type implementations
│   └── visualization/   # ASCII and Mermaid diagram generation
├── agents/              # Agent implementations
│   ├── prompts/         # Shared prompt fragments
│   ├── code_reviewer/   # CodeReviewerAgent (pre-gathered context)
│   ├── reviewers/       # UnifiedReviewerAgent, SimpleFixerAgent
│   ├── generators/      # Text generators (commit, PR, error, bead)
│   ├── implementer.py   # ImplementerAgent (bead execution)
│   ├── fixer.py         # FixerAgent (targeted validation fixes)
│   └── issue_fixer.py   # IssueFixerAgent (GitHub issue resolution)
├── beads/               # Bead models, client, speckit integration
├── library/             # Built-in workflows and actions
│   ├── workflows/       # YAML workflow definitions (fly-beads, refuel-speckit)
│   ├── actions/         # Python actions (jj, beads, workspace, review)
│   └── fragments/       # Reusable workflow fragments
├── tools/               # MCP tool definitions
├── runners/             # Subprocess runners (validation, commands)
├── models/              # Pydantic/dataclass models
└── utils/               # Shared utilities (github_client, secrets)
```

## Workflow DSL

Workflows are defined in YAML with a rich set of step types:

```yaml
version: "1.0"
name: my-workflow
description: Example workflow

inputs:
  branch_name:
    type: string
    required: true
  skip_tests:
    type: boolean
    default: false

steps:
  # Python action
  - name: setup
    type: python
    action: init_workspace
    kwargs:
      branch: ${{ inputs.branch_name }}

  # Agent invocation
  - name: implement
    type: agent
    agent: implementer
    context:
      task_description: ${{ steps.setup.output.task_description }}

  # Validation with retry
  - name: validate
    type: validate
    stages: ["format", "lint", "typecheck", "test"]
    retry: 3

  # Conditional execution
  - name: run_tests
    type: python
    action: run_tests
    when: ${{ not inputs.skip_tests }}

  # Parallel execution
  - name: parallel_reviews
    type: parallel
    steps:
      - name: agent_review
        type: agent
        agent: unified_reviewer
      - name: static_analysis
        type: python
        action: run_static_analysis

  # Loop with exit condition
  - name: work_loop
    type: loop
    until: ${{ steps.check_done.output.done }}
    max_iterations: 30
    steps:
      - name: do_work
        type: python
        action: process_next_item

  # Sub-workflow
  - name: create_pr
    type: subworkflow
    workflow: create-pr-with-summary
    inputs:
      base_branch: main
```

### Workflow Discovery

Workflows are discovered from three locations (higher precedence overrides lower):

1. **Project** — `.maverick/workflows/` — Project-specific customizations
2. **User** — `~/.config/maverick/workflows/` — User-wide customizations
3. **Built-in** — Packaged with Maverick — Default implementations

## Configuration

Maverick uses YAML configuration files with layered precedence:

1. Project config: `./maverick.yaml`
2. User config: `~/.config/maverick/config.yaml`
3. CLI arguments (highest precedence)

```yaml
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
```

## Technology Stack

| Category | Technology | Notes |
|----------|-----------|-------|
| Language | Python 3.10+ | `from __future__ import annotations` |
| Package Manager | uv | Fast, reproducible builds via `uv.lock` |
| Build System | Make | AI-friendly commands with minimal output |
| AI/Agents | Claude Agent SDK | `claude-agent-sdk` package |
| CLI | Click + Rich | Auto TTY detection for output |
| Validation | Pydantic | Configuration and data models |
| VCS (writes) | Jujutsu (jj) | Colocated mode; `maverick.library.actions.jj` |
| VCS (reads) | GitPython | `maverick.git` (read-only) |
| GitHub API | PyGithub | `maverick.utils.github_client` |
| Logging | structlog | `maverick.logging.get_logger()` |
| Retry Logic | tenacity | `@retry` or `AsyncRetrying` |
| Testing | pytest + pytest-asyncio | Parallel via xdist (`-n auto`) |
| Linting | Ruff | Fast, comprehensive Python linter |
| Type Checking | MyPy | Strict mode recommended |

## Development

### Development Commands

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
- [Claude Agent SDK](https://github.com/anthropics/anthropic-agent-sdk)
