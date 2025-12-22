"""Unit tests for TaskFile model."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from maverick.models.implementation import Task, TaskFile, TaskStatus


class TestTaskFileInstantiation:
    """Tests for TaskFile instantiation."""

    def test_instantiate_with_required_fields(self) -> None:
        """Test TaskFile instantiation with required fields."""
        path = Path("tasks.md")
        task_file = TaskFile(path=path, tasks=[], phases={})

        assert task_file.path == path
        assert task_file.tasks == []
        assert task_file.phases == {}

    def test_instantiate_with_tasks(self) -> None:
        """Test TaskFile instantiation with tasks."""
        path = Path("tasks.md")
        tasks = [
            Task(
                id="T001",
                description="First task",
                status=TaskStatus.PENDING,
            ),
            Task(
                id="T002",
                description="Second task",
                status=TaskStatus.PENDING,
            ),
        ]

        task_file = TaskFile(path=path, tasks=tasks, phases={})

        assert len(task_file.tasks) == 2
        assert task_file.tasks[0].id == "T001"
        assert task_file.tasks[1].id == "T002"

    def test_instantiate_with_phases(self) -> None:
        """Test TaskFile instantiation with phases."""
        path = Path("tasks.md")
        task1 = Task(
            id="T001",
            description="Phase 1 task",
            status=TaskStatus.PENDING,
            phase="Phase 1",
        )
        task2 = Task(
            id="T002",
            description="Phase 2 task",
            status=TaskStatus.PENDING,
            phase="Phase 2",
        )
        phases = {
            "Phase 1": [task1],
            "Phase 2": [task2],
        }
        tasks = [task1, task2]

        task_file = TaskFile(path=path, tasks=tasks, phases=phases)

        assert "Phase 1" in task_file.phases
        assert "Phase 2" in task_file.phases
        assert len(task_file.phases["Phase 1"]) == 1
        assert len(task_file.phases["Phase 2"]) == 1


class TestPendingTasks:
    """Tests for pending_tasks property."""

    def test_pending_tasks_empty(self) -> None:
        """Test pending_tasks returns empty list when no pending tasks."""
        tasks = [
            Task(
                id="T001",
                description="Completed task",
                status=TaskStatus.COMPLETED,
            ),
            Task(
                id="T002",
                description="Failed task",
                status=TaskStatus.FAILED,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.pending_tasks == []

    def test_pending_tasks_returns_all_pending(self) -> None:
        """Test pending_tasks returns all pending tasks."""
        tasks = [
            Task(
                id="T001",
                description="First pending",
                status=TaskStatus.PENDING,
            ),
            Task(
                id="T002",
                description="Completed",
                status=TaskStatus.COMPLETED,
            ),
            Task(
                id="T003",
                description="Second pending",
                status=TaskStatus.PENDING,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        pending = task_file.pending_tasks
        assert len(pending) == 2
        assert pending[0].id == "T001"
        assert pending[1].id == "T003"

    def test_pending_tasks_preserves_order(self) -> None:
        """Test pending_tasks preserves task order."""
        tasks = [
            Task(id="T003", description="Third", status=TaskStatus.PENDING),
            Task(id="T001", description="First", status=TaskStatus.PENDING),
            Task(id="T002", description="Second", status=TaskStatus.PENDING),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        pending = task_file.pending_tasks
        assert [t.id for t in pending] == ["T003", "T001", "T002"]


class TestCompletedTasks:
    """Tests for completed_tasks property."""

    def test_completed_tasks_empty(self) -> None:
        """Test completed_tasks returns empty list when no completed tasks."""
        tasks = [
            Task(
                id="T001",
                description="Pending task",
                status=TaskStatus.PENDING,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.completed_tasks == []

    def test_completed_tasks_returns_all_completed(self) -> None:
        """Test completed_tasks returns all completed tasks."""
        tasks = [
            Task(
                id="T001",
                description="First completed",
                status=TaskStatus.COMPLETED,
            ),
            Task(
                id="T002",
                description="Pending",
                status=TaskStatus.PENDING,
            ),
            Task(
                id="T003",
                description="Second completed",
                status=TaskStatus.COMPLETED,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        completed = task_file.completed_tasks
        assert len(completed) == 2
        assert completed[0].id == "T001"
        assert completed[1].id == "T003"


class TestFailedTasks:
    """Tests for failed_tasks property."""

    def test_failed_tasks_empty(self) -> None:
        """Test failed_tasks returns empty list when no failed tasks."""
        tasks = [
            Task(
                id="T001",
                description="Pending task",
                status=TaskStatus.PENDING,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.failed_tasks == []

    def test_failed_tasks_returns_all_failed(self) -> None:
        """Test failed_tasks returns all failed tasks."""
        tasks = [
            Task(
                id="T001",
                description="First failed",
                status=TaskStatus.FAILED,
            ),
            Task(
                id="T002",
                description="Pending",
                status=TaskStatus.PENDING,
            ),
            Task(
                id="T003",
                description="Second failed",
                status=TaskStatus.FAILED,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        failed = task_file.failed_tasks
        assert len(failed) == 2
        assert failed[0].id == "T001"
        assert failed[1].id == "T003"


class TestGetParallelBatch:
    """Tests for get_parallel_batch method."""

    def test_get_parallel_batch_empty_when_no_pending(self) -> None:
        """Test get_parallel_batch returns empty when no pending tasks."""
        tasks = [
            Task(
                id="T001",
                description="Completed",
                status=TaskStatus.COMPLETED,
                parallel=True,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.get_parallel_batch() == []

    def test_get_parallel_batch_empty_when_first_is_sequential(self) -> None:
        """Test get_parallel_batch returns empty when first pending task is
        sequential."""
        tasks = [
            Task(
                id="T001",
                description="Sequential task",
                status=TaskStatus.PENDING,
                parallel=False,
            ),
            Task(
                id="T002",
                description="Parallel task",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.get_parallel_batch() == []

    def test_get_parallel_batch_returns_consecutive_parallel_tasks(self) -> None:
        """Test get_parallel_batch returns consecutive parallel tasks."""
        tasks = [
            Task(
                id="T001",
                description="First parallel",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
            Task(
                id="T002",
                description="Second parallel",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
            Task(
                id="T003",
                description="Sequential",
                status=TaskStatus.PENDING,
                parallel=False,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        batch = task_file.get_parallel_batch()
        assert len(batch) == 2
        assert batch[0].id == "T001"
        assert batch[1].id == "T002"

    def test_get_parallel_batch_stops_at_non_parallel(self) -> None:
        """Test get_parallel_batch stops at first non-parallel task."""
        tasks = [
            Task(
                id="T001",
                description="First parallel",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
            Task(
                id="T002",
                description="Sequential",
                status=TaskStatus.PENDING,
                parallel=False,
            ),
            Task(
                id="T003",
                description="Another parallel",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        batch = task_file.get_parallel_batch()
        assert len(batch) == 1
        assert batch[0].id == "T001"

    def test_get_parallel_batch_ignores_completed_tasks(self) -> None:
        """Test get_parallel_batch only considers pending tasks."""
        tasks = [
            Task(
                id="T001",
                description="Completed parallel",
                status=TaskStatus.COMPLETED,
                parallel=True,
            ),
            Task(
                id="T002",
                description="Pending parallel",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        batch = task_file.get_parallel_batch()
        assert len(batch) == 1
        assert batch[0].id == "T002"

    def test_get_parallel_batch_excludes_tasks_with_dependencies(self) -> None:
        """Test get_parallel_batch excludes tasks with dependencies."""
        tasks = [
            Task(
                id="T001",
                description="Task with dependency",
                status=TaskStatus.PENDING,
                parallel=True,
                dependencies=["T000"],
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.get_parallel_batch() == []


class TestGetNextSequential:
    """Tests for get_next_sequential method."""

    def test_get_next_sequential_returns_none_when_no_pending(self) -> None:
        """Test get_next_sequential returns None when no pending tasks."""
        tasks = [
            Task(
                id="T001",
                description="Completed",
                status=TaskStatus.COMPLETED,
                parallel=False,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.get_next_sequential() is None

    def test_get_next_sequential_returns_none_when_all_pending_are_parallel(
        self,
    ) -> None:
        """Test get_next_sequential returns None when all pending are parallel."""
        tasks = [
            Task(
                id="T001",
                description="Parallel task",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
            Task(
                id="T002",
                description="Another parallel",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        assert task_file.get_next_sequential() is None

    def test_get_next_sequential_returns_first_sequential_pending(self) -> None:
        """Test get_next_sequential returns first sequential pending task."""
        tasks = [
            Task(
                id="T001",
                description="Parallel task",
                status=TaskStatus.PENDING,
                parallel=True,
            ),
            Task(
                id="T002",
                description="Sequential task",
                status=TaskStatus.PENDING,
                parallel=False,
            ),
            Task(
                id="T003",
                description="Another sequential",
                status=TaskStatus.PENDING,
                parallel=False,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        next_task = task_file.get_next_sequential()
        assert next_task is not None
        assert next_task.id == "T002"

    def test_get_next_sequential_skips_completed_parallel(self) -> None:
        """Test get_next_sequential skips completed tasks."""
        tasks = [
            Task(
                id="T001",
                description="Completed",
                status=TaskStatus.COMPLETED,
                parallel=False,
            ),
            Task(
                id="T002",
                description="Sequential pending",
                status=TaskStatus.PENDING,
                parallel=False,
            ),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        next_task = task_file.get_next_sequential()
        assert next_task is not None
        assert next_task.id == "T002"


class TestMarkTaskStatus:
    """Tests for mark_task_status method."""

    def test_mark_task_status_creates_new_instance(self) -> None:
        """Test mark_task_status creates new TaskFile instance."""
        tasks = [
            Task(id="T001", description="Task", status=TaskStatus.PENDING),
        ]
        original = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        updated = original.mark_task_status("T001", TaskStatus.COMPLETED)

        assert original is not updated
        assert original.tasks[0].status == TaskStatus.PENDING
        assert updated.tasks[0].status == TaskStatus.COMPLETED

    def test_mark_task_status_updates_single_task(self) -> None:
        """Test mark_task_status updates only specified task."""
        tasks = [
            Task(id="T001", description="First", status=TaskStatus.PENDING),
            Task(id="T002", description="Second", status=TaskStatus.PENDING),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        updated = task_file.mark_task_status("T001", TaskStatus.COMPLETED)

        assert updated.tasks[0].status == TaskStatus.COMPLETED
        assert updated.tasks[1].status == TaskStatus.PENDING

    def test_mark_task_status_preserves_task_properties(self) -> None:
        """Test mark_task_status preserves all other task properties."""
        original_task = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.PENDING,
            parallel=True,
            user_story="US1",
            phase="Phase 1",
            dependencies=["T000"],
        )
        task_file = TaskFile(path=Path("tasks.md"), tasks=[original_task], phases={})

        updated = task_file.mark_task_status("T001", TaskStatus.FAILED)
        updated_task = updated.tasks[0]

        assert updated_task.id == "T001"
        assert updated_task.description == "Test task"
        assert updated_task.parallel is True
        assert updated_task.user_story == "US1"
        assert updated_task.phase == "Phase 1"
        assert updated_task.dependencies == ["T000"]
        assert updated_task.status == TaskStatus.FAILED

    def test_mark_task_status_no_change_if_not_found(self) -> None:
        """Test mark_task_status doesn't change anything if task not found."""
        tasks = [
            Task(id="T001", description="Task", status=TaskStatus.PENDING),
        ]
        task_file = TaskFile(path=Path("tasks.md"), tasks=tasks, phases={})

        updated = task_file.mark_task_status("T999", TaskStatus.COMPLETED)

        assert updated.tasks[0].status == TaskStatus.PENDING

    def test_mark_task_status_updates_phases_dict(self) -> None:
        """Test mark_task_status updates phases dictionary."""
        task1 = Task(
            id="T001",
            description="Task 1",
            status=TaskStatus.PENDING,
            phase="Phase 1",
        )
        task2 = Task(
            id="T002",
            description="Task 2",
            status=TaskStatus.PENDING,
            phase="Phase 1",
        )
        phases = {"Phase 1": [task1, task2]}
        task_file = TaskFile(path=Path("tasks.md"), tasks=[task1, task2], phases=phases)

        updated = task_file.mark_task_status("T001", TaskStatus.COMPLETED)

        # Phases should be updated with new task instances
        assert "Phase 1" in updated.phases
        assert len(updated.phases["Phase 1"]) == 2
        assert updated.phases["Phase 1"][0].status == TaskStatus.COMPLETED


class TestTaskFileParse:
    """Tests for TaskFile.parse classmethod."""

    def test_parse_from_content(self) -> None:
        """Test TaskFile.parse with provided content."""
        content = """## Phase 1
- [ ] T001 First task
- [ ] T002 [P] Second task
"""
        task_file = TaskFile.parse(Path("tasks.md"), content)

        assert len(task_file.tasks) == 2
        assert task_file.tasks[0].id == "T001"
        assert task_file.tasks[1].id == "T002"
        assert task_file.tasks[1].parallel is True

    def test_parse_from_file(self) -> None:
        """Test TaskFile.parse reads from file when content not provided."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tasks.md"
            path.write_text("""## Phase 1
- [ ] T001 Task from file
""")

            task_file = TaskFile.parse(path)

            assert len(task_file.tasks) == 1
            assert task_file.tasks[0].description == "Task from file"

    def test_parse_maintains_path(self) -> None:
        """Test TaskFile.parse maintains the provided path."""
        content = "- [ ] T001 Task"
        path = Path("specs/feature/tasks.md")

        task_file = TaskFile.parse(path, content)

        assert task_file.path == path
