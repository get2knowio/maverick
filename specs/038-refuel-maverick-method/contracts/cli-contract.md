# CLI Contract: maverick refuel maverick

**Branch**: `038-refuel-maverick-method` | **Date**: 2026-02-27

## Command Signature

```
maverick refuel maverick <flight-plan-path> [OPTIONS]
```

## Arguments

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `flight-plan-path` | PATH | Yes | Path to the flight plan Markdown file |

## Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dry-run` | bool | False | Write work unit files but skip bead creation and commits |
| `--list-steps` | bool | False | Display workflow steps and exit |
| `--session-log` | PATH | None | Path to write session log |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — all work units written and beads created |
| 1 | Failure — flight plan parse error, agent failure, or critical validation error |
| 2 | Partial — some beads created but errors occurred |

## Example Usage

```bash
# Basic decomposition
maverick refuel maverick .maverick/flight-plans/add-auth.md

# Preview without creating beads
maverick refuel maverick .maverick/flight-plans/add-auth.md --dry-run

# Show workflow steps
maverick refuel maverick .maverick/flight-plans/add-auth.md --list-steps

# With session logging
maverick refuel maverick .maverick/flight-plans/add-auth.md --session-log /tmp/session.log
```

## Output Format

```
╭─ refuel-maverick ─╮
│ Flight plan: add-auth
│ Dry run: No
╰───────────────────╯

[STEP] parse_flight_plan
[OK]   Parsed flight plan "add-auth" (5 success criteria, 12 in-scope files)

[STEP] gather_context
[info] Reading 12 in-scope files...
[warn] File not found: src/old_module.py
[OK]   Gathered context (11 files, 45KB)

[STEP] decompose
[thinking] Analyzing flight plan structure...
[output]   Producing work units...
[OK]   Decomposed into 7 work units

[STEP] validate
[warn] SC-003 not explicitly covered by any work unit
[OK]   Dependency graph is acyclic (3 parallel groups)

[STEP] write_work_units
[info] Wrote 7 work unit files to .maverick/work-units/add-auth/
[OK]   7 files written

[STEP] create_beads
[info] Created epic: add-auth (bd_id: abc123)
[info] Created 7 task beads
[OK]   8 beads created

[STEP] wire_deps
[info] Wired 5 dependencies
[OK]   Dependencies wired

╭─ Summary ─╮
│ 7 work units written to .maverick/work-units/add-auth/
│ 8 beads created (1 epic + 7 tasks)
│ 5 dependencies wired
│ 1 coverage warning
╰───────────╯
```
