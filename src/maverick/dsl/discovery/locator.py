"""Workflow file locator for discovering YAML workflow definitions.

This module implements the WorkflowLocator protocol for finding workflow YAML
files in directories. It provides filesystem scanning without parsing, allowing
the loader to handle validation separately.

Example:
    ```python
    from pathlib import Path
    from maverick.dsl.discovery.locator import WorkflowLocator

    locator = WorkflowLocator()
    workflows = locator.scan(Path("~/.config/maverick/workflows"))
    for path in workflows:
        print(f"Found: {path}")
    ```
"""

from __future__ import annotations

from pathlib import Path

from maverick.logging import get_logger

__all__ = ["WorkflowLocator"]

logger = get_logger(__name__)


class WorkflowLocator:
    """Locator for finding workflow YAML files in a directory.

    This class implements filesystem scanning to discover workflow definition
    files. It focuses solely on file discovery and does not perform parsing
    or validation.

    The locator:
    - Scans for *.yaml files in a specified directory
    - Returns only files (not directories)
    - Handles inaccessible directories gracefully
    - Logs warnings for error conditions

    Example:
        ```python
        locator = WorkflowLocator()
        builtin_dir = Path("/usr/share/maverick/workflows")
        workflow_files = locator.scan(builtin_dir)

        if workflow_files:
            print(f"Found {len(workflow_files)} workflow(s)")
        else:
            print("No workflows found")
        ```
    """

    def scan(self, directory: Path) -> list[Path]:
        """Find all workflow YAML files in the specified directory.

        Scans the directory for files matching the *.yaml pattern. Only
        returns regular files, not directories. If the directory does not
        exist or is not readable, returns an empty list and logs a warning.

        Args:
            directory: Directory to scan for workflow files. Should be an
                absolute path for clarity, though relative paths are accepted.

        Returns:
            List of paths to workflow YAML files found in the directory.
            Returns empty list if directory doesn't exist or isn't accessible.
            Paths are returned in the order provided by the filesystem.

        Example:
            ```python
            locator = WorkflowLocator()
            user_dir = Path.home() / ".config" / "maverick" / "workflows"
            workflows = locator.scan(user_dir)

            for wf_path in workflows:
                print(f"Workflow file: {wf_path.name}")
            ```

        Notes:
            - Only scans the immediate directory (non-recursive)
            - Only returns *.yaml files (not *.yml or other extensions)
            - Filters out directories that match *.yaml pattern
            - Does not validate file contents or permissions
        """
        # Check if directory exists
        if not directory.exists():
            logger.warning(f"Workflow directory does not exist: {directory}")
            return []

        # Check if it's actually a directory
        if not directory.is_dir():
            logger.warning(f"Workflow path is not a directory: {directory}")
            return []

        # Try to scan for YAML files
        try:
            # Use glob to find all *.yaml files
            yaml_files = list(directory.glob("*.yaml"))

            # Filter to only files (exclude directories that somehow match)
            workflow_files = [path for path in yaml_files if path.is_file()]

            if workflow_files:
                logger.debug(
                    f"Found {len(workflow_files)} workflow file(s) in {directory}"
                )
            else:
                logger.debug(f"No workflow files found in {directory}")

            return workflow_files

        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {directory}")
            return []
        except OSError as e:
            logger.warning(f"Error reading directory {directory}: {e}")
            return []
