"""Deterministic Spec Kit artifact layer — parsing, detection, and
ingestion-plan building. No ``bd``/VCS side effects; see
``maverick.workflows.refuel_speckit`` for the workflow that consumes it.
"""

from __future__ import annotations

from maverick.speckit.build import (
    EPIC_TASK_ID,
    IngestionPlan,
    PlannedBead,
    build_ingestion_plan,
    derive_dependency_edges,
)
from maverick.speckit.detect import (
    SUPPORTED_SPECKIT_RANGE,
    FeatureResolution,
    TemplateCompatibility,
    check_template_compatibility,
    resolve_feature,
)
from maverick.speckit.enrichment import (
    apply_enrichment,
    build_enrichment_prompt,
    parse_enrichment_response,
)
from maverick.speckit.errors import (
    AmbiguousFeatureError,
    NothingToIngestError,
    SpeckitError,
    SpeckitParseError,
    SpeckitValidationError,
    UnsupportedTemplateError,
)
from maverick.speckit.models import ParsedSpec, SpeckitFeature, SpeckitPhase, SpeckitTask
from maverick.speckit.parser import parse_spec_md, parse_tasks_md

__all__ = [
    "EPIC_TASK_ID",
    "SUPPORTED_SPECKIT_RANGE",
    "AmbiguousFeatureError",
    "FeatureResolution",
    "IngestionPlan",
    "NothingToIngestError",
    "ParsedSpec",
    "PlannedBead",
    "SpeckitError",
    "SpeckitFeature",
    "SpeckitParseError",
    "SpeckitPhase",
    "SpeckitTask",
    "SpeckitValidationError",
    "TemplateCompatibility",
    "UnsupportedTemplateError",
    "apply_enrichment",
    "build_enrichment_prompt",
    "build_ingestion_plan",
    "check_template_compatibility",
    "derive_dependency_edges",
    "parse_enrichment_response",
    "parse_spec_md",
    "parse_tasks_md",
    "resolve_feature",
]
