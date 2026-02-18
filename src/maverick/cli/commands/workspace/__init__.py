"""Workspace CLI commands package.

Re-exports the ``workspace`` Click group so that
``from maverick.cli.commands.workspace import workspace`` works.
"""

from __future__ import annotations

# isort: off
# Import the group first so subcommand modules can attach to it.
from maverick.cli.commands.workspace._group import workspace

# Import subcommand modules to register commands on the group.
from maverick.cli.commands.workspace import clean as _clean  # noqa: F401
from maverick.cli.commands.workspace import status as _status  # noqa: F401

# isort: on

__all__ = ["workspace"]
