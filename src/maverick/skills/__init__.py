"""Packaged Claude Code skills bundled with maverick.

Each subpackage ships a ``SKILL.md`` that ``maverick init`` installs into
the target project's ``.claude/skills/`` directory (see
``maverick.skills.review_console``).
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["REVIEW_SKILL_RELATIVE_PATH"]

#: Where the packaged ``maverick-review`` skill lands in a target project,
#: relative to the project root. Owned here — a leaf module both the
#: install path (``maverick.init._install_review_skill``) and the removal
#: path (``maverick.cli.commands.uninstall``) already import transitively —
#: so the two can never disagree about the location and leave a stale
#: Maverick-owned skill behind after ``maverick uninstall``.
REVIEW_SKILL_RELATIVE_PATH = Path(".claude") / "skills" / "maverick-review" / "SKILL.md"
