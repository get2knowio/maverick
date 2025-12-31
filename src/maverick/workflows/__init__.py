"""Maverick Workflows Module.

NOTE: Legacy Python workflow implementations have been removed.
Workflows are now defined using the YAML-based DSL in maverick.library.workflows.

To run a workflow, use:
    maverick workflow run <workflow-name>

Available built-in workflows:
    - feature: Full spec-based development workflow
    - cleanup: Tech-debt resolution workflow
    - review: Code review orchestration
    - validate: Validation with optional fixes
    - quick-fix: Quick issue fix

Custom workflows can be defined in:
    - .maverick/workflows/ (project-level)
    - ~/.config/maverick/workflows/ (user-level)
"""

from __future__ import annotations

__all__: list[str] = []
