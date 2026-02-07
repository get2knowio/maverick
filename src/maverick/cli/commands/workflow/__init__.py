"""Workflow CLI commands package.

Re-exports the ``workflow`` Click group and ``_execute_workflow_run`` so that
existing import paths (``from maverick.cli.commands.workflow import ...``)
continue to work after the single-file-to-package refactor.
"""

from __future__ import annotations

# isort: off
# Import the group first so subcommand modules can attach to it.
from maverick.cli.commands.workflow._group import workflow

# Import every subcommand module to register commands on the group.
from maverick.cli.commands.workflow import info as _info  # noqa: F401
from maverick.cli.commands.workflow import list_cmd as _list_cmd  # noqa: F401
from maverick.cli.commands.workflow import new as _new  # noqa: F401
from maverick.cli.commands.workflow import run as _run  # noqa: F401
from maverick.cli.commands.workflow import search as _search  # noqa: F401
from maverick.cli.commands.workflow import show as _show  # noqa: F401
from maverick.cli.commands.workflow import validate as _validate  # noqa: F401
from maverick.cli.commands.workflow import viz as _viz  # noqa: F401

# Re-export the shared helper used by fly.py
from maverick.cli.commands.workflow.run import _execute_workflow_run

# isort: on

__all__ = [
    "_execute_workflow_run",
    "workflow",
]
