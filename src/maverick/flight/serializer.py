"""Round-trip serializers for Flight Plan and Work Unit documents.

Converts in-memory Pydantic models back to the Markdown+YAML frontmatter
format that can be reloaded by FlightPlanFile and WorkUnitFile loaders.

Public API:
    serialize_flight_plan(plan) -> str
    serialize_work_unit(unit) -> str
"""

from __future__ import annotations

from typing import Any

import yaml

from maverick.flight.models import FlightPlan, WorkUnit

# ---------------------------------------------------------------------------
# FlightPlan serializer
# ---------------------------------------------------------------------------


def serialize_flight_plan(plan: FlightPlan) -> str:
    """Serialize a FlightPlan model to Markdown+YAML string.

    The output can be reloaded via FlightPlanFile.load() with identical data.

    Args:
        plan: FlightPlan model instance.

    Returns:
        Markdown+YAML string with YAML frontmatter and Markdown sections.
        The document structure is:
        - YAML frontmatter (name, version, created, tags)
        - ## Objective
        - ## Success Criteria (checkbox list)
        - ## Scope (### In / ### Out / ### Boundaries sub-sections)
        - ## Context (omitted when empty)
        - ## Constraints (omitted when empty)
        - ## Notes (omitted when empty)
    """
    lines: list[str] = []

    # --- Frontmatter ---
    frontmatter: dict[str, Any] = {
        "name": plan.name,
        "version": plan.version,
        "created": plan.created.isoformat(),
        "tags": list(plan.tags),
    }
    if plan.depends_on_plans:
        frontmatter["depends-on-plans"] = list(plan.depends_on_plans)
    fm_yaml = yaml.dump(
        frontmatter,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    lines.append("---")
    lines.append(fm_yaml.rstrip())
    lines.append("---")
    lines.append("")

    # --- Objective ---
    lines.append("## Objective")
    lines.append("")
    lines.append(plan.objective)
    lines.append("")

    # --- Success Criteria ---
    lines.append("## Success Criteria")
    lines.append("")
    for criterion in plan.success_criteria:
        marker = "x" if criterion.checked else " "
        lines.append(f"- [{marker}] {criterion.text}")
    lines.append("")

    # --- Scope ---
    lines.append("## Scope")
    lines.append("")
    lines.append("### In")
    lines.append("")
    for item in plan.scope.in_scope:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Out")
    lines.append("")
    for item in plan.scope.out_of_scope:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Boundaries")
    lines.append("")
    for item in plan.scope.boundaries:
        lines.append(f"- {item}")
    lines.append("")

    # --- Context (optional) ---
    if plan.context:
        lines.append("## Context")
        lines.append("")
        lines.append(plan.context)
        lines.append("")

    # --- Constraints (optional) ---
    if plan.constraints:
        lines.append("## Constraints")
        lines.append("")
        for constraint in plan.constraints:
            lines.append(f"- {constraint}")
        lines.append("")

    # --- Verification Properties (optional) ---
    if plan.verification_properties:
        lines.append("## Verification Properties")
        lines.append("")
        lines.append(plan.verification_properties)
        lines.append("")

    # --- Notes (optional) ---
    if plan.notes:
        lines.append("## Notes")
        lines.append("")
        lines.append(plan.notes)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# WorkUnit serializer
# ---------------------------------------------------------------------------


def serialize_work_unit(unit: WorkUnit) -> str:
    """Serialize a WorkUnit model to Markdown+YAML string.

    The output can be reloaded via WorkUnitFile.load() with identical data.

    Args:
        unit: WorkUnit model instance.

    Returns:
        Markdown+YAML string with YAML frontmatter and Markdown sections.
        The document structure is:
        - YAML frontmatter (work-unit, flight-plan, sequence, depends-on,
          and optionally parallel-group)
        - ## Task
        - ## Acceptance Criteria (bullet list with optional [SC-###] refs)
        - ## File Scope (### Create / ### Modify / ### Protect sub-sections)
        - ## Instructions
        - ## Verification (bullet list)
        - ## Provider Hints (omitted when None)
    """
    lines: list[str] = []

    # --- Frontmatter ---
    frontmatter: dict[str, Any] = {
        "work-unit": unit.id,
        "flight-plan": unit.flight_plan,
        "sequence": unit.sequence,
        "depends-on": list(unit.depends_on),
    }
    if unit.parallel_group is not None:
        frontmatter["parallel-group"] = unit.parallel_group

    fm_yaml = yaml.dump(
        frontmatter,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    lines.append("---")
    lines.append(fm_yaml.rstrip())
    lines.append("---")
    lines.append("")

    # --- Task ---
    lines.append("## Task")
    lines.append("")
    lines.append(unit.task)
    lines.append("")

    # --- Acceptance Criteria ---
    lines.append("## Acceptance Criteria")
    lines.append("")
    for ac in unit.acceptance_criteria:
        if ac.trace_ref:
            lines.append(f"- {ac.text} [{ac.trace_ref}]")
        else:
            lines.append(f"- {ac.text}")
    lines.append("")

    # --- File Scope ---
    lines.append("## File Scope")
    lines.append("")
    lines.append("### Create")
    lines.append("")
    for item in unit.file_scope.create:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Modify")
    lines.append("")
    for item in unit.file_scope.modify:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Protect")
    lines.append("")
    for item in unit.file_scope.protect:
        lines.append(f"- {item}")
    lines.append("")

    # --- Instructions ---
    lines.append("## Procedure")
    lines.append("")
    lines.append(unit.instructions)
    lines.append("")

    # --- Test Specification (optional) ---
    if unit.test_specification:
        lines.append("## Test Specification")
        lines.append("")
        lines.append(unit.test_specification)
        lines.append("")

    # --- Verification ---
    lines.append("## Verification")
    lines.append("")
    for cmd in unit.verification:
        lines.append(f"- {cmd}")
    lines.append("")

    # --- Provider Hints (optional) ---
    if unit.provider_hints:
        lines.append("## Provider Hints")
        lines.append("")
        lines.append(unit.provider_hints)
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "serialize_flight_plan",
    "serialize_work_unit",
]
