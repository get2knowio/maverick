"""Fly CLI commands package.

Re-exports the ``fly`` Click group so that
``from maverick.cli.commands.fly import fly`` continues to work.
"""

from __future__ import annotations

# isort: off
# Import the group first so subcommand modules can attach to it.
from maverick.cli.commands.fly._group import fly

# Import subcommand modules to register commands on the group.
from maverick.cli.commands.fly import beads as _beads  # noqa: F401
from maverick.cli.commands.fly import run as _run  # noqa: F401

# isort: on

__all__ = ["fly"]
