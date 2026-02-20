# Maverick

Point your AI agents at a task list and let them fly. Maverick orchestrates
implementation, code review, fixes, and PR creation — the full development
lifecycle on autopilot.

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
uv tool install maverick
```

That's it. `maverick` lands on your PATH in its own isolated environment.

Alternatively, install from the repository:

```bash
uv tool install git+https://github.com/get2knowio/maverick.git
```

### Basic Usage

```bash
# Refuel: create beads from a SpecKit specification
maverick refuel speckit .specify/specs/my-feature/

# Fly: implement, validate, review, and commit
maverick fly
maverick fly --epic my-epic
maverick fly --skip-review --max-beads 5

# Land: curate history and push
maverick land
maverick land --dry-run
maverick land --heuristic-only

# Review queued beads before flying
maverick brief

# Watch bead status live while fly runs
maverick brief --watch --interval 2

# Initialize a new Maverick project
maverick init
```

## Workflows

Maverick uses a beads-only workflow model. All development is driven by beads
(units of work managed by the `bd` CLI tool).

### `maverick fly` — Bead-Driven Development

The primary command. Iterates over ready beads until done, running the
`fly-beads` YAML workflow:

```
preflight ──▶ create_workspace ──▶ bead loop
                                      │
                                      ├── select next ready bead
                                      ├── snapshot (jj operation for rollback)
                                      ├── describe_change (bead → change description)
                                      ├── implement (ImplementerAgent)
                                      ├── sync_deps (install/update dependencies)
                                      ├── validate & fix (format/lint/typecheck/test, 3 attempts)
                                      ├── create fix beads (for remaining failures)
                                      ├── review & fix (UnifiedReviewerAgent, 2 cycles)
                                      ├── create review beads (for remaining findings)
                                      ├── verify completion gate
                                      ├── rollback on failure / commit on success
                                      ├── close bead
                                      └── check_done (exit or next bead)
```

After `fly` finishes, run `maverick land` to curate history and push.

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

### `maverick brief` — Bead Dashboard

Review ready and blocked beads before starting a fly session. Use `--watch` for
live polling while `maverick fly` runs in another terminal.

### `maverick land` — Finalize and Ship

Curate commit history and push after `maverick fly` completes. Uses an AI agent
to intelligently reorganize commits (squash fix commits, improve messages,
reorder for logical flow), with user approval before applying changes.

```bash
maverick land                    # Agent-curated history + push
maverick land --dry-run          # Show plan without applying
maverick land --heuristic-only   # Heuristic curation (no agent)
maverick land --no-curate        # Skip curation, just push
maverick land --yes              # Auto-approve the plan
maverick land --base develop     # Custom base revision
```

| Flag | Default | Description |
|------|---------|-------------|
| `--no-curate` | false | Skip curation, just push |
| `--dry-run` | false | Show plan without executing |
| `--yes` / `-y` | false | Auto-approve curation plan |
| `--base <rev>` | main | Base revision for curation scope |
| `--heuristic-only` | false | Use heuristic curation (no agent) |
| `--eject` | false | Push to preview branch, keep workspace |
| `--finalize` | false | Create PR from preview branch, teardown |
| `--branch <name>` | `maverick/<project>` | Custom branch name |

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
│  maverick fly, refuel, init, brief, land                    │
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
│  SimpleFixerAgent, IssueFixerAgent, CuratorAgent, Generators│
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

See [CONTRIBUTING.md](CONTRIBUTING.md#directory-structure) for the full directory layout.

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
# Project identity — used for skill guidance and prompt injection
project_type: python

# Project-specific conventions injected into agent prompts at runtime.
# Agents run via the Claude Agent SDK without access to CLAUDE.md, so any
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
```

#### Agent Convention Injection

Agents run via the Claude Agent SDK and do **not** see CLAUDE.md at runtime.
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
- [Claude Agent SDK](https://github.com/anthropics/anthropic-agent-sdk)
