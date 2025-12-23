"""Integration tests for fragment override precedence.

Tests that project fragments override user fragments which override built-in fragments.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.dsl.discovery.models import WorkflowSource
from maverick.dsl.discovery.registry import DefaultWorkflowDiscovery


@pytest.fixture
def discovery_setup(tmp_path: Path):
    """Setup directory structure for discovery tests."""
    project_dir = tmp_path / "project"
    user_dir = tmp_path / "user_config"

    # Create structure
    (project_dir / ".maverick" / "workflows" / "fragments").mkdir(parents=True)
    (user_dir / "maverick" / "workflows" / "fragments").mkdir(parents=True)

    return project_dir, user_dir


def test_fragment_project_overrides_user(discovery_setup: tuple[Path, Path]):
    """Test that project fragment overrides user fragment."""
    project_dir, user_dir = discovery_setup

    # Create same fragment in both locations
    frag_name = "test-fragment.yaml"

    # User fragment
    user_frag = user_dir / "maverick" / "workflows" / "fragments" / frag_name
    user_frag.write_text("""
version: \"1.0\"
name: test-fragment
description: User version
steps:
  - name: dummy
    type: python
    action: print
    kwargs: {msg: \"test\"}
""")

    # Project fragment
    project_frag = project_dir / ".maverick" / "workflows" / "fragments" / frag_name
    project_frag.write_text("""
version: \"1.0\"
name: test-fragment
description: Project version
steps:
  - name: dummy
    type: python
    action: print
    kwargs: {msg: \"test\"}
""")

    # Mock paths in discovery
    with (
        patch.object(
            DefaultWorkflowDiscovery,
            "get_user_path",
            return_value=user_dir / "maverick" / "workflows",
        ),
        patch.object(
            DefaultWorkflowDiscovery,
            "get_project_path",
            return_value=project_dir / ".maverick" / "workflows",
        ),
    ):
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(include_builtin=False)

        # Debug
        print(f"Scanned locations: {result.locations_scanned}")
        print(f"Skipped: {result.skipped}")
        print(f"Fragments found: {[f.workflow.name for f in result.fragments]}")

        # Find the fragment
        fragments = [f for f in result.fragments if f.workflow.name == "test-fragment"]
        assert len(fragments) == 1

        discovered = fragments[0]
        assert discovered.source == WorkflowSource.PROJECT.value
        assert discovered.workflow.description == "Project version"

        # Verify overrides list contains user version
        assert len(discovered.overrides) == 1
        assert str(user_frag.resolve()) == str(discovered.overrides[0])


def test_fragment_user_overrides_builtin(
    discovery_setup: tuple[Path, Path], tmp_path: Path
):
    """Test that user fragment overrides builtin fragment."""
    project_dir, user_dir = discovery_setup

    # Create fake builtin directory that satisfies _infer_source
    # Must contain "maverick/library"
    builtin_root = tmp_path / "fake_package" / "maverick" / "library"
    builtin_fragments_dir = builtin_root / "fragments"
    builtin_fragments_dir.mkdir(parents=True)

    frag_name = "builtin-frag.yaml"

    # Builtin fragment
    builtin_frag = builtin_fragments_dir / frag_name
    builtin_frag.write_text("""
version: \"1.0\"
name: builtin-frag
description: Builtin version
steps:
  - name: dummy
    type: python
    action: print
    kwargs: {msg: \"test\"}
""")

    # User fragment (override)
    user_frag = user_dir / "maverick" / "workflows" / "fragments" / frag_name
    user_frag.write_text("""
version: \"1.0\"
name: builtin-frag
description: User override
steps:
  - name: dummy
    type: python
    action: print
    kwargs: {msg: \"test\"}
""")

    # Mock paths in discovery
    # We use real WorkflowLocator and WorkflowLoader now
    with (
        patch.object(
            DefaultWorkflowDiscovery,
            "get_user_path",
            return_value=user_dir / "maverick" / "workflows",
        ),
        patch.object(
            DefaultWorkflowDiscovery, "get_builtin_path", return_value=builtin_root
        ),
    ):
        discovery = DefaultWorkflowDiscovery()
        result = discovery.discover(project_dir=project_dir, include_builtin=True)

        # Debug
        print(f"Scanned locations: {result.locations_scanned}")
        print(f"Skipped: {result.skipped}")
        print(f"Fragments found: {[f.workflow.name for f in result.fragments]}")

        fragments = [f for f in result.fragments if f.workflow.name == "builtin-frag"]
        assert len(fragments) == 1

        discovered = fragments[0]
        assert discovered.source == WorkflowSource.USER.value
        assert discovered.workflow.description == "User override"

        # Verify override
        assert len(discovered.overrides) == 1
        assert str(builtin_frag.resolve()) == str(discovered.overrides[0])
