"""Unit tests for `JjClient.workspace_add`'s isolation-primitive extension.

Covers 057-isolated-bead-workspaces contract C3 — provisioning issues
`jj workspace add -r @ <dir>` so the workspace's working-copy commit is a
child of the checkout's `@` (research.md R2).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.jj.client import JjClient
from maverick.jj.models import JjWorkspaceInfo

from .conftest import make_result


class TestWorkspaceAddRevision:
    """`JjClient.workspace_add(target, revision=...)`."""

    @pytest.mark.asyncio
    async def test_revision_emits_dash_r(
        self, jj_client: JjClient, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = make_result()
        target = temp_dir / "ws1"
        await jj_client.workspace_add(target, revision="@")

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "workspace", "add", "-r", "@", str(target)]

    @pytest.mark.asyncio
    async def test_no_revision_is_backward_compatible(
        self, jj_client: JjClient, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = make_result()
        target = temp_dir / "ws2"
        await jj_client.workspace_add(target)

        cmd = mock_runner.run.call_args[0][0]
        assert cmd == ["jj", "workspace", "add", str(target)]


class TestWorkspaceList:
    """`JjClient.workspace_list()` (research.md R7/FR-028 — sweep needs
    jj's own registry, since a workspace's directory and its jj-side
    registration can diverge)."""

    @pytest.mark.asyncio
    async def test_parses_name_and_root(self, jj_client: JjClient, mock_runner: AsyncMock) -> None:
        mock_runner.run.return_value = make_result(
            stdout="default\x1f/home/user/proj\nbd-1\x1f/home/user/.maverick/workspaces/proj/fly/bd-1\n"
        )
        result = await jj_client.workspace_list()

        assert result.success is True
        assert result.workspaces == (
            JjWorkspaceInfo(name="default", path="/home/user/proj"),
            JjWorkspaceInfo(name="bd-1", path="/home/user/.maverick/workspaces/proj/fly/bd-1"),
        )

    @pytest.mark.asyncio
    async def test_missing_directory_parses_as_empty_path(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        # jj omits the root entirely for a workspace whose directory is
        # currently missing (verified against real jj 0.44) — the
        # template renders "" there rather than the next field (the
        # change id) bleeding into the path.
        mock_runner.run.return_value = make_result(stdout="bd-orphan\x1f\n")
        result = await jj_client.workspace_list()

        assert result.workspaces == (JjWorkspaceInfo(name="bd-orphan", path=""),)

    @pytest.mark.asyncio
    async def test_uses_a_template_not_the_human_readable_default(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="")
        await jj_client.workspace_list()

        cmd = mock_runner.run.call_args[0][0]
        assert cmd[:3] == ["jj", "workspace", "list"]
        assert "-T" in cmd

    @pytest.mark.asyncio
    async def test_blank_output_yields_no_workspaces(
        self, jj_client: JjClient, mock_runner: AsyncMock
    ) -> None:
        mock_runner.run.return_value = make_result(stdout="")
        result = await jj_client.workspace_list()

        assert result.workspaces == ()
