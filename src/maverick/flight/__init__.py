"""Flight Plan and Work Unit data models for Maverick.

This package provides:
- FlightPlan and WorkUnit frozen Pydantic models
- Markdown+YAML frontmatter parsing
- File loaders (FlightPlanFile, WorkUnitFile)
- Dependency resolver (resolve_execution_order)
- Round-trip serialization
- Skeleton generator (generate_skeleton)
- Structural validator (validate_flight_plan_file, ValidationIssue)

Public API::

    from maverick.flight import (
        FlightPlan, WorkUnit, FlightPlanFile, WorkUnitFile,
        resolve_execution_order, serialize_flight_plan, serialize_work_unit,
        FlightPlanNotFoundError, FlightPlanParseError, FlightPlanValidationError,
        generate_skeleton, validate_flight_plan_file, ValidationIssue,
    )
"""

from __future__ import annotations

from maverick.flight.errors import (
    FlightError,
    FlightPlanNotFoundError,
    FlightPlanParseError,
    FlightPlanValidationError,
    WorkUnitDependencyError,
    WorkUnitNotFoundError,
    WorkUnitValidationError,
)
from maverick.flight.loader import FlightPlanFile, WorkUnitFile
from maverick.flight.models import (
    AcceptanceCriterion,
    CompletionStatus,
    ExecutionBatch,
    ExecutionOrder,
    FileScope,
    FlightPlan,
    Scope,
    SuccessCriterion,
    WorkUnit,
)
from maverick.flight.parser import (
    parse_bullet_list,
    parse_checkbox_list,
    parse_flight_plan_sections,
    parse_frontmatter,
    parse_work_unit_sections,
)
from maverick.flight.resolver import resolve_execution_order
from maverick.flight.serializer import serialize_flight_plan, serialize_work_unit
from maverick.flight.template import generate_skeleton
from maverick.flight.validator import ValidationIssue, validate_flight_plan_file

__all__: list[str] = [
    # Errors
    "FlightError",
    "FlightPlanNotFoundError",
    "FlightPlanParseError",
    "FlightPlanValidationError",
    "WorkUnitDependencyError",
    "WorkUnitNotFoundError",
    "WorkUnitValidationError",
    # Models
    "AcceptanceCriterion",
    "CompletionStatus",
    "ExecutionBatch",
    "ExecutionOrder",
    "FileScope",
    "FlightPlan",
    "Scope",
    "SuccessCriterion",
    "WorkUnit",
    # Loaders
    "FlightPlanFile",
    "WorkUnitFile",
    # Resolver
    "resolve_execution_order",
    # Serializers
    "serialize_flight_plan",
    "serialize_work_unit",
    # Parser primitives
    "parse_bullet_list",
    "parse_checkbox_list",
    "parse_flight_plan_sections",
    "parse_frontmatter",
    "parse_work_unit_sections",
    # Template generator
    "generate_skeleton",
    # Validator
    "ValidationIssue",
    "validate_flight_plan_file",
]
