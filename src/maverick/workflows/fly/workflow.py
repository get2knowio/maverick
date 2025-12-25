"""Fly Workflow orchestrator implementation.

This module defines the FlyWorkflow class which orchestrates the complete
spec-based development workflow including setup, implementation, code review,
validation, convention updates, and PR management.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.agents.result import AgentUsage
from maverick.dsl.events import (
    ProgressEvent,
)
from maverick.dsl.events import (
    StepCompleted as DslStepCompleted,
)
from maverick.dsl.events import (
    StepStarted as DslStepStarted,
)
from maverick.dsl.events import (
    WorkflowCompleted as DslWorkflowCompleted,
)
from maverick.dsl.events import (
    WorkflowStarted as DslWorkflowStarted,
)
from maverick.dsl.results import WorkflowResult
from maverick.dsl.serialization.executor import WorkflowFileExecutor
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.workflows.base import WorkflowDSLMixin
from maverick.workflows.fly.dsl import DSL_STEP_TO_STAGE
from maverick.workflows.fly.events import (
    FlyProgressEvent,
    FlyStageCompleted,
    FlyStageStarted,
    FlyWorkflowCompleted,
    FlyWorkflowFailed,
    FlyWorkflowStarted,
)
from maverick.workflows.fly.models import (
    FlyConfig,
    FlyInputs,
    FlyResult,
    WorkflowStage,
    WorkflowState,
)

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent
    from maverick.agents.generators.commit_message import CommitMessageGenerator
    from maverick.agents.generators.pr_description import PRDescriptionGenerator
    from maverick.runners.coderabbit import CodeRabbitRunner
    from maverick.runners.git import GitRunner
    from maverick.runners.github import GitHubCLIRunner
    from maverick.runners.validation import ValidationRunner

logger = logging.getLogger(__name__)


class FlyWorkflow(WorkflowDSLMixin):
    """Fly workflow orchestrator.

    Orchestrates the complete spec-based development workflow across 8 stages:

    1. INIT Stage: Parse arguments, validate inputs, checkout branch,
       sync with origin/main
    2. IMPLEMENTATION Stage: Execute ImplementerAgent on tasks,
       parallel for "P:" marked tasks
    3. VALIDATION Stage: Run ValidationWorkflow with auto-fix,
       retry up to max_validation_attempts
    4. CODE_REVIEW Stage: Run parallel reviews, optionally integrate
       CodeRabbit CLI
    5. CONVENTION_UPDATE Stage: Analyze findings, suggest CLAUDE.md updates
    6. PR_CREATION Stage: Generate PR body, create/update via gh CLI
    7. COMPLETE Stage: Terminal success state
    8. FAILED Stage: Terminal failure state

    The workflow maintains immutable state transitions and supports
    graceful failure handling.

    Examples:
        Basic usage::

            workflow = FlyWorkflow()
            inputs = FlyInputs(branch_name="feature/my-feature")
            result = await workflow.execute(inputs)

        With custom configuration::

            config = FlyConfig(max_validation_attempts=5, auto_merge=True)
            workflow = FlyWorkflow(config=config)
            async for event in workflow.execute_stream(inputs):
                print(f"Event: {event}")
    """

    def __init__(
        self,
        config: FlyConfig | None = None,
        registry: ComponentRegistry | None = None,
        git_runner: GitRunner | None = None,
        validation_runner: ValidationRunner | None = None,
        github_runner: GitHubCLIRunner | None = None,
        coderabbit_runner: CodeRabbitRunner | None = None,
        implementer_agent: MaverickAgent[Any, Any] | None = None,
        code_reviewer_agent: MaverickAgent[Any, Any] | None = None,
        commit_generator: CommitMessageGenerator | None = None,
        pr_generator: PRDescriptionGenerator | None = None,
    ) -> None:
        """Initialize the fly workflow.

        Args:
            config: Optional workflow configuration. Uses defaults if None.
            registry: Component registry for DSL execution.
            git_runner: GitRunner instance for git operations.
            validation_runner: ValidationRunner for validation stages.
            github_runner: GitHubCLIRunner for PR creation.
            coderabbit_runner: CodeRabbitRunner for code review (optional).
            implementer_agent: ImplementerAgent for code implementation.
            code_reviewer_agent: CodeReviewerAgent for review interpretation.
            commit_generator: CommitMessageGenerator for commit messages.
            pr_generator: PRDescriptionGenerator for PR descriptions.
        """
        # Initialize the mixin first
        super().__init__()

        self._config: FlyConfig = config or FlyConfig()
        self._registry = registry or ComponentRegistry()
        self._git_runner = git_runner
        self._validation_runner = validation_runner
        self._github_runner = github_runner
        self._coderabbit_runner = coderabbit_runner
        self._implementer_agent = implementer_agent
        self._code_reviewer_agent = code_reviewer_agent
        self._commit_generator = commit_generator
        self._pr_generator = pr_generator

        # Internal state
        self._cancel_event = asyncio.Event()
        self._result: FlyResult | None = None
        self._state: WorkflowState | None = None
        self._usage_records: list[AgentUsage] = []

        # DSL executor
        self._executor: WorkflowFileExecutor | None = None

    def _aggregate_tokens(self) -> AgentUsage:
        """Aggregate token usage from all agent calls."""
        if not self._usage_records:
            return AgentUsage(
                input_tokens=0,
                output_tokens=0,
                total_cost_usd=0.0,
                duration_ms=0,
            )

        return AgentUsage(
            input_tokens=sum(u.input_tokens for u in self._usage_records),
            output_tokens=sum(u.output_tokens for u in self._usage_records),
            total_cost_usd=sum(u.total_cost_usd or 0.0 for u in self._usage_records),
            duration_ms=sum(u.duration_ms for u in self._usage_records),
        )

    def _translate_event(self, event: ProgressEvent) -> FlyProgressEvent | None:
        """Translate DSL progress events to FlyProgressEvent types.

        Maps DSL events to corresponding Fly workflow events based on step metadata
        and event types. Returns None for events that don't map to Fly events.

        Args:
            event: DSL ProgressEvent from WorkflowFileExecutor.

        Returns:
            Corresponding FlyProgressEvent, or None if no mapping exists.
        """
        # Map DSL WorkflowStarted to FlyWorkflowStarted
        if isinstance(event, DslWorkflowStarted):
            # Extract inputs from DSL event
            task_file = (
                Path(event.inputs["task_file"]) if "task_file" in event.inputs else None
            )
            fly_inputs = FlyInputs(
                branch_name=event.inputs.get("branch_name", "unknown"),
                task_file=task_file,
                skip_review=event.inputs.get("skip_review", False),
                skip_pr=event.inputs.get("skip_pr", False),
                draft_pr=event.inputs.get("draft_pr", False),
                base_branch=event.inputs.get("base_branch", "main"),
                dry_run=event.inputs.get("dry_run", False),
            )
            return FlyWorkflowStarted(inputs=fly_inputs, timestamp=event.timestamp)

        # Map DSL StepStarted to FlyStageStarted
        elif isinstance(event, DslStepStarted):
            # Use centralized mapping instead of duplicated dict
            stage = DSL_STEP_TO_STAGE.get(event.step_name)
            if stage:
                return FlyStageStarted(stage=stage, timestamp=event.timestamp)

        # Map DSL StepCompleted to FlyStageCompleted
        elif isinstance(event, DslStepCompleted):
            # Use centralized mapping instead of duplicated dict
            stage = DSL_STEP_TO_STAGE.get(event.step_name)
            if stage:
                # Result depends on the step
                result: Any = {
                    "success": event.success,
                    "duration_ms": event.duration_ms,
                }
                return FlyStageCompleted(
                    stage=stage, result=result, timestamp=event.timestamp
                )

        # WorkflowCompleted is handled separately in execute()
        return None

    def _build_fly_result(self, workflow_result: WorkflowResult) -> FlyResult:
        """Build FlyResult from DSL WorkflowResult.

        Extracts relevant information from the DSL workflow result and constructs
        a FlyResult with appropriate state, summary, and metadata.

        Args:
            workflow_result: WorkflowResult from DSL execution.

        Returns:
            FlyResult instance with workflow outcome.
        """
        # Determine final stage based on workflow success
        final_stage = (
            WorkflowStage.COMPLETE if workflow_result.success else WorkflowStage.FAILED
        )

        # Build state from workflow result
        state = WorkflowState(
            stage=final_stage,
            branch=self._state.branch if self._state else "unknown",
            task_file=self._state.task_file if self._state else None,
            started_at=self._state.started_at if self._state else datetime.now(),
            completed_at=datetime.now(),
        )

        # Copy existing state results if available
        if self._state:
            state.implementation_result = self._state.implementation_result
            state.validation_result = self._state.validation_result
            state.review_results = self._state.review_results
            state.pr_url = self._state.pr_url
            state.errors = self._state.errors

        # Extract errors from failed steps
        if not workflow_result.success:
            failed_step = workflow_result.failed_step
            if failed_step and failed_step.error:
                state.errors.append(f"{failed_step.name}: {failed_step.error}")

        # Build summary
        if workflow_result.success:
            summary = "Fly workflow completed successfully"
            if state.pr_url:
                summary += f". PR: {state.pr_url}"
        else:
            failed_step_name = (
                workflow_result.failed_step.name
                if workflow_result.failed_step
                else "unknown"
            )
            summary = f"Fly workflow failed at step: {failed_step_name}"

        # Create result
        return FlyResult(
            success=workflow_result.success,
            state=state,
            summary=summary,
            token_usage=self._aggregate_tokens(),
            total_cost_usd=self._aggregate_tokens().total_cost_usd or 0.0,
        )

    async def execute(self, inputs: FlyInputs) -> AsyncIterator[FlyProgressEvent]:
        """Execute the fly workflow.

        Args:
            inputs: Validated workflow inputs including branch name and options.

        Yields:
            Progress events for TUI consumption.
        """
        # Run preflight validation FIRST, before any state changes
        # This runs even in dry_run mode to validate the environment
        try:
            await self.run_preflight()
        except Exception as e:
            # Import here to check exception type
            from maverick.exceptions import PreflightValidationError

            if isinstance(e, PreflightValidationError):
                error_msg = f"Preflight validation failed: {e}"
            else:
                error_msg = f"Unexpected preflight error: {e}"
            logger.error(error_msg)
            # Create minimal state for error reporting
            self._state = WorkflowState(
                branch=inputs.branch_name,
                task_file=inputs.task_file,
            )
            self._state.errors.append(error_msg)
            self._state.stage = WorkflowStage.FAILED
            yield FlyWorkflowFailed(error=error_msg, state=self._state)
            return

        # Initialize state
        self._state = WorkflowState(
            branch=inputs.branch_name,
            task_file=inputs.task_file,
        )

        # DSL execution path (if enabled)
        if self._use_dsl:
            try:
                # Load workflow definition
                workflow = self._load_workflow("fly")

                # Create executor
                self._executor = WorkflowFileExecutor(
                    registry=self._registry,
                    config=self._config,
                )

                # Convert FlyInputs to dict for DSL executor
                workflow_inputs = inputs.model_dump()
                # Convert Path to string for YAML compatibility
                if workflow_inputs.get("task_file"):
                    workflow_inputs["task_file"] = str(workflow_inputs["task_file"])

                # Execute workflow and translate events
                async for event in self._executor.execute(
                    workflow, inputs=workflow_inputs
                ):
                    # Translate DSL events to FlyProgressEvent
                    fly_event = self._translate_event(event)
                    if fly_event:
                        yield fly_event

                    # Handle WorkflowCompleted specially
                    if isinstance(event, DslWorkflowCompleted):
                        # Build final result
                        workflow_result = self._executor.get_result()
                        self._result = self._build_fly_result(workflow_result)
                        yield FlyWorkflowCompleted(result=self._result)

                return

            except Exception as e:
                error_msg = f"DSL workflow execution failed: {e}"
                logger.exception(error_msg)
                if self._state:
                    self._state.errors.append(error_msg)
                    self._state.stage = WorkflowStage.FAILED
                    self._state.completed_at = datetime.now()
                    yield FlyWorkflowFailed(error=error_msg, state=self._state)
                return

        # Legacy execution path (original implementation)
        # Emit workflow started
        yield FlyWorkflowStarted(inputs=inputs)

        try:
            # INIT Stage
            if self._cancel_event.is_set():
                return

            yield FlyStageStarted(stage=WorkflowStage.INIT)
            self._state.stage = WorkflowStage.INIT

            # Create branch via GitRunner
            if inputs.dry_run:
                logger.info(f"[DRY-RUN] Would create branch: {inputs.branch_name}")
                actual_branch = inputs.branch_name
                self._state.branch = actual_branch
            else:
                # Initialize GitRunner with error handling (FR-001)
                if self._git_runner is None:
                    try:
                        from maverick.runners.git import GitRunner

                        self._git_runner = GitRunner()
                    except Exception as e:
                        error_msg = f"Failed to initialize GitRunner: {e}"
                        self._state.errors.append(error_msg)
                        yield FlyWorkflowFailed(error=error_msg, state=self._state)
                        return

                branch_result = await self._git_runner.create_branch_with_fallback(
                    inputs.branch_name, "HEAD"
                )

                if not branch_result.success:
                    error_msg = f"Failed to create branch: {branch_result.error}"
                    self._state.errors.append(error_msg)
                    yield FlyWorkflowFailed(error=error_msg, state=self._state)
                    return

                # Update actual branch name (in case fallback was used)
                actual_branch = branch_result.output
                self._state.branch = actual_branch

            # Parse task file (FR-002)
            tasks: list[str] = []
            if inputs.task_file is not None:
                if inputs.dry_run:
                    logger.info(f"[DRY-RUN] Would parse task file: {inputs.task_file}")
                else:
                    try:
                        task_content = inputs.task_file.read_text(encoding="utf-8")
                        # Parse tasks - each line starting with "- [ ]" is a task
                        for line in task_content.splitlines():
                            stripped = line.strip()
                            if stripped.startswith("- [ ]"):
                                tasks.append(stripped[5:].strip())
                            elif stripped.startswith("- [x]"):
                                # Already completed, skip
                                continue
                        logger.info(
                            f"Parsed {len(tasks)} tasks from {inputs.task_file}"
                        )
                    except FileNotFoundError:
                        error_msg = f"Task file not found: {inputs.task_file}"
                        self._state.errors.append(error_msg)
                        yield FlyWorkflowFailed(error=error_msg, state=self._state)
                        return
                    except Exception as e:
                        error_msg = f"Failed to parse task file: {e}"
                        self._state.errors.append(error_msg)
                        logger.error(error_msg)

            yield FlyStageCompleted(
                stage=WorkflowStage.INIT,
                result={"branch": actual_branch, "tasks": tasks},
            )

            # IMPLEMENTATION Stage
            if self._cancel_event.is_set():
                return

            yield FlyStageStarted(stage=WorkflowStage.IMPLEMENTATION)
            self._state.stage = WorkflowStage.IMPLEMENTATION

            if inputs.dry_run:
                logger.info("[DRY-RUN] Would execute ImplementerAgent on tasks")
                # Still emit progress event in dry-run mode
            else:
                if self._implementer_agent is not None:
                    try:
                        # Agent may be mock or real - handle both cases
                        impl_result = await self._implementer_agent.execute()  # type: ignore[call-arg]
                        if hasattr(impl_result, "usage") and impl_result.usage:
                            self._usage_records.append(impl_result.usage)
                        self._state.implementation_result = impl_result
                    except Exception as e:
                        error_msg = f"Implementation failed: {e}"
                        self._state.errors.append(error_msg)
                        logger.error(error_msg)

            yield FlyStageCompleted(
                stage=WorkflowStage.IMPLEMENTATION,
                result=self._state.implementation_result,
            )

            # VALIDATION Stage (FR-007, FR-008, FR-009)
            if self._cancel_event.is_set():
                return

            yield FlyStageStarted(stage=WorkflowStage.VALIDATION)
            self._state.stage = WorkflowStage.VALIDATION

            validation_passed = False

            if inputs.dry_run:
                logger.info("[DRY-RUN] Would run validation (format, lint, test)")
                max_attempts = self._config.max_validation_attempts
                logger.info(f"[DRY-RUN] Would retry up to {max_attempts} times")
                validation_passed = True  # Assume success in dry-run
            else:
                if self._validation_runner is not None:
                    from maverick.models.validation import ValidationWorkflowResult

                    # Validation retry loop (FR-009)
                    for attempt in range(1, self._config.max_validation_attempts + 1):
                        if self._cancel_event.is_set():
                            return

                        max_attempts = self._config.max_validation_attempts
                        logger.info(f"Validation attempt {attempt}/{max_attempts}")

                        try:
                            validation_output = await self._validation_runner.run()
                            validation_result = ValidationWorkflowResult(
                                success=validation_output.success,
                                stage_results=list(validation_output.stages),  # type: ignore[arg-type]
                            )
                            self._state.validation_result = validation_result
                            validation_passed = validation_result.success

                            if validation_passed:
                                logger.info(f"Validation passed on attempt {attempt}")
                                break

                            # Validation failed - invoke fix agent if available (FR-008)
                            if attempt < self._config.max_validation_attempts:
                                logger.warning(
                                    f"Validation failed on attempt {attempt}, "
                                    f"invoking fix agent"
                                )
                                # Use implementer agent as fix agent
                                if self._implementer_agent is not None:
                                    try:
                                        agent = self._implementer_agent
                                        fix_result = await agent.execute()  # type: ignore[call-arg]
                                        has_usage = hasattr(fix_result, "usage")
                                        if has_usage and fix_result.usage:
                                            self._usage_records.append(fix_result.usage)
                                    except Exception as e:
                                        logger.warning(f"Fix agent failed: {e}")

                        except Exception as e:
                            error_msg = f"Validation attempt {attempt} failed: {e}"
                            self._state.errors.append(error_msg)
                            logger.warning(error_msg)

                    # Check if we exhausted all retries (FR-009a)
                    if not validation_passed:
                        max_attempts = self._config.max_validation_attempts
                        logger.warning(
                            f"Validation exhausted after {max_attempts} attempts, "
                            f"continuing workflow with draft PR"
                        )

            yield FlyStageCompleted(
                stage=WorkflowStage.VALIDATION, result=self._state.validation_result
            )

            # CODE_REVIEW Stage
            if not inputs.skip_review:
                if self._cancel_event.is_set():
                    return

                yield FlyStageStarted(stage=WorkflowStage.CODE_REVIEW)
                self._state.stage = WorkflowStage.CODE_REVIEW

                if inputs.dry_run:
                    logger.info("[DRY-RUN] Would run code review")
                else:
                    # Run CodeRabbit if enabled and available
                    coderabbit_enabled = self._config.coderabbit_enabled
                    if coderabbit_enabled and self._coderabbit_runner is not None:
                        try:
                            if await self._coderabbit_runner.is_available():
                                await self._coderabbit_runner.run_review()
                        except Exception as e:
                            logger.warning(f"CodeRabbit review failed: {e}")

                    # Run CodeReviewerAgent
                    if self._code_reviewer_agent is not None:
                        try:
                            # Agent may be mock or real - handle both cases
                            review_result = await self._code_reviewer_agent.execute()  # type: ignore[call-arg]
                            if hasattr(review_result, "usage") and review_result.usage:
                                self._usage_records.append(review_result.usage)
                            self._state.review_results.append(review_result)
                        except Exception as e:
                            logger.warning(f"Code review failed: {e}")

                yield FlyStageCompleted(
                    stage=WorkflowStage.CODE_REVIEW, result=self._state.review_results
                )

            # CONVENTION_UPDATE Stage (Task #87)
            if self._cancel_event.is_set():
                return

            yield FlyStageStarted(stage=WorkflowStage.CONVENTION_UPDATE)
            self._state.stage = WorkflowStage.CONVENTION_UPDATE

            if inputs.dry_run:
                logger.info("[DRY-RUN] Would analyze findings and update conventions")
            else:
                # Placeholder logic: In future this will use ConventionAgent
                # For now, we assume convention updates happen via manual review or
                # separate command /speckit.constitution
                logger.info("Convention update stage (placeholder)")

            yield FlyStageCompleted(stage=WorkflowStage.CONVENTION_UPDATE, result=None)

            # Commit Stage - create commit with all changes
            if self._cancel_event.is_set():
                return

            # Get diff for commit message
            diff_output = ""
            commit_message = "chore: workflow changes"

            if inputs.dry_run:
                logger.info("[DRY-RUN] Would stage all changes with 'git add --all'")
                logger.info("[DRY-RUN] Would get staged diff")
                logger.info("[DRY-RUN] Would generate commit message")
                logger.info(f"[DRY-RUN] Would commit: {commit_message}")
            else:
                if self._git_runner is not None:
                    try:
                        await self._git_runner.add(add_all=True)
                        diff_output = await self._git_runner.diff(staged=True)
                    except Exception as e:
                        logger.warning(f"Failed to get diff: {e}")

                # Generate commit message
                if self._commit_generator is not None and diff_output:
                    try:
                        result = await self._commit_generator.generate(
                            {
                                "diff": diff_output,
                                "file_stats": {},
                            },
                            return_usage=False,
                        )
                        # When return_usage=False, result is always str
                        assert isinstance(result, str)
                        commit_message = result
                    except Exception as e:
                        logger.warning(f"Commit message generation failed: {e}")

                # Create commit
                if self._git_runner is not None:
                    try:
                        commit_result = await self._git_runner.commit(commit_message)
                        if not commit_result.success:
                            logger.warning(f"Commit failed: {commit_result.error}")
                    except Exception as e:
                        logger.warning(f"Failed to create commit: {e}")

            # PR_CREATION Stage
            if inputs.skip_pr:
                self._state.stage = WorkflowStage.COMPLETE
                self._state.completed_at = datetime.now()
                self._result = FlyResult(
                    success=validation_passed and len(self._state.errors) == 0,
                    state=self._state,
                    summary="Workflow completed without PR creation",
                    token_usage=self._aggregate_tokens(),
                    total_cost_usd=self._aggregate_tokens().total_cost_usd or 0.0,
                )
                yield FlyWorkflowCompleted(result=self._result)
                return

            if self._cancel_event.is_set():
                return

            yield FlyStageStarted(stage=WorkflowStage.PR_CREATION)
            self._state.stage = WorkflowStage.PR_CREATION

            # Generate PR description
            pr_body = "## Summary\n\nWorkflow execution completed."
            pr_url = None

            if inputs.dry_run:
                logger.info("[DRY-RUN] Would generate PR description")
                logger.info(f"[DRY-RUN] Would create PR: feat: {actual_branch}")
                logger.info(f"[DRY-RUN] Would target base branch: {inputs.base_branch}")
                is_draft_pr = inputs.draft_pr or not validation_passed
                logger.info(f"[DRY-RUN] Would set draft={is_draft_pr}")
                pr_url = "https://github.com/owner/repo/pull/[dry-run]"
                self._state.pr_url = pr_url
            else:
                if self._pr_generator is not None:
                    try:
                        result = await self._pr_generator.generate(
                            {
                                "commits": [commit_message] if commit_message else [],
                                "task_summary": f"Feature branch: {actual_branch}",
                                "validation_results": {
                                    "passed": validation_passed,
                                    "failures": self._state.errors,
                                },
                            },
                            return_usage=False,
                        )
                        # When return_usage=False, result is always str
                        assert isinstance(result, str)
                        pr_body = result
                    except Exception as e:
                        logger.warning(f"PR description generation failed: {e}")

                # Create PR
                if self._github_runner is not None:
                    try:
                        is_draft = inputs.draft_pr or not validation_passed
                        pr_result = await self._github_runner.create_pr(
                            title=f"feat: {actual_branch}",
                            body=pr_body,
                            base=inputs.base_branch,
                            draft=is_draft,
                        )
                        # Handle mock (string) and real (PullRequest) cases
                        if isinstance(pr_result, str):
                            pr_url = pr_result
                        else:
                            pr_url = pr_result.url
                        self._state.pr_url = pr_url
                    except Exception as e:
                        error_msg = f"PR creation failed: {e}"
                        self._state.errors.append(error_msg)
                        logger.error(error_msg)

            yield FlyStageCompleted(
                stage=WorkflowStage.PR_CREATION, result={"pr_url": pr_url}
            )

            # COMPLETE Stage
            self._state.stage = WorkflowStage.COMPLETE
            self._state.completed_at = datetime.now()

            summary = (
                f"Workflow completed. PR: {pr_url}" if pr_url else "Workflow completed"
            )
            self._result = FlyResult(
                success=validation_passed and len(self._state.errors) == 0,
                state=self._state,
                summary=summary,
                token_usage=self._aggregate_tokens(),
                total_cost_usd=self._aggregate_tokens().total_cost_usd or 0.0,
            )

            yield FlyWorkflowCompleted(result=self._result)

        except Exception as e:
            error_msg = f"Workflow failed: {e}"
            self._state.errors.append(error_msg)
            self._state.stage = WorkflowStage.FAILED
            self._state.completed_at = datetime.now()
            logger.exception(error_msg)
            yield FlyWorkflowFailed(error=error_msg, state=self._state)

    def cancel(self) -> None:
        """Request workflow cancellation."""
        self._cancel_event.set()

    def get_result(self) -> FlyResult:
        """Get the final workflow result.

        Returns:
            FlyResult with success status, final state, and summary.

        Raises:
            RuntimeError: If called before execute() completes.
        """
        if self._result is None:
            raise RuntimeError("Workflow has not completed. Call execute() first.")
        return self._result


__all__ = [
    "FlyWorkflow",
]
