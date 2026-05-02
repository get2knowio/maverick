"""Briefing prompt builders.

The four briefing personas (Navigator / Structuralist / Recon / Contrarian)
are markdown agent files under
``runtime/opencode/profile/agents/maverick.<name>.md``, invoked by the
xoscar :class:`maverick.actors.xoscar.briefing.BriefingActor` via
OpenCode's per-message ``agent=`` selector. Only the prompt builders
shared between supervisor and actor remain in
:mod:`maverick.agents.briefing.prompts`.
"""

from __future__ import annotations

__all__: list[str] = []
