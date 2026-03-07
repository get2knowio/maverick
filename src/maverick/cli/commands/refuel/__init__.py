"""Refuel CLI command package.

Re-exports the ``refuel`` Click command so that
``from maverick.cli.commands.refuel import refuel`` continues to work.
"""

from __future__ import annotations

from maverick.cli.commands.refuel._group import refuel

__all__ = ["refuel"]
