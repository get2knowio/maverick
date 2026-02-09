"""Unit tests for BeadClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDefinition, BeadDependency
from maverick.exceptions.beads import (
    BeadCloseError,
    BeadCreationError,
    BeadDependencyError,
    BeadError,
    BeadQueryError,
)
from maverick.runners.models import CommandResult


class TestBeadClientVerifyAvailable:
    """Tests for BeadClient.verify_available()."""

    @pytest.mark.asyncio
    async def test_available(self, mock_runner: AsyncMock, temp_dir: Path) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="bd v0.1.0",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        assert await client.verify_available()

    @pytest.mark.asyncio
    async def test_not_available(self, mock_runner: AsyncMock, temp_dir: Path) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=127,
            stdout="",
            stderr="Command not found: bd",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        assert not await client.verify_available()


class TestBeadClientCreateBead:
    """Tests for BeadClient.create_bead()."""

    @pytest.mark.asyncio
    async def test_create_success(
        self,
        mock_runner: AsyncMock,
        temp_dir: Path,
        sample_task_definition: BeadDefinition,
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout='{"id": "bead-001"}',
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.create_bead(sample_task_definition)
        assert result.bd_id == "bead-001"
        assert result.definition == sample_task_definition

    @pytest.mark.asyncio
    async def test_create_with_parent(
        self,
        mock_runner: AsyncMock,
        temp_dir: Path,
        sample_task_definition: BeadDefinition,
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout='{"id": "bead-002"}',
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.create_bead(sample_task_definition, parent_id="epic-001")
        assert result.bd_id == "bead-002"

        # Verify --parent was passed
        call_args = mock_runner.run.call_args
        cmd = call_args[0][0]
        assert "--parent" in cmd
        assert "epic-001" in cmd

    @pytest.mark.asyncio
    async def test_create_failure_raises(
        self,
        mock_runner: AsyncMock,
        temp_dir: Path,
        sample_task_definition: BeadDefinition,
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: not a git repository",
            duration_ms=100,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadCreationError) as exc_info:
            await client.create_bead(sample_task_definition)
        assert exc_info.value.bead_title == "Foundation"

    @pytest.mark.asyncio
    async def test_create_invalid_json_raises(
        self,
        mock_runner: AsyncMock,
        temp_dir: Path,
        sample_task_definition: BeadDefinition,
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="not json",
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadCreationError):
            await client.create_bead(sample_task_definition)

    @pytest.mark.asyncio
    async def test_create_missing_id_raises(
        self,
        mock_runner: AsyncMock,
        temp_dir: Path,
        sample_task_definition: BeadDefinition,
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout='{"status": "created"}',
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadCreationError):
            await client.create_bead(sample_task_definition)

    @pytest.mark.asyncio
    async def test_create_uses_bead_id_field(
        self,
        mock_runner: AsyncMock,
        temp_dir: Path,
        sample_task_definition: BeadDefinition,
    ) -> None:
        """Test fallback to 'bead_id' field in response."""
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout='{"bead_id": "bead-alt"}',
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.create_bead(sample_task_definition)
        assert result.bd_id == "bead-alt"


class TestBeadClientAddDependency:
    """Tests for BeadClient.add_dependency()."""

    @pytest.mark.asyncio
    async def test_add_dependency_success(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        dep = BeadDependency(blocker_id="a", blocked_id="b")
        await client.add_dependency(dep)

        call_args = mock_runner.run.call_args
        cmd = call_args[0][0]
        assert cmd == [
            "bd", "dep", "add", "b",
            "--blocked-by", "a", "--type", "blocks",
        ]

    @pytest.mark.asyncio
    async def test_add_dependency_failure_raises(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: bead not found",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        dep = BeadDependency(blocker_id="a", blocked_id="b")
        with pytest.raises(BeadDependencyError) as exc_info:
            await client.add_dependency(dep)
        assert exc_info.value.blocker_id == "a"
        assert exc_info.value.blocked_id == "b"


class TestBeadClientSync:
    """Tests for BeadClient.sync()."""

    @pytest.mark.asyncio
    async def test_sync_success(self, mock_runner: AsyncMock, temp_dir: Path) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        await client.sync()

    @pytest.mark.asyncio
    async def test_sync_failure_raises(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: sync failed",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadError, match="Failed to sync"):
            await client.sync()


class TestBeadClientReady:
    """Tests for BeadClient.ready()."""

    @pytest.mark.asyncio
    async def test_ready_returns_beads(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        import json

        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout=json.dumps([
                {"id": "b-1", "title": "Task 1", "priority": 1},
                {"id": "b-2", "title": "Task 2", "priority": 5},
            ]),
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.ready("epic-1", limit=2)

        assert len(result) == 2
        assert result[0].id == "b-1"
        assert result[0].priority == 1

        # Verify command
        cmd = mock_runner.run.call_args[0][0]
        assert "ready" in cmd
        assert "--parent" in cmd
        assert "epic-1" in cmd

    @pytest.mark.asyncio
    async def test_ready_empty_list(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="[]",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.ready("epic-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_ready_failure_raises(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: not found",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadQueryError):
            await client.ready("epic-1")


class TestBeadClientClose:
    """Tests for BeadClient.close()."""

    @pytest.mark.asyncio
    async def test_close_success(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        import json

        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout=json.dumps({
                "id": "b-1",
                "status": "closed",
                "closed_at": "2025-01-01T00:00:00Z",
            }),
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.close("b-1", reason="done")

        assert result.id == "b-1"
        assert result.status == "closed"

        cmd = mock_runner.run.call_args[0][0]
        assert "close" in cmd
        assert "b-1" in cmd
        assert "--reason" in cmd

    @pytest.mark.asyncio
    async def test_close_failure_raises(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: bead not found",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadCloseError) as exc_info:
            await client.close("b-1")
        assert exc_info.value.bead_id == "b-1"


class TestBeadClientShow:
    """Tests for BeadClient.show()."""

    @pytest.mark.asyncio
    async def test_show_success(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        import json

        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout=json.dumps({
                "id": "b-1",
                "title": "Task 1",
                "description": "Full desc",
                "status": "open",
                "priority": 3,
            }),
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.show("b-1")
        assert result.id == "b-1"
        assert result.title == "Task 1"

    @pytest.mark.asyncio
    async def test_show_failure_raises(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: not found",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadQueryError):
            await client.show("b-missing")


class TestBeadClientChildren:
    """Tests for BeadClient.children()."""

    @pytest.mark.asyncio
    async def test_children_success(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        import json

        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout=json.dumps([
                {"id": "c-1", "title": "Child 1", "status": "open", "priority": 1},
            ]),
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.children("epic-1")
        assert len(result) == 1
        assert result[0].id == "c-1"

    @pytest.mark.asyncio
    async def test_children_failure_raises(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: not found",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadQueryError):
            await client.children("epic-missing")


class TestBeadClientQuery:
    """Tests for BeadClient.query()."""

    @pytest.mark.asyncio
    async def test_query_success(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        import json

        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout=json.dumps([
                {"id": "q-1", "title": "Found 1", "status": "open", "priority": 2},
            ]),
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        result = await client.query("status=open")
        assert len(result) == 1
        assert result[0].id == "q-1"

        cmd = mock_runner.run.call_args[0][0]
        assert "query" in cmd
        assert "status=open" in cmd


class TestBeadClientSetState:
    """Tests for BeadClient.set_state()."""

    @pytest.mark.asyncio
    async def test_set_state_success(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        await client.set_state("b-1", {"branch": "main"}, reason="init")

        cmd = mock_runner.run.call_args[0][0]
        assert "set-state" in cmd
        assert "b-1" in cmd
        assert "branch=main" in cmd
        assert "--reason" in cmd

    @pytest.mark.asyncio
    async def test_set_state_failure_raises(
        self, mock_runner: AsyncMock, temp_dir: Path
    ) -> None:
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: bead not found",
            duration_ms=50,
            timed_out=False,
        )
        client = BeadClient(cwd=temp_dir, runner=mock_runner)
        with pytest.raises(BeadError, match="Failed to set state"):
            await client.set_state("b-1", {"key": "val"})
