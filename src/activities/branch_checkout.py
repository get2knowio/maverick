"""Branch checkout activities for git branch management.

Temporal activities for deriving, checking out, resetting, and deleting
task branches in the automation workflow.
"""

from temporalio import activity

from src.models.branch_management import (
    BranchSelection,
    CheckoutResult,
    DeletionResult,
    MainCheckoutResult,
)
from src.utils.logging import get_structured_logger


logger = get_structured_logger(__name__)


@activity.defn(name="derive_task_branch")
async def derive_task_branch(task_descriptor: dict) -> BranchSelection:
    """Derive the branch name for a task.

    Determines the branch to use based on explicit override or spec path slug.

    Args:
        task_descriptor: Task descriptor dict with spec_path and explicit_branch

    Returns:
        BranchSelection with derived branch name and source metadata

    Raises:
        ValueError: If branch name is invalid or spec_path not under specs/
    """
    from pathlib import Path

    from src.utils.git_cli import validate_branch_name

    logger.info("derive_task_branch_started", task_descriptor=task_descriptor)

    explicit_branch = task_descriptor.get("explicit_branch")
    spec_path_str = task_descriptor.get("spec_path")

    if not spec_path_str:
        error_msg = "Task descriptor missing spec_path"
        logger.error("derive_branch_failed", error=error_msg)
        raise ValueError(error_msg)

    spec_path = Path(spec_path_str)

    # Case 1: Explicit branch override
    if explicit_branch:
        # Validate git-safe branch name
        try:
            validate_branch_name(explicit_branch)
        except ValueError as e:
            logger.error(
                "explicit_branch_invalid",
                branch_name=explicit_branch,
                error=str(e),
            )
            raise ValueError(
                f"Explicit branch name is not git-safe: {explicit_branch}"
            ) from e

        log_message = f"Using explicit branch override: {explicit_branch}"
        logger.info("branch_derived", source="explicit", branch_name=explicit_branch)

        return BranchSelection(
            branch_name=explicit_branch,
            source="explicit",
            log_message=log_message,
        )

    # Case 2: Derive from specs/<slug>/ directory structure
    # Validate spec_path is under specs/
    path_parts = spec_path.parts
    try:
        specs_index = path_parts.index("specs")
    except ValueError:
        error_msg = f"spec_path must be under specs/ directory: {spec_path}"
        logger.error("spec_path_invalid", spec_path=str(spec_path), error=error_msg)
        raise ValueError(error_msg) from None

    # Extract slug from directory name after specs/
    if specs_index + 1 >= len(path_parts):
        error_msg = f"spec_path must have directory under specs/: {spec_path}"
        logger.error("spec_path_no_slug", spec_path=str(spec_path), error=error_msg)
        raise ValueError(error_msg)

    slug = path_parts[specs_index + 1]

    # Validate derived branch name
    try:
        validate_branch_name(slug)
    except ValueError as e:
        logger.error(
            "derived_branch_invalid",
            slug=slug,
            spec_path=str(spec_path),
            error=str(e),
        )
        raise ValueError(f"Derived branch name from slug is not git-safe: {slug}") from e

    log_message = f"Derived branch from spec directory: {slug}"
    logger.info("branch_derived", source="spec-slug", branch_name=slug, slug=slug)

    return BranchSelection(
        branch_name=slug,
        source="spec-slug",
        log_message=log_message,
    )


@activity.defn(name="checkout_task_branch")
async def checkout_task_branch(branch_name: str) -> CheckoutResult:
    """Check out a task branch.

    Performs git fetch, switch to branch, and verifies clean checkout.

    Args:
        branch_name: Name of branch to check out

    Returns:
        CheckoutResult with checkout status and git head SHA

    Raises:
        RuntimeError: If working tree is dirty or branch is missing
    """
    from src.utils.git_cli import run_git_command, validate_branch_name

    logger.info("checkout_task_branch_started", branch_name=branch_name)

    # Validate branch name
    try:
        validate_branch_name(branch_name)
    except ValueError as e:
        logger.error("invalid_branch_name", branch_name=branch_name, error=str(e))
        raise RuntimeError(f"Invalid branch name: {branch_name}") from e

    logs: list[str] = []

    # Step 1: Check if already on target branch
    current_branch_result = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    if not current_branch_result.success:
        logger.error(
            "failed_to_get_current_branch",
            returncode=current_branch_result.returncode,
            stderr=current_branch_result.stderr,
        )
        raise RuntimeError(
            f"Failed to determine current branch: {current_branch_result.stderr}"
        )

    current_branch = current_branch_result.stdout.strip()
    logs.append(f"Current branch: {current_branch}")

    if current_branch == branch_name:
        # Already on target branch - short circuit (idempotent)
        git_head_result = run_git_command(["rev-parse", "--short", "HEAD"])
        git_head = git_head_result.stdout.strip() if git_head_result.success else "unknown"

        logger.info(
            "already_on_branch",
            branch_name=branch_name,
            git_head=git_head,
        )

        return CheckoutResult(
            branch_name=branch_name,
            status="already-active",
            changed=False,
            git_head=git_head,
            logs=logs,
        )

    # Step 2: Check working tree cleanliness
    status_result = run_git_command(["status", "--porcelain"])
    if not status_result.success:
        logger.error(
            "failed_to_check_status",
            returncode=status_result.returncode,
            stderr=status_result.stderr,
        )
        raise RuntimeError(f"Failed to check git status: {status_result.stderr}")

    if status_result.stdout.strip():
        # Working tree is dirty
        dirty_files = status_result.stdout.strip().split("\n")
        logger.error(
            "dirty_worktree",
            branch_name=branch_name,
            dirty_files_count=len(dirty_files),
        )
        raise RuntimeError(
            f"Cannot checkout {branch_name}: working tree has uncommitted changes. "
            f"Found {len(dirty_files)} modified/untracked files."
        )

    logs.append("Working tree is clean")

    # Step 3: Fetch from origin
    fetch_result = run_git_command(["fetch", "origin", branch_name], timeout=30)
    if fetch_result.success:
        logs.append(f"Fetched branch {branch_name} from origin")
    else:
        # Fetch might fail if branch doesn't exist remotely, but could exist locally
        logs.append(f"Fetch warning: {fetch_result.stderr[:100]}")
        logger.warning(
            "fetch_failed",
            branch_name=branch_name,
            error_code=fetch_result.error_code,
            stderr=fetch_result.stderr[:200],
        )

    # Step 4: Switch to target branch
    switch_result = run_git_command(["switch", branch_name])
    if not switch_result.success:
        # Try checkout as fallback for older git versions
        checkout_result = run_git_command(["checkout", branch_name])
        if not checkout_result.success:
            logger.error(
                "checkout_failed",
                branch_name=branch_name,
                error_code=checkout_result.error_code,
                stderr=checkout_result.stderr,
            )

            # Check if it's a missing branch error
            if checkout_result.error_code == "missing_ref":
                raise RuntimeError(
                    f"Branch '{branch_name}' does not exist. "
                    "Please create the branch or check the branch name is correct."
                )

            raise RuntimeError(
                f"Failed to checkout branch {branch_name}: {checkout_result.stderr}"
            )

        logs.append(f"Checked out {branch_name} (using git checkout)")
    else:
        logs.append(f"Switched to {branch_name}")

    # Step 5: Verify checkout succeeded
    verify_result = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    if not verify_result.success or verify_result.stdout.strip() != branch_name:
        logger.error(
            "checkout_verification_failed",
            expected=branch_name,
            actual=verify_result.stdout.strip(),
        )
        raise RuntimeError(
            f"Checkout verification failed: expected {branch_name}, "
            f"got {verify_result.stdout.strip()}"
        )

    # Get short SHA
    git_head_result = run_git_command(["rev-parse", "--short", "HEAD"])
    git_head = git_head_result.stdout.strip() if git_head_result.success else "unknown"

    logger.info(
        "checkout_succeeded",
        branch_name=branch_name,
        git_head=git_head,
    )

    return CheckoutResult(
        branch_name=branch_name,
        status="success",
        changed=True,
        git_head=git_head,
        logs=logs,
    )


@activity.defn(name="checkout_main")
async def checkout_main(main_branch: str = "main") -> MainCheckoutResult:
    """Check out and update main branch.

    Switches to main branch and performs fast-forward pull.

    Args:
        main_branch: Name of main branch (default: "main")

    Returns:
        MainCheckoutResult with checkout and pull status
    """
    logger.info("checkout_main_started", main_branch=main_branch)

    # Implementation will be added in US2
    raise NotImplementedError("checkout_main not yet implemented")


@activity.defn(name="delete_task_branch")
async def delete_task_branch(branch_name: str) -> DeletionResult:
    """Delete a task branch locally.

    Removes the specified branch, treating missing branches as success.

    Args:
        branch_name: Name of branch to delete

    Returns:
        DeletionResult with deletion status and reason
    """
    logger.info("delete_task_branch_started", branch_name=branch_name)

    # Implementation will be added in US2
    raise NotImplementedError("delete_task_branch not yet implemented")
