"""xoscar-backed actor implementations.

Phase 1+ of the Thespian→xoscar migration lives here so the diff against
the legacy ``src/maverick/actors/*.py`` surface stays clean. The
top-level ``maverick.actors`` namespace will re-export these classes in
Phase 4 once the Thespian bodies are deleted.

See ``docs/prd-xoscar-migration.md`` for the migration design and
``/home/vscode/.claude/plans/cryptic-herding-cocoa.md`` for the
phase-by-phase plan.
"""

from __future__ import annotations

from maverick.actors.xoscar.pool import (
    DEFAULT_POOL_ADDRESS,
    actor_pool,
    create_pool,
    teardown_pool,
)

__all__ = [
    "DEFAULT_POOL_ADDRESS",
    "actor_pool",
    "create_pool",
    "teardown_pool",
]
