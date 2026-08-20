"""Unit tests for `JjClient.squash`'s isolation-primitive extensions.

Covers 057-isolated-bead-workspaces contract C4 (`from_`/`filesets`) — the
fold-back mechanism issues `jj squash --from '<ws>@' --into @ <filesets>`
from the checkout (research.md R2).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from maverick.jj.client import JjClient

from .conftest import make_result


class TestSquashFromWorkspace:
    """`JjClient.squash(from_=..., into=..., filesets=...)`."""

    @pytest.mark.asyncio
    async def test_from_and_into_emit_expected_command(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        result = await jj_client.squash(from_="ws1@", into="@", filesets=("~.maverick",))
        assert result.success is True

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "squash", "--from", "ws1@", "--into", "@", "~.maverick"]

    @pytest.mark.asyncio
    async def test_from_without_filesets(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result()
        await jj_client.squash(from_="ws1@", into="@")

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "squash", "--from", "ws1@", "--into", "@"]

    @pytest.mark.asyncio
    async def test_from_and_explicit_revision_are_mutually_exclusive(
        self, jj_client: JjClient
    ) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            await jj_client.squash(revision="kxyz", from_="ws1@", into="@")

    @pytest.mark.asyncio
    async def test_from_with_default_revision_is_allowed(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        # revision left at its default ("@") alongside from_ is fine — only
        # an *explicit* revision conflicts with jj's own -r/--from rejection.
        mock_runner.run.return_value = make_result()
        await jj_client.squash(from_="ws1@", into="@")

        cmd = mock_runner.run.call_args[0][0]
        assert "-r" not in cmd
