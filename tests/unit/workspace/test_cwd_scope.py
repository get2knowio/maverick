"""Unit tests for `maverick.workspace.cwd_scope.chdir_scope`.

Hoisted from `agents/spec_chain.py` (057-isolated-bead-workspaces, T014) —
see the module docstring for the airframe `ClaudeOptions` gap this seam
works around (research.md R1) and its exit criterion.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from maverick.workspace.cwd_scope import chdir_scope


class TestChdirScope:
    @pytest.mark.asyncio
    async def test_binds_and_restores_cwd(self, tmp_path: Path) -> None:
        previous = Path.cwd()
        target = tmp_path / "workspace"
        target.mkdir()

        async with chdir_scope(target):
            assert Path.cwd() == target.resolve()

        assert Path.cwd() == previous

    @pytest.mark.asyncio
    async def test_restores_cwd_even_when_body_raises(self, tmp_path: Path) -> None:
        previous = Path.cwd()
        target = tmp_path / "workspace"
        target.mkdir()

        with pytest.raises(RuntimeError, match="boom"):
            async with chdir_scope(target):
                assert Path.cwd() == target.resolve()
                raise RuntimeError("boom")

        assert Path.cwd() == previous

    @pytest.mark.asyncio
    async def test_serializes_concurrent_scopes(self, tmp_path: Path) -> None:
        """Two concurrent chdir_scope calls must never observe each
        other's target cwd — the whole point of the module-level lock."""
        target_a = tmp_path / "a"
        target_b = tmp_path / "b"
        target_a.mkdir()
        target_b.mkdir()
        observed: list[Path] = []

        async def scoped(target: Path) -> None:
            async with chdir_scope(target):
                observed.append(Path.cwd())
                await asyncio.sleep(0)
                # If the lock didn't serialize these, the other task's
                # chdir could have executed here, changing our cwd out
                # from under us.
                assert Path.cwd() == target.resolve()

        await asyncio.gather(scoped(target_a), scoped(target_b))
        assert set(observed) == {target_a.resolve(), target_b.resolve()}
