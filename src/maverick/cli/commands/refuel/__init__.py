"""Refuel CLI commands package.

Re-exports the ``refuel`` Click group so that
``from maverick.cli.commands.refuel import refuel`` continues to work.
"""

from __future__ import annotations

# isort: off
# Import the group first so subcommand modules can attach to it.
from maverick.cli.commands.refuel._group import refuel

# Import subcommand modules to register commands on the group.
from maverick.cli.commands.refuel import speckit as _speckit  # noqa: F401

# isort: on

__all__ = ["refuel"]
