"""Bundled ``maverick-review`` Claude Code skill.

The skill's body ships as a sibling ``SKILL.md`` file in this directory,
following the same simple "read a packaged ``.md`` file next to the
module" pattern used by
:mod:`maverick.agents.system_prompts` (``_PROMPT_DIR`` /
``load_persona_system_prompt``) rather than ``importlib.resources`` — it's
simpler and already proven in this codebase. ``maverick init`` installs
this content into the target project's
``.claude/skills/maverick-review/SKILL.md`` (see
:func:`maverick.init._install_review_skill`).
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["load_review_skill_markdown"]


_SKILL_DIR = Path(__file__).parent


def load_review_skill_markdown() -> str:
    """Return the packaged ``maverick-review`` ``SKILL.md`` content.

    Raises:
        FileNotFoundError: If the packaged ``SKILL.md`` is missing —
            this would indicate a broken install/build, so unlike the
            best-effort persona prompt loader, this is not swallowed
            here. Callers that want best-effort behavior (e.g.
            ``maverick init``'s install step) catch this themselves.
    """
    path = _SKILL_DIR / "SKILL.md"
    return path.read_text(encoding="utf-8")
