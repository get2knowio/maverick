"""Bundled persona system prompts.

Each ``maverick.<name>`` persona ships as a sibling ``.md`` file in this
directory; the body of the file is the system prompt passed via
``system=`` on :meth:`airframe.AgentRuntime.execute`. This is the
universal route — every airframe adapter honours ``system=``, whereas
``persona=`` is provider-specific (only the OpenCode Zen adapter
currently picks it up).

The previous home was
``runtime/opencode/profile/agents/maverick.<name>.md`` with YAML
frontmatter declaring tool permissions / mode; under airframe those
concerns moved to the ``agents:`` config block and the actor layer, so
only the prompt body survived the move.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

__all__ = ["available_personas", "load_persona_system_prompt"]


_PROMPT_DIR = Path(__file__).parent


@cache
def load_persona_system_prompt(name: str | None) -> str | None:
    """Return the system prompt for ``name`` or ``None`` when unmapped.

    ``name`` is the bundled-persona label (``"maverick.consolidator"``,
    ``"maverick.implementer"``, etc.) carried on each
    :class:`maverick.agents.base.Agent` subclass via its
    ``persona_name`` class var.

    A missing file is not an error — returning ``None`` lets the agent
    fall back to no system prompt rather than crashing on a typo or a
    newly-introduced persona that hasn't been authored yet. Callers
    should treat the absence as best-effort.
    """
    if not name:
        return None
    path = _PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").rstrip()


def available_personas() -> list[str]:
    """Return the persona names that have a bundled system prompt."""
    return sorted(p.stem for p in _PROMPT_DIR.glob("*.md"))
