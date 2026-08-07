"""Tests for :class:`maverick.protection.policy.PermissionGate` (Layer 1).

See specs/056-context-file-protection/data-model.md's "PermissionGate"
section and contracts/airframe-precursor.md for the callback contract this
implements against.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from airframe.permission import PermissionRequest

from maverick.agents.context import tagged
from maverick.protection.policy import PermissionGate, ProtectionPolicy
from maverick.protection.records import BlockCollector


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def policy(root: Path) -> ProtectionPolicy:
    return ProtectionPolicy.build(root)


@pytest.fixture
def collector() -> BlockCollector:
    return BlockCollector()


@pytest.fixture
def gate(policy: ProtectionPolicy, collector: BlockCollector) -> PermissionGate:
    return PermissionGate(
        policy=policy, collector=collector, agent_role="implement", workflow="fly-beads"
    )


class TestDenyOnProtectedFileWrite:
    async def test_write_tool_file_path_denied(self, gate: PermissionGate) -> None:
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "CLAUDE.md"})
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_edit_tool_file_path_denied(self, gate: PermissionGate) -> None:
        request = PermissionRequest(
            tool_name="Edit", tool_args={"file_path": "AGENTS.md", "old_string": "a"}
        )
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_multi_edit_denied(self, gate: PermissionGate) -> None:
        request = PermissionRequest(
            tool_name="MultiEdit", tool_args={"file_path": ".specify/memory/constitution.md"}
        )
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_notebook_edit_notebook_path_denied(self, gate: PermissionGate) -> None:
        request = PermissionRequest(
            tool_name="NotebookEdit", tool_args={"notebook_path": "sub/AGENTS.md"}
        )
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_generic_path_field_denied(self, gate: PermissionGate) -> None:
        request = PermissionRequest(
            tool_name="str_replace_editor", tool_args={"path": "CLAUDE.md"}
        )
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_rename_old_new_path_denied_on_source(self, gate: PermissionGate) -> None:
        request = PermissionRequest(
            tool_name="rename_file",
            tool_args={"old_path": "CLAUDE.md", "new_path": "CLAUDE.bak"},
        )
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_rename_old_new_path_denied_on_destination(self, gate: PermissionGate) -> None:
        request = PermissionRequest(
            tool_name="rename_file",
            tool_args={"old_path": "notes.txt", "new_path": "AGENTS.md"},
        )
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_deny_appends_block_record(
        self, gate: PermissionGate, collector: BlockCollector
    ) -> None:
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "CLAUDE.md"})
        await gate.handle(request)
        records = collector.drain()
        assert len(records) == 1
        assert records[0].layer == "pre-write"
        assert records[0].agent_role == "implement"
        assert records[0].workflow == "fly-beads"
        assert records[0].path == "CLAUDE.md"
        assert records[0].detail

    async def test_bead_id_read_from_ambient_tags_at_call_time(
        self, gate: PermissionGate, collector: BlockCollector
    ) -> None:
        """``bead_id`` isn't fixed at gate construction — a gate instance may
        outlive several beads, so it must reflect whichever bead is active
        for *this* call (mirrors ``Agent._emit_cost``'s ``current_tags()`` use).
        """
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "CLAUDE.md"})
        with tagged(bead_id="bd-42"):
            await gate.handle(request)
        with tagged(bead_id="bd-99"):
            await gate.handle(request)
        records = collector.drain()
        assert [r.bead_id for r in records] == ["bd-42", "bd-99"]


class TestAllowOnUnprotected:
    async def test_write_unprotected_file_allowed(self, gate: PermissionGate) -> None:
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "src/real_work.py"})
        decision = await gate.handle(request)
        assert decision == "allow"

    async def test_allow_appends_no_block_record(
        self, gate: PermissionGate, collector: BlockCollector
    ) -> None:
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "src/x.py"})
        await gate.handle(request)
        assert collector.drain() == []


class TestDeferOnUnknownOrBashLikeTools:
    """Tools the gate has no opinion about must return ``"defer"``, not
    ``"allow"``.

    Attaching ``on_permission=`` replaces the vendor's own permission
    policy. ``"allow"`` is an affirmative approval (Copilot:
    ``PermissionDecisionApproveOnce``); ``"defer"`` hands the decision
    back to the SDK (Copilot: ``PermissionDecisionUserNotAvailable``),
    which is exactly the pre-protection behavior.
    """

    async def test_bash_tool_deferred_never_parsed(self, gate: PermissionGate) -> None:
        request = PermissionRequest(
            tool_name="Bash", tool_args={"command": "rm CLAUDE.md AGENTS.md"}
        )
        decision = await gate.handle(request)
        assert decision == "defer"

    async def test_unknown_tool_name_deferred(self, gate: PermissionGate) -> None:
        request = PermissionRequest(tool_name="SomeVendorSpecificTool", tool_args={"x": 1})
        decision = await gate.handle(request)
        assert decision == "defer"

    async def test_known_tool_missing_path_field_deferred(self, gate: PermissionGate) -> None:
        request = PermissionRequest(tool_name="Write", tool_args={})
        decision = await gate.handle(request)
        assert decision == "defer"


class TestCallbackInternalErrorFailsClosed:
    async def test_exception_during_decide_denies_default_name(
        self, gate: PermissionGate, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(ProtectionPolicy, "decide", _boom)
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "CLAUDE.md"})
        decision = await gate.handle(request)
        assert decision == "deny"

    async def test_exception_during_decide_defers_non_default_name(
        self, gate: PermissionGate, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(ProtectionPolicy, "decide", _boom)
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "src/real_work.py"})
        decision = await gate.handle(request)
        assert decision == "defer"

    async def test_fail_closed_deny_still_records_block(
        self, gate: PermissionGate, collector: BlockCollector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(ProtectionPolicy, "decide", _boom)
        request = PermissionRequest(tool_name="Write", tool_args={"file_path": "AGENTS.md"})
        await gate.handle(request)
        records = collector.drain()
        assert len(records) == 1
        assert records[0].layer == "pre-write"
