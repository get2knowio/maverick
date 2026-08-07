"""Integration tests for `maverick reconcile` against real colocated jj repos.

Scenarios populated incrementally as reconcile's user stories land — see
specs/051-reconcile-changed-answers/quickstart.md.

Scenario 1 (US1, SC-001/SC-008) below combines the two existing
integration-test patterns in this repo:

* ``tests/integration/test_assumption_ledger_flow.py``'s real ``bd`` + real
  ``jj`` fixture (colocated ``git init`` / ``jj git init --colocate`` /
  ``bd init --non-interactive``).
* ``tests/integration/spec_chain/conftest.py``'s stubbed airframe runtime
  (monkeypatch ``airframe.runtime_for`` to a fake runtime class whose
  ``execute()`` returns a canned structured payload without calling any
  real model).

One genuine, pre-existing bug was found and FIXED while building this test
(see ``workflows/reconcile/detection.py``'s ``_find_stack_match``); a second
is an unrelated environment issue, worked around locally rather than fixed:

1. **Change-id format mismatch — FIXED.** ``JjClient.commit()``/
   ``JjClient.new()`` resolve their returned change id via a template with
   no ``.short()`` (``client.py``'s ``_resolve_change_id``, used at
   ``client.py:440`` and ``:465``) — the FULL ~32-char id — by design (a
   short id is only guaranteed unique at render time, unsafe to persist).
   But ``JjClient.log()`` (``client.py:552-566``) renders
   ``change_id.short()`` — a prefix of the full id, not equal to it. Since
   ``assumptions.ledger.stamp_change_id`` is always fed the FULL form (e.g.
   fly's commit action, or ``JjClient.commit().change_id`` directly),
   ``workflows.reconcile.detection._resolve_target``'s original exact-string
   lookup against a dict keyed by ``JjClient.log()``'s SHORT ids meant a
   genuinely real stamped change id would never resolve — every real
   changed answer would have hit ``target_change_id is None`` and
   terminal-marked ``needs-interactive-review: "unresolvable correction
   target"`` without ever attempting a correction. Fixed via prefix-aware
   matching in ``detection._find_stack_match`` (unit-regression-tested in
   ``tests/unit/workflows/reconcile/test_detection.py``). This test stamps
   entries with the REAL full-form id ``JjClient.commit()`` returns (see
   ``_write_and_commit`` below) — exactly what production's
   ``stamp_change_id`` callers supply — to exercise the fix against genuine
   production-shaped data, not a workaround.

2. **Installed ``bd`` CLI is incompatible with ``BeadClient`` in this
   sandbox (environment issue, predates and is unrelated to reconcile).**
   The globally installed ``@beads/bd`` (version 1.1.0, unpinned
   devcontainer feature) diverges from what ``src/maverick/beads/client.py``
   expects in ways confirmed while calibrating this test: ``bd show <id>
   --json`` always returns a JSON array (its ``show`` signature is now
   batch/multi-id capable — ``show [id...]``) rather than a bare object,
   breaking ``BeadClient.show()``'s ``BeadDetails.model_validate(data)``;
   ``bd show --json`` no longer emits a ``state`` object at all — only a
   ``labels`` array of ``dimension:value`` strings, the same data
   differently shaped; ``bd set-state`` now accepts exactly one
   ``<dimension>=<value>`` pair per invocation (rejecting the
   space-separated multi-pair form ``BeadClient.set_state()`` sends) and
   rejects empty values outright — breaking ``ledger.answer()``'s FR-017
   re-arm clear-to-``""`` step naively, though it's recoverable: since bd's
   state IS just `dimension:value` labels, clearing a key is instead
   implemented as removing that label directly (``bd label remove <id>
   "<dimension>:<value>"``, confirmed supported by this bd build — see
   ``_bd_set_state_compat`` in Scenario 2's fixtures below); and bare ``bd
   query "type=X"`` (no status
   clause) now defaults to open-only, silently excluding closed/answered
   beads, whereas ``assumptions.ledger.answered_unreconciled_entries()``
   (and ``_find_existing_standalone_entry``) rely on exactly that bare form
   returning every status (research.md R1 documents this as a *known*
   requirement — "must query beads regardless of bd status" — that no
   longer holds against this bd build). This is confirmed pre-existing and
   environment-wide, not something introduced by reconcile or this test:
   running the already-landed ``tests/integration/test_assumption_ledger_flow.py``
   in this same sandbox fails identically, at the same ``client.show()``
   call, for the same reason. Since every needed translation is a
   mechanical, format-only adaptation of data ``bd`` already returns (never
   reimplementing ledger/business logic), this module works around it
   locally via ``monkeypatch`` on ``BeadClient.show``/``set_state``/
   ``query`` (see ``_install_bd_compat_shims`` below) so this test still
   exercises the real, unmodified ``ReconcileWorkflow`` /
   ``assumptions.ledger`` / ``JjClient`` against real ``bd`` + real ``jj``
   subprocesses end-to-end. None of ``src/`` is modified.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.assumptions.ledger import answer, record_assumption, stamp_change_id
from maverick.assumptions.models import (
    KEY_RECONCILE_CHANGE_ID,
    KEY_RECONCILE_REASON,
    KEY_RECONCILE_STATUS,
    RECONCILE_STATUS_NEEDS_REVIEW,
    TERMINAL_RECONCILE_STATUSES,
    AssumptionRecord,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadCategory, BeadDefinition, BeadSummary, BeadType
from maverick.config import (
    AgentBindingConfig,
    AgentsConfig,
    MaverickConfig,
    ReconcileConfig,
    ValidationConfig,
)
from maverick.exceptions.beads import BeadError, BeadQueryError
from maverick.jj.client import JjClient
from maverick.payloads import AssumptionPayload
from maverick.workflows.reconcile.workflow import ReconcileWorkflow

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if shutil.which("bd") is None or shutil.which("jj") is None:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)

#: The fake reconciler runtime writes this sentinel into the target file so
#: the test can assert the correction actually landed (research R3 step 2).
SENTINEL_LINE = "# reconciled: corrected per the new human answer\n"

#: Feature owning the ledger entry, mirrors the reconcile spec's own number.
_OWNER_SPEC = "051-reconcile-changed-answers"

#: Every status this bd build's ``bd query`` help text documents. Used to
#: force a bare ``type=X`` query (no explicit status clause) back to
#: "every status", matching what ``assumptions.ledger``'s bare-form callers
#: assume (see bug note #2 above).
_ALL_STATUSES_CLAUSE = (
    "(status=open OR status=in_progress OR status=blocked OR "
    "status=deferred OR status=closed OR status=done)"
)


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _make_cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


# ---------------------------------------------------------------------------
# bd 1.1.0 compatibility shims (bug note #2) — mechanical, format-only
# translations of data bd already returns; no ledger/business logic here.
# ---------------------------------------------------------------------------


async def _bd_show_compat(self: BeadClient, bead_id: str) -> Any:
    from maverick.beads.models import BeadDetails

    cmd = ["bd", "show", bead_id, "--json"]
    data = await self._run_bd(
        cmd,
        error_cls=BeadQueryError,
        error_msg=f"Failed to show bead {bead_id}",
        query=f"show {bead_id}",
    )
    if isinstance(data, list):
        data = data[0]
    raw_labels = data.get("labels") or []
    state: dict[str, str] = {}
    plain_labels: list[str] = []
    for label in raw_labels:
        if ":" in label:
            dimension, _, value = label.partition(":")
            state[dimension] = value
        else:
            plain_labels.append(label)
    data = {**data, "labels": plain_labels, "state": state}
    return BeadDetails.model_validate(data)


async def _bd_set_state_compat(
    self: BeadClient, bead_id: str, state: dict[str, str], reason: str = ""
) -> None:
    # bd 1.1.0 rejects `dimension=` (empty value) outright (bug note #2).
    # ``ledger.answer()``'s FR-017 re-arm now writes the non-terminal
    # ``pending`` sentinel rather than clearing to ``""`` for exactly this
    # reason, so no production path sends an empty value here. This general
    # empty-value handling is kept as a defensive compat shim regardless: bd's
    # state IS just `dimension:value` labels (see ``_bd_show_compat``), and bd
    # exposes direct label removal (``bd label remove <id> "<dimension>:<value>"``,
    # confirmed against this bd build) — so "clear a key" is implementable as
    # "remove its current label", a mechanical, format-only reinterpretation
    # of the same operation, not new ledger/business logic.
    empty_keys = [key for key, value in state.items() if value == ""]
    if empty_keys:
        current = await self.show(bead_id)
        for key in empty_keys:
            current_value = (current.state or {}).get(key)
            if not current_value:
                continue  # already unset — nothing to remove
            remove_cmd = ["bd", "label", "remove", bead_id, f"{key}:{current_value}"]
            remove_result = await self._runner.run(remove_cmd, cwd=self._cwd)
            if not remove_result.success:
                raise BeadError(
                    f"Failed to clear state key {key} on bead {bead_id}: "
                    f"{remove_result.stderr.strip()}"
                )

    for key, value in state.items():
        if value == "":
            continue
        cmd = ["bd", "set-state", bead_id, f"{key}={value}"]
        if reason:
            cmd.extend(["--reason", reason])
        result = await self._runner.run(cmd, cwd=self._cwd)
        if not result.success:
            raise BeadError(f"Failed to set state on bead {bead_id}: {result.stderr.strip()}")


async def _bd_query_compat(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
    effective_expr = filter_expr
    if "status" not in filter_expr:
        effective_expr = f"{filter_expr} AND {_ALL_STATUSES_CLAUSE}"
    cmd = ["bd", "query", effective_expr, "--json"]
    data = await self._run_bd(
        cmd,
        error_cls=BeadQueryError,
        error_msg=f"Failed to query beads: {filter_expr}",
        query=filter_expr,
    )
    items = data if isinstance(data, list) else data.get("beads", [])
    return [BeadSummary.model_validate(item) for item in items]


def _install_bd_compat_shims(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``BeadClient`` for this bd build's CLI-contract drift (bug #2).

    Purely mechanical, format-only adaptations of data ``bd`` already
    returns (array-wrapping, ``labels``-encoded state, single-pair
    ``set-state``, default-open-only bare queries) — no ledger/business
    logic is reimplemented. Confirmed necessary by running the pre-existing
    ``tests/integration/test_assumption_ledger_flow.py`` in this same
    sandbox and observing an identical failure at the same call site.
    """
    monkeypatch.setattr(BeadClient, "show", _bd_show_compat)
    monkeypatch.setattr(BeadClient, "set_state", _bd_set_state_compat)
    monkeypatch.setattr(BeadClient, "query", _bd_query_compat)


class _StubSession:
    """Minimal ``AgentSession`` stand-in shared by every stub runtime in this
    file: ``Agent.open()`` now always routes through ``runtime.session(...)``
    when a squadron builds a real ``ProtectionPolicy``
    (056-context-file-protection), so each fake runtime's ``session()``
    must return something whose ``execute()`` delegates back to the
    runtime's own (stubbed) ``execute()``.
    """

    def __init__(self, runtime: Any, **kwargs: Any) -> None:
        self.id = "stub-session"
        self._runtime = runtime

    async def execute(self, prompt: str, **kwargs: Any) -> RuntimeResult:
        return await self._runtime.execute(prompt, **kwargs)

    async def close(self) -> None:
        return None


class _ReconcileCorrectionRuntime:
    """Fake airframe runtime for ``ReconcilerAgent.correct`` (Scenario 1).

    Scenario 1's stack never produces a rebase conflict (B/C don't touch
    the corrected lines), so ``resolve_conflicts`` never makes an agent
    call here. It DOES reach the semantic-dependents pass, though — T030
    wired ``run_semantic_pass`` unconditionally between the conflicts
    stage and the gate, so this stub also answers that call (no ``##
    Mode:`` marker, see ``agents/semantic_reviewer.py``) by declaring every
    supplied descendant non-dependent, letting the pass complete in one
    round with zero follow-up corrections — Scenario 1 is about the
    correction mechanism, not semantic dependents. It edits the real repo
    directly — the workflow never ``os.chdir``s, it runs real jj/bd
    subprocesses against an explicit ``cwd``, but this fake runtime
    executes in-process, so the repo path is captured via closure
    (``repo``) rather than read from ``Path.cwd()``.
    """

    label = "stub"

    def __init__(
        self,
        *,
        model: str | None = None,
        repo: Path | None = None,
        target_file: str = "a.py",
        **kwargs: object,
    ) -> None:
        self.model = model
        self._repo = repo
        self._target_file = target_file
        self.execute_calls: list[dict[str, object]] = []

    async def execute(self, prompt: str, **kwargs: object) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        if "## Mode: Correction" not in prompt:
            if "## Mode: Conflict Resolution" in prompt:
                raise AssertionError(
                    "Scenario 1's stack never produces a rebase conflict "
                    f"(B/C don't touch the corrected lines); unexpected "
                    f"conflict-resolution prompt: {prompt[:200]!r}"
                )
            # No ``## Mode:`` marker: the semantic-dependents pass' analyze
            # call (T030, unconditionally wired in after conflicts).
            # Declare every supplied descendant non-dependent.
            return RuntimeResult(
                text="",
                structured={"findings": []},
                cost=_make_cost(),
                finish="end_turn",
            )
        assert self._repo is not None
        target_path = self._repo / self._target_file
        existing = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
        target_path.write_text(existing + SENTINEL_LINE, encoding="utf-8")
        structured = {
            "summary": "Corrected scoping to match the new human answer.",
            "files_touched": [self._target_file],
            "no_change_required": False,
        }
        return RuntimeResult(text="", structured=structured, cost=_make_cost(), finish="end_turn")

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: object) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _StubSession:
        return _StubSession(self, **kwargs)


def _stub_reconcile_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo: Path,
    target_file: str = "a.py",
) -> list[_ReconcileCorrectionRuntime]:
    """Patch ``airframe.runtime_for`` (same point ``ReconcileSquadron`` calls
    via ``runtime_for_agent``); returns the constructed-instances list."""
    constructed: list[_ReconcileCorrectionRuntime] = []

    def _factory(provider_id: str) -> type[_ReconcileCorrectionRuntime]:
        class _Bound(_ReconcileCorrectionRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: object) -> None:
                super().__init__(model=model, repo=repo, target_file=target_file, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


# ---------------------------------------------------------------------------
# Scenario 2 (US2, SC-002) fixtures — two changed answers processed in one
# run: the first corrects cleanly (real gate pass), the second's correction
# gets folded but then genuinely trips a real gate command, forcing a real
# ``jj_restore_operation`` rollback. See ``test_scenario_2_rollback_on_gate_failure``.
# ---------------------------------------------------------------------------

#: Embedded in entry 1's question so the fake runtime (which sees both
#: entries' correction prompts in one run, since ``ReconcileSquadron`` builds
#: one persistent runtime instance for the whole run) can tell which
#: answer's correction call this is, without depending on jj diff formatting.
_ENTRY_ONE_MARKER = "ENTRY-ONE-CLEAN-CORRECTION"
#: Embedded in entry 2's question — its correction call sabotages ``b.py``.
_ENTRY_TWO_MARKER = "ENTRY-TWO-SABOTAGED-CORRECTION"
#: Written into ``b.py`` by entry 2's fake correction; a *real* gate command
#: (a tiny ``python -c`` script, not a per-answer-varied config) fails
#: whenever this literal string is present in ``b.py`` on disk — proving the
#: rollback undid a genuine, on-disk-verifiable mutation.
_UNSAFE_MARKER = "UNSAFE_VALUE_SENTINEL"


class _Scenario2CorrectionRuntime:
    """Fake airframe runtime handling BOTH Scenario 2 correction calls.

    Unlike ``_ReconcileCorrectionRuntime`` (fixed single target file/content
    for Scenario 1's one changed answer), this runtime must behave
    differently for each of the two changed answers processed in the same
    run — it disambiguates by looking for each entry's unique marker string
    (embedded in the ledger entry's ``question``, which flows verbatim into
    the correction prompt's ``### Question`` section, see
    ``ReconcilerAgent._build_correct_prompt``).

    Neither entry's correction produces a rebase conflict (each targets a
    distinct file/change with no other descendant touching those lines),
    so ``resolve_conflicts`` never makes an agent call here. Both entries
    DO reach the semantic-dependents pass, though — T030 wired
    ``run_semantic_pass`` unconditionally between the conflicts stage and
    the gate (which now runs *after* the semantic pass, per
    ``workflow.py``'s current stage order), so this stub also answers that
    call (no ``## Mode:`` marker) by declaring every supplied descendant
    non-dependent — Scenario 2 is about gate-failure rollback, not
    semantic dependents.
    """

    label = "stub"

    def __init__(
        self, *, model: str | None = None, repo: Path | None = None, **kwargs: object
    ) -> None:
        self.model = model
        self._repo = repo
        self.execute_calls: list[dict[str, object]] = []

    async def execute(self, prompt: str, **kwargs: object) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        if "## Mode: Correction" not in prompt:
            if "## Mode: Conflict Resolution" in prompt:
                raise AssertionError(
                    "Scenario 2's two entries never produce a rebase "
                    f"conflict; unexpected conflict-resolution prompt: {prompt[:200]!r}"
                )
            # No ``## Mode:`` marker: the semantic-dependents pass' analyze
            # call (T030, unconditionally wired in after conflicts).
            # Declare every supplied descendant non-dependent.
            return RuntimeResult(
                text="",
                structured={"findings": []},
                cost=_make_cost(),
                finish="end_turn",
            )
        assert self._repo is not None

        if _ENTRY_ONE_MARKER in prompt:
            # Clean correction: append the same harmless sentinel Scenario 1
            # uses, to a.py only — never touches b.py, so it never trips
            # the gate script below.
            target_path = self._repo / "a.py"
            existing = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
            target_path.write_text(existing + SENTINEL_LINE, encoding="utf-8")
            files_touched = ["a.py"]
        elif _ENTRY_TWO_MARKER in prompt:
            # Sabotaged correction: overwrite b.py with a value the real
            # gate script (see test body) genuinely rejects.
            target_path = self._repo / "b.py"
            target_path.write_text(f'SAFE_VALUE = "{_UNSAFE_MARKER}"\n', encoding="utf-8")
            files_touched = ["b.py"]
        else:
            raise AssertionError(
                f"correction prompt matched neither entry marker: {prompt[:200]!r}"
            )

        structured = {
            "summary": "Corrected per the new human answer.",
            "files_touched": files_touched,
            "no_change_required": False,
        }
        return RuntimeResult(text="", structured=structured, cost=_make_cost(), finish="end_turn")

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: object) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _StubSession:
        return _StubSession(self, **kwargs)


def _stub_scenario2_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo: Path,
) -> list[_Scenario2CorrectionRuntime]:
    """Same patch point as ``_stub_reconcile_runtime_factory`` (Scenario 1),
    bound to ``_Scenario2CorrectionRuntime`` instead."""
    constructed: list[_Scenario2CorrectionRuntime] = []

    def _factory(provider_id: str) -> type[_Scenario2CorrectionRuntime]:
        class _Bound(_Scenario2CorrectionRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: object) -> None:
                super().__init__(model=model, repo=repo, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


def _scenario2_config() -> MaverickConfig:
    """Config for Scenario 2: no-op format/lint/typecheck, a REAL test gate.

    ``run_independent_gate``'s commands are fixed for the whole run (built
    once from ``self._config.validation`` in ``ReconcileWorkflow._run``, not
    per-answer — confirmed by reading ``workflow.py``), so "one answer's
    gate passes, the next's fails" cannot be done by varying the gate
    command per answer. Instead the ``test`` stage is a real subprocess that
    inspects ``b.py`` on disk: it passes whenever entry 1's correction runs
    (b.py is untouched or still safe) and genuinely fails once entry 2's
    sabotaged correction has been folded into the working copy — a real,
    verifiable gate failure driven by what the fake reconciler wrote, not by
    a rigged command.
    """
    gate_script = (
        "import pathlib, sys\n"
        "p = pathlib.Path('b.py')\n"
        "text = p.read_text(encoding='utf-8') if p.exists() else ''\n"
        f"sys.exit(1 if {_UNSAFE_MARKER!r} in text else 0)\n"
    )
    noop_cmd = [sys.executable, "-c", "pass"]
    return MaverickConfig(
        agents=AgentsConfig(
            implement=AgentBindingConfig(provider="claude", model_id="stub-model"),
            review=AgentBindingConfig(provider="claude", model_id="stub-model"),
        ),
        validation=ValidationConfig(
            format_cmd=noop_cmd,
            lint_cmd=noop_cmd,
            typecheck_cmd=noop_cmd,
            test_cmd=[sys.executable, "-c", gate_script],
        ),
    )


@pytest.fixture
def reconcile_repo(tmp_path: Path) -> Path:
    """A tmp directory with a real, jj-colocated ``bd`` database."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    _run(["jj", "git", "init", "--colocate"], cwd=repo)
    _run(["bd", "init", "--non-interactive"], cwd=repo)

    # Mirrors what a real `maverick init` writes to .gitignore
    # (src/maverick/init/__init__.py's `_ensure_gitignore_entries`).
    # Without it, `.maverick/runs/<run-id>/reconcile.json` would dirty the
    # workflow's own "fresh empty landing change" (research R13) in this
    # test fixture -- not a reconcile bug, just what any real project setup
    # already avoids.
    (repo / ".gitignore").write_text(".maverick/runs/\n", encoding="utf-8")
    _run(["jj", "commit", "-m", "gitignore"], cwd=repo)
    return repo


async def _write_and_commit(jj_client: JjClient, repo: Path, filename: str, content: str) -> str:
    """Write *filename*, ``jj commit`` it, and return its FULL change id.

    Returns ``JjCommitResult.change_id`` directly — the same unabbreviated
    form production's ``stamp_change_id`` callers (e.g. fly's commit
    action) always stamp with — exercising the real
    ``detection._find_stack_match`` prefix-matching fix (module docstring
    bug note #1) against genuine production-shaped data.
    """
    (repo / filename).write_text(content, encoding="utf-8")
    commit_result = await jj_client.commit(filename)
    return commit_result.change_id


def _reconcile_config(*, format_cmd: list[str]) -> MaverickConfig:
    return MaverickConfig(
        agents=AgentsConfig(
            implement=AgentBindingConfig(provider="claude", model_id="stub-model"),
            review=AgentBindingConfig(provider="claude", model_id="stub-model"),
        ),
        validation=ValidationConfig(
            format_cmd=format_cmd,
            lint_cmd=format_cmd,
            typecheck_cmd=format_cmd,
            test_cmd=format_cmd,
        ),
    )


@pytest.mark.asyncio
async def test_scenario_1_clean_retroactive_application(
    reconcile_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quickstart.md Scenario 1 / SC-001 / SC-008.

    Builds ``base <- A <- B <- C`` where A is the ledger-stamped correction
    target and B/C each touch a distinct file the correction never touches.
    Reconciling should fold the correction into A, leave B/C's rebased
    content untouched, mark the ledger entry ``reconciled``, and a second
    invocation should be a total no-op (idempotence).
    """
    _install_bd_compat_shims(monkeypatch)

    repo = reconcile_repo
    jj_client = JjClient(cwd=repo)
    client = BeadClient(cwd=repo)

    # --- Build the jj stack: base <- A <- B <- C ------------------------
    await _write_and_commit(jj_client, repo, "base.py", "# base\n")
    a_change_id = await _write_and_commit(
        jj_client, repo, "a.py", "def scope():\n    return 'per-bead'\n"
    )
    b_change_id = await _write_and_commit(jj_client, repo, "b.py", "# b\n")
    c_change_id = await _write_and_commit(jj_client, repo, "c.py", "# c\n")

    # --- Ledger entry: answered, stamped on A, human answer differs -----
    epic = await client.create_bead(
        BeadDefinition(
            title=f"Integration epic ({_OWNER_SPEC})",
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": _OWNER_SPEC})
    source = await client.create_bead(
        BeadDefinition(
            title="Implement the thing",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        ),
        parent_id=epic.bd_id,
    )

    payload = AssumptionPayload(
        question="Should retries be scoped per bead or per run?",
        adopted_answer="Per bead — matches existing scoping.",
        alternatives=("Per run",),
        severity="medium",
    )
    record = await record_assumption(
        client, payload=payload, source_bead_id=source.bd_id, epic_id=epic.bd_id
    )
    assert record is not None

    stamp_result = await stamp_change_id(client, entry_ids=[record.bead_id], change_id=a_change_id)
    assert stamp_result.stamped == (record.bead_id,)

    await answer(
        client, bead_id=record.bead_id, answer_text="Per run — matches the new usage pattern."
    )

    # bd's own writes (.beads/interactions.jsonl etc.) dirty the jj working
    # copy; reconcile refuses to start unless @ is clean (FR-014), so fold
    # them into a fresh empty working-copy commit before running it.
    await jj_client.new()

    working_copy_stat = await jj_client.diff_stat(revision="@")
    assert working_copy_stat.files_changed == 0, "fixture setup must leave a clean @ (FR-014)"

    # --- Config: stub agent bindings + no-op gate commands ---------------
    config = _reconcile_config(format_cmd=[sys.executable, "-c", "pass"])
    constructed = _stub_reconcile_runtime_factory(monkeypatch, repo=repo, target_file="a.py")

    # --- Run 1: reconcile --------------------------------------------------
    workflow = ReconcileWorkflow(config=config)
    events = [
        event
        async for event in workflow.execute(
            {"run_id": "test-run-1", "cwd": str(repo), "dry_run": False}
        )
    ]
    assert workflow.result is not None
    assert workflow.result.success is True, [
        getattr(e, "error", None) for e in events if hasattr(e, "error")
    ]

    report = workflow.result.final_output
    assert report is not None
    outcomes = report["outcomes"]
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["entry_id"] == record.bead_id
    assert outcome["status"] == "reconciled"
    assert outcome["target_change_id"] == a_change_id
    assert outcome["gate_passed"] is True

    # The correction agent was actually invoked (not skipped).
    assert any(runtime.execute_calls for runtime in constructed)

    # --- Assertion: A's diff contains the corrected content ---------------
    a_diff = await jj_client.diff(revision=a_change_id)
    assert SENTINEL_LINE.strip() in a_diff.output

    # --- Assertion: B/C are still connected (rebased, not orphaned) -------
    # JjClient.log() renders SHORT change ids (a prefix of the FULL ids
    # this test tracks, per the module docstring's bug note #1) — match
    # accordingly rather than by exact set membership.
    final_log = await jj_client.log(revset="::@", limit=200)
    final_short_ids = {c.change_id for c in final_log.changes}

    def _still_present(full_id: str) -> bool:
        return any(full_id.startswith(short_id) for short_id in final_short_ids)

    assert _still_present(a_change_id)
    assert _still_present(b_change_id)
    assert _still_present(c_change_id)

    # Tip lands on a fresh, empty, description-less working copy (research
    # R13) -- i.e. no fixup change was left at the tip for this correction.
    assert final_log.changes[0].empty is True
    assert final_log.changes[0].description == ""

    # --- Assertion: B/C content is byte-identical to what they committed --
    assert (repo / "b.py").read_text(encoding="utf-8") == "# b\n"
    assert (repo / "c.py").read_text(encoding="utf-8") == "# c\n"

    # --- Assertion: ledger entry state is reconciled -----------------------
    entry_details = await client.show(record.bead_id)
    assert entry_details.state[KEY_RECONCILE_STATUS] == "reconciled"
    assert entry_details.state[KEY_RECONCILE_CHANGE_ID]

    # --- Assertion: idempotent re-run makes zero changes (SC-008) ---------
    op_log_before = _run(
        ["jj", "op", "log", "--no-graph", "-T", "id", "--limit", "1"], cwd=repo
    ).stdout
    change_log_before = _run(
        ["jj", "log", "--no-graph", "-T", 'change_id ++ "\\n"'], cwd=repo
    ).stdout

    workflow2 = ReconcileWorkflow(config=config)
    events2 = [
        event
        async for event in workflow2.execute(
            {"run_id": "test-run-2", "cwd": str(repo), "dry_run": False}
        )
    ]
    assert workflow2.result is not None
    assert workflow2.result.success is True, [
        getattr(e, "error", None) for e in events2 if hasattr(e, "error")
    ]
    report2 = workflow2.result.final_output
    assert report2 is not None
    assert report2["outcomes"] == []

    op_log_after = _run(
        ["jj", "op", "log", "--no-graph", "-T", "id", "--limit", "1"], cwd=repo
    ).stdout
    change_log_after = _run(
        ["jj", "log", "--no-graph", "-T", 'change_id ++ "\\n"'], cwd=repo
    ).stdout

    assert op_log_after == op_log_before, "re-run must not create any new jj operation"
    assert change_log_after == change_log_before, "re-run must not mutate jj history"


@pytest.mark.asyncio
async def test_scenario_2_rollback_on_gate_failure(
    reconcile_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quickstart.md Scenario 2 / SC-002 / research R8 / T023.

    Builds ``base <- TARGET`` (one commit introducing BOTH ``a.py`` and
    ``b.py``) with TWO changed-answer ledger entries stamped on the SAME
    ``TARGET`` change — a realistic shape (``stamp_change_id`` takes a
    sequence of entry ids for exactly this reason: a single bead can
    surface more than one assumption). Entry 1 (created — and so detected
    — first, per ``answered_unreconciled_entries``'s bead-id ordering)
    corrects ``a.py`` cleanly and passes the real gate; entry 2 corrects
    ``b.py`` but its correction genuinely trips the gate. Proves, in one
    run:

    1. The failing answer terminal-marks ``needs_interactive_review`` with
       a gate-failure reason.
    2. ``jj_restore_operation`` genuinely undoes the failed answer's
       mutation — ``b.py``'s on-disk content and ``TARGET``'s own diff are
       byte-identical to their pre-answer state, never containing the
       sabotaged value the fake reconciler wrote.
    3. The other, already-successful answer's correction stays applied
       (``TARGET``'s diff still contains entry 1's correction; its ledger
       entry is still ``reconciled``) — a rollback on one answer must not
       touch a sibling answer's already-landed work.
    4. The failed entry's bd state carries
       ``assumption_reconcile_status=needs-interactive-review`` plus a
       reason (data-model.md §2).
    5. Re-answering the failed entry via ``ledger.answer()`` clears that
       state (FR-017 re-arm) and a third workflow invocation picks the
       entry back up (it reappears in that run's outcomes).

    Why a SHARED target rather than a two-answer stack (``base <- A <-
    B``): this repo currently has ``workflows/reconcile/workflow.py``'s
    T032/T033 slice landed (per-answer target re-resolution via
    ``detection.resolve_target_against_current_stack``, using revset
    ``"::@"``) — landed concurrently while this test was being built (see
    the module docstring's bug note #3). Verified directly (both via a
    throwaway ``jj`` sandbox and by instrumenting this exact code path):
    after folding entry 1's correction into its target via
    ``jj_squash_into``, the working copy ``@`` becomes a NEW EMPTY CHILD
    OF THAT TARGET — a *sibling* of any change that was previously a
    descendant of the target, not a descendant itself (confirmed with
    jj 0.43: "Rebased N descendant commits" runs, but ``@`` does not move
    onto the rebased chain). So ``"::@"`` (ancestors-of-working-copy), used
    to re-verify a SECOND answer's target after the FIRST answer's fold,
    no longer contains that second target once it sits on a different
    branch than the FIRST answer's target — even though the change id
    itself is perfectly valid and reachable in the repo. A genuinely
    unrelated ``base <- A <- B`` two-target stack hits exactly this and
    always reports entry 2 as unlocatable, never reaching correction/gate
    at all. Stamping both entries on the SAME target sidesteps it (the
    target is always @'s own parent post-fold, never a sibling), letting
    this test actually exercise gate-failure rollback rather than the
    (separate, T032/T033-scoped) unresolvable-target path. Reported as a
    suspected bug rather than fixed here, per this task's scope.
    """
    _install_bd_compat_shims(monkeypatch)

    repo = reconcile_repo
    jj_client = JjClient(cwd=repo)
    client = BeadClient(cwd=repo)

    # --- Build the jj stack: base <- TARGET (adds a.py AND b.py) ----------
    await _write_and_commit(jj_client, repo, "base.py", "# base\n")
    (repo / "a.py").write_text("def scope():\n    return 'per-bead'\n", encoding="utf-8")
    (repo / "b.py").write_text('SAFE_VALUE = "safe"\n', encoding="utf-8")
    commit_result = await jj_client.commit("a_and_b")
    target_change_id = commit_result.change_id

    # --- Ledger entries: BOTH answered and stamped on the SAME target -----
    epic = await client.create_bead(
        BeadDefinition(
            title=f"Integration epic scenario 2 ({_OWNER_SPEC})",
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": _OWNER_SPEC})

    source1 = await client.create_bead(
        BeadDefinition(
            title="Implement the first thing",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        ),
        parent_id=epic.bd_id,
    )
    payload1 = AssumptionPayload(
        question=f"{_ENTRY_ONE_MARKER}: Should retries be scoped per bead or per run?",
        adopted_answer="Per bead — matches existing scoping.",
        alternatives=("Per run",),
        severity="medium",
    )
    record1 = await record_assumption(
        client, payload=payload1, source_bead_id=source1.bd_id, epic_id=epic.bd_id
    )
    assert record1 is not None
    stamp_result1 = await stamp_change_id(
        client, entry_ids=[record1.bead_id], change_id=target_change_id
    )
    assert stamp_result1.stamped == (record1.bead_id,)
    await answer(
        client, bead_id=record1.bead_id, answer_text="Per run — matches the new usage pattern."
    )

    source2 = await client.create_bead(
        BeadDefinition(
            title="Implement the second thing",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        ),
        parent_id=epic.bd_id,
    )
    payload2 = AssumptionPayload(
        question=f"{_ENTRY_TWO_MARKER}: Should the default value be safe or unsafe?",
        adopted_answer="Safe by default.",
        alternatives=("Unsafe by default",),
        severity="medium",
    )
    record2 = await record_assumption(
        client, payload=payload2, source_bead_id=source2.bd_id, epic_id=epic.bd_id
    )
    assert record2 is not None
    stamp_result2 = await stamp_change_id(
        client, entry_ids=[record2.bead_id], change_id=target_change_id
    )
    assert stamp_result2.stamped == (record2.bead_id,)
    await answer(
        client, bead_id=record2.bead_id, answer_text="Unsafe by default — sabotage the gate."
    )

    # bd's own writes dirty the jj working copy (see Scenario 1 fixture
    # comment) — fold them into a fresh empty working-copy commit before
    # running reconcile (FR-014 clean-@ precondition).
    await jj_client.new()
    working_copy_stat = await jj_client.diff_stat(revision="@")
    assert working_copy_stat.files_changed == 0, "fixture setup must leave a clean @ (FR-014)"

    # --- Pre-answer-2 snapshot: entry 1's correction only ever touches
    # a.py, so b.py's pristine committed state IS "the state right before
    # entry 2's own processing begins" (research R8's per-answer restore
    # point) regardless of entry 1 having already landed its own fold into
    # the same target commit ----------------------------------------------
    pre_b_content = (repo / "b.py").read_text(encoding="utf-8")

    # --- Config: stub agent bindings + a REAL, sabotage-detecting gate ----
    config = _scenario2_config()
    constructed = _stub_scenario2_runtime_factory(monkeypatch, repo=repo)

    # --- Run 1: reconcile both changed answers -----------------------------
    workflow = ReconcileWorkflow(config=config)
    events = [
        event
        async for event in workflow.execute(
            {"run_id": "test-run-scenario2-a", "cwd": str(repo), "dry_run": False}
        )
    ]
    assert workflow.result is not None
    # The RUN itself completes (one answer failing doesn't crash the run);
    # only the per-answer outcomes carry the failure.
    assert workflow.result.success is True, [
        getattr(e, "error", None) for e in events if hasattr(e, "error")
    ]

    report = workflow.result.final_output
    assert report is not None
    outcomes_by_entry = {o["entry_id"]: o for o in report["outcomes"]}
    assert len(outcomes_by_entry) == 2

    # --- Assertion 1: the sabotaged answer needs interactive review -------
    outcome2 = outcomes_by_entry[record2.bead_id]
    assert outcome2["status"] == "needs_interactive_review"
    assert outcome2["gate_passed"] is False
    assert "test" in outcome2["reason"].lower() or "gate" in outcome2["reason"].lower(), outcome2[
        "reason"
    ]

    # --- Assertion 2: b.py's content is byte-identical to pre-answer ------
    post_b_content = (repo / "b.py").read_text(encoding="utf-8")
    assert post_b_content == pre_b_content, "rollback must restore b.py byte-for-byte"
    assert _UNSAFE_MARKER not in post_b_content

    target_diff_after = (await jj_client.diff(revision=target_change_id)).output
    assert _UNSAFE_MARKER not in target_diff_after, (
        "rollback must leave the target's own diff free of the sabotaged value"
    )

    # --- Assertion 3: the successful answer's correction stays applied ---
    outcome1 = outcomes_by_entry[record1.bead_id]
    assert outcome1["status"] == "reconciled"
    assert outcome1["gate_passed"] is True

    assert SENTINEL_LINE.strip() in target_diff_after, (
        "entry 1's correction must remain folded into the target despite entry 2's rollback"
    )

    entry1_details = await client.show(record1.bead_id)
    assert entry1_details.state[KEY_RECONCILE_STATUS] == "reconciled"

    # The tip lands on a fresh, empty, description-less working copy
    # (research R13) -- no leftover fixup change from entry 2's aborted,
    # rolled-back attempt.
    final_log = await jj_client.log(revset="@", limit=1)
    assert final_log.changes[0].empty is True
    assert final_log.changes[0].description == ""

    # The correction agent was actually invoked for both entries, and both
    # also reach the semantic-dependents pass (T030, unconditionally wired
    # in between conflicts and the gate) before entry 2's gate failure --
    # 2 correction calls + 2 semantic-analyze calls (one of each per entry).
    assert len(constructed) >= 1
    assert sum(len(runtime.execute_calls) for runtime in constructed) == 4

    # --- Assertion 4: bd state for the failed entry -----------------------
    entry2_details = await client.show(record2.bead_id)
    assert entry2_details.state[KEY_RECONCILE_STATUS] == RECONCILE_STATUS_NEEDS_REVIEW
    assert entry2_details.state.get(KEY_RECONCILE_REASON, "")

    # --- Assertion 5: re-answering re-arms detection (FR-017) -------------
    await answer(
        client,
        bead_id=record2.bead_id,
        answer_text="Unsafe by default — sabotage the gate, take two.",
    )
    entry2_rearmed = await client.show(record2.bead_id)
    # bd rejects an empty state value, so the re-arm overwrites the terminal
    # marker with the non-terminal ``pending`` sentinel rather than clearing
    # it. What matters for FR-017 is that the status is no longer TERMINAL, so
    # detection stops excluding the entry (proven end-to-end below by the
    # re-armed entry reappearing in run 3's outcomes).
    rearmed_status = entry2_rearmed.state.get(KEY_RECONCILE_STATUS, "")
    assert rearmed_status not in TERMINAL_RECONCILE_STATUSES, (
        "re-answering must re-arm assumption_reconcile_status (FR-017): a "
        f"terminal status still excludes detection, got {rearmed_status!r}"
    )

    # bd's re-answer writes dirty @ again — clean before the next run.
    await jj_client.new()
    working_copy_stat_2 = await jj_client.diff_stat(revision="@")
    assert working_copy_stat_2.files_changed == 0

    workflow3 = ReconcileWorkflow(config=config)
    async for _event in workflow3.execute(
        {"run_id": "test-run-scenario2-b", "cwd": str(repo), "dry_run": False}
    ):
        pass
    assert workflow3.result is not None
    report3 = workflow3.result.final_output
    assert report3 is not None
    outcome_ids_run3 = {o["entry_id"] for o in report3["outcomes"]}
    assert record2.bead_id in outcome_ids_run3, (
        "re-armed entry must reappear in the next run's detection/outcomes"
    )


# ---------------------------------------------------------------------------
# Scenario 3 (US3) fixtures — descendant B edits the SAME line the
# correction will change in ``a.py``. Folding the correction into A (via
# ``jj squash --into``) auto-rebases B; since B's own edit and the
# correction both change the same line relative to A's original content, jj
# genuinely conflicts B during that rebase (confirmed against jj 0.43 — a
# real two-sided merge conflict, not a contrived one). This is exactly what
# ``resolve_conflicts`` (T026, ``workflows/reconcile/conflicts.py``) and the
# now-wired-in semantic-dependents pass (T030) exercise together in one
# real run. See ``test_scenario_3_conflict_resolved_within_budget`` and
# ``test_scenario_3_budget_exhaustion`` below.
#
# This relies on the SAME ``resolve_target_against_current_stack`` fix
# documented in this module's docstring (bug note #3, now fixed to use
# revset ``"all()"`` instead of ``"::@"``) — but note both Scenario 3 tests
# below have only ONE changed answer, so the T032/T033 re-resolution path
# (only exercised for the *second+* answer in a batch) never runs here; what
# they exercise instead is the auto-rebase-produces-a-real-conflict path
# that Scenario 2's shared-target workaround was forced to sidestep.
# ---------------------------------------------------------------------------

#: Original content of ``a.py`` at target A — both the correction below and
#: B's own edit change line 2 of this content, producing a genuine
#: two-sided rebase conflict once B is auto-rebased onto the corrected A.
_SCENARIO3_ORIGINAL_CONTENT = "def scope():\n    return 'per-bead'\n"
#: B's own descendant edit — changes the SAME line the correction changes.
_SCENARIO3_B_CONTENT = "def scope():\n    return 'per-run-B-edit'\n"
#: The corrected value the fake reconciler folds into A, and (in the
#: within-budget test) also what the fake conflict-resolution call
#: re-asserts when resolving the conflict — the new human answer wins over
#: B's now-stale edit.
_SCENARIO3_CORRECTED_CONTENT = "def scope():\n    return 'reconciled-value'\n"


class _Scenario3ReconcilerRuntime:
    """Fake airframe runtime for Scenario 3: correction, conflict-resolution,
    AND semantic-analysis calls all arrive on this one stub, disambiguated
    purely by inspecting the prompt text — the same technique
    ``_Scenario2CorrectionRuntime`` uses to tell apart two correction calls
    in one run, extended here to tell apart three different *kinds* of
    call in one run:

    * ``## Mode: Correction`` — ``ReconcilerAgent._build_correct_prompt``
      (``agents/reconciler.py``) always emits this heading.
    * ``## Mode: Conflict Resolution`` — ``ReconcilerAgent.
      _build_resolve_conflicts_prompt`` always emits this heading instead.
    * Neither marker present — this is the semantic-dependents pass'
      ``analyze`` call (``agents/semantic_reviewer.py``'s
      ``_build_analyze_prompt``), which carries no ``## Mode:`` heading at
      all (T030 wired ``run_semantic_pass`` unconditionally between the
      conflicts stage and the gate, so every Scenario 3 run that reaches
      the gate makes at least one of these calls too). Declaring every
      supplied descendant non-dependent (``findings=()``) lets the pass
      complete in a single round with zero follow-up corrections, keeping
      this test focused on conflict resolution rather than the (separately
      tested) semantic-dependents mechanism.
    """

    label = "stub"

    def __init__(
        self,
        *,
        model: str | None = None,
        repo: Path | None = None,
        unresolvable: bool = False,
        **kwargs: object,
    ) -> None:
        self.model = model
        self._repo = repo
        self._unresolvable = unresolvable
        self.execute_calls: list[dict[str, object]] = []

    async def execute(self, prompt: str, **kwargs: object) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        assert self._repo is not None

        if "## Mode: Correction" in prompt:
            (self._repo / "a.py").write_text(_SCENARIO3_CORRECTED_CONTENT, encoding="utf-8")
            structured: dict[str, object] = {
                "summary": "Corrected scoping to match the new human answer.",
                "files_touched": ["a.py"],
                "no_change_required": False,
            }
            return RuntimeResult(
                text="", structured=structured, cost=_make_cost(), finish="end_turn"
            )

        if "## Mode: Conflict Resolution" in prompt:
            if self._unresolvable:
                structured = {
                    "resolved_files": [],
                    "unresolvable": ["a.py"],
                    "notes": "cannot safely merge within the round budget",
                }
            else:
                # Write clean, marker-free content that keeps the
                # CORRECTED value (the new human answer wins over B's
                # stale edit) — exactly what the round-budgeted loop in
                # ``conflicts.py`` expects: it reads whatever is on disk
                # after this call and squashes it into the conflicted
                # change.
                (self._repo / "a.py").write_text(_SCENARIO3_CORRECTED_CONTENT, encoding="utf-8")
                structured = {
                    "resolved_files": ["a.py"],
                    "unresolvable": [],
                    "notes": "kept the corrected value over the stale descendant edit",
                }
            return RuntimeResult(
                text="", structured=structured, cost=_make_cost(), finish="end_turn"
            )

        # Neither ``## Mode:`` marker: the semantic-dependents pass'
        # analyze call. Declare every supplied descendant non-dependent so
        # the pass completes in one round with zero follow-up corrections
        # (an empty ``findings`` tuple means every supplied change_id is
        # "missing" from the response, which ``run_semantic_pass`` treats
        # as ``dependent=False`` per its own contract).
        structured = {"findings": []}
        return RuntimeResult(text="", structured=structured, cost=_make_cost(), finish="end_turn")

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: object) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _StubSession:
        return _StubSession(self, **kwargs)


def _stub_scenario3_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo: Path,
    unresolvable: bool = False,
) -> list[_Scenario3ReconcilerRuntime]:
    """Same patch point as Scenario 1/2, bound to ``_Scenario3ReconcilerRuntime``."""
    constructed: list[_Scenario3ReconcilerRuntime] = []

    def _factory(provider_id: str) -> type[_Scenario3ReconcilerRuntime]:
        class _Bound(_Scenario3ReconcilerRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: object) -> None:
                super().__init__(model=model, repo=repo, unresolvable=unresolvable, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


async def _build_scenario3_stack(jj_client: JjClient, repo: Path) -> tuple[str, str]:
    """Build ``base <- A <- B`` where B edits the same line A's correction
    will touch — the genuine rebase-conflict setup both Scenario 3 tests
    share. Returns ``(a_change_id, b_change_id)``, both FULL ids (see
    ``_write_and_commit``).
    """
    await _write_and_commit(jj_client, repo, "base.py", "# base\n")
    a_change_id = await _write_and_commit(jj_client, repo, "a.py", _SCENARIO3_ORIGINAL_CONTENT)
    b_change_id = await _write_and_commit(jj_client, repo, "a.py", _SCENARIO3_B_CONTENT)
    return a_change_id, b_change_id


async def _record_scenario3_answer(
    client: BeadClient, *, epic_title: str, source_title: str, a_change_id: str
) -> AssumptionRecord:
    """Create + stamp + answer one ledger entry targeting *a_change_id*.

    Shared setup for both Scenario 3 tests — differs only in the exact
    beads created (each test uses its own epic/source titles so bd query
    results never conflate the two runs sharing a filter by owner spec).
    """
    epic = await client.create_bead(
        BeadDefinition(
            title=epic_title,
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": _OWNER_SPEC})
    source = await client.create_bead(
        BeadDefinition(
            title=source_title,
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        ),
        parent_id=epic.bd_id,
    )
    payload = AssumptionPayload(
        question="Should retries be scoped per bead or per run?",
        adopted_answer="Per bead — matches existing scoping.",
        alternatives=("Per run",),
        severity="medium",
    )
    record = await record_assumption(
        client, payload=payload, source_bead_id=source.bd_id, epic_id=epic.bd_id
    )
    assert record is not None
    stamp_result = await stamp_change_id(client, entry_ids=[record.bead_id], change_id=a_change_id)
    assert stamp_result.stamped == (record.bead_id,)
    await answer(
        client, bead_id=record.bead_id, answer_text="Per run — matches the new usage pattern."
    )
    return record


@pytest.mark.asyncio
async def test_scenario_3_conflict_resolved_within_budget(
    reconcile_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quickstart.md Scenario 3 (US3) — conflict resolved within budget.

    Builds ``base <- A <- B`` where B edits the same line the correction
    changes in ``a.py``. Folding the correction into A auto-rebases B,
    producing a genuine two-sided merge conflict on that line (see the
    fixture section's docstring above). The stubbed conflict-resolution
    call — disambiguated from the correction call via the
    ``## Mode: Conflict Resolution`` marker ``ReconcilerAgent.
    _build_resolve_conflicts_prompt`` emits — resolves it in favor of the
    corrected value, well within the default 3-round budget
    (``ReconcileConfig.resolution_rounds``). Asserts the answer reconciles,
    ``conflicts()`` is empty repo-wide afterwards, B's resolved content
    reflects the corrected merge, and the run succeeds end to end
    (including the now-wired-in semantic-dependents pass, T030, which this
    stub also answers trivially).
    """
    _install_bd_compat_shims(monkeypatch)

    repo = reconcile_repo
    jj_client = JjClient(cwd=repo)
    client = BeadClient(cwd=repo)

    a_change_id, b_change_id = await _build_scenario3_stack(jj_client, repo)
    record = await _record_scenario3_answer(
        client,
        epic_title=f"Integration epic scenario 3a ({_OWNER_SPEC})",
        source_title="Implement the scoped thing",
        a_change_id=a_change_id,
    )

    # bd's own writes dirty the jj working copy (see Scenario 1 fixture
    # comment) — fold them into a fresh empty working-copy commit before
    # running reconcile (FR-014 clean-@ precondition).
    await jj_client.new()
    working_copy_stat = await jj_client.diff_stat(revision="@")
    assert working_copy_stat.files_changed == 0, "fixture setup must leave a clean @ (FR-014)"

    config = _reconcile_config(format_cmd=[sys.executable, "-c", "pass"])
    constructed = _stub_scenario3_runtime_factory(monkeypatch, repo=repo, unresolvable=False)

    workflow = ReconcileWorkflow(config=config)
    events = [
        event
        async for event in workflow.execute(
            {"run_id": "test-run-scenario3-a", "cwd": str(repo), "dry_run": False}
        )
    ]
    assert workflow.result is not None
    assert workflow.result.success is True, [
        getattr(e, "error", None) for e in events if hasattr(e, "error")
    ]

    report = workflow.result.final_output
    assert report is not None
    outcomes = report["outcomes"]
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["entry_id"] == record.bead_id
    assert outcome["status"] == "reconciled"
    assert outcome["target_change_id"] == a_change_id
    assert outcome["gate_passed"] is True

    # The correction call, at least one conflict-resolution call, and at
    # least one semantic-analyze call all actually ran (not skipped).
    assert sum(len(runtime.execute_calls) for runtime in constructed) >= 3

    # --- Assertion: no conflicts remain anywhere in the repo ---------------
    conflicts_log = await jj_client.log(revset="conflicts()", limit=100)
    assert conflicts_log.changes == (), "conflicts() must be empty after resolution"

    # --- Assertion: B's resolved content reflects the corrected merge -----
    assert (repo / "a.py").read_text(encoding="utf-8") == _SCENARIO3_CORRECTED_CONTENT

    # --- Assertion: ledger entry state is reconciled -----------------------
    entry_details = await client.show(record.bead_id)
    assert entry_details.state[KEY_RECONCILE_STATUS] == "reconciled"
    assert entry_details.state[KEY_RECONCILE_CHANGE_ID]

    # --- Assertion: B is still present (rebased + resolved, not orphaned) -
    final_log = await jj_client.log(revset="all()", limit=200)
    final_short_ids = {c.change_id for c in final_log.changes}
    assert any(b_change_id.startswith(short_id) for short_id in final_short_ids)


@pytest.mark.asyncio
async def test_scenario_3_budget_exhaustion(
    reconcile_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quickstart.md Scenario 3 — budget exhaustion variant.

    Same conflicting ``base <- A <- B`` stack as
    ``test_scenario_3_conflict_resolved_within_budget``, but
    ``reconcile.resolution_rounds=1`` and the stubbed conflict-resolution
    call declares the conflicted file ``unresolvable`` — contract:
    a non-empty ``unresolvable`` list is budget-terminating
    (``conflicts.py``'s ``resolve_conflicts`` docstring point 4), so the
    round loop stops on its first (and only) round rather than spending
    more rounds it doesn't have. Asserts the answer terminal-marks
    ``needs_interactive_review`` with a real escalation bead
    (data-model.md §6, ``kind="conflicts"``) carrying the expected
    labels/description/state, that the repo's affected file and the
    target's own diff are rolled back byte-identical to their
    pre-answer-processing state (same rollback-verification technique
    Scenario 2 uses), and that the RUN itself still succeeds — only the
    answer failed, per data-model.md §2 / research R8.
    """
    _install_bd_compat_shims(monkeypatch)

    repo = reconcile_repo
    jj_client = JjClient(cwd=repo)
    client = BeadClient(cwd=repo)

    a_change_id, b_change_id = await _build_scenario3_stack(jj_client, repo)
    record = await _record_scenario3_answer(
        client,
        epic_title=f"Integration epic scenario 3b ({_OWNER_SPEC})",
        source_title="Implement the scoped thing, take two",
        a_change_id=a_change_id,
    )

    await jj_client.new()
    working_copy_stat = await jj_client.diff_stat(revision="@")
    assert working_copy_stat.files_changed == 0, "fixture setup must leave a clean @ (FR-014)"

    # --- Pre-answer-processing snapshot (rollback verification target) ----
    pre_a_content = (repo / "a.py").read_text(encoding="utf-8")
    pre_b_diff = (await jj_client.diff(revision=b_change_id)).output

    config = _reconcile_config(format_cmd=[sys.executable, "-c", "pass"]).model_copy(
        update={"reconcile": ReconcileConfig(resolution_rounds=1)}
    )
    constructed = _stub_scenario3_runtime_factory(monkeypatch, repo=repo, unresolvable=True)

    workflow = ReconcileWorkflow(config=config)
    events = [
        event
        async for event in workflow.execute(
            {"run_id": "test-run-scenario3-b", "cwd": str(repo), "dry_run": False}
        )
    ]
    assert workflow.result is not None
    # The RUN itself completes (the answer failing doesn't crash the run);
    # only the per-answer outcome carries the failure.
    assert workflow.result.success is True, [
        getattr(e, "error", None) for e in events if hasattr(e, "error")
    ]

    report = workflow.result.final_output
    assert report is not None
    outcomes = report["outcomes"]
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["entry_id"] == record.bead_id
    assert outcome["status"] == "needs_interactive_review"

    # Only the correction call and exactly one conflict-resolution call
    # ran — the round-1 budget stops the loop immediately on the
    # agent-declared ``unresolvable`` result, and a failed answer never
    # reaches the semantic-dependents pass (T030 runs strictly after
    # ``CONFLICTS_RESOLVED``, which this answer never reaches).
    assert sum(len(runtime.execute_calls) for runtime in constructed) == 2

    # --- Assertion: a real escalation bead was created ---------------------
    escalation_bead_id = outcome["escalation_bead_id"]
    assert escalation_bead_id is not None

    escalation_details = await client.show(escalation_bead_id)
    assert "assumption-review" in escalation_details.labels
    assert "needs-human-review" in escalation_details.labels
    assert "## Remaining Conflicts" in escalation_details.description
    assert escalation_details.state.get("escalation_type") == "reconcile_exhaustion"

    # --- Assertion: rollback restored the repo byte-for-byte ---------------
    post_a_content = (repo / "a.py").read_text(encoding="utf-8")
    assert post_a_content == pre_a_content, "rollback must restore a.py byte-for-byte"
    assert _SCENARIO3_CORRECTED_CONTENT.strip() not in post_a_content

    post_b_diff = (await jj_client.diff(revision=b_change_id)).output
    assert post_b_diff == pre_b_diff, "rollback must leave B's own diff untouched"

    conflicts_log = await jj_client.log(revset="conflicts()", limit=100)
    assert conflicts_log.changes == (), "rollback must leave no conflicts anywhere in the repo"

    entry_details = await client.show(record.bead_id)
    assert entry_details.state[KEY_RECONCILE_STATUS] == RECONCILE_STATUS_NEEDS_REVIEW
    assert entry_details.state.get(KEY_RECONCILE_REASON, "")


# ---------------------------------------------------------------------------
# Scenario 4 (US4, SC-007) fixtures — descendant ``C`` hard-codes a value
# derived from the old assumption in ``c.py``, a file the correction itself
# never touches (the correction only touches ``a.py``); descendant ``B`` is
# unrelated (touches its own file, ``b.py``, with content that has nothing to
# do with either answer). Since the correction and C's derived value live in
# different files, folding the correction into A never produces a rebase
# conflict on C — the semantic-dependents pass (T030, ``workflows/reconcile/
# semantic.py``) is what has to catch and fix C's staleness; B must be left
# byte-identical (the core SC-007 assertion). See
# ``test_scenario_4_semantic_dependent_fixed_in_introducing_descendant``.
# ---------------------------------------------------------------------------

#: B's own descendant content — unrelated to both the old and new answer.
_SCENARIO4_B_CONTENT = "GREETING = 'hello from b'\n"
#: C's original content — hard-codes a value derived from the OLD (per-bead)
#: assumption, in a file the correction never touches. The literal
#: ``"DERIVED_TIMEOUT = 30"`` substring is this fixture's "stale" marker: the
#: fake semantic-analyze stub below flags any descendant whose diff still
#: contains it, and the fake fix-application stub removes it.
_SCENARIO4_C_ORIGINAL_CONTENT = (
    "DERIVED_TIMEOUT = 30  # derived from the old per-bead scoping assumption\n"
)
#: The value the fake semantic-fix-application correction writes once the
#: pass flags ``C`` as dependent — no longer contains the stale marker above,
#: so a follow-up analyze round (``semantic.py``'s verification round) sees
#: it as no longer dependent and the pass completes.
_SCENARIO4_C_FIXED_CONTENT = (
    "DERIVED_TIMEOUT = 3600  # updated to match the new per-run scoping answer\n"
)
#: The stale-value marker the fake analyze stub keys off of (see above).
_SCENARIO4_STALE_MARKER = "DERIVED_TIMEOUT = 30"


class _Scenario4ReconcilerRuntime:
    """Fake airframe runtime for Scenario 4: correction, semantic-fix-
    application (itself another ``## Mode: Correction`` call, per
    ``semantic.py``'s ``_apply_fix``, which reuses ``apply_correction``
    unchanged), and semantic-analyze calls all arrive on this one stub.

    Disambiguation, extending Scenario 3's prompt-marker technique:

    * ``## Mode: Conflict Resolution`` — never expected in this scenario
      (B/C touch different files than the correction; no rebase conflict is
      possible here), so an occurrence is a test bug, not a scenario input.
    * ``## Mode: Correction`` — both the ORIGINAL correction (targeting A)
      and the semantic pass's FIX-APPLICATION correction (targeting C, via
      ``semantic.py``'s ``_apply_fix`` -> ``apply_correction`` -> the
      identical ``ReconcilerAgent.correct`` code path) share this marker.
      They are told apart by inspecting the embedded ``### Target Diff``
      section instead: ``apply_correction`` always captures
      ``jj_diff(revision=target)`` *before* calling ``correct`` (see
      ``correction.py``), so the ORIGINAL call's target diff is A's own
      diff (touches only ``a.py``) while the FIX-APPLICATION call's target
      diff is C's own diff (touches only ``c.py``) — checking for the
      literal ``"c.py"`` substring in the prompt is a robust, content-based
      way to tell them apart that does not depend on call ordering/count.
    * ``## Correction Diff`` — present only in
      ``SemanticDependentsAgent._build_analyze_prompt`` (the correction/
      conflict-resolution prompts use ``### Target Diff``/``### Conflicted
      Files`` instead), so this is used as a *positive*, specific marker for
      the semantic-analyze call rather than falling back to "neither other
      marker matched" (Scenario 1-3's technique, fine there since those
      stubs give a trivial always-empty response; this scenario needs a
      real per-descendant judgement, so a wrong classification here would
      silently corrupt the fixture rather than just skip fix wiring).

    The analyze call itself parses each ``## Descendant <change_id>``
    section straight out of the prompt (real change ids are dynamic per
    test run, never hardcoded) and flags a descendant dependent iff its
    diff still contains the stale-value marker — true for C in round 1,
    false for both B (never contained it) and C in the verification round
    that follows the fix (the fixed value no longer contains it), so the
    pass completes in exactly 2 rounds without looping.
    """

    label = "stub"

    def __init__(
        self, *, model: str | None = None, repo: Path | None = None, **kwargs: object
    ) -> None:
        self.model = model
        self._repo = repo
        self.execute_calls: list[dict[str, object]] = []

    async def execute(self, prompt: str, **kwargs: object) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        assert self._repo is not None

        if "## Mode: Conflict Resolution" in prompt:
            raise AssertionError(
                "Scenario 4's stack never produces a rebase conflict (the "
                "correction only touches a.py; B/C touch distinct files); "
                f"unexpected conflict-resolution prompt: {prompt[:200]!r}"
            )

        if "## Mode: Correction" in prompt:
            structured: dict[str, object]
            if "c.py" in prompt:
                # Semantic-fix-application call, targeting C.
                (self._repo / "c.py").write_text(_SCENARIO4_C_FIXED_CONTENT, encoding="utf-8")
                structured = {
                    "summary": "Updated DERIVED_TIMEOUT to match the new per-run answer.",
                    "files_touched": ["c.py"],
                    "no_change_required": False,
                }
            else:
                # Original correction call, targeting A.
                target_path = self._repo / "a.py"
                existing = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
                target_path.write_text(existing + SENTINEL_LINE, encoding="utf-8")
                structured = {
                    "summary": "Corrected scoping to match the new human answer.",
                    "files_touched": ["a.py"],
                    "no_change_required": False,
                }
            return RuntimeResult(
                text="", structured=structured, cost=_make_cost(), finish="end_turn"
            )

        assert "## Correction Diff" in prompt, (
            f"expected the semantic-analyze prompt shape, got: {prompt[:200]!r}"
        )
        findings: list[dict[str, object]] = []
        for change_id, diff_text in re.findall(
            r"## Descendant (\S+)\n\n```diff\n(.*?)\n```", prompt, re.DOTALL
        ):
            if _SCENARIO4_STALE_MARKER in diff_text:
                findings.append(
                    {
                        "change_id": change_id,
                        "dependent": True,
                        "reason": (
                            "hard-codes DERIVED_TIMEOUT, a value derived from the "
                            "old per-bead scoping assumption"
                        ),
                        "fix_instructions": "update DERIVED_TIMEOUT to reflect the new answer",
                    }
                )
            else:
                findings.append(
                    {
                        "change_id": change_id,
                        "dependent": False,
                        "reason": "",
                        "fix_instructions": "",
                    }
                )
        return RuntimeResult(
            text="",
            structured={"findings": findings},
            cost=_make_cost(),
            finish="end_turn",
        )

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: object) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _StubSession:
        return _StubSession(self, **kwargs)


def _stub_scenario4_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo: Path,
) -> list[_Scenario4ReconcilerRuntime]:
    """Same patch point as Scenario 1/2/3, bound to ``_Scenario4ReconcilerRuntime``."""
    constructed: list[_Scenario4ReconcilerRuntime] = []

    def _factory(provider_id: str) -> type[_Scenario4ReconcilerRuntime]:
        class _Bound(_Scenario4ReconcilerRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: object) -> None:
                super().__init__(model=model, repo=repo, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


@pytest.mark.asyncio
async def test_scenario_4_semantic_dependent_fixed_in_introducing_descendant(
    reconcile_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quickstart.md Scenario 4 (US4, SC-007) — semantic dependents.

    Builds ``base <- A <- B <- C`` where A is the ledger-stamped correction
    target (touches ``a.py``), B is an unrelated descendant (touches its own
    ``b.py``), and C hard-codes a value derived from the OLD assumption in a
    separate file (``c.py``) the correction never touches — so folding the
    correction into A never produces a rebase conflict (different files
    entirely), and the only thing that can catch C's staleness is the
    semantic-dependents pass (T030/research R6). Asserts the pass flags C
    (not B), applies a fix to C via the reused correction mechanism, B stays
    byte-identical (the core SC-007 assertion — unrelated descendants must
    never be touched), the answer reconciles, and the run succeeds
    end-to-end.
    """
    _install_bd_compat_shims(monkeypatch)

    repo = reconcile_repo
    jj_client = JjClient(cwd=repo)
    client = BeadClient(cwd=repo)

    # --- Build the jj stack: base <- A <- B <- C ---------------------------
    await _write_and_commit(jj_client, repo, "base.py", "# base\n")
    a_change_id = await _write_and_commit(
        jj_client, repo, "a.py", "def scope():\n    return 'per-bead'\n"
    )
    b_change_id = await _write_and_commit(jj_client, repo, "b.py", _SCENARIO4_B_CONTENT)
    c_change_id = await _write_and_commit(jj_client, repo, "c.py", _SCENARIO4_C_ORIGINAL_CONTENT)

    # --- Ledger entry: answered, stamped on A, human answer differs -------
    epic = await client.create_bead(
        BeadDefinition(
            title=f"Integration epic scenario 4 ({_OWNER_SPEC})",
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": _OWNER_SPEC})
    source = await client.create_bead(
        BeadDefinition(
            title="Implement the derived-value thing",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        ),
        parent_id=epic.bd_id,
    )

    payload = AssumptionPayload(
        question="Should retries be scoped per bead or per run?",
        adopted_answer="Per bead — matches existing scoping.",
        alternatives=("Per run",),
        severity="medium",
    )
    record = await record_assumption(
        client, payload=payload, source_bead_id=source.bd_id, epic_id=epic.bd_id
    )
    assert record is not None

    stamp_result = await stamp_change_id(client, entry_ids=[record.bead_id], change_id=a_change_id)
    assert stamp_result.stamped == (record.bead_id,)

    await answer(
        client, bead_id=record.bead_id, answer_text="Per run — matches the new usage pattern."
    )

    # bd's own writes dirty the jj working copy (see Scenario 1 fixture
    # comment) — fold them into a fresh empty working-copy commit before
    # running reconcile (FR-014 clean-@ precondition).
    await jj_client.new()
    working_copy_stat = await jj_client.diff_stat(revision="@")
    assert working_copy_stat.files_changed == 0, "fixture setup must leave a clean @ (FR-014)"

    config = _reconcile_config(format_cmd=[sys.executable, "-c", "pass"])
    constructed = _stub_scenario4_runtime_factory(monkeypatch, repo=repo)

    workflow = ReconcileWorkflow(config=config)
    events = [
        event
        async for event in workflow.execute(
            {"run_id": "test-run-scenario4", "cwd": str(repo), "dry_run": False}
        )
    ]
    assert workflow.result is not None
    assert workflow.result.success is True, [
        getattr(e, "error", None) for e in events if hasattr(e, "error")
    ]

    report = workflow.result.final_output
    assert report is not None
    outcomes = report["outcomes"]
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["entry_id"] == record.bead_id
    assert outcome["status"] == "reconciled"
    assert outcome["target_change_id"] == a_change_id
    assert outcome["gate_passed"] is True

    # Exactly 4 calls: the primary correction, the round-1 analyze call
    # (both B and C), the fix-application correction on C, and the round-2
    # analyze call that re-verifies C alone and finds it no longer stale.
    assert sum(len(runtime.execute_calls) for runtime in constructed) == 4

    # --- Assertion: A's diff contains the primary correction ---------------
    a_diff = await jj_client.diff(revision=a_change_id)
    assert SENTINEL_LINE.strip() in a_diff.output

    # --- Assertion (SC-007 core): C's diff reflects the FIXED value -------
    c_diff = await jj_client.diff(revision=c_change_id)
    assert _SCENARIO4_C_FIXED_CONTENT.strip() in c_diff.output
    assert (repo / "c.py").read_text(encoding="utf-8") == _SCENARIO4_C_FIXED_CONTENT

    # --- Assertion (SC-007 core): B is byte-identical, never touched ------
    assert (repo / "b.py").read_text(encoding="utf-8") == _SCENARIO4_B_CONTENT
    b_diff = await jj_client.diff(revision=b_change_id)
    assert _SCENARIO4_STALE_MARKER not in b_diff.output
    assert _SCENARIO4_C_FIXED_CONTENT.strip() not in b_diff.output

    # --- Assertion: ledger entry state is reconciled -----------------------
    entry_details = await client.show(record.bead_id)
    assert entry_details.state[KEY_RECONCILE_STATUS] == "reconciled"
    assert entry_details.state[KEY_RECONCILE_CHANGE_ID]

    # --- Assertion: B/C are still connected (rebased, not orphaned) --------
    final_log = await jj_client.log(revset="all()", limit=200)
    final_short_ids = {change.change_id for change in final_log.changes}
    assert any(b_change_id.startswith(short_id) for short_id in final_short_ids)
    assert any(c_change_id.startswith(short_id) for short_id in final_short_ids)


# ---------------------------------------------------------------------------
# Scenario 5 (US5, SC-003/SC-005) fixtures — batch ordering + immutability
# bounds. Builds ``base <- Z <- X <- Y`` with THREE ledger entries stamped on
# Z/X/Y respectively (three different stack depths). Z is made immutable by
# setting the repo's own ``revset-aliases."immutable_heads()"`` jj config to
# ``"<Z's full change id> | trunk()"`` — verified empirically against jj
# 0.43.0 in a throwaway sandbox before writing this test:
#
#   jj config set --repo 'revset-aliases."immutable_heads()"' \
#       '<change_id> | trunk()'
#
# writes to a PER-USER, PER-REPO config file (``jj config path --repo``
# reports something like
# ``~/.config/jj/repos/<repo-id-hash>/config.toml``) — NOT
# ``.jj/repo/config.toml`` inside the checkout itself, despite the CLAUDE.md/
# research.md prose suggesting the latter. This matters for test isolation:
# the config lives *outside* ``tmp_path`` and is keyed by an internal repo
# id, so it is never cleaned up by pytest's ``tmp_path`` teardown, but a
# fresh ``tmp_path`` repo per test run gets a fresh repo id and therefore a
# fresh config file — no cross-test collision, just an accumulating (mostly
# harmless) directory in the sandbox's ``$HOME`` across many runs. Confirmed
# via sandbox that ``jj log -r 'immutable()'`` then reports exactly Z (and
# ``root()``/``trunk()``'s own ancestors) as immutable, while X and Y (both
# descendants of Z) remain in ``mutable()`` — matching
# ``jj_check_mutability``'s revset
# ``(::target & immutable() & target) | (descendants(target) & immutable())``:
# Z's own check trips (Z itself is immutable), X's and Y's checks don't
# (neither is immutable, nor is any of *their* descendants — immutability
# only propagates to Z's *ancestors*, i.e. ``base``, never to Z's
# *descendants*).
#
# X and Y touch disjoint files (``x.py``/``y.py``) with no other descendant
# touching either — by design, matching the task's framing that this
# scenario is about ordering/immutability, not conflict or semantic
# mechanics (already covered by Scenarios 3/4). Each ledger entry's question
# embeds a unique marker so the shared stub runtime (which serves BOTH the
# ``ReconcilerAgent`` correction calls AND the ``SemanticDependentsAgent``
# analyze calls — ``ReconcileSquadron`` builds one persistent runtime
# instance per agent for the whole run, same as every earlier scenario)
# can disambiguate calls purely by prompt content, the same technique
# Scenario 2/3/4 use.
# ---------------------------------------------------------------------------

#: Embedded in the X-targeted entry's question.
_SCENARIO5_X_MARKER = "ENTRY-X-CORRECTION"
#: Embedded in the Y-targeted entry's question.
_SCENARIO5_Y_MARKER = "ENTRY-Y-CORRECTION"


class _Scenario5ReconcilerRuntime:
    """Fake airframe runtime for Scenario 5: TWO correction calls (X, Y) plus
    whatever semantic-analyze calls naturally occur, all on one stub.

    Disambiguation (extending Scenario 2/3/4's prompt-marker technique):

    * ``## Mode: Conflict Resolution`` — never expected (X/Y touch disjoint
      files, and no other descendant touches either), so an occurrence is a
      test-setup bug, not a scenario input.
    * ``## Mode: Correction`` — told apart by the entry-specific marker
      embedded in the ledger question, which flows verbatim into the
      correction prompt's ``### Question`` section (same mechanism Scenario
      2 uses for its two correction calls). The immutable Z entry has NO
      marker defined here at all: the mutability guard (T034) must skip it
      before ``apply_correction`` is ever reached, so a correction prompt
      matching *neither* the X nor the Y marker would mean Z's target
      leaked past the guard — a genuine bug, not a stub gap — hence the
      ``AssertionError`` fallback below.
    * Neither marker present — the semantic-dependents pass' ``analyze``
      call (no ``## Mode:`` heading at all, T030). Declaring every supplied
      descendant non-dependent (``findings=[]``) lets each pass complete in
      one round with zero follow-up corrections, matching Scenario 1/2/3's
      simpler technique (Scenario 5 is about ordering/immutability, not
      semantic-dependents judgement).
    """

    label = "stub"

    def __init__(
        self, *, model: str | None = None, repo: Path | None = None, **kwargs: object
    ) -> None:
        self.model = model
        self._repo = repo
        self.execute_calls: list[dict[str, object]] = []

    async def execute(self, prompt: str, **kwargs: object) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        assert self._repo is not None

        if "## Mode: Conflict Resolution" in prompt:
            raise AssertionError(
                "Scenario 5's X/Y corrections touch disjoint files with no "
                "other descendant touching either; no rebase conflict is "
                f"possible here. Unexpected conflict-resolution prompt: {prompt[:200]!r}"
            )

        if "## Mode: Correction" in prompt:
            structured: dict[str, object]
            if _SCENARIO5_X_MARKER in prompt:
                target_path = self._repo / "x.py"
                existing = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
                target_path.write_text(existing + SENTINEL_LINE, encoding="utf-8")
                structured = {
                    "summary": "Corrected per the new human answer (X).",
                    "files_touched": ["x.py"],
                    "no_change_required": False,
                }
            elif _SCENARIO5_Y_MARKER in prompt:
                target_path = self._repo / "y.py"
                existing = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
                target_path.write_text(existing + SENTINEL_LINE, encoding="utf-8")
                structured = {
                    "summary": "Corrected per the new human answer (Y).",
                    "files_touched": ["y.py"],
                    "no_change_required": False,
                }
            else:
                # The immutable Z entry has no marker defined — reaching
                # here means its target leaked past the mutability guard
                # (T034), which must never happen (data-model.md §2:
                # "skipped" is a pre-mutation, pre-agent exit).
                raise AssertionError(
                    "correction prompt matched neither the X nor Y marker "
                    "-- the immutable Z entry must never reach the "
                    f"correction agent: {prompt[:200]!r}"
                )
            return RuntimeResult(
                text="", structured=structured, cost=_make_cost(), finish="end_turn"
            )

        # Neither ``## Mode:`` marker: the semantic-dependents pass' analyze
        # call. Declare every supplied descendant non-dependent so the pass
        # completes in one round with zero follow-up corrections.
        return RuntimeResult(
            text="",
            structured={"findings": []},
            cost=_make_cost(),
            finish="end_turn",
        )

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: object) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _StubSession:
        return _StubSession(self, **kwargs)


def _stub_scenario5_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo: Path,
) -> list[_Scenario5ReconcilerRuntime]:
    """Same patch point as Scenario 1/2/3/4, bound to ``_Scenario5ReconcilerRuntime``."""
    constructed: list[_Scenario5ReconcilerRuntime] = []

    def _factory(provider_id: str) -> type[_Scenario5ReconcilerRuntime]:
        class _Bound(_Scenario5ReconcilerRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: object) -> None:
                super().__init__(model=model, repo=repo, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


async def _record_scenario5_answer(
    client: BeadClient,
    *,
    epic_id: str,
    source_bead_id: str,
    change_id: str,
    marker: str,
) -> AssumptionRecord:
    """Create + stamp + answer one ledger entry targeting *change_id*.

    Shared setup for all three Scenario 5 entries (Z/X/Y) — each gets its
    own unique ``marker`` embedded in the question (for the stub's
    disambiguation, see ``_Scenario5ReconcilerRuntime``) and its own
    genuinely different human answer vs. adopted answer (the changed-answer
    detection precondition, research R1).

    Unlike Scenario 2/3/4 (which give each entry its own dedicated "source"
    task bead), all three Scenario 5 entries share ONE ``source_bead_id``
    (created once by the caller). ``record_assumption`` only ever stores
    ``source_bead_id`` as descriptive metadata and a ``discovered-from``
    edge target (never a uniqueness key — confirmed by reading
    ``ledger.py``: dedup keys strictly on ``epic_id`` + normalized
    question, and detection never reads it back), so sharing it is a safe,
    purely mechanical way to cut 2 of the ~12 real ``bd`` subprocess calls
    this helper would otherwise make per entry — meaningful here since this
    scenario needs three independent entries (vs. one or two for earlier
    scenarios) and every real ``bd`` invocation in this sandbox costs
    roughly a second.
    """
    payload = AssumptionPayload(
        question=f"{marker}: Should retries be scoped per bead or per run?",
        adopted_answer="Per bead — matches existing scoping.",
        alternatives=("Per run",),
        severity="medium",
    )
    record = await record_assumption(
        client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_id
    )
    assert record is not None
    stamp_result = await stamp_change_id(client, entry_ids=[record.bead_id], change_id=change_id)
    assert stamp_result.stamped == (record.bead_id,)
    await answer(
        client,
        bead_id=record.bead_id,
        answer_text=f"Per run — matches the new usage pattern ({marker}).",
    )
    return record


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_scenario_5_batch_order_and_immutability(
    reconcile_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quickstart.md Scenario 5 (US5, SC-003/SC-005) — batch, order, immutability.

    Builds ``base <- Z <- X <- Y`` with three changed-answer ledger entries
    stamped on Z/X/Y respectively (three distinct stack depths). Z is made
    immutable by configuring the repo's own
    ``revset-aliases."immutable_heads()"`` (see the fixture section's
    docstring above for the exact ``jj config set --repo`` invocation,
    verified against jj 0.43.0 in a throwaway sandbox first). X and Y touch
    disjoint files (``x.py``/``y.py``) with no other descendant touching
    either, so this test exercises ordering and the immutability guard in
    isolation from conflict/semantic mechanics (already covered by
    Scenarios 3/4).

    Asserts, in one workflow invocation:

    1. All three outcomes appear in ``report["outcomes"]`` in
       EARLIEST-FIRST stack order: Z (deepest/earliest), then X, then Y
       (FR-002 / SC-003).
    2. Z's outcome is ``status="skipped"`` with a reason mentioning
       immutability — the exact string ``workflow.py``'s mutability guard
       produces (``"correction target or a descendant it would rebase is
       immutable: ..."``).
    3. Z's own diff and history are completely untouched (byte-identical
       ``jj diff -r <Z>`` before/after), and no correction-agent call was
       EVER made targeting Z (asserted via the stub's marker-based call
       log, not just "the run succeeded").
    4. ``workflow.result.success is True`` (the run completes even though
       Z's answer wasn't reconciled) while ``report["exit_success"]`` is
       False (not everything reconciled — the CLI-layer FAILURE(1) mapping
       this test does not itself invoke).
    5. X's and Y's corrections both actually applied and persist
       (``status="reconciled"``, corrected content present on disk and in
       each change's own diff) — "the two applied answers remain applied"
       (quickstart wording).

    ``@pytest.mark.timeout(90)`` overrides this suite's module-wide 30s
    default (``pyproject.toml``'s ``[tool.pytest.ini_options]``): three
    independent ledger entries (vs. one or two in earlier scenarios) means
    roughly 12 real ``bd`` subprocess round-trips each (create/show/
    set-state/close), and this sandbox's ``bd`` binary costs roughly a
    second per invocation — fixture setup alone measured ~35-40s here even
    with the shared-source-bead trim below, before the workflow itself
    runs. This is the same underlying cause the module docstring already
    documents as occasional Scenario 2 flakiness under load (real
    subprocess-heavy fixture setup, not an open-ended or hanging test) —
    scaled up by having one more ledger entry than any other scenario in
    this file. The workflow run itself (2 full correct/semantic/gate
    pipelines + 1 cheap skip) is fast; ledger setup is the bottleneck.
    """
    _install_bd_compat_shims(monkeypatch)

    repo = reconcile_repo
    jj_client = JjClient(cwd=repo)
    client = BeadClient(cwd=repo)

    # --- Build the jj stack: base <- Z <- X <- Y ---------------------------
    await _write_and_commit(jj_client, repo, "base.py", "# base\n")
    z_change_id = await _write_and_commit(jj_client, repo, "z.py", "# z original\n")
    x_change_id = await _write_and_commit(jj_client, repo, "x.py", "# x original\n")
    y_change_id = await _write_and_commit(jj_client, repo, "y.py", "# y original\n")

    # --- Make Z immutable via the repo's own jj config ---------------------
    # Verified against jj 0.43.0 in a throwaway sandbox (see the fixture
    # docstring above): this covers Z and all of Z's ANCESTORS (``base``),
    # never Z's descendants (X, Y stay mutable).
    _run(
        [
            "jj",
            "config",
            "set",
            "--repo",
            'revset-aliases."immutable_heads()"',
            f"{z_change_id} | trunk()",
        ],
        cwd=repo,
    )
    immutable_log = await jj_client.log(revset="immutable()", limit=1000)
    immutable_short_ids = {change.change_id for change in immutable_log.changes}
    assert any(z_change_id.startswith(short_id) for short_id in immutable_short_ids), (
        "sanity check: the jj config change must actually make Z immutable"
    )
    mutable_log = await jj_client.log(revset="mutable()", limit=1000)
    mutable_short_ids = {change.change_id for change in mutable_log.changes}
    assert any(x_change_id.startswith(short_id) for short_id in mutable_short_ids), (
        "sanity check: X must remain mutable (immutability doesn't propagate to descendants)"
    )
    assert any(y_change_id.startswith(short_id) for short_id in mutable_short_ids), (
        "sanity check: Y must remain mutable (immutability doesn't propagate to descendants)"
    )

    # --- Three ledger entries: stamped on Z/X/Y, all answered differently --
    # One shared epic AND one shared source bead for all three entries (see
    # ``_record_scenario5_answer``'s docstring for why sharing the source
    # bead is safe) — this scenario is about batch ordering/immutability,
    # not lineage, and every real ``bd`` subprocess call in this sandbox is
    # expensive enough that trimming redundant bead creation meaningfully
    # cuts this test's wall-clock time (three independent ledger entries
    # already make it the heaviest fixture setup among these scenarios).
    epic = await client.create_bead(
        BeadDefinition(
            title=f"Integration epic scenario 5 ({_OWNER_SPEC})",
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": _OWNER_SPEC})
    source = await client.create_bead(
        BeadDefinition(
            title="Implement the batch-ordering thing",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        ),
        parent_id=epic.bd_id,
    )

    z_record = await _record_scenario5_answer(
        client,
        epic_id=epic.bd_id,
        source_bead_id=source.bd_id,
        change_id=z_change_id,
        marker="ENTRY-Z-IMMUTABLE",
    )
    x_record = await _record_scenario5_answer(
        client,
        epic_id=epic.bd_id,
        source_bead_id=source.bd_id,
        change_id=x_change_id,
        marker=_SCENARIO5_X_MARKER,
    )
    y_record = await _record_scenario5_answer(
        client,
        epic_id=epic.bd_id,
        source_bead_id=source.bd_id,
        change_id=y_change_id,
        marker=_SCENARIO5_Y_MARKER,
    )

    # bd's own writes dirty the jj working copy (see Scenario 1 fixture
    # comment) — fold them into a fresh empty working-copy commit before
    # running reconcile (FR-014 clean-@ precondition).
    await jj_client.new()
    working_copy_stat = await jj_client.diff_stat(revision="@")
    assert working_copy_stat.files_changed == 0, "fixture setup must leave a clean @ (FR-014)"

    # --- Pre-run snapshot: Z's own diff must stay byte-identical -----------
    pre_z_diff = (await jj_client.diff(revision=z_change_id)).output

    config = _reconcile_config(format_cmd=[sys.executable, "-c", "pass"])
    constructed = _stub_scenario5_runtime_factory(monkeypatch, repo=repo)

    # --- Run: reconcile all three changed answers in one invocation --------
    workflow = ReconcileWorkflow(config=config)
    events = [
        event
        async for event in workflow.execute(
            {"run_id": "test-run-scenario5", "cwd": str(repo), "dry_run": False}
        )
    ]
    assert workflow.result is not None

    # --- Assertion 4: the RUN completes even though Z's answer is skipped --
    assert workflow.result.success is True, [
        getattr(e, "error", None) for e in events if hasattr(e, "error")
    ]

    report = workflow.result.final_output
    assert report is not None
    outcomes = report["outcomes"]
    assert len(outcomes) == 3

    # --- Assertion 1: earliest-first ordering (FR-002/SC-003) --------------
    # Z is the deepest/earliest of the three targets (base <- Z <- X <- Y),
    # so it must appear first, then X, then Y — check actual output order,
    # not just membership.
    assert [o["entry_id"] for o in outcomes] == [
        z_record.bead_id,
        x_record.bead_id,
        y_record.bead_id,
    ], "outcomes must be ordered earliest-first by stack depth"

    outcomes_by_entry = {o["entry_id"]: o for o in outcomes}

    # --- Assertion 2: Z is skipped with an immutability reason -------------
    outcome_z = outcomes_by_entry[z_record.bead_id]
    assert outcome_z["status"] == "skipped"
    assert "immutable" in outcome_z["reason"].lower(), outcome_z["reason"]

    # --- Assertion 3: Z's history is completely untouched -------------------
    post_z_diff = (await jj_client.diff(revision=z_change_id)).output
    assert post_z_diff == pre_z_diff, "the immutable target's own diff must never change"
    assert SENTINEL_LINE.strip() not in post_z_diff

    # No correction call was EVER made for Z: exactly the X and Y markers
    # appear among correction-mode prompts, nothing else.
    all_calls: list[str] = [
        prompt
        for runtime in constructed
        for call in runtime.execute_calls
        if isinstance(prompt := call.get("prompt"), str)
    ]
    correction_prompts = [p for p in all_calls if "## Mode: Correction" in p]
    assert len(correction_prompts) == 2, correction_prompts
    assert all(
        (_SCENARIO5_X_MARKER in p) != (_SCENARIO5_Y_MARKER in p) for p in correction_prompts
    ), "every correction call must match exactly one of the X/Y markers, never Z"

    # Exactly 4 calls total: one correction + one semantic-analyze per
    # mutable answer (X, Y); Z never reaches the squadron's agents at all.
    assert sum(len(runtime.execute_calls) for runtime in constructed) == 4

    # --- Assertion 5: X's and Y's corrections both applied and persist -----
    outcome_x = outcomes_by_entry[x_record.bead_id]
    outcome_y = outcomes_by_entry[y_record.bead_id]
    assert outcome_x["status"] == "reconciled"
    assert outcome_y["status"] == "reconciled"
    assert outcome_x["gate_passed"] is True
    assert outcome_y["gate_passed"] is True
    assert outcome_x["target_change_id"] == x_change_id
    assert outcome_y["target_change_id"] == y_change_id

    x_diff = await jj_client.diff(revision=x_change_id)
    y_diff = await jj_client.diff(revision=y_change_id)
    assert SENTINEL_LINE.strip() in x_diff.output
    assert SENTINEL_LINE.strip() in y_diff.output
    assert (repo / "x.py").read_text(encoding="utf-8") == "# x original\n" + SENTINEL_LINE
    assert (repo / "y.py").read_text(encoding="utf-8") == "# y original\n" + SENTINEL_LINE

    entry_x_details = await client.show(x_record.bead_id)
    entry_y_details = await client.show(y_record.bead_id)
    assert entry_x_details.state[KEY_RECONCILE_STATUS] == "reconciled"
    assert entry_y_details.state[KEY_RECONCILE_STATUS] == "reconciled"

    entry_z_details = await client.show(z_record.bead_id)
    assert entry_z_details.state[KEY_RECONCILE_STATUS] == RECONCILE_STATUS_NEEDS_REVIEW

    # --- Additional workflow-level check: not everything reconciled --------
    assert report["exit_success"] is False, (
        "one skipped answer means the batch as a whole did not fully reconcile"
    )
