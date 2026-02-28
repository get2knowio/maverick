"""Flight plan skeleton generator.

Provides :func:`generate_skeleton` to create a new, blank flight plan
Markdown file with YAML frontmatter and all required sections.
"""

from __future__ import annotations

from datetime import date

import yaml


def generate_skeleton(name: str, created: date) -> str:
    """Generate a skeleton flight plan Markdown file.

    Returns Markdown+YAML content with YAML frontmatter and all required
    sections with HTML comment editing instructions.

    Args:
        name: The kebab-case name for the flight plan (used in the frontmatter).
        created: The creation date for the flight plan.

    Returns:
        A string containing the full Markdown+YAML flight plan skeleton.
    """
    # Build frontmatter using yaml.dump for correct quoting.
    # We need version to be the string "1" (quoted in YAML), so we represent
    # it as the string "1" which yaml.dump will emit as '1' or "1".
    frontmatter_data: dict[str, object] = {
        "name": name,
        "version": "1",
        "created": created,
        "tags": [],
    }
    # yaml.dump adds a trailing newline; we want explicit key ordering.
    fm_str = yaml.dump(
        frontmatter_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    body = """\

## Objective
<!-- Replace this comment with a clear, high-level objective statement. -->

## Success Criteria
<!-- Add measurable success criteria as checkbox items below. -->
- [ ] <!-- Describe your first success criterion here. -->

## Scope

### In
<!-- List items that are explicitly in scope. -->
- <!-- Item in scope -->

### Out
<!-- List items that are explicitly out of scope. -->
- <!-- Item out of scope -->

### Boundaries
<!-- List boundary conditions that define the scope. -->
- <!-- Boundary condition -->

## Context
<!-- Provide background context and motivation for this flight plan. -->

## Constraints
<!-- List any constraints, technical or otherwise. -->
- <!-- Constraint -->

## Notes
<!-- Add any additional notes, open questions, or references. -->
"""

    return f"---\n{fm_str}---\n{body}"
