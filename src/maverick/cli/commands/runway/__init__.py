"""Runway CLI commands package.

Re-exports the ``runway`` Click group so that
``from maverick.cli.commands.runway import runway`` works.
"""

from __future__ import annotations

# isort: off
# Import the group first so subcommand modules can attach to it.
from maverick.cli.commands.runway._group import runway

# Import subcommand modules to register commands on the group.
from maverick.cli.commands.runway import init as _init  # noqa: F401
from maverick.cli.commands.runway import status as _status  # noqa: F401

# isort: on

__all__ = ["runway"]
