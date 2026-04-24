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
