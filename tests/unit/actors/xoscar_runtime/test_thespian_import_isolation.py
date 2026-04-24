"""Regression guard: no Thespian imports on any xoscar workflow path.

``thespian`` was removed in Phase 4 of the xoscar migration. This test
keeps that property enforced: importing any of the three workflow
modules must not drag ``thespian`` (or any module containing that
substring) into ``sys.modules``. A future refactor that accidentally
reintroduces a ``thespian`` import will fail here.
"""

from __future__ import annotations

import sys


def _assert_no_thespian_after_import(module_path: str) -> None:
    """Spawn a subprocess that imports ``module_path`` and asserts
    ``thespian`` is not in ``sys.modules`` afterwards."""
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                f"import {module_path}  # noqa: F401\n"
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


def test_refuel_path_does_not_import_thespian() -> None:
    _assert_no_thespian_after_import("maverick.workflows.refuel_maverick")


def test_fly_path_does_not_import_thespian() -> None:
    _assert_no_thespian_after_import("maverick.workflows.fly_beads")


def test_plan_path_does_not_import_thespian() -> None:
    _assert_no_thespian_after_import("maverick.workflows.generate_flight_plan")
