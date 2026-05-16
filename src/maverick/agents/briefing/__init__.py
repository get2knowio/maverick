"""Briefing prompt builders.

The four briefing personas (Navigator / Structuralist / Recon / Contrarian)
are markdown system prompts under
``agents/system_prompts/maverick.<name>.md``, loaded by
:class:`maverick.agents.briefing.agent.BriefingAgent` and passed as
``system=`` on every airframe ``execute()`` call. Only the prompt
builders shared between supervisor and actor remain in
:mod:`maverick.agents.briefing.prompts`.
"""

from __future__ import annotations

__all__: list[str] = []
