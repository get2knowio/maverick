"""Maverick Agents Package.

All agentic execution flows through airframe-runtime-backed
:class:`maverick.agents.base.Agent` subclasses. Two shapes live here:

* Per-role mailbox agents (``CodingAgent``, ``ReviewerAgent``,
  ``BriefingAgent``, ``DecomposerAgent``, ``GeneratorAgent``) — driven
  by xoscar actor shells; one ``provider_tier`` class var per role.
* One-shot persona agents (``maverick.agents.personas``) — wrappers
  around bundled persona prompts (consolidator, curator, validation-
  fixer, runway-seed, flight-plan-generator); used by CLI commands and
  library actions that aren't part of the mailbox flow.

Prompt builders live alongside each agent module (e.g.
``briefing.prompts``, ``preflight_briefing.prompts``).
"""

from __future__ import annotations

__all__: list[str] = []
