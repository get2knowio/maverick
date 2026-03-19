"""Agent registration for DSL-based workflow execution.

This module provides functions to register all built-in agents with the
component registry. Agents are MaverickAgent classes that perform complex
tasks (code review, implementation, issue fixing, etc.).

Registration Functions:
    register_all_agents: Register all built-in agents with the registry.

Registered Agents:
    implementer: ImplementerAgent - Executes tasks from task files
    completeness_reviewer: CompletenessReviewerAgent - Reviews for requirement coverage
    correctness_reviewer: CorrectnessReviewerAgent - Reviews for technical correctness
    simple_fixer: SimpleFixerAgent - Fixes review findings
    validation_fixer: FixerAgent - Applies validation fixes
    decomposer: DecomposerAgent - Decomposes flight plans into work units
    flight_plan_generator: FlightPlanGeneratorAgent - Generates flight plans from PRDs
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.registry import ComponentRegistry

# Import agent classes
from maverick.agents.briefing import (
    ContrarianAgent,
    NavigatorAgent,
    ReconAgent,
    StructuralistAgent,
)
from maverick.agents.curator import CuratorAgent
from maverick.agents.decomposer import DecomposerAgent
from maverick.agents.fixer import FixerAgent, GateRemediationAgent
from maverick.agents.flight_plan_generator import FlightPlanGeneratorAgent
from maverick.agents.generators.consolidator import ConsolidatorAgent
from maverick.agents.implementer import ImplementerAgent
from maverick.agents.preflight_briefing import (
    CodebaseAnalystAgent,
    CriteriaWriterAgent,
    PreFlightContrarianAgent,
    ScopistAgent,
)
from maverick.agents.reviewers import (
    CompletenessReviewerAgent,
    CorrectnessReviewerAgent,
    SimpleFixerAgent,
)
from maverick.agents.seed import RunwaySeedAgent

__all__ = [
    "register_all_agents",
]


def register_all_agents(registry: ComponentRegistry) -> None:
    """Register all built-in agents with the component registry.

    This function registers agents that are referenced in workflow YAML files.
    Each agent is registered with a name that matches the YAML reference.

    Args:
        registry: Component registry to register agents with.

    Example:
        ```python
        from maverick.registry import component_registry
        from maverick.library.agents import register_all_agents

        register_all_agents(component_registry)

        # Now agents can be resolved by name
        implementer_class = component_registry.agents.get("implementer")
        ```
    """
    # Register implementer agent
    registry.agents.register("implementer", ImplementerAgent)

    # Register parallel review agents
    registry.agents.register("completeness_reviewer", CompletenessReviewerAgent)
    registry.agents.register("correctness_reviewer", CorrectnessReviewerAgent)
    registry.agents.register("simple_fixer", SimpleFixerAgent)

    # Register validation fixer agent (used in validate-and-fix fragment)
    registry.agents.register("validation_fixer", FixerAgent)

    # Register gate remediation agent (used in fly-beads gate remediation step)
    registry.agents.register("gate_remediator", GateRemediationAgent)

    # Register decomposer agent (used in refuel-maverick workflow)
    registry.agents.register("decomposer", DecomposerAgent)

    # Register flight plan generator agent (used in generate-flight-plan workflow)
    registry.agents.register("flight_plan_generator", FlightPlanGeneratorAgent)

    # Register briefing room agents (used in refuel-maverick briefing step)
    registry.agents.register("navigator", NavigatorAgent)
    registry.agents.register("structuralist", StructuralistAgent)
    registry.agents.register("recon", ReconAgent)
    registry.agents.register("contrarian", ContrarianAgent)

    # Register pre-flight briefing room agents (used in generate-flight-plan workflow)
    registry.agents.register("scopist", ScopistAgent)
    registry.agents.register("codebase_analyst", CodebaseAnalystAgent)
    registry.agents.register("criteria_writer", CriteriaWriterAgent)
    registry.agents.register("preflight_contrarian", PreFlightContrarianAgent)

    # Register runway seed agent (used in maverick runway seed).
    registry.agents.register("runway_seed", RunwaySeedAgent)

    # Register curator agent (used in maverick land for history curation).
    # CuratorAgent extends GeneratorAgent (not MaverickAgent) — skip
    # inheritance validation; it satisfies the build_prompt/name interface.
    registry.agents.register("curator", CuratorAgent, validate=False)  # type: ignore[arg-type]

    # Register consolidator agent (used in maverick land for runway consolidation).
    # ConsolidatorAgent extends GeneratorAgent (not MaverickAgent) — skip
    # inheritance validation; it satisfies the build_prompt/name interface.
    registry.agents.register("consolidator", ConsolidatorAgent, validate=False)  # type: ignore[arg-type]
