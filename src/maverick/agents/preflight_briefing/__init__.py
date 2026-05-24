"""Pre-Flight Briefing prompt builders.

The four pre-flight personas (Scopist / CodebaseAnalyst / CriteriaWriter /
PreFlightContrarian) are markdown system prompts under
``agents/system_prompts/maverick.<name>.md``, loaded by
:class:`maverick.agents.briefing.agent.BriefingAgent` and passed as
``system=`` on every airframe ``execute()`` call. Only the prompt
builders shared between the plan supervisor and the actor remain in
:mod:`maverick.agents.preflight_briefing.prompts`.
"""

from __future__ import annotations

__all__: list[str] = []
