"""Tests for the backstop snapshot/restore engine (protection/snapshot.py).

See specs/056-context-file-protection/data-model.md's "SnapshotManifest"
section and research.md R6 for the normative restore matrix this exercises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.protection.policy import ProtectionPolicy
from maverick.protection.records import BlockCollector
from maverick.protection.snapshot import SnapshotManifest, restore_and_report


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def policy(root: Path) -> ProtectionPolicy:
    return ProtectionPolicy.build(root)


class TestCapture:
    async def test_captures_existing_protected_files(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        (root / "AGENTS.md").write_text("original agents content")
        (root / "unprotected.py").write_text("code")
        manifest = await SnapshotManifest.capture(root, policy)
        assert "AGENTS.md" in manifest.entries
        assert "unprotected.py" not in manifest.entries

    async def test_captures_nested_specify_memory_tree(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        nested = root / ".specify" / "memory"
        nested.mkdir(parents=True)
        (nested / "constitution.md").write_text("principles")
        manifest = await SnapshotManifest.capture(root, policy)
        assert ".specify/memory/constitution.md" in manifest.entries

    async def test_capture_empty_repo_yields_empty_manifest(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        manifest = await SnapshotManifest.capture(root, policy)
        assert manifest.entries == {}

    async def test_prunes_git_and_venv_dirs(self, root: Path, policy: ProtectionPolicy) -> None:
        for pruned in (".git", ".venv", "node_modules", ".jj", ".maverick"):
            d = root / pruned
            d.mkdir()
            (d / "AGENTS.md").write_text("should not be captured")
        manifest = await SnapshotManifest.capture(root, policy)
        assert manifest.entries == {}


class TestRestoreEditUndone:
    async def test_edit_is_reverted_byte_identical(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        target = root / "CLAUDE.md"
        original = "original claude content\nline two"
        target.write_text(original)
        manifest = await SnapshotManifest.capture(root, policy)

        target.write_text("agent overwrote this")

        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )
        assert target.read_text() == original
        assert len(records) == 1
        assert records[0].operation == "restore"
        assert records[0].layer == "backstop"
        assert records[0].path == "CLAUDE.md"


class TestRestoreDeleteUndone:
    async def test_delete_is_reverted(self, root: Path, policy: ProtectionPolicy) -> None:
        target = root / "AGENTS.md"
        original = "keep me"
        target.write_text(original)
        manifest = await SnapshotManifest.capture(root, policy)

        target.unlink()

        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )
        assert target.exists()
        assert target.read_text() == original
        assert records[0].detail is not None and "delete/rename" in records[0].detail


class TestRestoreCreateUndone:
    async def test_newly_created_protected_file_is_removed(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        manifest = await SnapshotManifest.capture(root, policy)
        assert manifest.entries == {}

        new_file = root / "sub" / "AGENTS.md"
        new_file.parent.mkdir(parents=True)
        new_file.write_text("agent sneaked this in")

        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )
        assert not new_file.exists()
        assert len(records) == 1
        assert records[0].path == "sub/AGENTS.md"
        assert records[0].detail is not None and "create/rename-to" in records[0].detail


class TestRestoreRenameUndone:
    async def test_rename_away_restores_original_and_removes_new_location(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        target = root / "CLAUDE.md"
        original = "original"
        target.write_text(original)
        manifest = await SnapshotManifest.capture(root, policy)

        # Simulate a rename: CLAUDE.md -> renamed onto another protected name.
        target.rename(root / "AGENTS.md")
        (root / "AGENTS.md").write_text("renamed content, but AGENTS.md wasn't in manifest")

        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )
        # CLAUDE.md restored...
        assert target.exists()
        assert target.read_text() == original
        # ...and the AGENTS.md that appeared (not in the manifest) removed.
        assert not (root / "AGENTS.md").exists()
        assert len(records) == 2


class TestSymlinkRestore:
    async def test_symlink_plant_at_protected_path_is_unlinked(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        manifest = await SnapshotManifest.capture(root, policy)
        real_target = root / "elsewhere.txt"
        real_target.write_text("not protected itself")
        link = root / "AGENTS.md"
        link.symlink_to(real_target)

        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )
        assert not link.exists() and not link.is_symlink()
        assert real_target.exists()  # the target itself is untouched
        assert len(records) == 1


class TestNoChangeNoRestore:
    async def test_unchanged_protected_file_yields_no_records(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        (root / "AGENTS.md").write_text("stable")
        manifest = await SnapshotManifest.capture(root, policy)
        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )
        assert records == []


class TestCollectorIntegration:
    async def test_records_also_appended_to_collector(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        target = root / "CLAUDE.md"
        target.write_text("original")
        manifest = await SnapshotManifest.capture(root, policy)
        target.write_text("mutated")

        collector = BlockCollector()
        records = await restore_and_report(
            manifest,
            policy,
            agent_role="implement",
            workflow="fly-beads",
            bead_id="bd-1",
            collector=collector,
        )
        drained = collector.drain()
        assert drained == records
        assert drained[0].bead_id == "bd-1"


class TestRestoreFailureLogsAndContinues:
    async def test_restore_failure_on_one_entry_does_not_block_others(
        self, root: Path, policy: ProtectionPolicy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        claude = root / "CLAUDE.md"
        claude.write_text("claude original")
        agents = root / "AGENTS.md"
        agents.write_text("agents original")
        manifest = await SnapshotManifest.capture(root, policy)

        claude.write_text("claude mutated")
        agents.write_text("agents mutated")

        original_atomic_write_bytes = __import__(
            "maverick.protection.snapshot", fromlist=["atomic_write_bytes"]
        ).atomic_write_bytes

        def _flaky_write(path: object, content: bytes, **kwargs: object) -> None:
            if "CLAUDE.md" in str(path):
                raise OSError("simulated disk failure")
            original_atomic_write_bytes(path, content, **kwargs)

        monkeypatch.setattr("maverick.protection.snapshot.atomic_write_bytes", _flaky_write)

        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )
        assert len(records) == 2
        claude_record = next(r for r in records if r.path == "CLAUDE.md")
        agents_record = next(r for r in records if r.path == "AGENTS.md")
        assert claude_record.detail is not None and "FAILED" in claude_record.detail
        assert agents_record.detail is not None and "FAILED" not in agents_record.detail
        # The one that succeeded really was restored on disk.
        assert agents.read_text() == "agents original"
        # The one that failed is left as the agent's mutation (best effort).
        assert claude.read_text() == "claude mutated"


class TestNonUtf8ProtectedFiles:
    """A protected file need not be valid UTF-8.

    Restoring through a ``str`` round-trip raises ``UnicodeEncodeError``
    — a ``ValueError``, so it escapes the ``except OSError`` handler
    entirely and propagates out of the ``finally`` that brackets the
    agent send, replacing the send's own outcome.
    """

    async def test_restores_non_utf8_bytes_byte_identically(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        claude = root / "CLAUDE.md"
        original = b"# CLAUDE.md\n\xff\xfe not valid utf-8\n"
        claude.write_bytes(original)
        manifest = await SnapshotManifest.capture(root, policy)

        claude.write_bytes(b"agent overwrote this")
        records = await restore_and_report(
            manifest, policy, agent_role="implement", workflow="fly-beads"
        )

        assert claude.read_bytes() == original
        assert len(records) == 1
        assert records[0].detail is not None and "FAILED" not in records[0].detail

    async def test_crlf_content_survives_restore_byte_identically(
        self, root: Path, policy: ProtectionPolicy
    ) -> None:
        agents = root / "AGENTS.md"
        original = b"line one\r\nline two\r\n"
        agents.write_bytes(original)
        manifest = await SnapshotManifest.capture(root, policy)

        agents.write_bytes(b"mutated")
        await restore_and_report(manifest, policy, agent_role="implement", workflow="fly-beads")

        assert agents.read_bytes() == original


class TestUnreadableProtectedFileIsNotDeleted:
    """A protected file present but unreadable at capture time has no
    manifest entry; the post-step scan must not mistake it for something
    the agent created and delete the user's own file.
    """

    async def test_unreadable_at_capture_is_not_removed_by_restore(
        self, root: Path, policy: ProtectionPolicy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        claude = root / "CLAUDE.md"
        claude.write_text("the user's real context file")

        real_read_bytes = Path.read_bytes

        def _unreadable(self: Path) -> bytes:
            if self.name == "CLAUDE.md":
                raise PermissionError("simulated unreadable file")
            return real_read_bytes(self)

        monkeypatch.setattr(Path, "read_bytes", _unreadable)
        manifest = await SnapshotManifest.capture(root, policy)
        monkeypatch.undo()

        assert "CLAUDE.md" not in manifest.entries
        assert "CLAUDE.md" in manifest.unreadable

        collector = BlockCollector()
        await restore_and_report(
            manifest,
            policy,
            agent_role="implement",
            workflow="fly-beads",
            collector=collector,
        )

        assert claude.exists()
        assert claude.read_text() == "the user's real context file"
        assert collector.drain() == []
