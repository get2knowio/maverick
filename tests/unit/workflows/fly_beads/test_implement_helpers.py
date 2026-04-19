"""Tests for fly-beads implementation helper functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from maverick.workflows.fly_beads._implement import snapshot_and_describe
from maverick.workflows.fly_beads.models import BeadContext


class TestSnapshotAndDescribe:
    """Tests for snapshot_and_describe."""

    async def test_uses_path_cwd_and_dict_results(self, tmp_path: Path) -> None:
        """JJ helpers receive Path values and dict-shaped results are handled."""
        ctx = BeadContext(
            bead_id="B-1",
            title="Implement thing",
            description="Make the thing work",
            epic_id="E-1",
            cwd=tmp_path,
        )

        with (
            patch(
                "maverick.workflows.fly_beads._implement.jj_snapshot_operation",
                new_callable=AsyncMock,
            ) as mock_snapshot,
            patch(
                "maverick.workflows.fly_beads._implement.jj_describe",
                new_callable=AsyncMock,
            ) as mock_describe,
        ):
            mock_snapshot.return_value = {
                "success": True,
                "operation_id": "op-1",
                "error": None,
            }
            mock_describe.return_value = {"success": True, "error": None}

            await snapshot_and_describe(MagicMock(), ctx)

        mock_snapshot.assert_awaited_once_with(cwd=tmp_path)
        mock_describe.assert_awaited_once_with(
            message="bead(B-1): Implement thing",
            cwd=tmp_path,
        )
