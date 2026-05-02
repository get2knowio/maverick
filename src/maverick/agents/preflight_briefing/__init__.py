"""Pre-Flight Briefing prompt builders.

The four pre-flight personas (Scopist / CodebaseAnalyst / CriteriaWriter /
PreFlightContrarian) are markdown agent files under
``runtime/opencode/profile/agents/maverick.<name>.md``, invoked by the
xoscar :class:`maverick.actors.xoscar.briefing.BriefingActor` via
OpenCode's per-message ``agent=`` selector. Only the prompt builders
shared between the plan supervisor and the actor remain in
:mod:`maverick.agents.preflight_briefing.prompts`.
"""

from __future__ import annotations

__all__: list[str] = []
