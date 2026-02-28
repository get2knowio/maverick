"""Shared fixtures for maverick.flight unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal valid flight plan content (canonical source of truth)
# Also duplicated in tests/unit/cli/commands/flight_plan/conftest.py
# ---------------------------------------------------------------------------

VALID_FLIGHT_PLAN_CONTENT = """\
---
name: test-plan
version: "1.0"
created: 2026-02-28
---

## Objective

This is the objective text.

## Success Criteria

- [ ] First criterion
- [ ] Second criterion

## Scope

### In

- Something in scope

### Out

- Something out of scope
"""

# ---------------------------------------------------------------------------
# Sample Markdown strings
# ---------------------------------------------------------------------------

SAMPLE_FLIGHT_PLAN_MD = """\
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
"""

SAMPLE_WORK_UNIT_MD = """\
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
"""

SAMPLE_WORK_UNIT_MD_WITH_PARALLEL = """\
---
work-unit: add-login-endpoint
flight-plan: setup-authentication
sequence: 2
parallel-group: endpoints
depends-on:
  - setup-database
---

## Task

Implement the login endpoint.

## Acceptance Criteria

- POST /login accepts email and password
- Returns JWT on success [SC-002]

## File Scope

### Create

- src/api/login.py

### Modify

- src/api/__init__.py

### Protect

- src/db/connection.py

## Instructions

Use the database connection from setup-database work unit.

## Verification

- make test-fast
"""


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_flight_plan_md() -> str:
    """Return a sample Flight Plan Markdown string."""
    return SAMPLE_FLIGHT_PLAN_MD


@pytest.fixture
def sample_work_unit_md() -> str:
    """Return a sample Work Unit Markdown string."""
    return SAMPLE_WORK_UNIT_MD


@pytest.fixture
def sample_work_unit_md_with_parallel() -> str:
    """Return a sample Work Unit with parallel-group and depends-on."""
    return SAMPLE_WORK_UNIT_MD_WITH_PARALLEL


@pytest.fixture
def write_flight_plan(tmp_path: Path):
    """Return a helper that writes content to a temp file and returns its path."""

    def _write(content: str, filename: str = "plan.md") -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return p

    return _write
