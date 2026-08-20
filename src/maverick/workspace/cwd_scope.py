"""The process-global ``os.chdir`` seam shared by every isolated agent step.

Hoisted out of ``agents/spec_chain.py`` (research.md R1), which held this as
a private module-level lock before 057-isolated-bead-workspaces generalized
it for `maverick fly`'s isolated mode too.

airframe 0.9.2's ``ClaudeOptions`` still exposes no working-directory field
— unlike ``CopilotOptions``/``OpenCodeServerOptions`` — so there is no
provider-blind way to point an agent at a workspace today. Pointing only
some providers at it would leave the ``claude`` provider (the default
binding) unable to isolate at all, so every agent step is instead pointed
at its workspace by chdir'ing the process around the call.

``os.chdir`` is process-wide state, so every chdir-scoped call in the
process is serialized through one module-level ``asyncio.Lock``. This is
safe today because agent execution is already required to be process-wide
serial: the spec chain runs its steps strictly sequentially (FR-002), and
isolated fly keeps beads strictly serial (FR-015, FR-031) with at most one
isolated run per checkout (FR-048) — the lock costs nothing against
constraints that already hold.

**Exit criterion** (plan.md Complexity Tracking row 2): once airframe grows
a universal working-directory parameter, this module becomes a one-line
adapter call and the lock disappears. The concurrent dispatcher (roadmap
prompt 9) cannot ship until then.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

__all__ = ["chdir_scope"]

#: Serializes every chdir-scoped agent execution in this process. See the
#: module docstring for why this is safe under the feature's current
#: constraints and what retires it.
_CWD_BIND_LOCK = asyncio.Lock()


@asynccontextmanager
async def chdir_scope(target: Path | str) -> AsyncIterator[None]:
    """Bind the process working directory to *target* for the duration of
    the context.

    Acquires the process-wide lock, ``os.chdir``s to *target*, yields, then
    restores the previous working directory — even if the body raises.

    Args:
        target: Directory to chdir into for the scope's duration (a
            workspace path, or the checkout for non-isolated behavior).
    """
    async with _CWD_BIND_LOCK:
        previous = Path.cwd()
        os.chdir(target)
        try:
            yield
        finally:
            os.chdir(previous)
