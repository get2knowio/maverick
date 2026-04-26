"""Tool schemas for the supervisor inbox MCP server.

Each schema defines a message type the supervisor accepts.
Tools are the agent's outbound mailbox — calling a tool delivers
a structured message to the supervisor's inbox.

Schemas use JSON Schema format as required by the MCP Tool spec.
"""

from __future__ import annotations

from typing import Any


def _tool(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Helper to build a tool definition dict."""
    return {"name": name, "description": description, "inputSchema": schema}


# -------------------------------------------------------------------------
# Refuel decomposition tools
# -------------------------------------------------------------------------

SUBMIT_OUTLINE = _tool(
    name="submit_outline",
    description=(
        "Submit the work unit outline to the supervisor for validation. "
        "Call this after you've analyzed the flight plan and determined "
        "how to decompose it into work units."
    ),
    schema={
        "type": "object",
        "properties": {
            "work_units": {
                "type": "array",
                "description": "Ordered list of work unit skeletons",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Kebab-case unique identifier",
                        },
                        "task": {
                            "type": "string",
                            "description": "One-sentence description of the work",
                        },
                        "sequence": {
                            "type": "integer",
                            "description": "Execution order (1-based)",
                        },
                        "parallel_group": {
                            "type": "string",
                            "description": "Group label for parallel execution",
                        },
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "IDs of work units this depends on",
                        },
                        "file_scope": {
                            "type": "object",
                            "properties": {
                                "create": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "modify": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "protect": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                        "complexity": {
                            "type": "string",
                            "enum": ["trivial", "simple", "moderate", "complex"],
                            "description": (
                                "How much model intelligence this bead "
                                "needs. trivial = boilerplate / config / "
                                "single-file scaffolding. simple = "
                                "mechanical, well-specified, single-file. "
                                "moderate = typical implementation work, "
                                "design decisions made. complex = "
                                "architecturally meaningful, cross-cutting, "
                                "or reasoning-heavy. Used to route beads "
                                "to appropriately-sized models."
                            ),
                        },
                    },
                    "required": ["id", "task"],
                },
            },
            "rationale": {
                "type": "string",
                "description": "Why you chose this decomposition",
            },
        },
        "required": ["work_units"],
    },
)

SUBMIT_DETAILS = _tool(
    name="submit_details",
    description=(
        "Submit detailed work unit specifications to the supervisor. "
        "Call this after filling in instructions, acceptance criteria, "
        "and verification for each work unit."
    ),
    schema={
        "type": "object",
        "properties": {
            "details": {
                "type": "array",
                "description": "Detail entries, one per work unit",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Must match a work unit ID from the outline",
                        },
                        "instructions": {
                            "type": "string",
                            "description": "Step-by-step procedure (MUST/SHOULD/MAY)",
                        },
                        "acceptance_criteria": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {
                                        "type": "string",
                                        "description": "What must be true",
                                    },
                                    "trace_ref": {
                                        "type": "string",
                                        "description": "SC reference (e.g. SC-001)",
                                    },
                                },
                                "required": ["text"],
                            },
                            "description": "Acceptance criteria with SC trace refs",
                        },
                        "verification": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Commands to verify correctness",
                        },
                        "test_specification": {
                            "type": "string",
                            "description": "Test function body that fails before, passes after",
                        },
                    },
                    "required": ["id", "instructions"],
                },
            },
        },
        "required": ["details"],
    },
)

SUBMIT_FIX = _tool(
    name="submit_fix",
    description=(
        "Submit a patched decomposition after fixing validation gaps. "
        "Include the COMPLETE updated set of work units and details."
    ),
    schema={
        "type": "object",
        "properties": {
            "work_units": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Complete updated work unit list",
            },
            "details": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Complete updated details list",
            },
        },
        "required": ["work_units", "details"],
    },
)

# -------------------------------------------------------------------------
# Fly implementation tools
# -------------------------------------------------------------------------

SUBMIT_IMPLEMENTATION = _tool(
    name="submit_implementation",
    description=(
        "Signal that implementation is complete. Call this after you've "
        "written all code and run verification."
    ),
    schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of what was implemented",
            },
            "files_changed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files that were created or modified",
            },
        },
        "required": ["summary"],
    },
)

SUBMIT_REVIEW = _tool(
    name="submit_review",
    description=(
        "Submit your code review findings to the supervisor. "
        "Set approved=true if no critical/major issues found."
    ),
    schema={
        "type": "object",
        "properties": {
            "approved": {
                "type": "boolean",
                "description": "True if code passes review",
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "major", "minor"],
                        },
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "issue": {"type": "string"},
                    },
                    "required": ["severity", "issue"],
                },
                "description": "List of issues found (empty if approved)",
            },
        },
        "required": ["approved"],
    },
)

SUBMIT_FIX_RESULT = _tool(
    name="submit_fix_result",
    description=(
        "Signal that you've addressed the requested fixes. "
        "List which findings were addressed and any you're contesting."
    ),
    schema={
        "type": "object",
        "properties": {
            "addressed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Finding IDs that were fixed",
            },
            "contested": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "Finding ID -> reason for contesting",
            },
            "summary": {
                "type": "string",
                "description": "Brief description of changes made",
            },
        },
        "required": ["summary"],
    },
)

# -------------------------------------------------------------------------
# Plan briefing tools
# -------------------------------------------------------------------------

SUBMIT_SCOPE = _tool(
    name="submit_scope",
    description="Submit scope analysis to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "in_scope": {"type": "array", "items": {"type": "string"}},
            "out_scope": {"type": "array", "items": {"type": "string"}},
            "boundaries": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["in_scope"],
    },
)

SUBMIT_ANALYSIS = _tool(
    name="submit_analysis",
    description="Submit codebase analysis to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "modules": {"type": "array", "items": {"type": "string"}},
            "patterns": {"type": "array", "items": {"type": "string"}},
            "dependencies": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["modules"],
    },
)

SUBMIT_CRITERIA = _tool(
    name="submit_criteria",
    description="Submit acceptance criteria to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "criteria": {"type": "array", "items": {"type": "string"}},
            "test_scenarios": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["criteria"],
    },
)

SUBMIT_CHALLENGE = _tool(
    name="submit_challenge",
    description="Submit contrarian challenges to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "risks": {"type": "array", "items": {"type": "string"}},
            "blind_spots": {"type": "array", "items": {"type": "string"}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["risks"],
    },
)

SUBMIT_FLIGHT_PLAN = _tool(
    name="submit_flight_plan",
    description=(
        "Submit the generated flight plan to the supervisor. "
        "You MUST call this tool — do not put the plan in text."
    ),
    schema={
        "type": "object",
        "properties": {
            "objective": {
                "type": "string",
                "description": "One-line objective summarizing what this plan achieves.",
            },
            "context": {
                "type": "string",
                "description": "Background context for the plan (markdown).",
            },
            "success_criteria": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "verification": {"type": "string"},
                    },
                    "required": ["description"],
                },
                "description": "Measurable success criteria for the plan.",
            },
            "in_scope": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Items explicitly in scope.",
            },
            "out_of_scope": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Items explicitly out of scope.",
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Constraints or limitations.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for categorization.",
            },
        },
        "required": ["objective", "success_criteria"],
    },
)

# -------------------------------------------------------------------------
# Refuel briefing tools
# -------------------------------------------------------------------------

SUBMIT_NAVIGATOR_BRIEF = _tool(
    name="submit_navigator_brief",
    description="Submit architecture and module layout analysis to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "architecture_decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "decision": {"type": "string"},
                        "rationale": {"type": "string"},
                        "alternatives_considered": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "decision"],
                },
            },
            "module_structure": {"type": "string"},
            "integration_points": {
                "type": "array",
                "items": {"type": "string"},
            },
            "summary": {"type": "string"},
        },
        "required": ["architecture_decisions", "summary"],
    },
)

SUBMIT_STRUCTURALIST_BRIEF = _tool(
    name="submit_structuralist_brief",
    description="Submit data model and interface analysis to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "module_path": {"type": "string"},
                        "fields": {"type": "array", "items": {"type": "string"}},
                        "relationships": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name"],
                },
            },
            "interfaces": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "methods": {"type": "array", "items": {"type": "string"}},
                        "consumers": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name"],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["entities", "summary"],
    },
)

SUBMIT_RECON_BRIEF = _tool(
    name="submit_recon_brief",
    description="Submit risks, ambiguities, and testing strategy to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "mitigation": {"type": "string"},
                    },
                    "required": ["description"],
                },
            },
            "ambiguities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "context": {"type": "string"},
                        "suggested_resolution": {"type": "string"},
                    },
                    "required": ["question"],
                },
            },
            "testing_strategy": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["risks", "summary"],
    },
)

SUBMIT_CONTRARIAN_BRIEF = _tool(
    name="submit_contrarian_brief",
    description="Submit challenges and simplifications to the supervisor.",
    schema={
        "type": "object",
        "properties": {
            "challenges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "counter_argument": {"type": "string"},
                        "recommendation": {"type": "string"},
                    },
                    "required": ["target", "counter_argument"],
                },
            },
            "simplifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "current_approach": {"type": "string"},
                        "simpler_alternative": {"type": "string"},
                        "tradeoff": {"type": "string"},
                    },
                    "required": ["current_approach", "simpler_alternative"],
                },
            },
            "consensus_points": {
                "type": "array",
                "items": {"type": "string"},
            },
            "summary": {"type": "string"},
        },
        "required": ["challenges", "summary"],
    },
)

# -------------------------------------------------------------------------
# Registry: all tools by name
# -------------------------------------------------------------------------

ALL_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "submit_outline": SUBMIT_OUTLINE,
    "submit_details": SUBMIT_DETAILS,
    "submit_fix": SUBMIT_FIX,
    "submit_implementation": SUBMIT_IMPLEMENTATION,
    "submit_review": SUBMIT_REVIEW,
    "submit_fix_result": SUBMIT_FIX_RESULT,
    "submit_scope": SUBMIT_SCOPE,
    "submit_analysis": SUBMIT_ANALYSIS,
    "submit_criteria": SUBMIT_CRITERIA,
    "submit_challenge": SUBMIT_CHALLENGE,
    "submit_flight_plan": SUBMIT_FLIGHT_PLAN,
    "submit_navigator_brief": SUBMIT_NAVIGATOR_BRIEF,
    "submit_structuralist_brief": SUBMIT_STRUCTURALIST_BRIEF,
    "submit_recon_brief": SUBMIT_RECON_BRIEF,
    "submit_contrarian_brief": SUBMIT_CONTRARIAN_BRIEF,
}
