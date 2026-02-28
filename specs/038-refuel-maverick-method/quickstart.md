# Quickstart: Refuel Maverick Method

**Branch**: `038-refuel-maverick-method` | **Date**: 2026-02-27

## Prerequisites

- Maverick CLI installed (`maverick --version`)
- `bd` CLI available on PATH for bead management
- A valid Maverick flight plan file (see [Flight Plan Format](#flight-plan-format))

## Basic Usage

### 1. Create a Flight Plan

Write a flight plan file describing your feature (see `maverick.flight.models.FlightPlan` for the schema):

```markdown
---
name: add-user-auth
version: "1.0"
created: 2026-02-27
tags: [auth, security]
---

## Objective
Add user authentication to the application.

## Success Criteria
- [ ] Users can register with email and password (SC-001)
- [ ] Users can log in and receive a session token (SC-002)
- [ ] Protected routes reject unauthenticated requests (SC-003)

## Scope

### In
- src/auth/
- src/middleware/
- tests/auth/

### Out
- src/admin/
- deployment/

### Boundaries
- src/config.py (protect - read only)
```

### 2. Run Decomposition

```bash
maverick refuel maverick path/to/flight-plan.md
```

### 3. Preview with Dry Run

```bash
maverick refuel maverick path/to/flight-plan.md --dry-run
```

This writes work unit files for inspection but does not create beads.

### 4. Inspect Generated Work Units

```bash
ls .maverick/work-units/add-user-auth/
# 001-add-user-model.md
# 002-add-registration-endpoint.md
# 003-add-login-endpoint.md
# 004-add-auth-middleware.md
# 005-add-protected-route-tests.md
```

### 5. Execute Work Units

```bash
maverick fly
```

Maverick picks up the created beads and executes them in dependency order.

## Flight Plan Format

Flight plans use Markdown with YAML frontmatter. Required sections:

| Section | Description |
|---------|-------------|
| Frontmatter | `name`, `version`, `created` (YAML) |
| Objective | Single paragraph describing the goal |
| Success Criteria | Checkbox list with SC-### references |
| Scope | In/Out/Boundaries subsections with file paths |

Optional sections: Context, Constraints, Notes.

## Work Unit Format

Generated work units follow the standard Maverick format:

| Section | Description |
|---------|-------------|
| Frontmatter | `work-unit`, `flight-plan`, `sequence`, `depends-on`, `parallel-group` (YAML) |
| Task | What to implement |
| Acceptance Criteria | With SC-### trace references |
| File Scope | Create/Modify/Protect file lists |
| Instructions | How to implement |
| Verification | Runnable commands to validate |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Flight plan not found" | Check the file path is correct and the file exists |
| "bd: command not found" | Install the `bd` CLI tool or use `--dry-run` |
| "Circular dependency detected" | Review your flight plan scope — the agent may have created conflicting dependencies. Re-run or edit work units manually |
| "SC-### not covered" | This is a warning. The success criterion may be cross-cutting. Verify coverage manually if needed |
