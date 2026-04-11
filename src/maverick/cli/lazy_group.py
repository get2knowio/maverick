"""Lazy Click group that defers command module imports.

Top-level command modules (``fly``, ``refuel``, ``brief`` …) drag in
workflows, the ACP SDK, Thespian, etc. — easily 400ms on startup.
The CLI entry point registers command *pointers* with :class:`LazyGroup`;
the pointed-to module is imported only when that command is actually
invoked, and ``maverick --help`` renders a stored short description
without loading any of them.
"""

from __future__ import annotations

import importlib
from typing import Any

import click


class LazyGroup(click.Group):
    """Click group whose subcommands are imported on demand.

    ``lazy_subcommands`` maps ``command_name`` → ``(import_path, short_help)``
    where ``import_path`` is ``"pkg.module:attr"`` pointing at the real
    :class:`click.Command` instance.
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, tuple[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._lazy: dict[str, tuple[str, str]] = dict(lazy_subcommands or {})
        self._resolved: dict[str, click.Command] = {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        eager = super().list_commands(ctx)
        return sorted({*eager, *self._lazy.keys()})

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self._lazy:
            return self._resolve(cmd_name)
        return super().get_command(ctx, cmd_name)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Render command list without importing lazy modules.

        Eager subcommands (registered via :meth:`add_command`) are loaded
        normally; lazy ones use their stored short help string.
        """
        rows: list[tuple[str, str]] = []
        for name in self.list_commands(ctx):
            if name in self._lazy:
                _, short_help = self._lazy[name]
                rows.append((name, short_help))
                continue
            cmd = super().get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            rows.append((name, cmd.get_short_help_str()))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)

    def _resolve(self, cmd_name: str) -> click.Command:
        cached = self._resolved.get(cmd_name)
        if cached is not None:
            return cached
        import_path, _ = self._lazy[cmd_name]
        modname, _, attr = import_path.partition(":")
        if not attr:
            raise RuntimeError(
                f"LazyGroup entry {cmd_name!r} must use 'module:attr' form, got {import_path!r}"
            )
        module = importlib.import_module(modname)
        command = getattr(module, attr)
        if not isinstance(command, click.Command):
            raise TypeError(
                f"LazyGroup target {import_path!r} is {type(command).__name__}, "
                "expected click.Command"
            )
        self._resolved[cmd_name] = command
        return command
