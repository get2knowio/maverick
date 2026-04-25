"""Regression guard: every xoscar actor subclass must call super().__init__().

``xoscar.AsyncActorMixin.__init__`` initialises ``self._generators``, the
per-actor map that the ``@xo.generator`` decorator writes into when a
generator method is invoked. Without it, any actor with a
``@xo.generator`` method (notably the three supervisors' ``run()``)
crashes on first call with ``AttributeError: 'Supervisor' object has no
attribute '_generators'``.

The migration from Thespian to xoscar produced actor ``__init__``
methods that did not call ``super().__init__()``. Unit tests did not
catch this because they assert on method-level routing rather than
end-to-end ``run()``. This test enforces the invariant statically so
that future actors added under ``src/maverick/actors/xoscar/`` cannot
regress.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ACTOR_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "src"
    / "maverick"
    / "actors"
    / "xoscar"
)

#: Non-actor modules in the xoscar package.
_EXCLUDE = {"__init__.py", "messages.py", "pool.py"}


def _actor_files() -> list[Path]:
    return sorted(p for p in _ACTOR_DIR.glob("*.py") if p.name not in _EXCLUDE)


@pytest.mark.parametrize("path", _actor_files(), ids=lambda p: p.name)
def test_actor_module_calls_super_init(path: Path) -> None:
    src = path.read_text()
    if not re.search(r"^\s*def __init__\(", src, re.MULTILINE):
        return  # No __init__ — inherits xo.Actor's, which is fine.
    assert re.search(r"super\(\)\.__init__\(", src), (
        f"{path.name} defines __init__ without calling super().__init__(). "
        "xoscar's AsyncActorMixin.__init__ initialises self._generators; "
        "skipping it breaks any @xo.generator method on the actor."
    )


@pytest.mark.parametrize("path", _actor_files(), ids=lambda p: p.name)
def test_actor_module_calls_self_ref_as_method(path: Path) -> None:
    """``self.ref`` is a ``cpdef ActorRef ref(self)`` method on xoscar's
    ``_BaseActor`` — not a property. Accessing it without calling it
    returns an unbound Cython function, which then gets passed to
    children as ``supervisor_ref`` and produces
    ``'_cython_3_2_4.cython_function_or_method' object has no
    attribute '<method_name>'`` at first RPC call.

    This test forbids the bare ``self.ref`` form. Use ``self.ref()``.
    """
    src = path.read_text()
    # Match "self.ref" NOT followed by an opening paren or another word
    # character. That excludes valid forms like self.ref() and things
    # like self._refresh or self.refresh that happen to share a prefix.
    bare_ref_matches = re.findall(r"self\.ref(?![\w(])", src)
    assert not bare_ref_matches, (
        f"{path.name} uses 'self.ref' without parentheses. "
        "self.ref is a Cython cpdef method on xoscar's _BaseActor; "
        "you must call it — self.ref() — to get an ActorRef. "
        f"Found {len(bare_ref_matches)} bare occurrence(s)."
    )


@pytest.mark.parametrize("path", _actor_files(), ids=lambda p: p.name)
def test_on_tool_call_is_no_lock(path: Path) -> None:
    """Actor methods run under ``self._lock`` by default, which serialises
    every incoming message. ``on_tool_call`` is dispatched by the shared
    :class:`AgentToolGateway` while the agent actor is still blocked
    inside its own ``send_*`` method awaiting the ACP ``prompt_session``
    response — which cannot complete until the MCP tool call the agent
    just issued returns. Without ``@xo.no_lock`` this is a hard deadlock:
    ``on_tool_call`` waits for the lock ``send_*`` holds, ``send_*``
    waits for the ACP prompt which waits for the MCP tool response
    which waits for ``on_tool_call``.

    This test enforces the decorator on any ``on_tool_call`` method.
    """
    src = path.read_text()
    if "async def on_tool_call(" not in src:
        return  # deterministic actors don't own MCP tools
    # Look for @xo.no_lock (or @no_lock with xoscar import) on the line
    # immediately before `async def on_tool_call(`.
    match = re.search(
        r"(@[\w.]+\s*)+\n\s*async def on_tool_call\(",
        src,
    )
    assert match and ("xo.no_lock" in match.group(0) or "@no_lock" in match.group(0)), (
        f"{path.name} defines on_tool_call without @xo.no_lock. "
        "This causes a deadlock with the agent's own send_* method "
        "(both take the actor lock, but on_tool_call arrives while "
        "send_* is blocked inside prompt_session)."
    )


#: Supervisor-style methods (called by child actors via RPC) that must
#: not take the supervisor's actor lock — the supervisor's
#: ``@xo.generator`` ``run()`` method holds that lock while blocked on
#: ``self._event_queue.get()``, and the callbacks are what push onto
#: that queue. Without ``@xo.no_lock`` every such call deadlocks.
_SUPERVISOR_CALLBACK_SUFFIXES = ("_ready", "_error", "_result", "get_terminal_result")


def _supervisor_files() -> list[Path]:
    return [p for p in _actor_files() if "supervisor" in p.name]


@pytest.mark.parametrize("path", _supervisor_files(), ids=lambda p: p.name)
def test_supervisor_callback_methods_are_no_lock(path: Path) -> None:
    """Supervisor callback methods invoked by child actors must carry
    ``@xo.no_lock``. If the supervisor is suspended inside its
    ``@xo.generator run()`` awaiting the event queue (which it nearly
    always is, between child events), the actor lock is held and any
    incoming callback RPC queues forever. The callbacks are what push
    onto the queue, so the generator never wakes up."""
    src = path.read_text()
    # Find every "async def <name>(" where the name ends with a
    # callback-style suffix and the method is defined at class scope
    # (indented four spaces — xoscar Actors keep everything at that
    # level). Skip private helpers (names starting with _).
    methods = re.findall(
        r"^(?:    @[\w.]+\s*\n)*    async def ([a-z][\w]*)\(",
        src,
        re.MULTILINE,
    )
    callbacks = [
        name
        for name in methods
        if any(name.endswith(suffix) for suffix in _SUPERVISOR_CALLBACK_SUFFIXES)
        or name == "get_terminal_result"
    ]
    missing: list[str] = []
    for name in callbacks:
        # Require that the `async def <name>(` line is immediately
        # preceded by a line containing `@xo.no_lock` (allowing blank
        # comments between).
        match = re.search(
            rf"(@[\w.]+\s*\n\s*)+async def {re.escape(name)}\(",
            src,
        )
        if not match or "xo.no_lock" not in match.group(0):
            missing.append(name)
    assert not missing, (
        f"{path.name} has supervisor callback(s) without @xo.no_lock: {missing}. "
        "These methods are invoked by child actor RPC; without @xo.no_lock "
        "they deadlock against the supervisor's @xo.generator run() "
        "which holds the actor lock while awaiting the event queue."
    )


@pytest.mark.parametrize("path", _actor_files(), ids=lambda p: p.name)
def test_actor_module_decodes_self_uid(path: Path) -> None:
    """``self.uid`` on an xoscar Actor returns ``bytes``, not ``str``.

    xoscar's ``_BaseActor.__init__`` encodes any str uid at construction
    time (``if isinstance(uid, str): uid = uid.encode()``), so every
    subsequent ``self.uid`` access yields bytes. Using ``self.uid``
    directly in an f-string produces the repr ``"b'actor-name'"`` and
    in a subprocess argv list it gets coerced to that same ugly string.
    Either way, external tools downstream (MCP inbox subprocess,
    xo.actor_ref lookups, log scrapers) break.

    The rule: every ``self.uid`` access must be followed by
    ``.decode()``. Use it for uid= kwargs when spawning child actors
    and for argv entries in McpServerStdio.args.
    """
    src = path.read_text()
    # Match `self.uid` that is NOT followed by `.decode()` or a word
    # character. Word-character exclusion skips `self.uid_something`
    # (hypothetical, but safe).
    bare_uid_matches = re.findall(r"self\.uid(?!\.decode\(\))(?!\w)", src)
    assert not bare_uid_matches, (
        f"{path.name} uses 'self.uid' without '.decode()'. "
        "self.uid is bytes on xoscar; f-strings produce the 'b\\'...\\'' "
        "repr and subprocess argv entries carry the ugly string. "
        "Use self.uid.decode() instead. "
        f"Found {len(bare_uid_matches)} bare occurrence(s)."
    )
