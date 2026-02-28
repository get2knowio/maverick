"""Flight Plan CLI commands package.

Re-exports the ``flight_plan`` Click group so that
``from maverick.cli.commands.flight_plan import flight_plan`` works.
"""

from __future__ import annotations

# isort: off
# Import the group first so subcommand modules can attach to it.
from maverick.cli.commands.flight_plan._group import flight_plan

# isort: on

# Import subcommand modules so they register themselves on the group.
from maverick.cli.commands.flight_plan import create as _create  # noqa: F401
from maverick.cli.commands.flight_plan import (
    validate_cmd as _validate_cmd,  # noqa: F401
)

__all__ = ["flight_plan"]
