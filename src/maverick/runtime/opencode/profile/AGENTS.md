# Maverick Cross-Cutting Conventions

These rules apply to every persona maverick spawns. Persona-specific
prompts (`agents/maverick.<role>.md`) layer on top.

## Version Control

- Use `jj` (Jujutsu) for all write-path VCS — `commit`, `push`,
  `merge`, `branch`. NEVER shell out to `git` for writes.
- Read-only git inspection (status, log, diff, blame) is fine.

## Output

- No emoji in CLI output. Use Rich markup like `[green]check[/]` /
  `[red]x[/]` instead.
- Format warnings as structured `[yellow]Warning:[/yellow] ...` —
  never let raw structlog rows leak to the user.
- Human-readable phase names ("Gathering context...") not
  `snake_case`.
- No implementation labels in user output (don't show
  `(python)` / `(agentic)`).

## Async-First

- Never call `subprocess.run` from an `async def` path — it blocks
  the event loop. Use the project's `CommandRunner` for subprocess
  execution with timeouts.
- Network/IO calls always carry an explicit timeout and a
  tenacity-style retry with exponential backoff.

## Complete Work

- Each task is self-contained. No `TODO` / `FIXME` / `HACK` punts.
- If a change requires a follow-up (update callers, remove a shim,
  migrate tests), do it in this session — there is no "later".

## Scope Discipline

- Make only the changes directly required by the task. Do not add
  features, refactor surrounding code, or pre-emptively generalize.
- Read existing code before modifying it. Match the surrounding
  style.
