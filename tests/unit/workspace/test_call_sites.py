"""Repository-wide inspection test for the bd/ledger/commit-graph boundary
guard (057-isolated-bead-workspaces, User Story 4, T081).

Contract C6 / research.md R9 describe three enforcement layers:

1. Type-level — every bd/ledger/commit-graph entry point's ``cwd``
   parameter is annotated ``CheckoutPath`` (a ``NewType`` over ``Path``),
   so mypy rejects a raw workspace ``Path`` at authoring time.
2. Runtime — every such entry point calls
   ``maverick.workspace.assert_checkout`` as its first real action, so a
   call that somehow reaches it with a live-workspace path still raises
   ``IsolationBoundaryError`` instead of silently writing there.
3. This test — a static, AST-based inspection of the source files that
   own these entry points. It exists so that a future contributor who
   adds a new bd/ledger/commit-graph entry point *without* wiring in the
   guard gets a specific, named failure here rather than a silent gap
   that only surfaces later as a real isolation-boundary violation.

See specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md
(contract C6, T15/T81) and specs/057-isolated-bead-workspaces/research.md
(R9) for the full contract this test is standing in for.

This is deliberately **not** a runtime/behavioral test — it never imports
or executes any of the inspected modules' functions. It only parses their
source with :mod:`ast` and asserts on the shape of the parsed tree. Actual
runtime behavior of ``assert_checkout`` itself is covered by
``tests/unit/workspace/test_boundary.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src" / "maverick"

_BEADS_PATH = _SRC / "library" / "actions" / "beads.py"
_LEDGER_PATH = _SRC / "assumptions" / "ledger.py"
_JJ_PATH = _SRC / "library" / "actions" / "jj.py"

#: Functions in beads.py that take a raw ``cwd`` and must both call
#: ``assert_checkout`` and annotate ``cwd`` as ``CheckoutPath``.
_BEADS_GUARDED_FUNCTIONS = frozenset(
    {
        "create_beads",
        "wire_dependencies",
        "select_next_bead",
        "mark_bead_complete",
        "defer_bead",
        "create_remediation_beads",
    }
)

#: Functions in ledger.py that take an already-scoped ``client: BeadClient``
#: and must call ``assert_checkout(client.cwd)`` — no signature change,
#: per the contract (BeadClient.cwd is already the checkout by
#: construction elsewhere).
_LEDGER_GUARDED_FUNCTIONS = frozenset(
    {
        "record_assumption",
        "record_standalone_assumption",
        "answer",
        "waive",
        "bulk_waive",
        "mark_reconciled",
        "mark_needs_interactive_review",
        "create_reconcile_escalation",
        "stamp_change_id",
    }
)

#: jj.py's guarded entry points — also carry the ``CheckoutPath`` signature
#: requirement (their ``cwd`` stays optional: ``CheckoutPath | None``).
#: ``jj_fold_back`` is the primitive's own commit-graph-mutating squash
#: (``foldback.py``'s cross-workspace fold-back), guarded the same way as
#: ``jj_commit_bead``.
_JJ_GUARDED_FUNCTIONS = frozenset({"jj_commit_bead", "jj_fold_back"})


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _top_level_functions(tree: ast.Module) -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    """Map function name -> its AST node, for every top-level (sync or
    async) function definition in *tree*. Deliberately module-level only
    (not nested/methods) — every guarded entry point here is a bare
    module function.
    """
    functions: dict[str, ast.AsyncFunctionDef | ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            functions[node.name] = node
    return functions


def _calls_assert_checkout(func: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """True if *func*'s body contains a call to ``assert_checkout``
    anywhere (direct ``assert_checkout(...)`` or ``module.assert_checkout(...)``).
    """
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == "assert_checkout":
            return True
        if isinstance(callee, ast.Attribute) and callee.attr == "assert_checkout":
            return True
    return False


def _cwd_annotation_mentions_checkout_path(
    func: ast.AsyncFunctionDef | ast.FunctionDef,
) -> bool:
    """True if *func* has a ``cwd`` parameter (positional, keyword-only,
    or otherwise) whose annotation's dump mentions ``CheckoutPath`` —
    handles both ``cwd: CheckoutPath`` and ``cwd: CheckoutPath | None``.
    """
    all_args = [
        *func.args.posonlyargs,
        *func.args.args,
        *func.args.kwonlyargs,
    ]
    for arg in all_args:
        if arg.arg != "cwd":
            continue
        if arg.annotation is None:
            return False
        return "CheckoutPath" in ast.dump(arg.annotation)
    return False


@pytest.fixture(scope="module")
def beads_functions() -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    return _top_level_functions(_parse(_BEADS_PATH))


@pytest.fixture(scope="module")
def ledger_functions() -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    return _top_level_functions(_parse(_LEDGER_PATH))


@pytest.fixture(scope="module")
def jj_functions() -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    return _top_level_functions(_parse(_JJ_PATH))


class TestAssertCheckoutCalled:
    """Every guarded entry point must call ``assert_checkout`` somewhere
    in its body (contract C6 layer 2)."""

    @pytest.mark.parametrize("name", sorted(_BEADS_GUARDED_FUNCTIONS))
    def test_beads_function_calls_assert_checkout(
        self, beads_functions: dict[str, ast.AsyncFunctionDef | ast.FunctionDef], name: str
    ) -> None:
        assert name in beads_functions, (
            f"{name!r} not found as a top-level function in {_BEADS_PATH} — "
            "has it been renamed or moved? Update this test's expected set."
        )
        func = beads_functions[name]
        assert _calls_assert_checkout(func), (
            f"{_BEADS_PATH}:{name} does not call assert_checkout() anywhere in its "
            "body. Every bd-writing entry point in beads.py must call "
            "maverick.workspace.assert_checkout(cwd) as its guard against "
            "targeting a live isolated workspace (contract C6)."
        )

    @pytest.mark.parametrize("name", sorted(_LEDGER_GUARDED_FUNCTIONS))
    def test_ledger_function_calls_assert_checkout(
        self, ledger_functions: dict[str, ast.AsyncFunctionDef | ast.FunctionDef], name: str
    ) -> None:
        assert name in ledger_functions, (
            f"{name!r} not found as a top-level function in {_LEDGER_PATH} — "
            "has it been renamed or moved? Update this test's expected set."
        )
        func = ledger_functions[name]
        assert _calls_assert_checkout(func), (
            f"{_LEDGER_PATH}:{name} does not call assert_checkout() anywhere in "
            "its body. Every ledger write entry point must call "
            "maverick.workspace.assert_checkout(client.cwd) as its guard "
            "against targeting a live isolated workspace (contract C6)."
        )

    @pytest.mark.parametrize("name", sorted(_JJ_GUARDED_FUNCTIONS))
    def test_jj_function_calls_assert_checkout(
        self, jj_functions: dict[str, ast.AsyncFunctionDef | ast.FunctionDef], name: str
    ) -> None:
        assert name in jj_functions, (
            f"{name!r} not found as a top-level function in {_JJ_PATH} — "
            "has it been renamed or moved? Update this test's expected set."
        )
        func = jj_functions[name]
        assert _calls_assert_checkout(func), (
            f"{_JJ_PATH}:{name} does not call assert_checkout() anywhere in its "
            "body. jj_commit_bead must call "
            "maverick.workspace.assert_checkout(cwd) (when cwd is not None) as "
            "its guard against targeting a live isolated workspace (contract C6)."
        )


class TestCheckoutPathAnnotated:
    """Every guarded entry point's ``cwd`` parameter must be type-annotated
    with ``CheckoutPath`` (contract C6 layer 1)."""

    @pytest.mark.parametrize("name", sorted(_BEADS_GUARDED_FUNCTIONS))
    def test_beads_function_cwd_is_checkout_path(
        self, beads_functions: dict[str, ast.AsyncFunctionDef | ast.FunctionDef], name: str
    ) -> None:
        func = beads_functions[name]
        assert _cwd_annotation_mentions_checkout_path(func), (
            f"{_BEADS_PATH}:{name}'s cwd parameter is not annotated CheckoutPath. "
            "Type-level enforcement (contract C6 layer 1) requires the cwd "
            "parameter be annotated maverick.workspace.CheckoutPath so mypy "
            "rejects a raw workspace Path at authoring time."
        )

    @pytest.mark.parametrize("name", sorted(_JJ_GUARDED_FUNCTIONS))
    def test_jj_function_cwd_is_checkout_path(
        self, jj_functions: dict[str, ast.AsyncFunctionDef | ast.FunctionDef], name: str
    ) -> None:
        func = jj_functions[name]
        assert _cwd_annotation_mentions_checkout_path(func), (
            f"{_JJ_PATH}:{name}'s cwd parameter is not annotated CheckoutPath "
            "(or CheckoutPath | None). Type-level enforcement (contract C6 "
            "layer 1) requires the cwd parameter be annotated with "
            "maverick.workspace.CheckoutPath so mypy rejects a raw workspace "
            "Path at authoring time."
        )
