"""Adapter module to convert CLI models to workflow input.

Adapts CLITaskDescriptor instances to OrchestrationInput for the
MultiTaskOrchestrationWorkflow.
"""

import re
from pathlib import Path

from src.cli._git import derive_branch_name_hint
from src.cli._models import CLITaskDescriptor
from src.common.logging import get_logger
from src.models.orchestration import OrchestrationInput, TaskDescriptor


logger = get_logger(__name__)


def adapt_to_orchestration_input(
    cli_descriptors: list[CLITaskDescriptor],
    repo_root: str,
    return_to_branch: str,
    interactive_mode: bool = False,
    default_model: str | None = None,
    default_agent_profile: str | None = None,
    retry_limit: int = 3,
) -> OrchestrationInput:
    """Adapt CLI task descriptors to workflow OrchestrationInput.

    Converts CLITaskDescriptor objects to TaskDescriptor objects expected by
    the MultiTaskOrchestrationWorkflow. The workflow will derive phases from
    the task files themselves.

    Args:
        cli_descriptors: List of CLI task descriptors
        repo_root: Absolute repository root path
        return_to_branch: Current branch to return to after workflow
        interactive_mode: Enable interactive pause mode
        default_model: Optional default AI model
        default_agent_profile: Optional default agent profile
        retry_limit: Maximum retry attempts (1-10)

    Returns:
        OrchestrationInput ready for workflow execution

    Raises:
        ValueError: If inputs are invalid or conversion fails
    """
    if not cli_descriptors:
        raise ValueError("cli_descriptors must contain at least one descriptor")

    if not repo_root or not repo_root.strip():
        raise ValueError("repo_root must be non-empty")

    if not return_to_branch or not return_to_branch.strip():
        raise ValueError("return_to_branch must be non-empty")

    if retry_limit < 1 or retry_limit > 10:
        raise ValueError("retry_limit must be between 1 and 10")

    logger.info(
        f"Adapting {len(cli_descriptors)} CLI descriptor(s) to OrchestrationInput"
    )

    # Convert CLI descriptors to workflow TaskDescriptors
    workflow_descriptors: list[TaskDescriptor] = []

    for cli_desc in cli_descriptors:
        # Derive branch name if not provided
        branch_name = cli_desc.branch_name
        if branch_name is None:
            branch_name = derive_branch_name_hint(cli_desc.task_id)

        # Create workflow TaskDescriptor
        # Note: phases will be empty here - workflow will discover them from task file
        workflow_desc = TaskDescriptor(
            task_id=cli_desc.task_id,
            spec_path=cli_desc.task_file,
            explicit_branch=branch_name,
            phases=["placeholder"],  # Workflow will replace with actual phases
        )

        workflow_descriptors.append(workflow_desc)

        logger.debug(
            f"Converted CLI descriptor: task_id={cli_desc.task_id}, "
            f"branch={branch_name}, spec_path={cli_desc.task_file}"
        )

    # Build OrchestrationInput
    orchestration_input = OrchestrationInput(
        task_descriptors=tuple(workflow_descriptors),
        interactive_mode=interactive_mode,
        retry_limit=retry_limit,
        repo_path=repo_root,
        default_model=default_model,
        default_agent_profile=default_agent_profile,
    )

    logger.info(
        f"Created OrchestrationInput with {len(workflow_descriptors)} task(s), "
        f"interactive_mode={interactive_mode}, retry_limit={retry_limit}"
    )

    return orchestration_input


def build_cli_descriptor(
    task_file: Path,
    spec_root: Path,
    repo_root: Path,
    return_to_branch: str,
    interactive: bool = False,
    branch_name_hint: str | None = None,
    model_prefs: dict[str, str | int] | None = None,
) -> CLITaskDescriptor:
    """Build a CLITaskDescriptor from discovered task information.

    Args:
        task_file: Absolute path to tasks.md file
        spec_root: Absolute path to spec directory
        repo_root: Absolute repository root
        return_to_branch: Current git branch
        interactive: Interactive mode flag
        branch_name_hint: Optional explicit branch name
        model_prefs: Optional model preferences

    Returns:
        CLITaskDescriptor instance

    Raises:
        ValueError: If inputs are invalid
    """
    if not task_file.exists():
        raise ValueError(f"Task file does not exist: {task_file}")

    if not spec_root.exists():
        raise ValueError(f"Spec root does not exist: {spec_root}")

    if not repo_root.exists():
        raise ValueError(f"Repo root does not exist: {repo_root}")

    if not return_to_branch or not return_to_branch.strip():
        raise ValueError("return_to_branch must be non-empty")

    task_file_resolved = task_file.resolve()
    spec_root_resolved = spec_root.resolve()
    repo_root_resolved = repo_root.resolve()

    # Ensure spec root is inside repository root
    try:
        spec_root_resolved.relative_to(repo_root_resolved)
    except ValueError as e:
        raise ValueError(
            f"spec_root must be under repo_root: {spec_root_resolved} not under {repo_root_resolved}"
        ) from e

    # Ensure task file is inside spec root (and therefore repo)
    try:
        task_file_resolved.relative_to(spec_root_resolved)
    except ValueError as e:
        raise ValueError(
            f"task_file must be under spec_root: {task_file_resolved} not under {spec_root_resolved}"
        ) from e

    # Derive task_id from spec directory name and task file stem for stability
    task_id = f"{spec_root_resolved.name}-{_slugify(task_file_resolved.stem)}"

    logger.debug(
        f"Building CLI descriptor: task_id={task_id}, "
        f"task_file={task_file_resolved}, spec_root={spec_root_resolved}"
    )

    return CLITaskDescriptor(
        task_id=task_id,
        task_file=str(task_file_resolved),
        spec_root=str(spec_root_resolved),
        branch_name=branch_name_hint,
        return_to_branch=return_to_branch,
        repo_root=str(repo_root_resolved),
        interactive=interactive,
        model_prefs=model_prefs,
    )


def _slugify(value: str) -> str:
    """Convert a file stem into a CLI-friendly slug."""
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "tasks"
