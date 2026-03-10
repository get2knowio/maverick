# CLI Output Rules

Rules governing how Maverick renders workflow progress to the terminal.
These apply to all workflows (generate, refuel, fly, land).

## Rules

### R1 — Step lifecycle

Every step has exactly one start line and one completion line.
The completion line always includes the step name and wall-clock timing.

```
⚙ step_name (python)
✓ step_name (1.23s)
```

### R2 — Completion line is step name + timing only

The completion line never contains messages — only the step name and
wall-clock duration. All meaningful output is shown via interim lines (R3).

### R3 — Interim prefix

All interim lines use `  ∟` (two-space indent + right-angle bracket).
Never repeat the step name — the parent `⚙` line provides context.

```
⚙ briefing (agentic)
  ∟ 🤖 Scopist... (claude/claude-opus-4-6)
  ∟ ✓ Scopist (71.8s)
```

### R4 — Agent lifecycle interims

Every agent invocation within a step produces two interim lines:

- **Start**: `  ∟ 🤖 AgentName... (provider/model)`
- **End**:   `  ∟ ✓ AgentName (Xs)`

### R5 — No interims for trivial steps

Steps completing in < 1s with no sub-operations need no interim lines —
just the `⚙` start and `✓` completion.

```
⚙ write_flight_plan (python)
✓ write_flight_plan (0.01s)
```

### R6 — Icons are semantic

| Icon | Meaning |
|------|---------|
| `⚙`  | Step started (deterministic/python work) |
| `🤖` | Agent invocation (AI doing work) |
| `✓`  | Completed successfully |
| `✗`  | Failed |

### R7 — Start line type annotation

The `⚙` line shows `(python)` for deterministic steps or `(agentic)`
for steps involving AI agents. No provider/model details on the start
line.

```
⚙ read_prd (python)
⚙ briefing (agentic)
⚙ generate (agentic)
```

### R8 — Agent interim shows actual provider/model

Each agent lifecycle interim line includes the real provider name and
resolved model ID in parentheses. The provider name is the ACP endpoint
key from the maverick config (e.g., `claude`, `copilot`) or, for custom
user-provided ACP agents, the executable name. This is the **only** place
provider/model details appear.

```
  ∟ 🤖 Scopist... (copilot/claude-sonnet-4-20250514)
  ∟ 🤖 Contrarian... (claude/claude-opus-4-6)
```

## Full Example

```
⚙ read_prd (python)
  ∟ PRD: "Greet CLI — Product Requirements Document" (3,195 chars, 83 lines)
✓ read_prd (0.00s)
⚙ briefing (agentic)
  ∟ 🤖 Scopist... (copilot/claude-sonnet-4-20250514)
  ∟ 🤖 CodebaseAnalyst... (copilot/claude-sonnet-4-20250514)
  ∟ 🤖 CriteriaWriter... (copilot/claude-sonnet-4-20250514)
  ∟ ✓ CriteriaWriter (53.2s)
  ∟ ✓ CodebaseAnalyst (71.3s)
  ∟ ✓ Scopist (71.8s)
  ∟ 🤖 Contrarian... (copilot/claude-sonnet-4-20250514)
  ∟ ✓ Contrarian (48.4s)
  ∟ Briefing complete: 9 scope items, 11 criteria, 8 open questions
✓ briefing (120.16s)
⚙ generate (agentic)
  ∟ 🤖 FlightPlanGenerator... (copilot/claude-sonnet-4-20250514)
  ∟ ✓ FlightPlanGenerator (68.90s)
  ∟ Generated 12 success criteria
✓ generate (68.90s)
⚙ write_flight_plan (python)
  ∟ Wrote flight plan to .maverick/plans/greet-cli/flight-plan.md
✓ write_flight_plan (0.01s)
⚙ validate (python)
  ∟ Flight plan passes all V1-V9 validation checks
✓ validate (0.00s)

Workflow completed successfully in 189.08s
  Flight plan created at .maverick/plans/greet-cli/flight-plan.md
```
