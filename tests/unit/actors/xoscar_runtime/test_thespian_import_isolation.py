"""Regression guard: no Thespian imports on the xoscar refuel path.

Confirms that importing the refuel-maverick workflow does not drag
``thespian`` into ``sys.modules``. Once Phase 4 removes ``thespian``
from dependencies entirely, this test becomes belt-and-suspenders, but
while both runtimes coexist it catches accidental re-introductions of
the legacy path.
"""

from __future__ import annotations

import sys


def test_refuel_path_does_not_import_thespian() -> None:
    # Subprocess-level check is more reliable than in-process (test
    # collection might have already imported thespian for other test
    # modules). Do an in-process check as a best-effort too.
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import maverick.workflows.refuel_maverick  # noqa: F401\n"
                "assert 'thespian' not in sys.modules, "
                "sorted(m for m in sys.modules if 'thespian' in m)\n"
                "print('OK')\n"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"subprocess import leaked thespian:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "OK" in result.stdout
