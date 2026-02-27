"""Maverick Workflows Module.

Provides Python-native workflow implementations and the PythonWorkflow
abstract base class.

To run a workflow from the CLI:
    maverick fly
    maverick refuel speckit <spec>

Available built-in Python workflows:
    - FlyBeadsWorkflow: Bead-driven development workflow
    - RefuelSpeckitWorkflow: Spec-to-beads pipeline

Custom Python workflows can subclass PythonWorkflow:
    from maverick.workflows import PythonWorkflow
"""

from __future__ import annotations

from maverick.workflows.base import PythonRollbackAction, PythonWorkflow
from maverick.workflows.fly_beads import FlyBeadsWorkflow
from maverick.workflows.refuel_speckit import RefuelSpeckitWorkflow

__all__ = [
    "PythonWorkflow",
    "PythonRollbackAction",
    "FlyBeadsWorkflow",
    "RefuelSpeckitWorkflow",
]
