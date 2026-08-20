"""Unit tests for the isolation-primitive support actions in `jj.py`.

Foundational-phase (057-isolated-bead-workspaces): `jj_fold_back` and
`jj_workspace_snapshot` are thin, mechanical wrappers — see the module's
"Isolation primitive support" section docstring for the layering rationale.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.jj.models import JjSquashResult, JjStatusResult
from maverick.library.actions.git_models import JjFoldBackResult, JjWorkspaceSnapshotResult
from maverick.library.actions.jj import jj_fold_back, jj_workspace_snapshot

MOCK_CLIENT = "maverick.library.actions.jj._make_client"


def make_mock_client() -> AsyncMock:
    client = AsyncMock(spec=JjClient)
    client.cwd = None
    return client


class TestJjFoldBack:
    """Tests for the `jj_fold_back` action."""

    @pytest.mark.asyncio
    async def test_squashes_from_workspace(self) -> None:
        mock_client = make_mock_client()
        mock_client.squash.return_value = JjSquashResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_fold_back("ws1", into="@", filesets=("~.maverick",))

        assert result == JjFoldBackResult(success=True, error=None)
        mock_client.squash.assert_called_once_with(
            from_="ws1@", into="@", filesets=("~.maverick",)
        )

    @pytest.mark.asyncio
    async def test_handles_jj_error(self) -> None:
        mock_client = make_mock_client()
        mock_client.squash.side_effect = JjError("jj squash failed: conflicting workspace")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_fold_back("ws1")

        assert result.success is False
        assert result.error is not None


class TestJjWorkspaceSnapshot:
    """Tests for the `jj_workspace_snapshot` action."""

    @pytest.mark.asyncio
    async def test_forces_snapshot(self) -> None:
        mock_client = make_mock_client()
        mock_client.snapshot_working_copy.return_value = JjStatusResult(
            success=True, output="", working_copy_change_id="abc", conflict=False
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_workspace_snapshot()

        assert result == JjWorkspaceSnapshotResult(success=True, error=None)
        mock_client.snapshot_working_copy.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handles_jj_error(self) -> None:
        mock_client = make_mock_client()
        mock_client.snapshot_working_copy.side_effect = JjError("jj status failed")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_workspace_snapshot()

        assert result.success is False
        assert result.error is not None
