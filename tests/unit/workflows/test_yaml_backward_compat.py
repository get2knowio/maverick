"""YAML backward-compatibility regression tests for feature 035-python-workflow.

These tests verify that migrating the fly and refuel speckit commands to Python
workflow classes did NOT break the underlying YAML-based workflow infrastructure.

None of these tests actually execute workflows — they only verify that the
relevant modules, files, and classes still exist and are importable.
"""

from __future__ import annotations

from pathlib import Path


def test_yaml_workflow_files_still_exist() -> None:
    """fly-beads.yaml and refuel-speckit.yaml still exist in the library."""
    library_dir = (
        Path(__file__).parents[3] / "src" / "maverick" / "library" / "workflows"
    )
    fly_beads_yaml = library_dir / "fly-beads.yaml"
    refuel_speckit_yaml = library_dir / "refuel-speckit.yaml"

    assert fly_beads_yaml.exists(), (
        f"fly-beads.yaml not found at {fly_beads_yaml}. "
        "YAML workflows must be preserved for backward compatibility."
    )
    assert refuel_speckit_yaml.exists(), (
        f"refuel-speckit.yaml not found at {refuel_speckit_yaml}. "
        "YAML workflows must be preserved for backward compatibility."
    )


def test_workflow_discovery_still_works() -> None:
    """WorkflowFileExecutor can still be imported and instantiated."""
    from maverick.dsl.serialization import WorkflowFileExecutor

    assert WorkflowFileExecutor is not None
    assert callable(WorkflowFileExecutor)


def test_execute_workflow_run_still_importable() -> None:
    """execute_workflow_run still exists and is importable from workflow_executor."""
    from maverick.cli.workflow_executor import execute_workflow_run

    assert execute_workflow_run is not None
    assert callable(execute_workflow_run)


def test_render_workflow_events_importable() -> None:
    """render_workflow_events is importable from workflow_executor (new in T014)."""
    from maverick.cli.workflow_executor import render_workflow_events

    assert render_workflow_events is not None
    assert callable(render_workflow_events)


def test_python_workflow_run_config_importable() -> None:
    """PythonWorkflowRunConfig is importable from workflow_executor (new in T015)."""
    from maverick.cli.workflow_executor import PythonWorkflowRunConfig

    assert PythonWorkflowRunConfig is not None


def test_execute_python_workflow_importable() -> None:
    """execute_python_workflow is importable from workflow_executor (new in T015)."""
    from maverick.cli.workflow_executor import execute_python_workflow

    assert execute_python_workflow is not None
    assert callable(execute_python_workflow)


def test_python_workflow_classes_importable() -> None:
    """PythonWorkflow, FlyBeadsWorkflow, RefuelSpeckitWorkflow are importable."""
    from maverick.workflows import (
        FlyBeadsWorkflow,
        PythonWorkflow,
        RefuelSpeckitWorkflow,
    )

    assert PythonWorkflow is not None
    assert FlyBeadsWorkflow is not None
    assert RefuelSpeckitWorkflow is not None


def test_workflows_init_exports() -> None:
    """maverick.workflows.__all__ contains the expected classes."""
    import maverick.workflows as wf_module

    expected = {
        "PythonWorkflow",
        "PythonRollbackAction",
        "FlyBeadsWorkflow",
        "RefuelSpeckitWorkflow",
    }
    actual = set(wf_module.__all__)
    missing = expected - actual
    assert not missing, (
        f"maverick.workflows.__all__ is missing: {missing}. "
        "Update workflows/__init__.py to export all workflow classes."
    )


def test_python_workflow_run_config_has_required_fields() -> None:
    """PythonWorkflowRunConfig can be instantiated with workflow_class only."""
    from maverick.cli.workflow_executor import PythonWorkflowRunConfig
    from maverick.workflows import FlyBeadsWorkflow

    cfg = PythonWorkflowRunConfig(workflow_class=FlyBeadsWorkflow)
    assert cfg.workflow_class is FlyBeadsWorkflow
    assert cfg.inputs == {}
    assert cfg.session_log_path is None
    assert cfg.restart is False


def test_fly_beads_workflow_has_workflow_name_constant() -> None:
    """FlyBeadsWorkflow's constants module still exposes WORKFLOW_NAME."""
    from maverick.workflows.fly_beads.constants import WORKFLOW_NAME

    assert WORKFLOW_NAME == "fly-beads"


def test_refuel_speckit_workflow_has_workflow_name_constant() -> None:
    """RefuelSpeckitWorkflow's constants module still exposes WORKFLOW_NAME."""
    from maverick.workflows.refuel_speckit.constants import WORKFLOW_NAME

    assert WORKFLOW_NAME == "refuel-speckit"
