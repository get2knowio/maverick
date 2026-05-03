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
            message="bead(B-1): Implement thing\n\nBead: B-1",
            cwd=tmp_path,
        )


class TestBuildBeadCommitMessage:
    def test_subject_prefix_preserved_for_curator_extraction(self) -> None:
        """``bead(<id>): <title>`` subject is preserved so
        ``library.actions.curation.extract_bead_ids`` keeps working."""
        from maverick.workflows.fly_beads._commit import build_bead_commit_message

        msg = build_bead_commit_message("X-1", "Add login")
        assert msg.startswith("bead(X-1): Add login")

    def test_trailer_appended_with_blank_line(self) -> None:
        """Standard git-trailer format: blank line then ``Bead: <id>``."""
        from maverick.workflows.fly_beads._commit import build_bead_commit_message

        msg = build_bead_commit_message("X-1", "Add login")
        assert msg == "bead(X-1): Add login\n\nBead: X-1"

    def test_trailer_uses_same_id_as_subject(self) -> None:
        """The trailer mirrors the subject's bead id verbatim."""
        from maverick.workflows.fly_beads._commit import build_bead_commit_message

        msg = build_bead_commit_message("project-x.42", "Refactor authn")
        assert "Bead: project-x.42" in msg.split("\n\n", 1)[1]
