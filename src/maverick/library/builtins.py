"""Built-in workflow library.

This module previously contained the BuiltinLibrary abstract base class.
That ABC was removed as part of the YAML DSL cleanup
(041-remove-yaml-dsl) because it had no implementations and no
consumers. Personas now live under ``agents/system_prompts/`` and are
loaded via :func:`maverick.agents.system_prompts.load_persona_system_prompt`.
"""
