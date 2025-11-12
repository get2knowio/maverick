"""Performance tests for CLI discovery.

Verifies that discovery and descriptor building completes within performance SLA.
Per FR-010: Build 100+ TaskDescriptors < 5s in devcontainer.
"""

import time
from pathlib import Path

import pytest


@pytest.mark.perf
def test_cli_discovery_performance_200_tasks(tmp_path: Path):
    """Test that discovery+descriptor build for 200+ tasks completes in ≤5s.

    This test synthesizes 200+ tasks.md files and verifies that:
    1. Discovery finds all files
    2. Descriptor building completes for all tasks
    3. Total time is ≤ 5 seconds (FR-010 SLA)

    The test runs in the devcontainer environment as specified.
    """
    from src.cli._adapter import build_cli_descriptor
    from src.cli._discovery import discover_tasks

    # Setup: Create synthetic repository with 200+ task files
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    specs_dir = repo_root / "specs"
    specs_dir.mkdir()

    # Create 200 task files with numeric prefixes for deterministic ordering
    num_tasks = 200
    for i in range(num_tasks):
        feature_dir = specs_dir / f"{i:03d}-feature-{i}"
        feature_dir.mkdir()

        tasks_file = feature_dir / "tasks.md"
        tasks_file.write_text(
            f"# Tasks: Feature {i}\n\n"
            f"## Phase 1: Setup\n"
            f"- [ ] T001 Initialize feature {i}\n\n"
            f"## Phase 2: Implementation\n"
            f"- [ ] T002 Implement core logic for feature {i}\n"
        )

    # Start timing
    start_time = time.time()

    # Execute discovery
    discovered_tasks = discover_tasks(repo_root, target_task_file=None)

    # Verify discovery found all tasks
    assert len(discovered_tasks) == num_tasks, (
        f"Expected {num_tasks} tasks, discovered {len(discovered_tasks)}"
    )

    # Build descriptors for all discovered tasks
    descriptors = []
    for task in discovered_tasks:
        descriptor = build_cli_descriptor(
            task_file=Path(task.file_path),
            spec_root=Path(task.spec_dir),
            repo_root=repo_root,
            return_to_branch="main",
            interactive=False,
        )
        descriptors.append(descriptor)

    # Stop timing
    end_time = time.time()
    duration = end_time - start_time

    # Verify all descriptors were built
    assert len(descriptors) == num_tasks, (
        f"Expected {num_tasks} descriptors, built {len(descriptors)}"
    )

    # Verify performance SLA: ≤5 seconds
    assert duration <= 5.0, (
        f"Discovery+descriptor build took {duration:.2f}s, "
        f"exceeds 5s SLA (FR-010)"
    )

    # Log performance metrics for monitoring
    print(f"\nPerformance: {num_tasks} tasks processed in {duration:.2f}s")
    print(f"  Discovery: {len(discovered_tasks)} files found")
    print(f"  Descriptors: {len(descriptors)} built")
    print(f"  Throughput: {num_tasks / duration:.1f} tasks/second")


@pytest.mark.perf
def test_cli_discovery_ordering_performance(tmp_path: Path):
    """Test that task ordering is deterministic and fast with many files."""
    from src.cli._discovery import discover_tasks

    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    specs_dir = repo_root / "specs"
    specs_dir.mkdir()

    # Create tasks with various naming patterns
    patterns = [
        ("001-feature-a", "tasks.md"),
        ("001-feature-b", "tasks.md"),
        ("002-feature-c", "tasks.md"),
        ("010-feature-d", "tasks.md"),
        ("feature-no-prefix", "tasks.md"),
        ("zzz-feature-z", "tasks.md"),
    ]

    for dirname, filename in patterns:
        feature_dir = specs_dir / dirname
        feature_dir.mkdir()
        (feature_dir / filename).write_text(f"# {dirname}")

    # Time multiple discovery runs
    timings = []
    for _ in range(10):
        start = time.time()
        discovered = discover_tasks(repo_root, target_task_file=None)
        duration = time.time() - start
        timings.append(duration)

        # Verify order is deterministic
        assert len(discovered) == len(patterns)
        assert discovered[0].file_path.endswith("001-feature-a/tasks.md")
        assert discovered[1].file_path.endswith("001-feature-b/tasks.md")

    # Verify consistent performance across runs
    avg_time = sum(timings) / len(timings)
    max_time = max(timings)

    print("\nOrdering performance:")
    print(f"  Avg: {avg_time*1000:.1f}ms")
    print(f"  Max: {max_time*1000:.1f}ms")

    # Discovery should be fast even with repeated calls
    assert max_time < 1.0, "Discovery should complete in <1s for small repos"


@pytest.mark.perf
def test_cli_descriptor_build_performance(tmp_path: Path):
    """Test descriptor building performance with realistic task files."""
    from src.cli._adapter import build_cli_descriptor

    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    spec_root = repo_root / "specs" / "001-test"
    spec_root.mkdir(parents=True)

    # Create a realistic tasks.md with multiple phases
    tasks_file = spec_root / "tasks.md"
    tasks_file.write_text(
        "# Tasks: Test Feature\n\n"
        "## Phase 1: Setup\n"
        "- [ ] T001 Initialize project\n"
        "- [ ] T002 Setup dependencies\n\n"
        "## Phase 2: Core\n"
        "- [ ] T003 Implement feature A\n"
        "- [ ] T004 Implement feature B\n\n"
        "## Phase 3: Tests\n"
        "- [ ] T005 Unit tests\n"
        "- [ ] T006 Integration tests\n"
    )

    # Build 100 descriptors to measure throughput
    start_time = time.time()

    descriptors = []
    for _ in range(100):
        descriptor = build_cli_descriptor(
            task_file=tasks_file,
            spec_root=spec_root,
            repo_root=repo_root,
            return_to_branch="main",
            interactive=False,
        )
        descriptors.append(descriptor)

    duration = time.time() - start_time

    # Verify all descriptors built correctly
    assert len(descriptors) == 100
    for desc in descriptors:
        assert desc.task_id == "001-test-tasks"
        assert desc.task_file == str(tasks_file)
        assert desc.spec_root == str(spec_root)

    # Descriptor building should be fast
    per_descriptor = duration / 100
    print("\nDescriptor build performance:")
    print(f"  Total: {duration*1000:.1f}ms for 100 descriptors")
    print(f"  Per descriptor: {per_descriptor*1000:.2f}ms")

    assert per_descriptor < 0.05, (
        f"Descriptor build took {per_descriptor*1000:.1f}ms per descriptor, "
        "should be <50ms"
    )
