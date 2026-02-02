"""Composable prerequisite system for workflow execution.

This package provides a declarative prerequisite system where:
- Steps can declare `requires: [prereq_names]` in YAML
- Actions/agents declare default prerequisites at registration time
- The executor aggregates unique prerequisites and runs them before workflow start

Components:
- models: Prerequisite, PrerequisiteResult, PreflightPlan dataclasses
- registry: PrerequisiteRegistry - catalog of all checks
- checks: Built-in check functions (git, gh, anthropic, etc.)
- collector: PrerequisiteCollector - scans workflows, resolves prereqs
- runner: PrerequisiteRunner - executes checks with dependency ordering
"""

from __future__ import annotations

# Import checks module to register built-in checks
from maverick.dsl.prerequisites import checks as _checks  # noqa: F401
from maverick.dsl.prerequisites.collector import PrerequisiteCollector
from maverick.dsl.prerequisites.models import (
    PreflightCheckResult,
    PreflightPlan,
    PreflightResult,
    Prerequisite,
    PrerequisiteResult,
)
from maverick.dsl.prerequisites.registry import (
    PrerequisiteRegistry,
    prerequisite_registry,
)
from maverick.dsl.prerequisites.runner import PrerequisiteRunner

__all__ = [
    # Models
    "Prerequisite",
    "PrerequisiteResult",
    "PreflightCheckResult",
    "PreflightPlan",
    "PreflightResult",
    # Registry
    "PrerequisiteRegistry",
    "prerequisite_registry",
    # Collector
    "PrerequisiteCollector",
    # Runner
    "PrerequisiteRunner",
]
