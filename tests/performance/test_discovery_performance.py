"""Performance tests for workflow discovery.

This module validates that workflow discovery meets performance requirements:
- T064: Discovery must complete in under 500ms for 100 workflow files
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.discovery import DefaultWorkflowDiscovery


class TestDiscoveryPerformance:
    """Performance tests for workflow discovery."""

    def test_discovery_performance_100_workflows(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test discovery completes in under 500ms for 100 workflow files.

        This test validates:
        - Discovery can handle 100 workflow files
        - Discovery completes in under 500ms
        - All workflows are discovered correctly

        Performance requirement: < 500ms (T064)
        """
        # Set up directory structure
        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        # Create 100 minimal workflow files
        # Using minimal valid YAML to focus on discovery overhead
        for i in range(100):
            workflow_path = project_workflows_dir / f"workflow-{i:03d}.yaml"
            workflow_content = f"""version: "1.0"
name: workflow-{i:03d}
description: Test workflow {i}

inputs: {{}}
steps:
  - name: step1
    type: python
    action: test_action_{i}
"""
            workflow_path.write_text(workflow_content)

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Run discovery and measure performance
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=None,
            include_builtin=False,  # Exclude builtins to isolate test performance
        )

        # Verify all workflows were discovered
        assert len(result.workflows) == 100, (
            f"Expected 100 workflows, found {len(result.workflows)}"
        )

        # Verify performance requirement: < 500ms
        assert result.discovery_time_ms < 500, (
            f"Discovery took {result.discovery_time_ms:.2f}ms, requirement is < 500ms"
        )

        # Report performance metrics
        print("\n=== Discovery Performance Metrics ===")
        print(f"Workflows discovered: {len(result.workflows)}")
        print(f"Discovery time: {result.discovery_time_ms:.2f}ms")
        print(f"Average per workflow: {result.discovery_time_ms / 100:.2f}ms")
        print(f"Skipped files: {len(result.skipped)}")
        print(f"Locations scanned: {len(result.locations_scanned)}")

        # Verify all workflow names are correct
        workflow_names = result.workflow_names
        for i in range(100):
            expected_name = f"workflow-{i:03d}"
            assert expected_name in workflow_names, (
                f"Expected workflow {expected_name} not found"
            )

    def test_discovery_performance_with_fragments(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test discovery performance with mixed workflows and fragments.

        This test validates:
        - Discovery handles 50 workflows + 50 fragments efficiently
        - Performance remains under 500ms with mixed content
        - Fragment discovery doesn't significantly impact performance

        Performance requirement: < 500ms (T064)
        """
        # Set up directory structure
        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        project_fragments_dir = project_workflows_dir / "fragments"
        project_fragments_dir.mkdir(parents=True)

        # Create 50 workflows
        for i in range(50):
            workflow_path = project_workflows_dir / f"workflow-{i:03d}.yaml"
            workflow_content = f"""version: "1.0"
name: workflow-{i:03d}
description: Test workflow {i}

inputs: {{}}
steps:
  - name: step1
    type: python
    action: test_action_{i}
"""
            workflow_path.write_text(workflow_content)

        # Create 50 fragments
        for i in range(50):
            fragment_path = project_fragments_dir / f"fragment-{i:03d}.yaml"
            fragment_content = f"""version: "1.0"
name: fragment-{i:03d}
description: Test fragment {i}

inputs: {{}}
steps:
  - name: step1
    type: python
    action: test_action_{i}
"""
            fragment_path.write_text(fragment_content)

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Run discovery
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=None,
            include_builtin=False,
        )

        # Verify all workflows and fragments were discovered
        assert len(result.workflows) == 50, (
            f"Expected 50 workflows, found {len(result.workflows)}"
        )
        assert len(result.fragments) == 50, (
            f"Expected 50 fragments, found {len(result.fragments)}"
        )

        # Verify performance requirement: < 500ms
        assert result.discovery_time_ms < 500, (
            f"Discovery took {result.discovery_time_ms:.2f}ms, requirement is < 500ms"
        )

        # Report performance metrics
        print("\n=== Discovery Performance Metrics (Mixed) ===")
        print(f"Workflows discovered: {len(result.workflows)}")
        print(f"Fragments discovered: {len(result.fragments)}")
        print(f"Total files: {len(result.workflows) + len(result.fragments)}")
        print(f"Discovery time: {result.discovery_time_ms:.2f}ms")
        print(f"Average per file: {result.discovery_time_ms / 100:.2f}ms")

    def test_discovery_performance_with_nested_directories(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test discovery performance with nested directory structure.

        This test validates:
        - Discovery handles nested directories efficiently
        - Recursive glob doesn't cause significant slowdown
        - Performance remains under 500ms

        Performance requirement: < 500ms (T064)
        """
        # Set up nested directory structure
        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        # Create workflows in nested directories (10 dirs, 10 workflows each)
        for dir_idx in range(10):
            subdir = project_workflows_dir / f"category-{dir_idx}"
            subdir.mkdir(parents=True)

            for file_idx in range(10):
                workflow_path = subdir / f"workflow-{dir_idx}-{file_idx}.yaml"
                workflow_content = f"""version: "1.0"
name: workflow-{dir_idx}-{file_idx}
description: Test workflow {dir_idx}-{file_idx}

inputs: {{}}
steps:
  - name: step1
    type: python
    action: test_action_{dir_idx}_{file_idx}
"""
                workflow_path.write_text(workflow_content)

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Run discovery
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=None,
            include_builtin=False,
        )

        # Verify all workflows were discovered
        assert len(result.workflows) == 100, (
            f"Expected 100 workflows, found {len(result.workflows)}"
        )

        # Verify performance requirement: < 500ms
        assert result.discovery_time_ms < 500, (
            f"Discovery took {result.discovery_time_ms:.2f}ms, requirement is < 500ms"
        )

        # Report performance metrics
        print("\n=== Discovery Performance Metrics (Nested) ===")
        print(f"Workflows discovered: {len(result.workflows)}")
        print(f"Discovery time: {result.discovery_time_ms:.2f}ms")
        print(f"Average per workflow: {result.discovery_time_ms / 100:.2f}ms")
        print("Directory depth: 2 levels")

    @pytest.mark.benchmark
    def test_discovery_performance_benchmark_200_workflows(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Benchmark test with 200 workflows to identify scaling limits.

        This test validates:
        - Discovery can handle larger numbers of workflows
        - Performance scaling characteristics
        - Identifies if there are O(n^2) bottlenecks

        Note: This test is marked as benchmark and may be skipped in CI.
        """
        # Set up directory structure
        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        # Create 200 workflows
        for i in range(200):
            workflow_path = project_workflows_dir / f"workflow-{i:03d}.yaml"
            workflow_content = f"""version: "1.0"
name: workflow-{i:03d}
description: Test workflow {i}

inputs: {{}}
steps:
  - name: step1
    type: python
    action: test_action_{i}
"""
            workflow_path.write_text(workflow_content)

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Run discovery
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=None,
            include_builtin=False,
        )

        # Verify all workflows were discovered
        assert len(result.workflows) == 200, (
            f"Expected 200 workflows, found {len(result.workflows)}"
        )

        # Report performance metrics (no strict requirement for benchmark)
        print("\n=== Discovery Performance Benchmark (200 workflows) ===")
        print(f"Workflows discovered: {len(result.workflows)}")
        print(f"Discovery time: {result.discovery_time_ms:.2f}ms")
        print(f"Average per workflow: {result.discovery_time_ms / 200:.2f}ms")

        # Check if scaling is roughly linear
        # If time per workflow is similar to 100-workflow test, scaling is good
        avg_time_per_workflow = result.discovery_time_ms / 200
        print("\nScaling analysis:")
        print(f"  Average time per workflow: {avg_time_per_workflow:.3f}ms")
        if avg_time_per_workflow > 5.0:
            print("  WARNING: Performance may degrade with large numbers of workflows")
