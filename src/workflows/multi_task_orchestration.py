"""Multi-task orchestration workflow.

This module implements the workflow for orchestrating sequential processing
of multiple task files through all phases (initialize, implement, review/fix, PR/CI/merge).
"""


import asyncio

from temporalio import workflow

# Mark models as passthrough to avoid path validation issues in workflow context
with workflow.unsafe.imports_passed_through():
    from src.models.orchestration import (
        OrchestrationInput,
        OrchestrationResult,
        PhaseResult,
        TaskResult,
    )
    from src.models.phase_automation import (
        AutomatePhaseTasksParams,
        RetryPolicySettings,
    )


@workflow.defn(name="MultiTaskOrchestrationWorkflow")
class MultiTaskOrchestrationWorkflow:
    """Temporal workflow for orchestrating multiple task files sequentially.

    This workflow processes a list of task files one by one, calling the
    AutomatePhaseTasksWorkflow for each task file. It implements fail-fast
    behavior, stopping on the first task failure and returning partial results.

    Architecture:
        The workflow uses pure workflow composition - it calls AutomatePhaseTasksWorkflow
        as a child workflow for each task file. No activities are directly invoked.
        All phase discovery and execution logic is delegated to the child workflow.

    Features:
        - Sequential task processing (no parallelism to avoid branch conflicts)
        - Fail-fast error handling (stops on first failure, returns partial results)
        - Resume capability after worker restart (via Temporal replay)
        - Optional interactive mode with approval gates between tasks
        - Progress tracking via query handlers (get_progress, get_task_results)
        - Signal handlers for interactive control (continue, skip)

    State Management:
        All state is stored in workflow instance variables and survives worker
        restarts through Temporal's deterministic replay mechanism. No external
        storage is used (per FR-017, FR-019).

    Interactive Mode:
        When interactive_mode=True, the workflow pauses after each task completes
        and waits for a signal before proceeding. Two signals are supported:
        - continue_to_next_phase: Resume workflow and process next task
        - skip_current_task: Skip the upcoming task and move to the next one

    Error Handling:
        - Task failures: Workflow stops immediately and returns partial results
        - Child workflow exceptions: Captured and converted to failed TaskResult
        - Empty phase lists: Treated as task failure with synthetic PhaseResult
        - Validation errors: Caught during OrchestrationInput construction

    Query Handlers:
        - get_progress(): Returns current task index, pause state, completion info
        - get_task_results(): Returns all completed TaskResult objects

    Examples:
        Basic batch processing:
        >>> orchestration_input = OrchestrationInput(
        ...     task_file_paths=("tasks/feature-001.md", "tasks/feature-002.md"),
        ...     interactive_mode=False,
        ...     retry_limit=3,
        ...     repo_path="/workspace/myrepo",
        ...     branch="main",
        ... )
        >>> result = await client.execute_workflow(
        ...     "MultiTaskOrchestrationWorkflow",
        ...     orchestration_input,
        ...     id="orchestrate-batch-001",
        ...     task_queue="maverick-task-queue",
        ... )

        Interactive mode with approval gates:
        >>> orchestration_input = OrchestrationInput(
        ...     task_file_paths=("tasks/feature-001.md",),
        ...     interactive_mode=True,
        ...     retry_limit=3,
        ...     repo_path="/workspace/myrepo",
        ...     branch="main",
        ... )
        >>> handle = await client.start_workflow(
        ...     "MultiTaskOrchestrationWorkflow",
        ...     orchestration_input,
        ...     id="orchestrate-interactive-001",
        ...     task_queue="maverick-task-queue",
        ... )
        >>> # Workflow pauses after first task
        >>> await handle.signal("continue_to_next_phase")  # Resume to next task
        >>> # Or skip the next task:
        >>> await handle.signal("skip_current_task")
    """

    def __init__(self) -> None:
        """Initialize workflow state variables.
        
        State Variables:
            _completed_task_indices: List of zero-based task indices that have completed
            _task_results: List of TaskResult objects for all processed tasks
            _current_task_index: Zero-based index of currently processing task
            _total_tasks: Total number of tasks in workflow input (for progress tracking)
            _current_task_file: Path of currently processing task file
            _continue_event: asyncio.Event for pause/resume control in interactive mode
            _skip_current: Flag indicating whether to skip the upcoming/current task
            _is_paused: Flag indicating whether workflow is currently paused
            
        All state variables survive worker restarts through Temporal's deterministic replay.
        No external storage is used.
        """
        self._completed_task_indices: list[int] = []
        self._task_results: list[TaskResult] = []
        self._current_task_index: int = 0
        self._total_tasks: int = 0
        self._current_task_file: str | None = None
        # Interactive mode state
        self._continue_event: asyncio.Event = asyncio.Event()
        self._skip_current: bool = False
        self._is_paused: bool = False

    @workflow.signal
    async def continue_to_next_phase(self) -> None:
        """Signal handler to resume workflow from pause.
        
        Used in interactive mode to resume workflow execution after a pause.
        When the workflow is paused (after task completion), calling this signal
        will unblock the workflow and allow it to proceed to the next task.
        
        Behavior:
            - Sets the continue event to unblock workflow execution
            - Idempotent - multiple signals while paused have no additional effect
            - Can be called even when not paused (no-op, but logged)
            - Thread-safe and replay-safe (uses asyncio.Event)
            
        Usage:
            >>> handle = client.get_workflow_handle("orchestrate-abc123")
            >>> await handle.signal("continue_to_next_phase")
        """
        workflow.logger.info(
            "signal_received_continue",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "is_paused": self._is_paused,
                "current_task_index": self._current_task_index,
            }
        )
        self._continue_event.set()

    @workflow.signal
    async def skip_current_task(self) -> None:
        """Signal handler to skip the upcoming/current task.
        
        Used in interactive mode to skip a task without processing it.
        When the workflow is paused, calling this signal will mark the next
        task to be skipped and resume workflow execution.
        
        Behavior:
            - Sets _skip_current flag to true
            - Sets continue event to unblock workflow execution
            - Most effective when workflow is paused in interactive mode
            - The skip applies to the NEXT task to be processed
            - Creates a TaskResult with overall_status="skipped"
            - Workflow will pause again after skip (if interactive_mode=True)
            
        Usage:
            >>> handle = client.get_workflow_handle("orchestrate-abc123")
            >>> await handle.signal("skip_current_task")
            
        Note:
            If called while a task is already in progress (child workflow executing),
            the skip will apply to the NEXT task, not the currently running one.
        """
        workflow.logger.info(
            "signal_received_skip_task",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "is_paused": self._is_paused,
                "current_task_index": self._current_task_index,
            }
        )
        self._skip_current = True
        self._continue_event.set()

    @workflow.query
    def get_progress(self) -> dict:
        """Query handler to get current workflow progress.
        
        Provides real-time visibility into workflow state, useful for monitoring
        and debugging running workflows.
        
        Returns:
            Dict with the following keys:
                - current_task_index (int): Zero-based index of current task
                - total_tasks (int): Total number of tasks in workflow
                - current_task_file (str | None): Path of current task file
                - current_phase (None): Phase tracking (not implemented in this architecture)
                - completed_tasks (list[int]): List of completed task indices
                - is_paused (bool): Whether workflow is currently paused
                - waiting_for (str | None): Name of signal workflow is waiting for, if paused
                
        Usage:
            >>> handle = client.get_workflow_handle("orchestrate-abc123")
            >>> progress = await handle.query("get_progress")
            >>> print(f"Processing task {progress['current_task_index'] + 1}/{progress['total_tasks']}")
        """
        return {
            "current_task_index": self._current_task_index,
            "total_tasks": self._total_tasks,
            "current_task_file": self._current_task_file,
            "current_phase": None,  # Not tracking phase-level state in this architecture
            "completed_tasks": self._completed_task_indices,
            "is_paused": self._is_paused,
            "waiting_for": "continue_to_next_phase" if self._is_paused else None,
        }

    @workflow.query
    def get_task_results(self) -> list[TaskResult]:
        """Query handler to get all completed task results.
        
        Retrieves detailed results for all tasks that have been processed so far,
        including phase-level outcomes and timing information.
        
        Returns:
            List of TaskResult objects for completed tasks, in processing order.
            Each TaskResult contains:
                - task_file_path: Path to the task file
                - overall_status: "success", "failed", "skipped", or "unprocessed"
                - phase_results: Tuple of PhaseResult objects for each phase executed
                - total_duration_seconds: Total time spent processing the task
                - failure_reason: Error description if task failed
                
        Usage:
            >>> handle = client.get_workflow_handle("orchestrate-abc123")
            >>> results = await handle.query("get_task_results")
            >>> for result in results:
            ...     print(f"Task {result.task_file_path}: {result.overall_status}")
        """
        return self._task_results

    @workflow.run
    async def run(self, params: OrchestrationInput) -> OrchestrationResult:
        """Execute multi-task orchestration workflow.

        Args:
            params: Workflow input parameters defining task list and settings

        Returns:
            OrchestrationResult with aggregated statistics and task results

        Raises:
            ValueError: If input validation fails (caught and returned in result)
        """
        workflow_start_time = workflow.now()
        
        # Store total tasks for progress queries
        self._total_tasks = len(params.task_file_paths)

        workflow.logger.info(
            "orchestration_workflow_started",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "total_tasks": len(params.task_file_paths),
                "interactive_mode": params.interactive_mode,
                "retry_limit": params.retry_limit,
            }
        )

        # Process each task sequentially
        for task_index, task_file_path in enumerate(params.task_file_paths):
            self._current_task_index = task_index
            self._current_task_file = task_file_path

            # Check if this task should be skipped
            if self._skip_current:
                workflow.logger.info(
                    "task_skipped_before_processing",
                    extra={
                        "task_index": task_index,
                        "task_file_path": task_file_path,
                        "workflow_id": workflow.info().workflow_id,
                    }
                )
                
                # Create skipped task result
                skipped_result = TaskResult(
                    task_file_path=task_file_path,
                    overall_status="skipped",
                    phase_results=(),
                    total_duration_seconds=0,
                    failure_reason=None,
                )
                self._task_results.append(skipped_result)
                self._skip_current = False
                
                # If in interactive mode, pause after skip
                if params.interactive_mode:
                    self._is_paused = True
                    self._continue_event.clear()
                    
                    workflow.logger.info(
                        "workflow_paused_after_skip",
                        extra={
                            "task_index": task_index,
                            "workflow_id": workflow.info().workflow_id,
                        }
                    )
                    
                    await self._continue_event.wait()
                    self._is_paused = False
                
                continue  # Skip to next task

            workflow.logger.info(
                "task_processing_started",
                extra={
                    "task_index": task_index,
                    "task_file_path": task_file_path,
                    "workflow_id": workflow.info().workflow_id,
                }
            )

            task_start_time = workflow.now()

            try:
                # Invoke AutomatePhaseTasksWorkflow as child workflow
                phase_params = AutomatePhaseTasksParams(
                    repo_path=params.repo_path,
                    branch=params.branch,
                    tasks_md_path=task_file_path,
                    tasks_md_content=None,
                    default_model=params.default_model,
                    default_agent_profile=params.default_agent_profile,
                    timeout_minutes=30,
                    retry_policy=RetryPolicySettings(
                        maximum_attempts=params.retry_limit,
                        initial_interval_seconds=10.0,
                        maximum_interval_seconds=300.0,
                        non_retryable_error_types=("ValidationError",),
                    ),
                )

                # Execute child workflow by name - Temporal handles retries internally
                # Use workflow name to ensure test mocks work correctly
                # MUST specify result_type for proper deserialization (Constitution IV Type Safety)
                from src.models.phase_automation import PhaseAutomationSummary
                phase_summary = await workflow.execute_child_workflow(
                    "AutomatePhaseTasksWorkflow",
                    phase_params,
                    result_type=PhaseAutomationSummary,
                )

                # Convert PhaseAutomationSummary to TaskResult
                task_end_time = workflow.now()
                task_duration_seconds = int((task_end_time - task_start_time).total_seconds())

                # T050: Log discovered phase count
                phase_count = len(phase_summary.results)
                workflow.logger.info(
                    "task_phases_discovered",
                    extra={
                        "task_index": task_index,
                        "task_file_path": task_file_path,
                        "phase_count": phase_count,
                        "workflow_id": workflow.info().workflow_id,
                    }
                )

                # T049: Validate empty phase list
                if phase_count == 0:
                    error_message = f"No phases discovered in task file: {task_file_path}"
                    workflow.logger.error(
                        "task_no_phases_discovered",
                        extra={
                            "task_index": task_index,
                            "task_file_path": task_file_path,
                            "workflow_id": workflow.info().workflow_id,
                        }
                    )
                    
                    # Create failed task result with synthetic phase result
                    synthetic_phase_result = PhaseResult(
                        phase_name="phase_discovery",
                        status="failed",
                        duration_seconds=task_duration_seconds,
                        error_message=error_message,
                        retry_count=0,
                    )
                    
                    task_result = TaskResult(
                        task_file_path=task_file_path,
                        overall_status="failed",
                        phase_results=(synthetic_phase_result,),
                        total_duration_seconds=task_duration_seconds,
                        failure_reason=error_message,
                    )
                    
                    self._task_results.append(task_result)
                    
                    # Fail-fast: Stop on empty phase list
                    workflow.logger.warning(
                        "task_failed_stopping_orchestration",
                        extra={
                            "task_index": task_index,
                            "task_file_path": task_file_path,
                            "failure_reason": error_message,
                            "workflow_id": workflow.info().workflow_id,
                        }
                    )
                    break  # Exit task loop

                # Build phase results from automation summary
                phase_results: list[PhaseResult] = []
                for phase_automation_result in phase_summary.results:
                    phase_result = PhaseResult(
                        phase_name=phase_automation_result.phase_id,
                        status="success" if phase_automation_result.status == "success" else "failed",
                        duration_seconds=phase_automation_result.duration_ms // 1000,
                        error_message=phase_automation_result.error,
                        retry_count=0,  # Retries handled by child workflow
                    )
                    phase_results.append(phase_result)

                # Determine overall task status
                has_failures = any(pr.status == "failed" for pr in phase_results)
                task_status = "failed" if has_failures else "success"
                failure_reason = None
                if has_failures:
                    failed_phase = next(pr for pr in phase_results if pr.status == "failed")
                    failure_reason = f"Phase '{failed_phase.phase_name}' failed: {failed_phase.error_message}"

                task_result = TaskResult(
                    task_file_path=task_file_path,
                    overall_status=task_status,
                    phase_results=tuple(phase_results),
                    total_duration_seconds=task_duration_seconds,
                    failure_reason=failure_reason,
                )

                self._task_results.append(task_result)
                self._completed_task_indices.append(task_index)

                workflow.logger.info(
                    "task_processing_completed",
                    extra={
                        "task_index": task_index,
                        "task_file_path": task_file_path,
                        "task_status": task_status,
                        "duration_seconds": task_duration_seconds,
                        "workflow_id": workflow.info().workflow_id,
                    }
                )

                # Interactive mode: Pause after task completion
                if params.interactive_mode:
                    # Check if skip was requested
                    if self._skip_current:
                        workflow.logger.info(
                            "task_skipped",
                            extra={
                                "task_index": task_index,
                                "task_file_path": task_file_path,
                                "workflow_id": workflow.info().workflow_id,
                            }
                        )
                        self._skip_current = False
                        continue  # Move to next task

                    # Pause and wait for continue signal
                    self._is_paused = True
                    self._continue_event.clear()
                    
                    workflow.logger.info(
                        "workflow_paused",
                        extra={
                            "task_index": task_index,
                            "task_file_path": task_file_path,
                            "workflow_id": workflow.info().workflow_id,
                        }
                    )
                    
                    # Wait for signal
                    await self._continue_event.wait()
                    
                    self._is_paused = False
                    
                    workflow.logger.info(
                        "workflow_resumed",
                        extra={
                            "task_index": task_index,
                            "workflow_id": workflow.info().workflow_id,
                        }
                    )
                    
                    # Check if skip was requested during pause
                    # Note: We DON'T reset _skip_current here - it will be handled
                    # at the start of the next task iteration (line ~155)
                    if self._skip_current:
                        workflow.logger.info(
                            "skip_requested_during_pause",
                            extra={
                                "next_task_index": task_index + 1 if task_index + 1 < len(params.task_file_paths) else task_index,
                                "workflow_id": workflow.info().workflow_id,
                            }
                        )

                # Fail-fast: Stop on first task failure
                if task_status == "failed":
                    workflow.logger.warning(
                        "task_failed_stopping_orchestration",
                        extra={
                            "task_index": task_index,
                            "task_file_path": task_file_path,
                            "failure_reason": failure_reason,
                            "workflow_id": workflow.info().workflow_id,
                        }
                    )
                    break  # Exit task loop, proceed to result construction

            except Exception as e:
                # Handle child workflow exceptions
                task_end_time = workflow.now()
                task_duration_seconds = int((task_end_time - task_start_time).total_seconds())

                error_message = f"Child workflow failed: {type(e).__name__}: {str(e)}"

                workflow.logger.error(
                    "task_child_workflow_error",
                    extra={
                        "task_index": task_index,
                        "task_file_path": task_file_path,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "workflow_id": workflow.info().workflow_id,
                    }
                )

                # Create failed task result with synthetic phase result
                # (required by TaskResult validation - failed status needs at least one failed phase)
                synthetic_phase_result = PhaseResult(
                    phase_name="workflow_execution",
                    status="failed",
                    duration_seconds=task_duration_seconds,
                    error_message=error_message,
                    retry_count=0,
                )

                task_result = TaskResult(
                    task_file_path=task_file_path,
                    overall_status="failed",
                    phase_results=(synthetic_phase_result,),
                    total_duration_seconds=task_duration_seconds,
                    failure_reason=error_message,
                )

                self._task_results.append(task_result)

                # Fail-fast: Stop on exception
                break

        # Build final orchestration result
        workflow_end_time = workflow.now()
        total_duration_seconds = int((workflow_end_time - workflow_start_time).total_seconds())

        total_tasks = len(params.task_file_paths)
        processed_tasks = len(self._task_results)
        unprocessed_count = total_tasks - processed_tasks

        # Calculate status counts
        successful_tasks = sum(1 for tr in self._task_results if tr.overall_status == "success")
        failed_tasks = sum(1 for tr in self._task_results if tr.overall_status == "failed")
        skipped_tasks = sum(1 for tr in self._task_results if tr.overall_status == "skipped")

        # Build list of unprocessed task paths
        unprocessed_paths = tuple(
            params.task_file_paths[i]
            for i in range(processed_tasks, total_tasks)
        )

        early_termination = unprocessed_count > 0

        result = OrchestrationResult(
            total_tasks=total_tasks,
            successful_tasks=successful_tasks,
            failed_tasks=failed_tasks,
            skipped_tasks=skipped_tasks,
            unprocessed_tasks=unprocessed_count,
            task_results=tuple(self._task_results),
            unprocessed_task_paths=unprocessed_paths,
            early_termination=early_termination,
            total_duration_seconds=total_duration_seconds,
        )

        workflow.logger.info(
            "orchestration_workflow_completed",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "total_tasks": total_tasks,
                "successful_tasks": successful_tasks,
                "failed_tasks": failed_tasks,
                "unprocessed_tasks": unprocessed_count,
                "early_termination": early_termination,
                "total_duration_seconds": total_duration_seconds,
            }
        )

        return result
