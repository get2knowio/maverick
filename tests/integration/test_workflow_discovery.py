"""Integration tests for workflow discovery override precedence.

This module validates the complete workflow discovery flow, including:
- Multi-location scanning (builtin, user, project)
- Override precedence rules (project > user > builtin)
- Error resilience (invalid files don't break discovery)
- Fragment discovery with same precedence rules
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from maverick.dsl.discovery import (
    DefaultWorkflowDiscovery,
    WorkflowSource,
)


class TestWorkflowDiscoveryIntegration:
    """Integration tests for complete workflow discovery flow."""

    def test_complete_discovery_flow_with_all_sources(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test discovery from builtin, user, and project with precedence.

        This test validates:
        - Discovery works with all three sources
        - Project overrides user which overrides builtin
        - Override tracking is correct in DiscoveredWorkflow.overrides
        - All valid workflows are discovered
        """
        # Set up directory structure
        os.chdir(temp_dir)

        # Create user workflows directory
        user_workflows_dir = temp_dir / ".config" / "maverick" / "workflows"
        user_workflows_dir.mkdir(parents=True)

        # Create project workflows directory
        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        # Patch home directory to use temp_dir
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Create a project workflow that overrides builtin "fly"
        project_fly_path = project_workflows_dir / "fly.yaml"
        project_fly_path.write_text("""
version: "1.0"
name: fly
description: Project-specific fly workflow (overrides builtin)

inputs:
  branch_name:
    type: string
    required: true
    description: Feature branch name

steps:
  - name: custom-init
    type: python
    action: custom_project_init
    kwargs:
      branch_name: ${{ inputs.branch_name }}
""")

        # Create a user workflow that would be overridden by project
        # (but we're testing that user has lower precedence than project)
        user_fly_path = user_workflows_dir / "fly.yaml"
        user_fly_path.write_text("""
version: "1.0"
name: fly
description: User-specific fly workflow (overridden by project)

inputs:
  branch_name:
    type: string
    required: true

steps:
  - name: user-init
    type: python
    action: user_custom_init
    kwargs:
      branch_name: ${{ inputs.branch_name }}
""")

        # Create a user-only workflow (not in builtin or project)
        user_custom_path = user_workflows_dir / "custom.yaml"
        user_custom_path.write_text("""
version: "1.0"
name: custom
description: User-only custom workflow

inputs:
  param1:
    type: string
    required: false

steps:
  - name: step1
    type: python
    action: custom_action
""")

        # Create a project-only workflow
        project_deploy_path = project_workflows_dir / "deploy.yaml"
        project_deploy_path.write_text("""
version: "1.0"
name: deploy
description: Project-specific deployment workflow

inputs:
  environment:
    type: string
    required: true

steps:
  - name: deploy-step
    type: python
    action: deploy_to_env
    kwargs:
      env: ${{ inputs.environment }}
""")

        # Run discovery
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=user_workflows_dir,
            include_builtin=True,
        )

        # Verify we found workflows from all sources
        assert len(result.workflows) > 0
        workflow_names = result.workflow_names

        # Verify builtin workflows are present (unless overridden)
        # "fly" should be present but from project source
        assert "fly" in workflow_names

        # Verify user-only workflow is present
        assert "custom" in workflow_names

        # Verify project-only workflow is present
        assert "deploy" in workflow_names

        # Verify "fly" is from project source (highest precedence)
        fly_workflow = result.get_workflow("fly")
        assert fly_workflow is not None
        assert fly_workflow.source == WorkflowSource.PROJECT.value
        assert "Project-specific fly workflow" in fly_workflow.workflow.description

        # Verify override tracking: project "fly" should override both user and builtin
        assert len(fly_workflow.overrides) > 0  # At least user "fly" is overridden
        # Check that user fly path is in overrides
        assert any(str(user_fly_path) in str(p) for p in fly_workflow.overrides)

        # Verify "custom" is from user source
        custom_workflow = result.get_workflow("custom")
        assert custom_workflow is not None
        assert custom_workflow.source == WorkflowSource.USER.value
        assert len(custom_workflow.overrides) == 0  # Nothing to override

        # Verify "deploy" is from project source
        deploy_workflow = result.get_workflow("deploy")
        assert deploy_workflow is not None
        assert deploy_workflow.source == WorkflowSource.PROJECT.value
        assert len(deploy_workflow.overrides) == 0  # Nothing to override

        # Verify builtin workflows that weren't overridden are present
        # For example, "refuel" should still be from builtin
        refuel_workflow = result.get_workflow("refuel")
        if refuel_workflow:  # May not be present if builtin library isn't installed
            assert refuel_workflow.source == WorkflowSource.BUILTIN.value
            assert len(refuel_workflow.overrides) == 0

    def test_partial_discovery_without_builtin(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test discovery with include_builtin=False.

        This test validates:
        - Discovery works when builtins are excluded
        - Only user and project workflows are found
        - No builtin workflows appear in results
        """
        os.chdir(temp_dir)

        # Create directories
        user_workflows_dir = temp_dir / ".config" / "maverick" / "workflows"
        user_workflows_dir.mkdir(parents=True)

        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Create a user workflow
        user_path = user_workflows_dir / "user-workflow.yaml"
        user_path.write_text("""
version: "1.0"
name: user-workflow
description: User workflow

inputs: {}
steps:
  - name: step1
    type: python
    action: user_action
""")

        # Create a project workflow
        project_path = project_workflows_dir / "project-workflow.yaml"
        project_path.write_text("""
version: "1.0"
name: project-workflow
description: Project workflow

inputs: {}
steps:
  - name: step1
    type: python
    action: project_action
""")

        # Run discovery WITHOUT builtins
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=user_workflows_dir,
            include_builtin=False,
        )

        # Verify we only found user and project workflows
        workflow_names = result.workflow_names
        assert "user-workflow" in workflow_names
        assert "project-workflow" in workflow_names

        # Verify no builtin workflows are present
        # (builtin workflows like "fly", "refuel", etc. should not appear)
        for wf in result.workflows:
            assert wf.source != WorkflowSource.BUILTIN.value

        # Verify sources are correct
        user_wf = result.get_workflow("user-workflow")
        assert user_wf is not None
        assert user_wf.source == WorkflowSource.USER.value

        project_wf = result.get_workflow("project-workflow")
        assert project_wf is not None
        assert project_wf.source == WorkflowSource.PROJECT.value

    def test_error_resilience_with_invalid_files(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test discovery continues when some files are invalid.

        This test validates:
        - Discovery doesn't crash when encountering invalid YAML
        - Valid workflows are still discovered
        - Invalid files appear in skipped list with error details
        """
        os.chdir(temp_dir)

        # Create project workflows directory
        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Create a valid workflow
        valid_path = project_workflows_dir / "valid.yaml"
        valid_path.write_text("""
version: "1.0"
name: valid
description: Valid workflow

inputs: {}
steps:
  - name: step1
    type: python
    action: valid_action
""")

        # Create an invalid YAML file (syntax error)
        invalid_yaml_path = project_workflows_dir / "invalid-yaml.yaml"
        invalid_yaml_path.write_text("""
version: "1.0"
name: invalid-yaml
description: This YAML is malformed
invalid: [unclosed bracket
steps:
  - name: step1
""")

        # Create a YAML file with missing required fields
        invalid_schema_path = project_workflows_dir / "invalid-schema.yaml"
        invalid_schema_path.write_text("""
version: "1.0"
# Missing 'name' field!
description: Missing name field

inputs: {}
steps: []
""")

        # Run discovery
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=None,  # No user dir
            include_builtin=False,  # Skip builtins for simplicity
        )

        # Verify valid workflow was found
        assert "valid" in result.workflow_names
        valid_wf = result.get_workflow("valid")
        assert valid_wf is not None
        assert valid_wf.source == WorkflowSource.PROJECT.value

        # Verify invalid files were skipped
        assert len(result.skipped) >= 2

        # Check that skipped files include our invalid ones
        skipped_paths = [str(s.file_path) for s in result.skipped]
        assert any("invalid-yaml.yaml" in p for p in skipped_paths)
        assert any("invalid-schema.yaml" in p for p in skipped_paths)

        # Verify error messages are populated
        for skipped in result.skipped:
            assert len(skipped.error_message) > 0
            assert len(skipped.error_type) > 0

    def test_fragment_discovery_with_override_precedence(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fragment discovery follows same precedence rules as workflows.

        This test validates:
        - Fragments are discovered from all sources
        - Fragment override precedence works (project > user > builtin)
        - Fragment overrides are tracked correctly
        """
        os.chdir(temp_dir)

        # Create directories with fragments subdirectories
        user_fragments_dir = (
            temp_dir / ".config" / "maverick" / "workflows" / "fragments"
        )
        user_fragments_dir.mkdir(parents=True)

        project_fragments_dir = temp_dir / ".maverick" / "workflows" / "fragments"
        project_fragments_dir.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Create a project fragment that overrides builtin "validate-and-fix"
        project_fragment_path = project_fragments_dir / "validate-and-fix.yaml"
        project_fragment_path.write_text("""
version: "1.0"
name: validate-and-fix
description: Project-specific validation fragment (overrides builtin)

inputs:
  stages:
    type: array
    required: false
    default: ["format", "lint"]

steps:
  - name: custom-validate
    type: python
    action: project_validate
    kwargs:
      stages: ${{ inputs.stages }}
""")

        # Create a user fragment that would be overridden by project
        user_fragment_path = user_fragments_dir / "validate-and-fix.yaml"
        user_fragment_path.write_text("""
version: "1.0"
name: validate-and-fix
description: User-specific validation fragment (overridden by project)

inputs:
  stages:
    type: array
    required: false

steps:
  - name: user-validate
    type: python
    action: user_validate
""")

        # Create a user-only fragment
        user_custom_fragment_path = user_fragments_dir / "custom-fragment.yaml"
        user_custom_fragment_path.write_text("""
version: "1.0"
name: custom-fragment
description: User-only fragment

inputs: {}
steps:
  - name: step1
    type: python
    action: fragment_action
""")

        # Run discovery
        user_workflows_dir = temp_dir / ".config" / "maverick" / "workflows"
        project_workflows_dir = temp_dir / ".maverick" / "workflows"

        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=user_workflows_dir,
            include_builtin=True,
        )

        # Verify fragments were discovered
        fragment_names = result.fragment_names
        assert "validate-and-fix" in fragment_names
        assert "custom-fragment" in fragment_names

        # Verify "validate-and-fix" is from project source (highest precedence)
        validate_fragment = result.get_fragment("validate-and-fix")
        assert validate_fragment is not None
        assert validate_fragment.source == WorkflowSource.PROJECT.value
        assert (
            "Project-specific validation fragment"
            in validate_fragment.workflow.description
        )

        # Verify override tracking for fragment
        assert len(validate_fragment.overrides) > 0
        assert any(
            str(user_fragment_path) in str(p) for p in validate_fragment.overrides
        )

        # Verify user-only fragment is from user source
        custom_fragment = result.get_fragment("custom-fragment")
        assert custom_fragment is not None
        assert custom_fragment.source == WorkflowSource.USER.value
        assert len(custom_fragment.overrides) == 0

    def test_builtin_workflows_from_library(self) -> None:
        """Test discovery includes real builtin workflows from maverick.library.

        This test validates:
        - Builtin workflows are accessible
        - They have correct metadata
        - They can be parsed and loaded
        """
        discovery = DefaultWorkflowDiscovery()

        # Run discovery with ONLY builtins (no user/project dirs)
        result = discovery.discover(
            project_dir=None,
            user_dir=None,
            include_builtin=True,
        )

        # Verify we found builtin workflows
        # At minimum, we should have the core workflows
        workflow_names = result.workflow_names

        # Check for expected builtin workflows (based on library/builtins.py)
        # Note: These may not all be present if library isn't fully installed,
        # but at least some should be
        expected_builtins = {"fly-beads", "refuel-speckit"}
        found_builtins = expected_builtins.intersection(workflow_names)
        assert len(found_builtins) > 0, (
            f"Expected at least one builtin workflow, found: {workflow_names}"
        )

        # Verify all found workflows are from builtin source
        for wf in result.workflows:
            assert wf.source == WorkflowSource.BUILTIN.value

        # Verify we can load a specific builtin workflow
        if "fly-beads" in workflow_names:
            fly = result.get_workflow("fly-beads")
            assert fly is not None
            assert fly.workflow.name == "fly-beads"
            assert fly.workflow.version is not None
            assert len(fly.workflow.steps) > 0
            # Verify it has expected inputs
            assert "epic_id" in fly.workflow.inputs

    def test_builtin_fragments_from_library(self) -> None:
        """Test discovery includes real builtin fragments from maverick.library.

        This test validates:
        - Builtin fragments are accessible
        - They have correct metadata
        - Fragment directory structure is recognized
        """
        discovery = DefaultWorkflowDiscovery()

        # Run discovery with ONLY builtins
        result = discovery.discover(
            project_dir=None,
            user_dir=None,
            include_builtin=True,
        )

        # Verify we found builtin fragments
        fragment_names = result.fragment_names

        # Check for expected builtin fragments (based on library/builtins.py)
        expected_fragments = {
            "validate-and-fix",
            "commit-and-push",
            "create-pr-with-summary",
        }
        found_fragments = expected_fragments.intersection(fragment_names)
        assert len(found_fragments) > 0, (
            f"Expected at least one builtin fragment, found: {fragment_names}"
        )

        # Verify all found fragments are from builtin source
        for frag in result.fragments:
            assert frag.source == WorkflowSource.BUILTIN.value

        # Verify we can load a specific builtin fragment
        if "validate-and-fix" in fragment_names:
            validate_frag = result.get_fragment("validate-and-fix")
            assert validate_frag is not None
            assert validate_frag.workflow.name == "validate-and-fix"
            assert validate_frag.workflow.version is not None
            assert len(validate_frag.workflow.steps) > 0

    def test_discovery_performance_metrics(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that discovery result includes performance metrics.

        This test validates:
        - Discovery time is tracked
        - Locations scanned are recorded
        - Metrics are reasonable
        """
        os.chdir(temp_dir)

        # Create minimal directory structure
        project_workflows_dir = temp_dir / ".maverick" / "workflows"
        project_workflows_dir.mkdir(parents=True)

        # Create one simple workflow
        workflow_path = project_workflows_dir / "test.yaml"
        workflow_path.write_text("""
version: "1.0"
name: test
description: Test workflow

inputs: {}
steps:
  - name: step1
    type: python
    action: test_action
""")

        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Run discovery
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(
            project_dir=project_workflows_dir,
            user_dir=None,
            include_builtin=False,
        )

        # Verify performance metrics are present
        assert result.discovery_time_ms > 0
        assert result.discovery_time_ms < 10000  # Should be under 10 seconds

        # Verify locations scanned are recorded
        assert len(result.locations_scanned) > 0
        scanned_paths = [str(p) for p in result.locations_scanned]
        assert any(str(project_workflows_dir) in p for p in scanned_paths)
