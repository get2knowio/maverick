"""Shared integration-test harness for ``maverick fly`` / ``maverick fly --isolated``.

Real ``git`` + real ``jj`` (colocated) + real ``bd`` — no live model calls.
Mirrors the two closest precedents in this repo:

* ``tests/integration/workflows/test_reconcile_jj.py``'s real ``bd``/``jj``
  fixture pattern (git init / jj git init --colocate / bd init
  --non-interactive) and its bd-CLI compatibility notes.
* ``tests/integration/spec_chain/conftest.py``'s stubbed airframe runtime
  (monkeypatch ``airframe.runtime_for`` to a fake runtime class whose
  ``execute()`` returns a canned structured payload — no HTTP, no
  subprocess SDK, no real model).

Bug-note update relative to ``test_reconcile_jj.py``'s module docstring:
that file documents a bd 1.1.0 incompatibility (array-wrapped ``bd show``,
labels-encoded state, single-pair ``set-state``, default-open-only bare
queries) that required ``BeadClient`` monkeypatch shims. This sandbox's
installed ``bd`` (probed at harness-design time: ``bd version 1.2.2``) has
moved on from that shape — ``BeadClient.show()`` already unwraps the
array and reads state via the dedicated ``bd state list`` command instead
of decoding it out of labels (see ``src/maverick/beads/client.py``), and
``bd query`` with the exact filter strings ``src/maverick/assumptions/
ledger.py`` sends works unpatched. Probed directly against this sandbox's
``bd`` before writing this fixture (``bd create``/``ready``/``show``/
``query``/``close``/``state list``, plus a real ``cp -r`` of a live
bd+jj+git repo) rather than assumed — no compatibility shims were needed
for the fly happy-path surface this harness drives (``ready``, ``show``
inside a try/except that already tolerates failure, ``create``, ``close``,
``state list``/``set-state``). A future sibling test that hits a genuinely
incompatible corner should add a narrowly-scoped shim here, following
``test_reconcile_jj.py``'s pattern, rather than assume this note still
holds against whatever ``bd`` build a later run has.

Bead-ID determinism note: ``bd`` assigns each bead a random-suffixed ID
(``<repo-basename>-<random>``) at creation time — confirmed by creating
the identically-named epic twice in two independently-``bd init``'d
directories and observing two different IDs. Contract F1 (SC-001) needs
byte-identical commit subjects/trailers between the "normal" and
"isolated" runs, which random per-run bead IDs would break. The fixture
therefore builds **one** repo (git + jj + bd + beads), then hands out
independent ``cp``-style copies of that single already-provisioned
directory for each run — "two independent copies of the *same* starting
repo state," matching the run guide's own phrasing
(``specs/057-isolated-bead-workspaces/quickstart.md`` Scenario 2) more
literally than re-running ``bd init`` twice would.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.config import (
    AgentBindingConfig,
    AgentsConfig,
    MaverickConfig,
    ValidationConfig,
)
from maverick.payloads import (
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)
from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

__all__ = [
    "BeadSpec",
    "FlyFixtureRepo",
    "FlyStubRuntime",
    "build_fly_repo",
    "clone_fly_repo",
    "commit_descriptions_since",
    "make_fly_config",
    "noop_gate_commands",
    "run_fly_workflow",
    "stub_fly_runtime_factory",
    "working_copy_dirt",
]

BD_UNAVAILABLE = shutil.which("bd") is None
JJ_UNAVAILABLE = shutil.which("jj") is None


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _run_bd_json(cmd: list[str], *, cwd: Path) -> Any:
    result = _run(cmd, cwd=cwd)
    return json.loads(result.stdout)


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
# Repo fixture — one real git+jj-colocated+bd repo, cloneable by value.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BeadSpec:
    """One ready task bead to create under the fixture's epic."""

    title: str
    description: str = ""
    priority: int = 1


#: Default two-bead fixture: two independent tasks (neither touches the
#: other's file), priority-ordered so selection order is deterministic.
DEFAULT_BEAD_SPECS: tuple[BeadSpec, ...] = (
    BeadSpec(title="Add alpha module", description="Implement the alpha module.", priority=1),
    BeadSpec(title="Add beta module", description="Implement the beta module.", priority=2),
)


@dataclass(frozen=True)
class FlyFixtureRepo:
    """A provisioned fixture repo: git + jj (colocated) + bd, one epic,
    N ready task beads, and a clean ``@`` at ``baseline_change_id``.

    ``baseline_change_id`` is the last change *before* any bead work — a
    revset upper bound (``f"{baseline_change_id}..@-"``) isolates exactly
    the commits a ``maverick fly`` run itself produces, excluding the
    fixture's own scaffold/bead-creation commit.
    """

    path: Path
    epic_id: str
    task_ids: tuple[str, ...]
    task_titles: tuple[str, ...]
    baseline_change_id: str


def build_fly_repo(
    repo_dir: Path,
    *,
    bead_specs: Sequence[BeadSpec] = DEFAULT_BEAD_SPECS,
    epic_title: str = "Fixture epic",
) -> FlyFixtureRepo:
    """Build one real git+jj-colocated+bd repo with a ready bead set.

    Mirrors ``tests/integration/workflows/test_reconcile_jj.py``'s
    ``reconcile_repo`` fixture for the git/jj/bd scaffold, then layers on
    an epic + N task beads via real ``bd create`` calls. ``bd``'s own
    writes dirty the jj working copy (its state lives in
    ``.beads/issues.jsonl``, only partially gitignored by ``bd init``) —
    settled into history by the same commit that lands ``README.md``, so
    ``@`` is clean before any caller starts a fly run against this repo.
    """
    repo_dir.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], cwd=repo_dir)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir)
    _run(["git", "config", "user.name", "Test"], cwd=repo_dir)
    _run(["jj", "git", "init", "--colocate"], cwd=repo_dir)
    _run(["bd", "init", "--non-interactive"], cwd=repo_dir)

    # Mirrors what a real `maverick init` writes to .gitignore (see
    # reconcile_repo's identical comment) — without it, this fixture's own
    # `.maverick/runs/<run-id>/...` output would dirty the working copy
    # the moment `FlyBeadsWorkflow` writes its run metadata.
    gitignore = repo_dir / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    if ".maverick/runs/" not in existing:
        gitignore.write_text(existing + ".maverick/runs/\n", encoding="utf-8")

    (repo_dir / "README.md").write_text("# Fixture repo\n", encoding="utf-8")

    epic_data = _run_bd_json(
        [
            "bd",
            "create",
            "--title",
            epic_title,
            "--type",
            "epic",
            "--priority",
            "1",
            "--json",
        ],
        cwd=repo_dir,
    )
    epic_id = str(epic_data["id"])

    task_ids: list[str] = []
    for spec in bead_specs:
        cmd = [
            "bd",
            "create",
            "--title",
            spec.title,
            "--type",
            "task",
            "--priority",
            str(spec.priority),
            "--parent",
            epic_id,
            "--json",
        ]
        if spec.description:
            cmd.extend(["--description", spec.description])
        data = _run_bd_json(cmd, cwd=repo_dir)
        task_ids.append(str(data["id"]))

    # One commit settles README.md *and* bd's dirtied .beads/ state
    # together (jj has no staging area — `jj commit` always finalizes the
    # whole working-copy diff) — this is the "clean @" baseline every
    # subsequent bead commit builds on top of.
    _run(["jj", "commit", "-m", "baseline: repo scaffold + fixture beads"], cwd=repo_dir)
    baseline_change_id = _run(
        ["jj", "log", "-r", "@-", "--no-graph", "-T", "change_id"], cwd=repo_dir
    ).stdout.strip()

    return FlyFixtureRepo(
        path=repo_dir,
        epic_id=epic_id,
        task_ids=tuple(task_ids),
        task_titles=tuple(spec.title for spec in bead_specs),
        baseline_change_id=baseline_change_id,
    )


def clone_fly_repo(source: FlyFixtureRepo, dest_dir: Path) -> FlyFixtureRepo:
    """Copy a provisioned :class:`FlyFixtureRepo` byte-for-byte into
    *dest_dir* — a real filesystem copy (git objects, ``.jj/``, and
    ``.beads/`` all included), not a fresh ``bd init``, so the clone's
    bead IDs are identical to the source's (see module docstring's
    bead-ID determinism note).
    """
    shutil.copytree(source.path, dest_dir)
    return FlyFixtureRepo(
        path=dest_dir,
        epic_id=source.epic_id,
        task_ids=source.task_ids,
        task_titles=source.task_titles,
        baseline_change_id=source.baseline_change_id,
    )


def commit_descriptions_since(repo_dir: Path, baseline_change_id: str) -> list[str]:
    """Full commit ``description`` (subject + trailers) for every change
    strictly after *baseline_change_id* up to (and including) the parent
    of the current working-copy change, oldest-first (bead processing
    order).

    Uses a raw ``jj log`` call rather than ``JjClient.log()`` because
    that helper's template only renders ``description.first_line()`` —
    contract F1 needs the full multi-line message (trailers included).
    """
    revset = f"{baseline_change_id}..@-"
    result = _run(
        ["jj", "log", "-r", revset, "--no-graph", "-T", 'description ++ "\\0"'],
        cwd=repo_dir,
    )
    parts = result.stdout.split("\0")
    descriptions = [p for p in parts if p != ""]
    # jj log's default order is newest-first; reverse for chronological
    # (= bead processing) order.
    return list(reversed(descriptions))


_JJ_STATUS_PATH_RE = re.compile(r"^[A-Z] (.+)$")


def working_copy_dirt(repo_dir: Path) -> tuple[str, ...]:
    """Paths ``jj status`` reports as changed in the current working copy.

    Real ``bd`` writes its own per-command audit trail to
    ``.beads/interactions.jsonl`` — a `bd close` issued *after* a bead's
    `jj commit` (see ``commit()``'s ordering: ``jj_commit_bead`` then
    ``mark_bead_complete``) always leaves that one file dirtied in the
    working copy, in real ``maverick fly`` usage too, not just this
    fixture. Callers wanting "nothing unexpected leaked into the
    checkout" should assert every returned path starts with ``.beads/``
    rather than asserting an empty return — a genuinely clean ``@`` after
    a bead commit is not this stack's actual invariant.
    """
    result = _run(["jj", "status"], cwd=repo_dir)
    paths: list[str] = []
    for line in result.stdout.splitlines():
        match = _JJ_STATUS_PATH_RE.match(line)
        if match:
            paths.append(match.group(1))
    return tuple(paths)


# ---------------------------------------------------------------------------
# Config — trivial no-op validation commands, implement+review bindings.
# ---------------------------------------------------------------------------


def noop_gate_commands() -> list[str]:
    """A validation command that always exits 0 — the exact idiom
    ``test_reconcile_jj.py`` uses for its own no-op gate stages."""
    return [sys.executable, "-c", "pass"]


def make_fly_config(*, workspace_root: Path | None = None) -> MaverickConfig:
    """A minimal ``MaverickConfig`` for driving ``FlyBeadsWorkflow``:
    stub ``implement``/``review`` bindings (the only two roles
    ``FlySquadron`` builds) and trivial no-op validation commands so the
    pre-loop baseline gate (which *does* honor ``MaverickConfig.validation``,
    unlike the per-bead gate — see the harness module docstring on
    ``noop_gate_commands``/the ``patch_default_gate_commands`` fixture
    below) can never fail against this fixture's beadless-of-tooling repo.

    ``workspace_root`` threads ``workspace.root`` (057-isolated-bead-
    workspaces) so an isolated run provisions workspaces under a tmp_path
    the test controls, never the real ``~/.maverick/workspaces``.
    """
    noop = noop_gate_commands()
    workspace_block: dict[str, Any] | None = None
    if workspace_root is not None:
        workspace_block = {"enabled": True, "root": str(workspace_root)}
    return MaverickConfig(
        agents=AgentsConfig(
            implement=AgentBindingConfig(provider="claude", model_id="stub-model"),
            review=AgentBindingConfig(provider="claude", model_id="stub-model"),
        ),
        validation=ValidationConfig(
            format_cmd=noop,
            lint_cmd=noop,
            typecheck_cmd=noop,
            test_cmd=noop,
        ),
        workspace=workspace_block,
    )


# ---------------------------------------------------------------------------
# Stubbed airframe runtime — implement/fix/review/aggregate, no live model.
# ---------------------------------------------------------------------------

_BEAD_ID_RE = re.compile(r"^## Bead: (\S+)", re.MULTILINE)


def _extract_bead_id(prompt: str) -> str:
    match = _BEAD_ID_RE.search(prompt)
    if match is None:
        raise AssertionError(f"could not find '## Bead: <id>' in prompt: {prompt[:200]!r}")
    return match.group(1)


class _StubSession:
    """Minimal ``AgentSession`` stand-in — ``Agent.open()`` always routes
    through ``runtime.session(...)`` once a squadron builds a real
    ``ProtectionPolicy`` (056-context-file-protection, always on for a
    real ``Squadron.open()``); delegates back to the runtime's own
    stubbed ``execute()``. Identical shape to the ``_StubSession`` classes
    in ``test_reconcile_jj.py`` / ``spec_chain/conftest.py``.
    """

    def __init__(self, runtime: FlyStubRuntime) -> None:
        self.id = "stub-session"
        self._runtime = runtime

    async def execute(self, prompt: str, **kwargs: Any) -> RuntimeResult:
        return await self._runtime.execute(prompt, **kwargs)

    async def close(self) -> None:
        return None


class FlyStubRuntime:
    """Fake airframe runtime satisfying every call shape fly's happy path
    makes: implementer (``implement``/``fix``) and both reviewer lenses
    (``review``/``aggregate``) share this one class, dispatching on the
    ``schema=`` kwarg airframe threads through — the same value each
    agent's ``result_model`` declares — rather than sniffing prompt text.

    * ``SubmitImplementationPayload`` (implement): writes a real file to
      **``Path.cwd()``**, not a captured checkout path — isolated mode
      chdirs the process into the bead's workspace for the duration of
      this call (``workspace/cwd_scope.chdir_scope``), and writing
      relative to whatever the *actual* process cwd is at call time is
      what makes this stub exercise that chdir instead of silently
      defeating it. The bead id is parsed out of the prompt's
      ``## Bead: <id>`` header (``_build_implement_prompt``'s exact
      shape) rather than threaded in some other way, since this runtime
      instance is shared across every bead in the run.
    * ``SubmitFixResultPayload`` (fix): raises — the happy-path fixture
      is built so gate/ac/spec/review all pass on the first attempt;
      a fix call landing here means something upstream regressed and
      should fail loudly, not be silently satisfied.
    * ``SubmitReviewPayload`` (review or aggregate — both reviewers and
      the epic-level aggregate pass use the same schema): always
      approves with zero findings.

    Every call is recorded on ``calls`` (schema + prompt) for tests that
    want to assert what was actually invoked.
    """

    label = "stub"

    def __init__(
        self, *, model: str | None = None, calls: list[dict[str, Any]] | None = None, **kwargs: Any
    ) -> None:
        self.model = model
        self.calls: list[dict[str, Any]] = calls if calls is not None else []
        self.written_files: list[Path] = []

    async def execute(self, prompt: str, *, schema: Any = None, **kwargs: Any) -> RuntimeResult:
        self.calls.append({"prompt": prompt, "schema": schema, **kwargs})

        if schema is SubmitImplementationPayload:
            bead_id = _extract_bead_id(prompt)
            target = Path.cwd() / f"{bead_id}.txt"
            target.write_text(f"implemented {bead_id}\n", encoding="utf-8")
            self.written_files.append(target)
            structured: dict[str, Any] = {
                "summary": f"Implemented {bead_id}.",
                "files_changed": [target.name],
                "assumptions": [],
            }
        elif schema is SubmitFixResultPayload:
            raise AssertionError(
                "unexpected fix() call — this fixture's beads are built so "
                f"gate/ac/spec/review all pass on the first attempt; prompt={prompt[:200]!r}"
            )
        elif schema is SubmitReviewPayload:
            structured = {"approved": True, "findings": [], "assumptions": []}
        else:
            raise AssertionError(f"unexpected schema {schema!r}; prompt={prompt[:200]!r}")

        return RuntimeResult(text="", structured=structured, cost=_make_cost(), finish="end_turn")

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: Any) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _StubSession:
        return _StubSession(self)


def stub_fly_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[FlyStubRuntime]:
    """Patch ``airframe.runtime_for`` (the exact point ``runtime_for_agent``
    calls — see ``src/maverick/runtime/agent_factory.py``) so every
    ``CodingAgent``/``ReviewerAgent`` a ``FlySquadron`` builds gets a
    ``FlyStubRuntime`` instance instead of a real provider adapter.

    Every constructed instance shares one ``calls`` list — fly builds
    up to three independent runtimes (implementer, correctness reviewer,
    completeness reviewer), and tests asserting "what happened this run"
    want one combined call log, not three to merge by hand.

    Returns the list of constructed runtime instances (one per agent the
    squadron builds).
    """
    constructed: list[FlyStubRuntime] = []
    shared_calls: list[dict[str, Any]] = []

    def _factory(provider_id: str) -> type[FlyStubRuntime]:
        class _Bound(FlyStubRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, calls=shared_calls, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


@pytest.fixture
def patch_default_gate_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op the per-bead gate's validation commands.

    ``build_fly_application``'s per-bead ``gate`` action is always bound
    with ``validation_commands=None`` by ``workflow.py``'s
    ``_run_bead_loop`` (confirmed by reading it — the baseline pre-loop
    gate *does* thread ``MaverickConfig.validation`` through, but the
    per-bead gate inside the Burr loop never does, in both isolated and
    non-isolated mode), so ``run_independent_gate`` always falls back to
    module-level ``DEFAULT_STAGE_COMMANDS`` (``ruff``/``mypy``/``pytest``)
    regardless of what ``ValidationConfig`` a test configures. Patching
    ``MaverickConfig.validation`` alone (as ``test_reconcile_jj.py`` does
    for ``ReconcileWorkflow``, which *does* thread config through) is
    therefore not sufficient here — this module-level default is the
    actual lever. Opt-in per test (not autouse) so a future gate-failure
    test (T056/T057) can still exercise a real failing gate.
    """
    from maverick.library.actions import validation as validation_module

    noop = tuple(noop_gate_commands())
    monkeypatch.setattr(
        validation_module,
        "DEFAULT_STAGE_COMMANDS",
        {"format": noop, "lint": noop, "typecheck": noop, "test": noop},
    )


# ---------------------------------------------------------------------------
# Driving FlyBeadsWorkflow — the real production entry point.
# ---------------------------------------------------------------------------


@dataclass
class FlyRunOutcome:
    """What a driven ``FlyBeadsWorkflow.execute(...)`` run produced."""

    success: bool
    final_output: dict[str, Any] | None
    events: list[Any] = field(default_factory=list)


async def run_fly_workflow(
    *,
    config: MaverickConfig,
    cwd: Path,
    epic_id: str,
    isolated: bool | None,
    monkeypatch: pytest.MonkeyPatch,
    max_beads: int = 0,
) -> FlyRunOutcome:
    """Drive ``FlyBeadsWorkflow`` end to end — the real production entry
    point (``FlyBeadsWorkflow._run`` via the ``PythonWorkflow.execute``
    template method), not a hand-reconstructed Burr app. Exercises the
    same ``isolated=True/False`` input the CLI passes
    (``src/maverick/cli/commands/fly/_group.py``), including the
    isolation-session/policy construction ``workflow.py``'s
    ``_run_bead_loop`` owns — nothing about isolation is reconstructed
    here, only driven.

    ``isolated=None`` omits the ``"isolated"`` key from ``inputs``
    entirely rather than sending an explicit ``False`` — the FR-035/
    SC-011 contract ("absent both [the flag and config], behavior is
    byte-identical to today") is about the key being *absent*, and
    ``FlyBeadsWorkflow._run`` reads it via
    ``bool(inputs.get("isolated", False))``, so an explicit ``False``
    and a missing key are two different inputs that happen to resolve
    to the same default — T055 wants to exercise the actual default,
    not merely a value equal to it.

    **Chdirs the test process into ``cwd`` for the duration of the run**
    (``monkeypatch.chdir`` — restored automatically at test teardown).
    This isn't incidental: two things in the real (non-isolated) code
    path are ambient-process-cwd-dependent by design, not by accident —

    1. ``workspace/cwd_scope.py``'s own docstring explains *why* isolated
       mode chdirs the process around every agent step at all: airframe
       0.9.2 exposes no working-directory field on any adapter's options,
       so chdir is the only provider-blind way to point an agent
       somewhere. That implies the non-isolated path already relies on
       the ambient process cwd matching the target repo — it works in
       real ``maverick fly`` usage only because the CLI resolves
       ``cwd = Path.cwd().resolve()`` (the user invokes it *from* the
       repo), never because anything threads a directory through
       explicitly at send time (``Agent._dispatch`` passes no ``cwd`` to
       ``execute()`` at all — confirmed by reading ``agents/base.py``).
    2. ``FlyBeadsWorkflow._run``'s "Step 2: Snapshot uncommitted changes"
       calls ``git_has_changes()`` with **no** ``cwd`` argument
       (``src/maverick/workflows/fly_beads/workflow.py``), so it too
       reads the ambient process cwd rather than the ``cwd`` input the
       rest of the function threads through explicitly (arguably a
       Guardrail 7 gap on its own — predates 057 by a wide margin, see
       ``git log -S`` — but invisible in real CLI usage for the same
       reason as (1): the two cwds already coincide there).

    A harness driving this workflow from a pytest process whose own cwd
    is the maverick checkout (not the fixture repo) must therefore chdir
    to match real invocation shape, or both of the above silently target
    the wrong directory — this is what makes ``FlyStubRuntime.execute``'s
    ``Path.cwd()``-based file write land in the fixture repo for the
    *non*-isolated run too, not just the isolated one (where
    ``chdir_scope`` does its own nested chdir on top of this one).
    """
    monkeypatch.chdir(cwd)

    workflow = FlyBeadsWorkflow(config=config)
    inputs: dict[str, Any] = {
        "epic_id": epic_id,
        "max_beads": max_beads,
        "auto_commit": False,
        "watch": False,
        "skip_preflight": True,
        "cwd": str(cwd),
    }
    if isolated is not None:
        inputs["isolated"] = isolated
    events = [event async for event in workflow.execute(inputs)]
    assert workflow.result is not None
    return FlyRunOutcome(
        success=workflow.result.success,
        final_output=workflow.result.final_output,
        events=events,
    )
