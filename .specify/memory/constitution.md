<!--
Sync Impact Report
==================
Version change: 2.0.0 to 2.0.1 (PATCH)

Bump rationale: factual correction to the Technology Stack table only -- the
language floor is Python 3.12+, not 3.11+. No principle, guardrail, or appendix
changed, so PATCH ("clarifications, wording improvements") applies.

Corrected drift:
  - Technology Stack: Python 3.11+ -> Python 3.12+. airframe-agents >= 0.9.2
    requires Python >= 3.12, so 056-context-file-protection raised
    pyproject.toml's requires-python and the CI matrix (3.12 / 3.13) to match.
    README.md and CLAUDE.md carried the same stale floor and were corrected in
    the same change.

Source: post-merge sweep after 056-context-file-protection (PRs #184, #185).

--- Previous amendment (2.0.0) -------------------------------------------------

Version change: 1.11.0 to 2.0.0 (MAJOR)

Bump rationale: Principle II is redefined (its TUI display-only and streaming-first
mandates are removed and replaced with the airframe/Burr layering), two architectural
guardrails are removed, and the guardrail numbering is renumbered to align with
CLAUDE.md. These are backward-incompatible governance changes under the amendment
policy, which requires MAJOR for principle removals or redefinitions.

Modified principles:
  - II. Separation of Concerns -> II. Separation of Concerns (redefined)
    Removed the TUI display-only rule and the streaming-first design mandate; replaced
    with the four-layer model actually in use: Agents / Squadrons / Workflows + Burr
    graphs / Actions, plus a CLI presentation boundary.
  - X. Architectural Guardrails: renumbered 1-10 to 0-10 so the constitution and
    CLAUDE.md refer to the same guardrail by the same number. Removed the TUI
    display-only guardrail and the TUI unified-event-pattern guardrail. Added
    Guardrail 0 (single-repo CWD model), Guardrail 7 (explicit cwd threading), and
    Guardrail 10 (deterministic ingestion preferred over model inference).

Added sections:
  - XIII. Determinism Over Inference (new principle; the Spec Kit default)
  - Appendix F: Decomposition Entry Paths (Spec Kit default, classic fallback)

Removed sections:
  - Appendix C: TUI Streaming Architecture -> replaced by Appendix C: CLI Output
    Conventions. src/maverick/tui/ does not exist; Textual is not a dependency.
  - Claude Agent SDK Patterns -> replaced by Agent Runtime (airframe) Patterns.
    claude-agent-sdk is not a dependency; every LLM call goes through airframe.

Corrected drift (documented modules that no longer exist):
  - Technology Stack: Textual, Claude Agent SDK, WorkspaceManager, Python 3.10+
  - Appendix B: WorkspaceManager row removed; VCS-writes row corrected to jj
  - File Organization: replaced with the current layout (no tui/, exceptions/ is a
    package, workspace/ holds only spec_chain.py)

Templates requiring updates:
  - .specify/templates/plan-template.md   -- no change needed (Constitution Check is a
    generic "[Gates determined based on constitution file]" placeholder)
  - .specify/templates/spec-template.md   -- no change needed (no constitution refs)
  - .specify/templates/tasks-template.md  -- no change needed (no constitution refs)
  - .claude/skills/speckit-*/SKILL.md     -- no change needed (no agent-specific or
    outdated CLAUDE-only references found)

Propagated:
  - CLAUDE.md updated in the same change (Spec Kit as default path; removed the
    unregistered `maverick workspace status|clean` row).

Follow-up TODOs:
  - .claude/skills/tui-debugger/ references a TUI that no longer exists. Out of scope
    for a constitution amendment; flagged for manual removal.

Source: User directive 2026-07-27 -- "update our constitution and Claude.md to reflect
our speckit focus going forward", with the classic flight-plan path retained as a
supported fallback rather than deprecated.
-->

# Maverick Constitution

## Core Principles

### I. Async-First

All agent interactions and workflows MUST be async. This is non-negotiable for maintaining
responsiveness and enabling concurrent operations.

- Use `asyncio` patterns consistently; no threading for I/O operations
- Workflows MUST yield progress as async generators for CLI consumption
- All airframe runtime interactions are inherently async and MUST remain so
- Blocking I/O in async contexts is prohibited
- **Never call `subprocess.run` from an `async def` path**—use `CommandRunner` or
  `asyncio.create_subprocess_exec` with proper timeouts
- Python action callables MUST be async, or MUST be offloaded via `asyncio.to_thread`

**Rationale**: Long-running agent operations must report progress without blocking the
event loop. Blocking calls in async contexts cause stalls and deadlocks.

### II. Separation of Concerns

Components have distinct, non-overlapping responsibilities. Maverick composes four
layers, and each layer MUST stay inside its boundary:

- **Agents** (`src/maverick/agents/`): Know HOW to do a task—prompts, role, and the
  `result_model` that airframe forces the provider to return. Agents provide judgment
  (implementation, review, decomposition, fix suggestions). They MUST NOT own
  deterministic side effects such as commits, pushes, or running validation, and they
  MUST NOT orchestrate themselves.
- **Squadrons** (`src/maverick/squadron/`): Own per-run lifecycle. A squadron builds one
  airframe runtime per agent role, opens every agent the workflow needs, and closes them
  all on exit. Opened once per run and handed to the graph.
- **Workflows and Burr graphs** (`src/maverick/workflows/<name>/`): Know WHAT to do and
  WHEN. `burr_graph.py` wires actions into a state machine with explicit transitions;
  this is the only place control flow lives. Workflows own deterministic execution,
  retries, checkpointing, and error-recovery policy.
- **Actions** (`actions.py`, `src/maverick/library/actions/`): Plain `async def`
  functions decorated with `@action(reads=[...], writes=[...])`. Each owns one step and
  reads/writes only the state slots it declares. Actions MUST be pure functions of state
  plus injected collaborators bound via `.bind(...)` in the graph.

**CLI presentation is a boundary, not a layer with logic.** All user-facing output goes
through the Rich `console` / `err_console` in `maverick.cli.console` (see Appendix C).
Business logic MUST NOT live in CLI command modules; they resolve arguments, resolve
`cwd`, invoke a workflow, and render its events.

**Rationale**: Clear boundaries enable independent testing, easier debugging, and prevent
the coupling that makes systems brittle. Keeping control flow in the graph—rather than
smeared across actions—is what makes a workflow's behavior reviewable as a whole.

### III. Dependency Injection

Agents and workflows MUST receive configuration and dependencies, not access global state.

- Airframe runtimes are constructed by the squadron and injected, not created inside agents
- Configuration objects are injected at construction time
- External service clients (GitHub, git, jj, bd) are injectable for testing
- Collaborators reach actions through Burr's `.bind(...)`, never through module globals
- No module-level mutable state

**Rationale**: Dependency injection enables testing with fakes and makes dependencies
explicit rather than hidden.

### IV. Fail Gracefully, Recover Aggressively

One agent or work item failing MUST NOT crash the entire workflow. The system MUST
prioritize forward progress over early termination.

- Always capture and report errors with context before attempting recovery
- Retry failed operations with exponential backoff (default: 3 attempts)
- Provide actionable error messages that help diagnose what went wrong
- Use structured error types from the exception hierarchy
- Continue processing remaining work items even when some fail
- Aggregate partial results rather than discarding successful work
- **A failed agent in a fan-out MUST degrade, not abort**, whenever its output is
  optional to downstream consumers. If every consumer already treats a result as
  optional, a failure to produce it MUST be reported as a warning and the run MUST
  continue.
- **Caches MUST persist before the next thing that can fail**, not after. A cache whose
  purpose is making a failure cheap is worthless if the only write sits downstream of
  the most likely failure point.
- **Resilience features MUST be real, not stubs**: retry and fix loops MUST actually
  invoke the fixer and re-run validation. If the graph is the right place for retry
  logic, implement it there rather than simulating it in an action.

**Rationale**: Parallel agent execution means partial success is valuable. Unattended
operation requires recovering from transient failures without human intervention. The
degrade-and-cache rules are not hypothetical: a briefing agent failing structured-output
validation once took down an entire refuel and discarded 290 seconds of already-completed
agent work, because the failure was fatal and the only cache write sat behind it.
Stub resilience creates false confidence and hides real failure modes.

### V. Test-First (Anti-Deferral)

Every public class and function MUST have tests. Testing is mandatory, not optional.
No PR shall be merged without tests covering new functionality.

- Use pytest fixtures for common setup
- Mock external dependencies (model providers, GitHub API, filesystem)
- Async tests use `pytest.mark.asyncio`
- Tests are written BEFORE implementation (Red-Green-Refactor)
- Do NOT comment out or skip failing tests; fix them immediately (including failures
  that predate your change)
- For async components, testing MUST verify concurrency and error states, not just
  happy paths
- **A regression test MUST bind to the real code path**, not to a copy of the expression
  it is testing. If a function is untestable because it is inlined inside an
  orchestration path, extract it rather than duplicating it into the test.
- **A new regression test MUST be observed failing against the unfixed code** before the
  fix is accepted. A test that passes both before and after proves nothing.

**Rationale**: TDD catches design problems early. Comprehensive tests enable confident
refactoring and serve as executable documentation. The bind-to-real-code and
observed-failing rules exist because a test that mirrors the implementation, or that
never went red, silently stops protecting the behavior it names.

### VI. Type Safety & Typed Contracts

Complete type hints are required throughout the codebase. No magic numbers or strings.
All workflow actions MUST have a single, typed contract.

- All public functions MUST have complete type annotations
- Use `TypeAlias` for complex types to improve readability
- Prefer `@dataclass` or Pydantic `BaseModel` over plain dicts for structured data
- Use `Protocol` (structural typing) for interfaces between components to avoid
  circular dependencies and tight coupling
- Use `@dataclass(frozen=True)` for immutable value objects
- No magic numbers or string literals in logic code; extract to named constants or config
- **Actions MUST NOT return ad-hoc `dict[str, Any]` blobs.** Use frozen dataclasses
  (with `to_dict()` where serialization is needed) or `TypedDict` validated at boundaries.
- **Keep action outputs stable across versions**; treat them as public interfaces.
- **Agent results are Pydantic models.** An agent declares a `result_model` and airframe
  forces the provider to return it; payloads round-trip via `maverick.payloads`.
- **Pydantic Field descriptions**: required `Field(...)` declarations SHOULD include a
  `description` for schema generation.

**Rationale**: Static typing catches errors at development time and serves as inline
documentation. Typed contracts prevent runtime surprises and make refactoring safe.
Structured output is what lets a model's answer be validated rather than parsed.

### VII. Simplicity & DRY

Avoid over-engineering. Start simple and add complexity only when justified.
Zero tolerance for duplication.

- No global mutable state
- No massive god-classes; prefer composition over inheritance
- No hardcoded paths; use `pathlib` and configuration
- No premature abstractions; three similar lines are better than a premature helper
- No `shell=True` in subprocess calls without explicit security justification
- No `print()` or `click.echo()` for output; use the Rich console (Appendix C)
- If logic for VCS operations, validation, or GitHub API calls is needed in a second
  location, refactor to a shared utility IMMEDIATELY—do not wait for "cleanup"
- Use mixins or composition over inheritance for shared agent capabilities

**Rationale**: YAGNI. Simple code is easier to understand, test, and maintain.
Copy-paste creates maintenance nightmares and inconsistent behavior.

### VIII. Relentless Progress

The system MUST make forward progress at all costs during unattended operation. This is
the paramount principle for autonomous agent orchestration.

- **Never give up silently**: exhaust all recovery options before failing a task
- **Checkpoint state**: persist progress after each significant operation to enable resumption
- **Degrade gracefully**: when optimal paths fail, fall back to slower but reliable alternatives
- **Isolate failures**: one task's failure MUST NOT block unrelated tasks from proceeding
- **Auto-recover external dependencies**: retry with backoff for GitHub API and VCS
  operations (default: 3 attempts with exponential backoff)
- **Preserve partial work**: commit completed work before attempting risky operations
- **Log for resumption**: record sufficient state to allow manual or automatic retry

Recovery hierarchy (in order of preference):

1. Retry the exact operation with backoff
2. Try an alternative approach to achieve the same goal
3. Skip the failing component and continue with remaining work
4. Checkpoint state and surface an actionable error for user intervention

**Rationale**: Maverick operates unattended for extended periods. Human intervention is
expensive and slow. Forward progress is more valuable than early termination with a
clean error message.

### IX. Hardening by Default

All external interactions MUST assume unreliable networks and resources.
Never assume external calls will succeed on the first attempt.

- All external calls (model providers, GitHub API, VCS subprocesses) MUST have:
  - Explicit timeouts (no infinite waits)
  - Retry logic with exponential backoff for network operations
  - Specific exception handling (no bare `except Exception`)
- **Retry logic MUST use tenacity**: use the `@retry` decorator or `AsyncRetrying`.
  Do NOT write manual `for attempt in range(retries):` loops.
- Validate at system boundaries (user input, external APIs) but trust internal code
- Documentation examples MUST be treated as code—add tests that validate snippets in
  `README.md` or `docs/quickstart.md` so they remain executable

**Rationale**: Transient failures are inevitable in distributed systems. Proper hardening
prevents cascading failures and makes debugging easier. Bare exception handlers hide bugs.

### X. Architectural Guardrails

These concrete rules operationalize the abstract principles above. Violations MUST be
caught in code review. If a change would violate any item below, stop and refactor the
design before proceeding. **Guardrail numbers here match CLAUDE.md's guardrail numbers**;
cite them as `X.<n>`.

0. **Single-repo (CWD) workflow model, jj-colocated**: `plan`, `refuel`, `fly`, `land`,
   `reconcile`, and every other long-running command operate directly in the user's
   checkout under `Path.cwd()`, resolved once at the CLI boundary. There is no hidden
   workspace and no clone bridge. Artifacts land in `<cwd>/.maverick/{plans,runs,runway}/`
   and survive across runs with no sync step. All commit-graph mutations go through
   `JjClient` or `library/actions/jj.py`. **One documented exception**: `maverick spec`
   runs the Spec Kit chain in a hidden jj workspace (see Appendix E). (Enforces
   Principles II and VII)

1. **Async-first means no blocking on the event loop**: never call `subprocess.run` from
   an `async def` path. Prefer `CommandRunner` (`src/maverick/runners/command.py`) for
   subprocess execution with timeouts. Python action callables MUST be async or offloaded
   via `asyncio.to_thread`. (Enforces Principle I)

2. **Deterministic ops belong to workflows/runners, not agents**: agents provide judgment.
   They MUST NOT own deterministic side effects such as commits, pushes, bead writes, or
   running validation. Workflows own execution, retries, checkpointing, and recovery.
   (Enforces Principle II)

3. **Actions have a single typed contract**: actions MUST NOT return ad-hoc
   `dict[str, Any]` blobs. Use frozen dataclasses with `to_dict()` or `TypedDict` with
   boundary validation. Keep outputs stable across versions. (Enforces Principle VI)

4. **Resilience features MUST be real, not stubs**: retry and fix loops MUST actually
   invoke fixers and re-run validation. A fix loop MUST NOT be pointed at a condition no
   fix can satisfy—see Guardrail 10. (Enforces Principle IV)

5. **One canonical wrapper per external system**: do not duplicate VCS, GitHub, or
   validation wrappers. Prefer `src/maverick/runners/**` for execution and have callers
   delegate rather than re-implement. (Enforces Principle VII)

6. **Runtime and tool factories are async-safe**: factory functions MUST NOT call
   `asyncio.run()` internally. Prefer lazy prerequisite verification on first use, or an
   explicit async `verify_prerequisites()`. Return concrete types; avoid `Any` on public
   APIs. (Enforces Principles I and VI)

7. **Explicit cwd threading**: every step receives a `cwd` resolved at the CLI boundary.
   Agent steps take it in their context; jj actions take `cwd`; bd, runway, and plan
   parsing take `cwd=cwd`. A grep for `Path.cwd()` inside `src/maverick/workflows/` MUST
   return approximately zero hits in a clean tree; new occurrences are bugs in waiting.
   (Operational form of Guardrail 0; enforces Principle III)

8. **Use canonical third-party libraries**: do NOT introduce alternatives to the
   established libraries. Specifically:
   - **VCS writes**: use `maverick.jj.client.JjClient` or `library/actions/jj.py`,
     NOT `subprocess.run("git commit/push ...")`
   - **VCS reads**: use `maverick.git` (GitPython), NOT `subprocess.run("git ...")`
   - **GitHub API**: use `maverick.utils.github_client`, NOT subprocess calls to `gh`
     (except for auth token retrieval)
   - **Logging**: use `maverick.logging.get_logger()`, NOT stdlib `logging.getLogger()`
   - **Retry logic**: use `tenacity`, NOT manual `for attempt in range()` loops
   - **Secret detection**: use `maverick.utils.secrets.detect_secrets`, NOT custom regex

   (Enforces Principles VII and IX. See Appendix B for the complete list.)

9. **Branch names MUST match the target repository**: when working across maverick core
   and sample-maverick-project, branch names MUST use the prefix appropriate to the
   target repo, and `git remote -v` MUST be verified before pushing. Never push sample
   project branches to maverick core or vice versa. (See Appendix D.)

10. **Deterministic ingestion is preferred over model inference**: when a structured
    artifact already carries the information, derive it deterministically rather than
    asking a model to re-derive it. A model call on a path where parsing would do is a
    design smell, not a feature. Corollaries:
    - Validation MUST NOT fail on conditions no fix can close. A check that a fixer
      cannot satisfy MUST be advisory (reported to the human) rather than routed into a
      fix loop.
    - Advisory findings MUST NOT share a state slot with actionable ones, because the
      slot that feeds the fixer is exactly how an uncloseable condition reaches it.

    (Enforces Principle XIII.)

**Rationale**: Abstract principles are necessary but insufficient. Concrete, reviewable
rules prevent principle drift and make code review objective. Each guardrail traces to
the principle it operationalizes.

### XI. Modularize Early

Long, multi-responsibility modules are a primary driver of slow iteration, merge
conflicts, and accumulated technical debt. Treat file growth as a design smell.

**Line-of-Code Thresholds**:

- **Soft limit**: aim for modules < ~500 LOC and test modules < ~400–600 LOC
- **Refactor trigger**: if a module exceeds ~800 LOC or has many unrelated top-level
  definitions, split it as part of the change (or file a `tech debt` issue scoped to
  the split)
- **Hard stop**: avoid adding new features to modules > ~1000 LOC without first carving
  out a focused submodule/package

**Single Responsibility**: each module/package MUST have one "reason to change"—one
domain, one layer, one cohesive feature area.

**Backwards-Compatible Refactors**: when splitting a public module, preserve import
stability:

- Prefer creating a package and re-exporting the current public surface from `__init__.py`
- If external consumers import from the old module path, keep a small shim module for a
  migration period
- Maintain `__all__` so the public API stays intentional and discoverable

**Rationale**: "God modules" accumulate responsibilities, slow navigation, increase merge
conflicts, and make testing brittle. Proactive modularization prevents the debt spiral.

### XII. Ownership & Follow-Through

The default stance is full ownership of the repository state while working. "That's not
my problem" is not an acceptable response.

- **Do what you're asked, then keep going**: complete the requested change end-to-end,
  then address collateral failures and obvious correctness issues encountered along the way
- **Fix what you find**: broken tests, lint failures, type errors, flaky behavior, or
  obvious bugs get fixed—even if they predate your change
- **Keep the tree green**: do not rationalize failures as "unrelated." If the repo is
  failing, the task is not done
- **No artificial scope minimization**: prefer a complete, robust solution over a
  narrowly-scoped patch unless explicitly instructed otherwise
- **No deferral by difficulty**: "too hard" is a signal to decompose the work, not to stop
- **Only defer when truly blocked**: defer only when work is impossible in the current
  context (missing requirements, missing access, non-reproducible failures). When
  deferring, document exactly what is blocked and the next concrete step
- **Report outcomes faithfully**: state what was verified and what was not. A fix that
  has unit tests but was never exercised end-to-end MUST be described that way

**Rationale**: Autonomous agents and human contributors alike must leave the codebase
better than they found it. Partial fixes that "work for my change" accumulate into
systemic rot. Faithful reporting matters because the next contributor's decisions depend
on knowing which claims were actually observed.

### XIII. Determinism Over Inference

**Spec Kit ingestion is the default entry path for turning intent into beads.** Where a
repository carries Spec Kit artifacts (`specs/NNN-name/{spec.md,tasks.md}`), Maverick MUST
derive its work breakdown from those artifacts deterministically rather than asking a
model to invent one.

- **Default path**: `maverick spec` (headless Spec Kit chain) produces the artifacts;
  `maverick refuel --speckit` ingests them into beads with **zero model calls**—one epic
  plus one task bead per open task, preserving IDs, phases, `[P]` markers, and file scope,
  with dependencies wired as a phase barrier.
- **Fallback path**: the classic flight-plan path (`maverick plan generate` →
  `maverick refuel`) remains **fully supported** for repositories without Spec Kit
  artifacts. Mode is auto-detected from repository shape and may be forced with
  `--speckit`. The classic path is not deprecated; it is no longer the default.
- **New decomposition capability SHOULD target the Spec Kit path first.** Where a
  capability is meaningful on both, the deterministic implementation is the reference
  and the inferred one follows.
- **Model calls on the deterministic path MUST be opt-in and named.** `--enrich` is the
  only step permitted to touch a model during Spec Kit ingestion, and it must remain
  optional.
- **Determinism MUST be verifiable**: `--dry-run` MUST preview the complete plan with
  zero writes, so the ingestion result can be inspected before anything is created.
- **Human judgment is recorded, not inferred.** Assumptions adopted by agents are filed
  in the assumption ledger with question, adopted answer, alternatives, and severity, and
  resolved explicitly by a human via `maverick review`. An unresolved assumption blocks
  `maverick land`; there is no bypass flag.

**Rationale**: A model asked to re-derive a breakdown that already exists in a structured
artifact is a source of nondeterminism, cost, and error with no compensating benefit.
Measured on the classic path, a validation check the fixer could not satisfy consumed the
entire fix budget—59% of a 55-minute run—and drove the fixer to invent redundant work
units (7 became 18 on one run and 33 on another, with confirmed duplicates that would
have been implemented twice). Determinism converts that class of failure into a parse
error you can read. Preferring it does not mean removing judgment: it means spending
judgment where an artifact cannot answer the question.

## Appendix A: Preferred Split Patterns

Use these repository-specific patterns to prevent common "god file" failures:

| Component | Pattern |
|-----------|---------|
| **CLI** | Keep `src/maverick/main.py` as a thin lazy-loading entrypoint; put each Click command in `src/maverick/cli/commands/<command>.py` (or a package for multi-verb commands); keep shared options and error handling in `src/maverick/cli/common.py` |
| **Workflows** | Package-per-workflow (`src/maverick/workflows/<name>/`) split into `actions.py`, `burr_graph.py`, `models.py`, `events.py`/`constants.py`, and `workflow.py` |
| **Agents** | One module per role under `src/maverick/agents/<role>.py`; shared capabilities via mixins/composition, never a god base class |
| **Artifact parsing** | Keep pure parsing/detection/building modules free of CLI and workflow imports (see `src/maverick/speckit/`) so they stay unit-testable |
| **Tests** | Split by unit-under-test and scenario group; move shared fixtures into a directory-scoped `conftest.py` instead of copy/paste |

## Technology Stack

These technology choices are non-negotiable constraints for all Maverick development:

| Category | Technology | Notes |
|----------|------------|-------|
| Language | Python 3.12+ | Use `from __future__ import annotations` |
| Package manager | uv | Reproducible via `uv.lock` |
| Build | Make | AI-friendly minimal-noise targets |
| Agent runtime | airframe (`airframe.AgentRuntime`) | `maverick.runtime.agent_factory` |
| Orchestration | Burr state machines | `maverick.burr` + `workflows/*/burr_graph.py` |
| Structured output | Pydantic result models | `maverick.payloads` |
| CLI | Click + Rich | `maverick.cli.console` |
| Validation | Pydantic | Configuration and data models |
| Testing | pytest + pytest-asyncio + xdist | Parallel via `-n auto` |
| Linting | Ruff | `ruff check` and `ruff format` |
| Type checking | MyPy | Strict mode |
| VCS (writes) | Jujutsu (jj) | `maverick.jj.client.JjClient`; requires colocated mode |
| VCS (reads) | GitPython | `maverick.git` (read-only) |
| VCS (protocol) | `VcsRepository` | `maverick.vcs` abstracts reads |
| GitHub API | PyGithub | `maverick.utils.github_client` |
| Logging | structlog | `maverick.logging.get_logger` |
| Retry | tenacity | `AsyncRetrying` |
| Secrets | detect-secrets | `maverick.utils.secrets` |
| Issue tracking | bd (beads) | Epics and task beads |
| Spec artifacts | Spec Kit | Vendored templates gated to a supported version range |
| Workspaces | spec-chain only | `maverick.workspace.spec_chain` (Guardrail 0's one exception) |

## Code Style & Conventions

### Naming

| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `CodeReviewerAgent`, `RefuelSquadron` |
| Functions/Methods | snake_case | `execute_review`, `create_pr` |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Private | Leading underscore | `_build_prompt`, `_validate_input` |

### Docstrings

All public classes and functions MUST have docstrings using Google-style format:

```python
def execute_task(task_id: str, config: TaskConfig) -> TaskResult:
    """Execute a single task with the given configuration.

    Args:
        task_id: Unique identifier for the task to execute.
        config: Configuration object containing execution parameters.

    Returns:
        TaskResult containing execution status and any outputs.

    Raises:
        TaskNotFoundError: If the task_id does not exist.
        ExecutionError: If the task fails during execution.
    """
```

### Error Handling

- Define custom exceptions under the `src/maverick/exceptions/` package
- Exception hierarchy: `MaverickError` → `AgentError`, `WorkflowError`, `ConfigError`, etc.
- Never catch bare `Exception` except at top-level boundaries
- Log errors with context before re-raising or wrapping
- **Precondition failures carry a stable machine-readable `reason` code**, so rewording a
  human-facing message can never silently reclassify an error for JSON consumers

## Agent Runtime (airframe) Patterns

Every LLM call goes through **airframe**, a provider-abstraction layer.
`maverick.runtime.agent_factory.runtime_for_agent(role, ...)` maps a role name to a
constructed `AgentRuntime` plus its resolved `(provider, model_id)` binding. There is no
long-lived HTTP server and no per-workflow subprocess.

- Roles are fixed (`agent_factory.KNOWN_ROLES`): `implement`, `review`, `briefing`,
  `decompose`, `generate`. Each maps to an `agents.<role>` block in `maverick.yaml`.
- **A role with no binding MUST raise at squadron-open** rather than silently selecting a
  model the user never authorized. `runtime_for_agent` validates the binding against the
  adapter before returning.
- Agents declare `result_model` / `provider_tier` / `persona_name` and call
  `_execute_via_runtime()` (structured) or `_execute_text_via_runtime()` (plain text).
  Extract and structure agent outputs; do not return raw text to callers.
- Use `rotate_session()` for a fresh context between work items.
- **Per-complexity tiers** (`actors.<workflow>.<actor>.tiers.<complexity>`) route work to
  a different provider/model by assigned complexity. Malformed tier blocks MUST degrade
  to `None` with a warning—one typo must not take down workflow startup.
- **Escalation ladders come from the squadron, never hardcoded.** A rung may only name a
  tier the squadron built a *distinct* binding for. Escalating to an identical binding is
  a retry in disguise and hides the fact that the binding never varied.

### Burr orchestration

- **The driver defers exceptions.** An action that raises does *not* interrupt
  `driver.events()`; the exception is stored and re-raised when `driver.result` is
  touched. Tests asserting on a raising action MUST drain events first, then access
  `.result`.
- Actions declare `reads`/`writes` explicitly. Adding a state slot means adding it to the
  producing action's `writes`, every consumer's `reads`, *and* the graph's
  `.with_state(...)` seed.
- Disk and network reads belong in one place—see `refuel_maverick`'s `init_state`, the
  only action that reads the refuel cache.

## File Organization

```
src/maverick/
├── main.py              # Click entrypoint (lazy subcommand loading)
├── config.py            # Pydantic config models (agents:, actors:, tiers)
├── exceptions/          # MaverickError hierarchy
├── types.py / events.py / results.py / constants.py / payloads.py
├── runtime/             # agent_factory (role → airframe runtime), registry
├── burr/                # BurrWorkflowDriver + ProgressEventHook
├── squadron/            # per-workflow agent sets + shared tier helpers
├── agents/              # Agent subclasses: prompts + role (HOW)
├── executor/            # StepConfig resolution
├── jj/ vcs/ git/        # JjClient, VcsRepository protocol, GitPython reads
├── speckit/             # Spec Kit parsing / detection / plan building
├── workspace/           # spec-chain workspace (Guardrail 0's one exception)
├── workflows/           # spec_chain / refuel_speckit / refuel_maverick /
│                        #   generate_flight_plan / fly_beads / reconcile
│                        #   each: actions.py + burr_graph.py
├── assumptions/         # assumption ledger, land report, serialization
├── beads/ runway/       # bd integration; episodic + semantic knowledge store
├── cli/                 # console, commands/, json_output envelope
├── skills/              # packaged Claude Code skills (maverick-review)
├── runners/             # CommandRunner, process_group, provider_health
├── library/actions/     # typed action layer (jj, git, beads, runway, ...)
└── hooks/ utils/        # safety hooks; shared helpers
```

## Governance

This constitution supersedes all other practices and conventions. All code contributions
MUST comply with these principles.

### Amendment Process

1. Amendments require documentation of the change rationale
2. Breaking changes to principles require migration plans for existing code
3. Version increments follow semantic versioning:
   - MAJOR: backward-incompatible principle changes, removals, or redefinitions
   - MINOR: new principles or material expansions
   - PATCH: clarifications, wording improvements

### Compliance Review

- All PRs MUST be reviewed for constitution compliance
- Complexity deviations MUST be justified in PR descriptions
- Use `.specify/memory/constitution.md` as the authoritative reference
- Architectural guardrails (Principle X) MUST be checked in code review
- Canonical library usage (Guardrail X.8, Appendix B) MUST be verified in code review
- Module size thresholds (Principle XI) MUST be checked before merging large files
- Ownership expectations (Principle XII) apply to all contributors including AI agents
- Branch naming conventions (Guardrail X.9, Appendix D) MUST be verified before pushing
- Explicit cwd threading (Guardrail X.7, Appendix E) MUST be verified for all new
  workflow steps
- **New decomposition capability MUST state which entry path it targets** (Principle XIII,
  Appendix F). Adding a model call to the deterministic path requires explicit
  justification in the PR description.

**Version**: 2.0.1 | **Ratified**: 2025-12-12 | **Last Amended**: 2026-08-11

## Appendix B: Canonical Third-Party Libraries

These libraries are the canonical choices for their domains. Do NOT introduce alternatives
or custom implementations. Violations found in code review MUST be refactored.

| Domain | Library | Maverick Wrapper | Do NOT Use |
|--------|---------|------------------|------------|
| Agent runtime | airframe | `maverick.runtime.agent_factory` | Direct provider SDK calls |
| Orchestration | Burr | `maverick.burr.BurrWorkflowDriver` | Hand-rolled state machines |
| VCS Writes | Jujutsu (jj) | `maverick.jj.client.JjClient`, `maverick.library.actions.jj` | `subprocess.run("git commit/push ...")` |
| VCS Reads | GitPython | `maverick.git.GitRepository`, `AsyncGitRepository` | `subprocess.run("git ...")` for reads |
| VCS Abstraction | `VcsRepository` | `maverick.vcs.factory.create_vcs_repository()` | Direct git/jj calls for portable reads |
| GitHub API | PyGithub | `maverick.utils.github_client.GitHubClient` | `subprocess.run("gh ...")` except auth |
| Logging | structlog | `maverick.logging.get_logger()` | stdlib `logging.getLogger()` |
| Retry Logic | tenacity | `@retry`, `AsyncRetrying` | Manual `for attempt in range()` |
| Secret Detection | detect-secrets | `maverick.utils.secrets.detect_secrets` | Custom regex patterns |
| Terminal output | Rich | `maverick.cli.console` | `print()`, `click.echo()` |

**Usage Examples**:

```python
# Agent runtime + squadron lifecycle - CORRECT
async with FlySquadron(cwd=cwd, config=config, cost_sink=sink) as squadron:
    app = build_fly_application(squadron=squadron, event_queue=queue, ...)
    driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
    async for evt in driver.events():
        ...
    _, _, state = driver.result

# VCS write operations (jj) - CORRECT
from maverick.library.actions.jj import jj_commit_bead
result = await jj_commit_bead(bead_id, title, cwd=cwd)

# VCS read operations (GitPython) - CORRECT
from maverick.git import GitRepository
branch = GitRepository(path).current_branch()

# Logging - CORRECT
from maverick.logging import get_logger
logger = get_logger(__name__)
logger.info("operation_started", item_id=item_id)

# Retry logic - CORRECT
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential
async for attempt in AsyncRetrying(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
):
    with attempt:
        result = await risky_operation()
```

**Rationale**: Canonical libraries ensure consistent behavior, centralized configuration,
proper error handling, and easier testing. Multiple implementations of the same capability
lead to subtle bugs and maintenance burden.

## Appendix C: CLI Output Conventions

Maverick is a terminal application. All user-facing output MUST go through the Rich
`console` / `err_console` in `maverick.cli.console`. `print()` and `click.echo()` are
prohibited (Principle VII).

### Rules

| Rule | Detail |
|------|--------|
| **Human-readable phase names** | "Gathering context...", never `gathering_context` |
| **No implementation labels** | Do not surface `(python)` / `(agentic)` to users |
| **No emoji** | Use Rich markup: `[green]✓[/]`, `[red]✗[/]` |
| **Structured warnings** | Never let raw structlog output leak to the user. Format as `[yellow]Warning:[/yellow] ...` |
| **Fan-out progress** | Rich `Live` table for parallel agents, updating in place. Show all agents immediately: pending = `(waiting)`, active = spinner, done = timing + ✓ |
| **Sequential operations** | One completion line with timing (`✓ Outline (312.0s)`), not separate start/end lines |
| **Diagnostics go to stderr** | structlog is configured to stderr; user-facing results go to stdout so output remains pipeable |

### Log level discipline

A log line that duplicates information already carried on a raised exception or already
rendered by the console MUST be `debug`, not `warning`. Warning-level structlog output
appears interleaved with Rich output and reads as a defect to users—one validation pass
once emitted sixteen raw structlog rows that duplicated the exception's own message.

### Machine-readable output

Every JSON verb shares one envelope shape and error-kind registry
(`src/maverick/cli/json_output.py`). Documents carry a top-level `degraded` flag when a
gate could not be fully evaluated, so consumers can distinguish "clear" from "unknown".
Human-mode output MUST remain available and unchanged as the bare-terminal fallback.

**Rationale**: A single output path keeps formatting consistent, keeps diagnostics out of
piped results, and makes the CLI scriptable without a second implementation.

## Appendix D: Repository and Branch Naming Conventions

Maverick development involves two distinct repositories with different purposes. Confusing
them causes branch pollution, incorrect commits, and wasted cleanup effort.

### Repository Overview

| Repository | Purpose | Location | Branch Prefix Examples |
|------------|---------|----------|------------------------|
| **maverick** | Core Maverick CLI application | `/workspaces/maverick` | `050-headless-spec-chain`, `053-assumption-review-console` |
| **sample-maverick-project** | Test project for E2E testing and demos | `/workspaces/sample-maverick-project` | `001-greet-cli`, `002-todo-app` |

### Branch Naming Rules

**Maverick Core Repository** (`get2knowio/maverick`):

- Branch format: `###-descriptive-name` where `###` is a maverick feature spec number
- Spec location: `/workspaces/maverick/specs/###-feature-name/`
- NEVER use low numbers (001-019) for maverick branches—these are reserved for sample projects

**Sample Project Repository** (`get2knowio/sample-maverick-project`):

- Branch format: `###-descriptive-name` where `###` starts from `001`
- Spec location: `/workspaces/sample-maverick-project/specs/###-feature-name/`
- Used for testing maverick workflows against a real project

### Pre-Push Verification Checklist

Before pushing any branch, verify:

```bash
# 1. Check which repository you're in
pwd
git remote -v

# 2. Verify branch name matches repository
git branch --show-current

# 3. Check that your commits belong to this repo
git log --oneline -5
```

### Common Mistakes to Avoid

| Mistake | How It Happens | Prevention |
|---------|----------------|------------|
| Sample branch in maverick | Working in wrong terminal/directory | Always check `git remote -v` before push |
| Maverick branch in sample | Copy/paste branch name from wrong context | Verify spec directory exists in current repo |
| Commits to wrong repo | Multiple terminals with similar prompts | Use distinct terminal titles or prompts per repo |

### Recovery Procedure

If you accidentally push a branch to the wrong repository:

1. **Do NOT force-push or rewrite history** on shared branches
2. Delete the incorrect remote branch: `git push origin --delete <branch-name>`
3. If commits need preservation, cherry-pick to the correct repo
4. Document the incident to prevent recurrence

**Rationale**: The 001-greet-cli incident (2026-01-21) demonstrated how easily branch
confusion can occur when working across multiple repositories.

## Appendix E: Workspace Isolation Architecture

**Default: single-repo CWD model (Guardrail X.0).** `fly`, `refuel`, `land`, `reconcile`,
and every other long-running command operate directly in the user's checkout under
`Path.cwd()` (resolved once at the CLI boundary and threaded explicitly through every
layer beneath it—see Guardrails X.0 and X.7). There is no hidden workspace, no clone
bridge, and no `WorkspaceManager` for these commands. Two implementations of a
general-purpose hidden-workspace model were tried and retired before this model was
adopted (`jj git clone`—drifted on bd state, gone in `cf11db4`; `jj workspace add`—bd's
gitignored `embeddeddolt/` didn't travel into the workspace). See CLAUDE.md Guardrail 0
for the full history.

### The scoped exception: spec-chain's hidden jj workspace

`maverick spec` (spec 050-headless-spec-chain) is a **documented exception** to the
single-repo model. Each chain step (specify → clarify → plan → tasks → analyze) mutates
`specs/`, `.specify/feature.json`, and agent scratch state over a multi-minute model call;
the user's checkout must stay untouched until each step's artifacts are verified complete,
and only completed-step artifacts may land. Running steps directly in the user's checkout
would expose half-written spec artifacts mid-run and make atomic landing impossible
without ad-hoc staging.

The historic reason general-purpose workspaces were retired—bd's gitignored
`embeddeddolt/` not traveling into `jj workspace add`—does **not** apply here: the spec
chain never runs `bd` inside the workspace. All bead and ledger writes (assumption-ledger
entries from clarify, remediation beads from analyze) happen in the user's checkout via
the workflow (`src/maverick/workflows/spec_chain/workflow.py`), never the agent and never
the workspace. This keeps Guardrail X.2 (agents never own deterministic side effects) and
Guardrail X.8 (canonical wrappers) intact even inside the exception.

**Mechanism** (`src/maverick/workspace/spec_chain.py`, `research.md` R3):

- Location: `~/.maverick/workspaces/<project-slug>/spec-chain/<feature>/`—per-feature, so
  two features' chains never share (and one can never destroy the other's resumable state).
- Creation: `JjClient.workspace_add`, from the user's colocated checkout—the shared
  backing store materializes committed files (`.claude/skills/speckit-*/SKILL.md`,
  `.specify/**`, existing `specs/**`) into the workspace. The PRD file (often untracked)
  is copied in explicitly.
- Reuse and cleanup: a resumable chain (`status` `halted`/`running`) reuses its workspace
  on resume; a fresh or completed chain forgets and recreates it, so runs start clean.
- Landing: after each step succeeds (verified against the filesystem, never the agent's
  self-report—research.md R9), `src/maverick/workflows/spec_chain/landing.py` syncs
  `specs/<feature-dir>/**` from the workspace into the user's checkout via an atomic
  staged copy (temp sibling + rename). This is what makes "only completed artifacts land"
  and "resume never regenerates a landed step" both hold.

### CWD contract inside the exception

Within the spec-chain workflow itself, the ordinary Guardrail X.7 rules still apply one
level down: `SpecChainWorkflow._run()` resolves the workspace path once (via
`prepare_workspace`) and threads it explicitly to every step (`build_step_prompt`,
`verify_step_artifacts`, `land_step_artifacts`) and to `SpecChainSquadron`—no step
re-derives or defaults it. The one deliberate deviation is `SpecChainAgent.run_step`,
which binds the OS process working directory via a locked `os.chdir()`/restore pair for
the duration of a single airframe `execute()` call—a workaround for airframe 0.9.0rc1
exposing no `cwd`/`working_directory` parameter on the `claude` provider's runtime
(research.md R1; the field exists on `CopilotOptions`/`KimiOptions`/
`OpenCodeServerOptions` but not `ClaudeOptions`, an adapter gap worth upstreaming later).
Because chain steps run strictly sequentially and one Maverick CLI invocation runs one
workflow per process, the exposure window is a single in-process critical section, not
cross-workflow concurrency.

**Rationale**: The workspace isolation debugging session (2026-02-20) that originally
motivated this appendix revealed that an implementer agent can silently write to the wrong
directory when no step passes `cwd` explicitly—the bug is invisible until downstream steps
find nothing to work with. That lesson generalizes to both models above: whether the
working directory is the user's checkout (the default) or a hidden workspace (this scoped
exception), every step must receive it explicitly, and nothing in `workflows/` may default
to `Path.cwd()`.

## Appendix F: Decomposition Entry Paths

Maverick has two paths from intent to beads. **The Spec Kit path is the default**
(Principle XIII); the classic flight-plan path is a supported fallback for repositories
that carry no Spec Kit artifacts.

### Path comparison

| | **Spec Kit path (default)** | **Classic path (fallback)** |
|---|---|---|
| Entry | `maverick spec <feature> --from-prd <file>` | `maverick plan generate <name> --from-prd <file>` |
| Ingestion | `maverick refuel <feature> --speckit` | `maverick refuel <plan-name>` |
| Source of truth | `specs/NNN-name/{spec.md,tasks.md}` | `.maverick/plans/<name>/flight-plan.md` |
| Model calls at ingestion | **Zero** (only opt-in `--enrich`) | Briefings, outline, detail fan-out, fix loop |
| Determinism | Same artifacts → same beads | Model-dependent |
| Preview | `--dry-run`, zero writes | Cache-backed resume |
| Delta re-runs | Appends only new tasks under the existing epic | Re-decomposes |

### Selection

Mode is **auto-detected from repository shape** (`src/maverick/speckit/detect.py`) and may
be forced with `--speckit`. `NAME` resolves via exact directory name, `NNN` prefix, or
exact name suffix; an ambiguous resolution MUST fail rather than guess.

The vendored Spec Kit template version is **gated to a supported range**
(`SUPPORTED_SPECKIT_RANGE`). An unsupported or unknown template version MUST be surfaced
rather than parsed optimistically—the parser's guarantees only hold for shapes that have
been verified.

### Obligations on each path

**Spec Kit path**: preserve task IDs, phases, `[P]` parallel markers, and file scope
exactly as authored. Wire dependencies as a phase barrier. Never introduce a model call
outside `--enrich`. Analyze findings become standalone `spec-remediation` beads that
`refuel --speckit` later adopts under the epic it creates.

**Classic path**: remains fully supported and MUST be kept green. Bugs are fixed, not
deferred (Principle XII). Its validation MUST obey Guardrail X.10—a criterion that no work
unit can satisfy (a cross-cutting constraint such as a LOC budget or "lint passes") is
advisory, never routed into the fix loop.

**Both paths** converge on the same downstream contract: an epic plus task beads, then
`maverick fly` to implement, the assumption ledger for recorded judgment, `maverick review`
and `maverick reconcile` to resolve it, and `maverick land` gated on an empty assumption
frontier.

**Rationale**: Naming a default is what makes the codebase's center of gravity legible to
contributors. Keeping the fallback first-class is what keeps Maverick usable on
repositories that have not adopted Spec Kit—which includes most repositories it will meet.
