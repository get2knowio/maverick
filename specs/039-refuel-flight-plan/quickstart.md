# Quickstart: Refuel Flight-Plan Subcommand

**Feature Branch**: `039-refuel-flight-plan`
**Date**: 2026-02-28

## Overview

The `maverick refuel flight-plan` command decomposes a Maverick Flight Plan Markdown file into work units and beads for execution by `maverick fly`.

## Prerequisites

- `bd` CLI tool installed (for bead creation)
- `git` and `gh` CLI tools available
- A valid Maverick Flight Plan Markdown file (spec 037 format)

## Usage

### Basic Usage

```bash
# Decompose a flight plan into work units and beads
maverick refuel flight-plan .maverick/flight-plans/add-auth.md
```

This will:
1. Parse the flight plan file
2. Gather codebase context from in-scope files
3. Use an AI agent to decompose into work units
4. Validate the dependency graph
5. Write work unit files to `.maverick/work-units/{plan-name}/`
6. Create one epic bead and one task bead per work unit
7. Wire dependencies between beads

### Preview Mode (Dry Run)

```bash
# Preview decomposition without creating beads
maverick refuel flight-plan .maverick/flight-plans/add-auth.md --dry-run
```

Writes work unit files but skips bead creation (steps 6-7). Use this to review the AI-generated decomposition before committing to bead creation.

### List Workflow Steps

```bash
# Show the workflow steps without executing
maverick refuel flight-plan .maverick/flight-plans/add-auth.md --list-steps
```

### Session Logging

```bash
# Capture workflow events for debugging
maverick refuel flight-plan .maverick/flight-plans/add-auth.md --session-log ./session.jsonl
```

## Output

### Work Unit Files

Written to `.maverick/work-units/{plan-name}/`:

```
.maverick/work-units/add-auth/
├── 001-setup-models.md
├── 002-add-registration.md
├── 003-add-login.md
└── 004-add-middleware.md
```

### Beads

- One **epic bead** representing the overall flight plan
- One **task bead** per work unit with dependencies matching the `depends_on` graph
- Execute with `maverick fly` after bead creation

## Relationship to Other Commands

| Command | Purpose |
|---------|---------|
| `maverick refuel flight-plan` | Decompose a flight plan into beads (this command) |
| `maverick refuel maverick` | Same functionality, alternative entry point |
| `maverick refuel speckit` | Decompose a SpecKit specification into beads |
| `maverick fly` | Execute beads created by refuel commands |
