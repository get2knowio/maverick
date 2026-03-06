"""Serialize a BriefingDocument to Markdown+YAML frontmatter.

Follows the ``src/maverick/flight/serializer.py`` pattern.
"""

from __future__ import annotations

from typing import Any

import yaml

from maverick.briefing.models import BriefingDocument


def serialize_briefing(doc: BriefingDocument) -> str:
    """Render a BriefingDocument as Markdown with YAML frontmatter.

    Args:
        doc: The briefing document to serialize.

    Returns:
        Markdown string with YAML frontmatter.
    """
    lines: list[str] = []

    # --- Frontmatter ---
    frontmatter: dict[str, Any] = {
        "flight-plan": doc.flight_plan_name,
        "created": doc.created,
    }
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

    # --- Summary ---
    lines.append("## Summary")
    lines.append("")
    lines.append("### Navigator")
    lines.append("")
    lines.append(doc.navigator.summary)
    lines.append("")
    lines.append("### Structuralist")
    lines.append("")
    lines.append(doc.structuralist.summary)
    lines.append("")
    lines.append("### Recon")
    lines.append("")
    lines.append(doc.recon.summary)
    lines.append("")
    lines.append("### Contrarian")
    lines.append("")
    lines.append(doc.contrarian.summary)
    lines.append("")

    # --- Key Decisions ---
    if doc.key_decisions:
        lines.append("## Key Decisions")
        lines.append("")
        for decision in doc.key_decisions:
            lines.append(f"- {decision}")
        lines.append("")

    # --- Key Risks ---
    if doc.key_risks:
        lines.append("## Key Risks")
        lines.append("")
        for risk in doc.key_risks:
            lines.append(f"- {risk}")
        lines.append("")

    # --- Open Questions ---
    if doc.open_questions:
        lines.append("## Open Questions")
        lines.append("")
        for question in doc.open_questions:
            lines.append(f"- {question}")
        lines.append("")

    # --- Architecture Decisions ---
    if doc.navigator.architecture_decisions:
        lines.append("## Architecture Decisions")
        lines.append("")
        for adr in doc.navigator.architecture_decisions:
            lines.append(f"### {adr.title}")
            lines.append("")
            lines.append(f"**Decision:** {adr.decision}")
            lines.append("")
            lines.append(f"**Rationale:** {adr.rationale}")
            lines.append("")
            if adr.alternatives_considered:
                lines.append("**Alternatives considered:**")
                for alt in adr.alternatives_considered:
                    lines.append(f"- {alt}")
            lines.append("")

    # --- Data Model ---
    if doc.structuralist.entities or doc.structuralist.interfaces:
        lines.append("## Data Model")
        lines.append("")
        for entity in doc.structuralist.entities:
            lines.append(f"### {entity.name} (`{entity.module_path}`)")
            lines.append("")
            if entity.fields:
                lines.append("Fields:")
                for field in entity.fields:
                    lines.append(f"- `{field}`")
            if entity.relationships:
                lines.append("Relationships:")
                for rel in entity.relationships:
                    lines.append(f"- {rel}")
            lines.append("")
        for iface in doc.structuralist.interfaces:
            lines.append(f"### {iface.name} (interface)")
            lines.append("")
            if iface.methods:
                lines.append("Methods:")
                for method in iface.methods:
                    lines.append(f"- `{method}`")
            if iface.consumers:
                lines.append("Consumers:")
                for consumer in iface.consumers:
                    lines.append(f"- {consumer}")
            lines.append("")

    # --- Challenges ---
    if doc.contrarian.challenges:
        lines.append("## Challenges")
        lines.append("")
        for challenge in doc.contrarian.challenges:
            lines.append(f"### {challenge.target}")
            lines.append("")
            lines.append(f"**Counter-argument:** {challenge.counter_argument}")
            lines.append("")
            lines.append(f"**Recommendation:** {challenge.recommendation}")
            lines.append("")

    return "\n".join(lines)
