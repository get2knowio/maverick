"""API contracts for the maverick.flight package.

This file defines the public API surface — the classes, functions, and types
that consumers import and use. It serves as a contract specification, NOT
executable code. See data-model.md for field details and validation rules.
"""

from __future__ import annotations


# =============================================================================
# Models (frozen Pydantic BaseModel, all in models.py)
# =============================================================================

# FlightPlan: The top-level planning document model.
#   - Properties: name, version, created, tags, objective, success_criteria,
#                 scope, context, constraints, notes, source_path
#   - Computed:   completion -> CompletionStatus
#   - Methods:    to_dict() -> dict[str, object]

# WorkUnit: The actionable task document model.
#   - Properties: id, flight_plan, sequence, parallel_group, depends_on,
#                 task, acceptance_criteria, file_scope, instructions,
#                 verification, provider_hints, source_path
#   - Methods:    to_dict() -> dict[str, object]

# SuccessCriterion: Individual criterion with checked state.
#   - Properties: text, checked

# CompletionStatus: Computed completion stats.
#   - Properties: checked, total, percentage (float | None)

# Scope: In/Out/Boundaries subsections.
#   - Properties: in_scope, out_of_scope, boundaries (all tuple[str, ...])

# AcceptanceCriterion: Individual criterion with optional trace ref.
#   - Properties: text, trace_ref (str | None)

# FileScope: Create/Modify/Protect file lists.
#   - Properties: create, modify, protect (all tuple[str, ...])

# ExecutionOrder: Resolved execution batches.
#   - Properties: batches (tuple[ExecutionBatch, ...])

# ExecutionBatch: Parallelizable work unit group.
#   - Properties: units (tuple[WorkUnit, ...]), parallel_group (str | None)


# =============================================================================
# Parser (parser.py)
# =============================================================================

# parse_frontmatter(content: str) -> tuple[dict[str, Any], str]
#   Splits Markdown+YAML content into (metadata_dict, markdown_body).
#   Raises FlightPlanParseError on malformed input.

# parse_flight_plan_sections(body: str) -> dict[str, str | dict[str, str]]
#   Extracts named sections from Markdown body.
#   Returns dict mapping section names to content strings.

# parse_work_unit_sections(body: str) -> dict[str, str | dict[str, str]]
#   Extracts named sections from Work Unit Markdown body.
#   Returns dict mapping section names to content strings.

# parse_checkbox_list(content: str) -> list[tuple[bool, str]]
#   Parses checkbox lines into (checked, text) tuples.

# parse_bullet_list(content: str) -> list[str]
#   Parses bullet list lines into strings.


# =============================================================================
# Serializer (serializer.py)
# =============================================================================

# serialize_flight_plan(plan: FlightPlan) -> str
#   Converts FlightPlan model to Markdown+YAML string.
#   Output is valid for re-loading (round-trip fidelity).

# serialize_work_unit(unit: WorkUnit) -> str
#   Converts WorkUnit model to Markdown+YAML string.
#   Output is valid for re-loading (round-trip fidelity).


# =============================================================================
# Loader (loader.py)
# =============================================================================

# FlightPlanFile: File loading facade for Flight Plans.
#
#   @classmethod
#   def load(cls, path: Path) -> FlightPlan:
#       """Load a Flight Plan from a Markdown file (synchronous)."""
#
#   @classmethod
#   async def aload(cls, path: Path) -> FlightPlan:
#       """Load a Flight Plan from a Markdown file (asynchronous)."""
#
#   @classmethod
#   def save(cls, plan: FlightPlan, path: Path) -> None:
#       """Save a Flight Plan to a Markdown file (synchronous)."""
#
#   @classmethod
#   async def asave(cls, plan: FlightPlan, path: Path) -> None:
#       """Save a Flight Plan to a Markdown file (asynchronous)."""

# WorkUnitFile: File loading facade for Work Units.
#
#   @classmethod
#   def load(cls, path: Path) -> WorkUnit:
#       """Load a Work Unit from a Markdown file (synchronous)."""
#
#   @classmethod
#   async def aload(cls, path: Path) -> WorkUnit:
#       """Load a Work Unit from a Markdown file (asynchronous)."""
#
#   @classmethod
#   def load_directory(cls, directory: Path) -> list[WorkUnit]:
#       """Load all Work Units from a directory (synchronous).
#       Discovers files matching ###-slug.md pattern."""
#
#   @classmethod
#   async def aload_directory(cls, directory: Path) -> list[WorkUnit]:
#       """Load all Work Units from a directory (asynchronous)."""
#
#   @classmethod
#   def save(cls, unit: WorkUnit, path: Path) -> None:
#       """Save a Work Unit to a Markdown file (synchronous)."""
#
#   @classmethod
#   async def asave(cls, unit: WorkUnit, path: Path) -> None:
#       """Save a Work Unit to a Markdown file (asynchronous)."""


# =============================================================================
# Resolver (resolver.py)
# =============================================================================

# resolve_execution_order(units: list[WorkUnit]) -> ExecutionOrder:
#   Resolves dependency order using topological sort.
#   Groups units by parallel_group within each dependency tier.
#   Raises WorkUnitDependencyError on circular or missing dependencies.


# =============================================================================
# Errors (errors.py, re-exports from exceptions/flight.py)
# =============================================================================

# FlightError(MaverickError): Base error for flight package.
# FlightPlanParseError(FlightError): YAML/Markdown parsing failure.
# FlightPlanValidationError(FlightError): Model validation failure.
# FlightPlanNotFoundError(FlightError): File not found.
# WorkUnitValidationError(FlightError): Work Unit model validation failure.
# WorkUnitDependencyError(FlightError): Dependency resolution failure.


# =============================================================================
# Package __init__.py exports
# =============================================================================

# __all__ = [
#     # Models
#     "FlightPlan",
#     "WorkUnit",
#     "SuccessCriterion",
#     "CompletionStatus",
#     "Scope",
#     "AcceptanceCriterion",
#     "FileScope",
#     "ExecutionOrder",
#     "ExecutionBatch",
#     # Loader
#     "FlightPlanFile",
#     "WorkUnitFile",
#     # Resolver
#     "resolve_execution_order",
#     # Serializer
#     "serialize_flight_plan",
#     "serialize_work_unit",
#     # Parser
#     "parse_frontmatter",
#     # Errors
#     "FlightError",
#     "FlightPlanParseError",
#     "FlightPlanValidationError",
#     "FlightPlanNotFoundError",
#     "WorkUnitValidationError",
#     "WorkUnitDependencyError",
# ]
