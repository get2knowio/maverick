# Quickstart: Flight Plan and Work Unit Models

## Load a Flight Plan

```python
from pathlib import Path
from maverick.flight import FlightPlanFile

# Synchronous
plan = FlightPlanFile.load(Path("flight-plan.md"))
print(plan.name, plan.version)
print(plan.objective)

# Check completion
status = plan.completion
print(f"{status.checked}/{status.total} ({status.percentage}%)")

# Asynchronous
plan = await FlightPlanFile.aload(Path("flight-plan.md"))
```

## Load Work Units

```python
from maverick.flight import WorkUnitFile

# Load a single Work Unit
unit = WorkUnitFile.load(Path("001-setup-database.md"))
print(unit.id, unit.sequence, unit.flight_plan)

# Load all Work Units from a directory
units = WorkUnitFile.load_directory(Path("work-units/"))
for u in units:
    print(f"{u.sequence}: {u.id} (depends on: {u.depends_on})")
```

## Resolve Execution Order

```python
from maverick.flight import WorkUnitFile, resolve_execution_order

units = WorkUnitFile.load_directory(Path("work-units/"))
order = resolve_execution_order(units)

for batch in order.batches:
    group = f" [{batch.parallel_group}]" if batch.parallel_group else ""
    ids = ", ".join(u.id for u in batch.units)
    print(f"Batch{group}: {ids}")
```

## Round-Trip Serialization

```python
from maverick.flight import FlightPlanFile, serialize_flight_plan

# Load, modify, save
plan = FlightPlanFile.load(Path("flight-plan.md"))
updated = plan.model_copy(update={"notes": "Updated notes."})
FlightPlanFile.save(updated, Path("flight-plan.md"))
```

## Error Handling

```python
from maverick.flight import (
    FlightPlanFile,
    FlightPlanNotFoundError,
    FlightPlanParseError,
    FlightPlanValidationError,
)

try:
    plan = FlightPlanFile.load(Path("missing.md"))
except FlightPlanNotFoundError as e:
    print(f"File not found: {e}")
except FlightPlanParseError as e:
    print(f"Parse error: {e}")
except FlightPlanValidationError as e:
    print(f"Validation error: {e}")
```

## Sample Flight Plan Document

```markdown
---
name: setup-authentication
version: "1.0"
created: 2026-02-27
tags:
  - auth
  - security
---

## Objective

Implement user authentication with JWT tokens.

## Success Criteria

- [x] Users can register with email and password
- [ ] Users can log in and receive a JWT
- [ ] Protected routes reject unauthenticated requests

## Scope

### In

- Registration endpoint
- Login endpoint
- JWT middleware

### Out

- OAuth providers
- Password reset flow

### Boundaries

- JWT tokens expire after 24 hours

## Context

Building on the existing Express.js API framework.

## Constraints

- Must use bcrypt for password hashing
- Token secret from environment variable

## Notes

Consider adding refresh tokens in a follow-up.
```

## Sample Work Unit Document

```markdown
---
work-unit: setup-database
flight-plan: setup-authentication
sequence: 1
depends-on: []
---

## Task

Create the users table and database connection module.

## Acceptance Criteria

- Database connection pool is configured [SC-001]
- Users table has email, password_hash, created_at columns

## File Scope

### Create

- src/db/connection.py
- src/db/models/user.py

### Modify

- src/config.py

### Protect

- src/main.py

## Instructions

Use SQLAlchemy with async support. Follow existing patterns in the project.

## Verification

- make test-fast
- make lint
- make typecheck
```
