"""Maverick Workflows Module.

Provides Python-native workflow implementations and the PythonWorkflow
abstract base class.

Available built-in Python workflows:
    - FlyBeadsWorkflow: Bead-driven development workflow
    - RefuelMaverickWorkflow: Flight-plan-to-beads decomposition pipeline
    - GenerateFlightPlanWorkflow: PRD-to-flight-plan generation

Custom Python workflows can subclass PythonWorkflow:
    from maverick.workflows import PythonWorkflow
"""

from __future__ import annotations

from maverick.workflows.base import PythonRollbackAction, PythonWorkflow
from maverick.workflows.fly_beads import FlyBeadsWorkflow

__all__ = [
    "PythonWorkflow",
    "PythonRollbackAction",
    "FlyBeadsWorkflow",
]
