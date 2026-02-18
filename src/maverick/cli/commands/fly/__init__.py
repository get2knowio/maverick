"""Fly CLI command package.

Re-exports the ``fly`` Click command so that
``from maverick.cli.commands.fly import fly`` continues to work.
"""

from __future__ import annotations

from maverick.cli.commands.fly._group import fly

__all__ = ["fly"]
