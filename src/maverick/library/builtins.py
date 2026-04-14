"""Built-in workflow library.

This module previously contained the BuiltinLibrary abstract base class.
That ABC was removed as part of the YAML DSL cleanup (041-remove-yaml-dsl)
because it had no implementations and no consumers.

Built-in components are now registered via:
- ``maverick.library.agents.register_all_agents``
"""
