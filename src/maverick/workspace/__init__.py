"""Hidden jj workspace lifecycle for the interim short-term model.

A workspace here is a ``jj workspace add`` working copy under
``~/.maverick/workspaces/<project>/`` that shares the **same backing
repo** as the user's checkout. Bead commits made in the workspace are
visible in the user's checkout's ``jj log`` immediately — no clone
bridge, no apply-to-user-repo dance, no two-copies-of-bd drift.

This package replaces the pre-collapse ``WorkspaceManager``
(``src/maverick/workspace/`` deleted in commit ``cf11db4``) which used
``jj git clone`` to isolate. The clone-based pattern was the root of
every 2026-05-02 bug; the workspace-add pattern sidesteps every one
because there is only one underlying repo.

This is **interim** — short-term scaffolding until the full
pull-work-push architecture (``architecture-pull-work-push.md``) lands
and maverick owns the working directory entirely.
"""

from __future__ import annotations

from maverick.workspace.manager import WorkspaceManager

__all__ = ["WorkspaceManager"]
