"""Unit tests for BeadClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDefinition, BeadDependency
from maverick.exceptions.beads import (
    BeadCreationError,
    BeadDependencyError,
    BeadError,
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
        dep = BeadDependency(from_id="a", to_id="b")
        await client.add_dependency(dep)

        call_args = mock_runner.run.call_args
        cmd = call_args[0][0]
        assert cmd == ["bd", "dep", "add", "a", "b"]

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
        dep = BeadDependency(from_id="a", to_id="b")
        with pytest.raises(BeadDependencyError) as exc_info:
            await client.add_dependency(dep)
        assert exc_info.value.from_id == "a"
        assert exc_info.value.to_id == "b"


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
