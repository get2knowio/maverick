"""Shared markdown rendering for generated flight plans."""

from __future__ import annotations

from datetime import date

import yaml

from maverick.tools.agent_inbox.models import SubmitFlightPlanPayload


def render_flight_plan_markdown(
    *,
    plan_name: str,
    prd_content: str,
    flight_plan: SubmitFlightPlanPayload,
) -> str:
    """Render a generated flight plan payload into persisted markdown.

    The renderer preserves the current file format expected by Maverick's
    plan parser: YAML frontmatter followed by canonical ``Objective``,
    ``Success Criteria``, ``Scope``, and ``Constraints`` sections.
    """

    default_objective = prd_content.split("\n")[0].lstrip("#").strip()[:200]
    objective = flight_plan.objective or default_objective

    frontmatter = {
        "name": flight_plan.name or plan_name,
        "version": flight_plan.version or "1",
        "created": str(date.today()),
        "objective": objective,
        "tags": list(flight_plan.tags),
        "scope": {
            "in_scope": list(flight_plan.in_scope),
            "out_of_scope": list(flight_plan.out_of_scope),
            "boundaries": list(flight_plan.boundaries),
        },
    }
    frontmatter_text = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False)

    body_parts = [f"# {plan_name}\n", f"## Objective\n\n{objective}\n"]

    if flight_plan.context:
        body_parts.append(f"## Context\n\n{flight_plan.context}\n")

    body_parts.append("## Success Criteria\n")
    for criterion in flight_plan.success_criteria:
        description = criterion.description
        if criterion.verification:
            description = f"{description} (Verification: {criterion.verification})"
        body_parts.append(f"- [ ] {description}")

    if flight_plan.in_scope or flight_plan.out_of_scope:
        body_parts.append("\n## Scope\n")
        if flight_plan.in_scope:
            body_parts.append("### In\n")
            for item in flight_plan.in_scope:
                body_parts.append(f"- {item}")
        if flight_plan.out_of_scope:
            body_parts.append("\n### Out\n")
            for item in flight_plan.out_of_scope:
                body_parts.append(f"- {item}")

    if flight_plan.constraints:
        body_parts.append("\n## Constraints\n")
        for item in flight_plan.constraints:
            body_parts.append(f"- {item}")

    if flight_plan.notes:
        body_parts.append(f"\n## Notes\n\n{flight_plan.notes}\n")

    return f"---\n{frontmatter_text}---\n\n" + "\n".join(body_parts) + "\n"


__all__ = ["render_flight_plan_markdown"]
