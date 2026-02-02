"""Unit tests for the prerequisite collector."""

from __future__ import annotations

import pytest

from maverick.dsl.prerequisites.collector import PrerequisiteCollector
from maverick.dsl.prerequisites.models import PrerequisiteResult
from maverick.dsl.prerequisites.registry import PrerequisiteRegistry
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import PythonStepRecord, WorkflowFile
from maverick.dsl.types import StepType


@pytest.fixture
def prereq_registry() -> PrerequisiteRegistry:
    """Create a prerequisite registry with some test prerequisites."""
    registry = PrerequisiteRegistry()

    @registry.register(name="git", display_name="Git")
    async def check_git() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="OK")

    @registry.register(name="git_repo", display_name="Git Repo", dependencies=("git",))
    async def check_repo() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="OK")

    @registry.register(
        name="git_identity", display_name="Git ID", dependencies=("git",)
    )
    async def check_id() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="OK")

    @registry.register(name="gh", display_name="GitHub CLI")
    async def check_gh() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="OK")

    @registry.register(name="gh_auth", display_name="GitHub Auth", dependencies=("gh",))
    async def check_gh_auth() -> PrerequisiteResult:
        return PrerequisiteResult(success=True, message="OK")

    return registry


@pytest.fixture
def component_registry() -> ComponentRegistry:
    """Create a component registry with some test actions."""
    registry = ComponentRegistry()

    def do_nothing() -> None:
        pass

    registry.actions.register("simple_action", do_nothing)
    registry.actions.register("git_action", do_nothing, requires=("git", "git_repo"))
    registry.actions.register("github_action", do_nothing, requires=("gh", "gh_auth"))

    return registry


class TestPrerequisiteCollector:
    """Tests for PrerequisiteCollector."""

    def test_collect_no_prerequisites(
        self,
        prereq_registry: PrerequisiteRegistry,
        component_registry: ComponentRegistry,
    ) -> None:
        """Test collecting from workflow where actions have no prerequisites."""
        workflow = WorkflowFile(
            version="1.0",
            name="simple",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="simple_action",
                )
            ],
        )

        collector = PrerequisiteCollector()
        plan = collector.collect(workflow, component_registry, prereq_registry)

        assert plan.prerequisites == ()

    def test_collect_action_prerequisites(
        self,
        prereq_registry: PrerequisiteRegistry,
        component_registry: ComponentRegistry,
    ) -> None:
        """Test collecting prerequisites from action registrations."""
        workflow = WorkflowFile(
            version="1.0",
            name="git-workflow",
            steps=[
                PythonStepRecord(
                    name="git_step",
                    type=StepType.PYTHON,
                    action="git_action",
                )
            ],
        )

        collector = PrerequisiteCollector()
        plan = collector.collect(workflow, component_registry, prereq_registry)

        # Should collect git and git_repo from action
        assert "git" in plan.prerequisites
        assert "git_repo" in plan.prerequisites

        # Execution order should respect dependencies (git before git_repo)
        git_idx = plan.execution_order.index("git")
        repo_idx = plan.execution_order.index("git_repo")
        assert git_idx < repo_idx

    def test_collect_step_level_requires(
        self,
        prereq_registry: PrerequisiteRegistry,
        component_registry: ComponentRegistry,
    ) -> None:
        """Test collecting prerequisites from step-level requires field."""
        workflow = WorkflowFile(
            version="1.0",
            name="step-requires",
            steps=[
                PythonStepRecord(
                    name="commit_step",
                    type=StepType.PYTHON,
                    action="simple_action",
                    requires=["git_identity"],
                )
            ],
        )

        collector = PrerequisiteCollector()
        plan = collector.collect(workflow, component_registry, prereq_registry)

        # Should collect git_identity and its dependency (git)
        assert "git_identity" in plan.prerequisites
        assert "git" in plan.execution_order  # Transitive dependency

    def test_collect_merges_multiple_steps(
        self,
        prereq_registry: PrerequisiteRegistry,
        component_registry: ComponentRegistry,
    ) -> None:
        """Test that prerequisites from multiple steps are merged."""
        workflow = WorkflowFile(
            version="1.0",
            name="multi-step",
            steps=[
                PythonStepRecord(
                    name="git_step",
                    type=StepType.PYTHON,
                    action="git_action",
                ),
                PythonStepRecord(
                    name="gh_step",
                    type=StepType.PYTHON,
                    action="github_action",
                ),
            ],
        )

        collector = PrerequisiteCollector()
        plan = collector.collect(workflow, component_registry, prereq_registry)

        # Should have both git and gh prerequisites
        assert "git" in plan.prerequisites
        assert "gh" in plan.prerequisites

    def test_collect_deduplicates(
        self,
        prereq_registry: PrerequisiteRegistry,
        component_registry: ComponentRegistry,
    ) -> None:
        """Test that duplicate prerequisites are deduplicated."""
        workflow = WorkflowFile(
            version="1.0",
            name="duplicate",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="git_action",
                ),
                PythonStepRecord(
                    name="step2",
                    type=StepType.PYTHON,
                    action="git_action",  # Same action, same prereqs
                ),
            ],
        )

        collector = PrerequisiteCollector()
        plan = collector.collect(workflow, component_registry, prereq_registry)

        # Each prerequisite should appear only once in execution_order
        assert plan.execution_order.count("git") == 1
        assert plan.execution_order.count("git_repo") == 1

    def test_collect_tracks_affected_steps(
        self,
        prereq_registry: PrerequisiteRegistry,
        component_registry: ComponentRegistry,
    ) -> None:
        """Test that step_requirements tracks which steps need each prerequisite."""
        workflow = WorkflowFile(
            version="1.0",
            name="tracking",
            steps=[
                PythonStepRecord(
                    name="init",
                    type=StepType.PYTHON,
                    action="git_action",
                ),
                PythonStepRecord(
                    name="commit",
                    type=StepType.PYTHON,
                    action="simple_action",
                    requires=["git_identity"],
                ),
            ],
        )

        collector = PrerequisiteCollector()
        plan = collector.collect(workflow, component_registry, prereq_registry)

        # git is needed by init (from action)
        assert "init" in plan.step_requirements.get("git", ())
        # git_identity is needed by commit (from step-level requires)
        assert "commit" in plan.step_requirements.get("git_identity", ())

    def test_collect_unknown_prerequisite_skipped(
        self,
        prereq_registry: PrerequisiteRegistry,
        component_registry: ComponentRegistry,
    ) -> None:
        """Test that unknown prerequisites are skipped with warning."""
        workflow = WorkflowFile(
            version="1.0",
            name="unknown",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="simple_action",
                    requires=["nonexistent_prereq"],
                )
            ],
        )

        collector = PrerequisiteCollector()
        plan = collector.collect(workflow, component_registry, prereq_registry)

        # Unknown prerequisite should be filtered out
        assert "nonexistent_prereq" not in plan.execution_order
