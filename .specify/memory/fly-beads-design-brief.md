# Design Brief: Bead-Driven Fly Workflow

## Goal

Design and implement a `maverick fly beads` workflow that replaces the current branch-centric `fly feature` with a bead-driven execution loop. Instead of specifying a branch and executing all phases from a `tasks.md`, the workflow takes an epic ID and iterates: pick the next ready bead, implement it, validate, review, and close it — repeating until the epic is complete.

## Core Insight: Unify Implementation, Validation-Fixing, and Review-Fixing

The key architectural insight is that **everything is a bead**. Review findings and validation failures don't trigger inline fix loops — they create new beads under the same epic. This means:

- **One agent type** (implementer) handles all work — original spec tasks, validation fixes, and review findings
- **No fixer agent** — fixing IS implementing a bead whose description says "fix X"
- **No fix loops** — the outer "keep iterating on beads" loop IS the fix loop
- **Full traceability** — every piece of work is a tracked bead with history
- **Natural resumability** — `bd` knows exactly which beads are done; no checkpoint files needed

The loop terminates when a validation + review cycle produces **zero new beads** (clean pass), with safety valves for max total beads or convergence detection.

## What `bd` Already Provides

We discovered that `bd` (the beads CLI) already has infrastructure for nearly everything needed. The current `BeadClient` only wraps 3 commands (`create`, `dep add`, `sync`) out of 60+. Key capabilities:

### Work Queue / Selection
```bash
bd ready --parent <epic> --limit N --json   # Next N ready beads (open, unblocked)
bd ready --parent <epic> --sort priority     # Priority-ordered
bd children <epic> --json                    # All children of epic
bd close <id> --suggest-next                 # Close bead, show what unblocked
bd close <id> --continue                     # Close and auto-advance
```

### Agent Lifecycle (maverick registers as a bd agent)
```bash
bd agent state <agent-id> working|idle|done  # Report agent state
bd agent heartbeat <agent-id>                # Liveness signal
bd slot set <agent-id> hook <bead-id>        # "I'm working on THIS bead"
bd slot clear <agent-id> hook                # "Done with that bead"
```

### Creating Fix/Review Beads Mid-Flight
```bash
bd create --parent <epic> --type task --title "Fix: ..." --priority 1 --json
bd dep add <new-bead> --blocked-by <blocker>  # Or no dep = immediately ready
```

### Swarm (this IS the bead-driven fly concept)
```bash
bd swarm create <epic>          # "Orchestrate work on this epic's DAG"
bd swarm status                 # Progress overview
bd epic status                  # Completion check
bd epic close-eligible          # Auto-close when all children done
```

### Rich Querying
```bash
bd query "parent=<epic> AND status=open" --json
bd query "parent=<epic> AND label=review-finding" --json
bd blocked                      # What's stuck?
```

### State Tracking
```bash
bd set-state <id> phase=validating --reason "Running lint/test"
bd set-state <id> phase=reviewing --reason "Code review pass"
```

## Proposed Workflow Shape

```yaml
name: fly-beads
inputs:
  epic_id: { type: string, required: true }
  max_beads: { type: integer, default: 30 }

steps:
  # Loop: pick next ready bead, implement, validate, review, close
  - name: work_loop
    loop:
      until: no more ready beads under epic
      max_iterations: ${{ inputs.max_beads }}
    steps:
      - select_next_bead    # bd ready --parent <epic> --limit 1 --json
      - implement_bead      # agent step: implementer reads bead description
      - validate            # subworkflow: format/lint/typecheck/test
      - create_fix_beads    # if failures → bd create under epic (high priority)
      - review              # agent step: reviewer examines changes
      - create_review_beads # if findings → bd create under epic
      - commit              # git commit with bead reference
      - close_bead          # bd close <bead> --suggest-next

  - name: create_pr         # subworkflow: create-pr-with-summary
```

## Priority-Based Ordering for Generated Beads

When validation/review creates new beads, their priority determines pickup order:

| Source | Priority | Rationale |
|--------|----------|-----------|
| Test failure | 1 (highest) | Blocks confidence in further work |
| Lint/type error | 5 | Fix before next story bead |
| Critical review finding | 3 | Significant code issue |
| Minor review finding | 20 | Accumulate, do during cleanup |

The implementer doesn't know or care whether it's building a feature or fixing a lint error — the bead description tells it what to do.

## Bead Categories (Expanded)

Existing: `FOUNDATION`, `USER_STORY`, `CLEANUP`
New: `VALIDATION` (lint/type/test failure), `REVIEW` (code review finding)

These are metadata for humans and priority ordering, not routing to different agents.

## Bead Lifecycle in This Workflow

1. Bead is created (by `refuel speckit` or by validation/review during execution)
2. Bead becomes "ready" when all blockers are resolved
3. `bd ready` surfaces it to the workflow
4. Maverick agent claims it (`bd slot set <agent> hook <bead>`)
5. Implementer executes the work described in the bead
6. Bead is closed (`bd close <bead>`)
7. If bead work introduced failures → new beads created, they enter the queue

A completed bead is "done" even if it introduced failures — those are tracked as new beads with full traceability.

## What Needs to Be Built

### 1. Expand BeadClient
Current: wraps `create`, `dep add`, `sync`
Needed: `ready()`, `close()`, `show()`, `children()`, `query()`, `set_state()`, agent/slot operations

### 2. New Workflow Actions
- `select_next_bead` — calls `bd ready --parent <epic> --limit 1 --json`
- `create_beads_from_failures` — converts validation failures to beads
- `create_beads_from_findings` — converts review findings to beads
- `mark_bead_complete` — calls `bd close` with reason
- `check_epic_done` — calls `bd ready` and returns true if empty

### 3. New Workflow YAML
- `fly-beads.yaml` — the main bead-driven workflow
- Reuses existing subworkflows: `validate-and-fix` (minus the fix loop), `commit-and-push`, `create-pr-with-summary`
- Review becomes a simpler "find issues → create beads" step instead of the current `review-and-fix-with-registry.yaml`

### 4. CLI Command
- `maverick fly beads --epic <id>` or `maverick fly beads <epic-id>`
- Options: `--max-beads`, `--dry-run`, `--continue` (resume)

## Key Design Decisions to Make During Planning

1. **Branching strategy**: One branch for the whole epic? Per-bead branches? Stacking?
2. **Review scope**: Review after each bead, or batch review after N beads?
3. **Termination**: Clean-pass only? Max iterations? Convergence detection?
4. **Swarm integration**: Should we use `bd swarm create` to formally register the orchestration, or keep it simpler?
5. **Agent registration**: Should maverick register as a `bd agent` with heartbeats, or is that overkill for a single-agent sequential workflow?
6. **Validation simplification**: Can `validate-and-fix` be simplified to just `validate` (no fix loop) since fixes become beads?

## Relevant Codebase Locations

- `src/maverick/beads/` — models, client, speckit (current bead system)
- `src/maverick/library/workflows/feature.yaml` — current fly feature workflow
- `src/maverick/library/workflows/refuel-speckit.yaml` — bead generation workflow
- `src/maverick/library/actions/beads.py` — current bead actions
- `src/maverick/library/actions/workspace.py` — workspace init
- `src/maverick/library/fragments/review-and-fix-with-registry.yaml` — current review system
- `src/maverick/cli/commands/fly.py` — fly CLI entry point
- `src/maverick/cli/commands/refuel/speckit.py` — refuel speckit CLI
- `src/maverick/exceptions/beads.py` — bead exception hierarchy
- `src/maverick/runners/command.py` — CommandRunner for subprocess execution
