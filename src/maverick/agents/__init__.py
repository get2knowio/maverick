"""Maverick Agents Package.

All agentic execution flows through OpenCode markdown personas under
``runtime/opencode/profile/agents/maverick.<name>.md``, invoked either
by:

* :class:`maverick.actors.xoscar.opencode_mixin.OpenCodeAgentMixin`
  (xoscar mailbox actors), or
* :meth:`maverick.runtime.opencode.OpenCodeStepExecutor.execute_named`
  (single-shot CLI / library actions).

What remains here are the prompt-builder helpers used by xoscar
supervisors and actors (``briefing.prompts``, ``preflight_briefing
.prompts``). New code should pick a persona file under the OpenCode
profile dir and route through ``execute_named`` or the actor mixin
instead of adding modules here.
"""

from __future__ import annotations

__all__: list[str] = []
