"""Built-in workflow library.

This module previously contained the BuiltinLibrary abstract base class.
That ABC was removed as part of the YAML DSL cleanup (041-remove-yaml-dsl)
because it had no implementations and no consumers. The follow-on
``library.agents`` registration shim was removed when the OpenCode
substrate migration moved all personas to bundled markdown agent files
under ``runtime/opencode/profile/agents/``.
"""
