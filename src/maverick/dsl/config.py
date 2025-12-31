"""DSL configuration and default values.

This module centralizes all default values and magic constants for DSL execution,
context building, and visualization. By consolidating these values in one place,
we ensure consistency across the codebase and make it easier to tune behavior.

Design Rationale:
    - All constants are defined in a frozen dataclass to prevent accidental mutation
    - A singleton instance (DEFAULTS) provides convenient access
    - Constants are grouped by functional area for clarity
    - Each constant is documented with its purpose and rationale
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DSLDefaults",
    "DEFAULTS",
]


@dataclass(frozen=True, slots=True)
class DSLDefaults:
    """Default values for DSL execution and context building.

    This class contains all magic constants and default values used throughout
    the DSL subsystem. Values are frozen to prevent accidental modification.

    Attributes:
        Command Execution:
            COMMAND_TIMEOUT: Default timeout for shell commands in seconds.
                Why 30.0: Balances between allowing slow operations (tree, git)
                and preventing indefinite hangs. Most commands complete in <5s.

        Project Structure:
            PROJECT_STRUCTURE_MAX_DEPTH: Maximum depth for directory tree traversal.
                Why 3: Captures src/package/module structure while avoiding
                deep node_modules, .venv, and build artifact recursion.

        Retry Behavior:
            DEFAULT_RETRY_ATTEMPTS: Maximum retry attempts for validate steps.
                Why 3: Industry standard (initial + 2 retries). Enough to handle
                transient failures without excessive delays.
            DEFAULT_RETRY_DELAY: Base delay in seconds for exponential backoff.
                Why 1.0: First retry at 1s, second at 2s, third at 4s. Reasonable
                for validation stages (lint, format) that may need file I/O to settle.
            RETRY_BACKOFF_MAX: Maximum delay cap in seconds for retry backoff.
                Why 60.0: Prevents excessive waits while allowing sufficient backoff
                for rate-limited APIs or slow network operations.
            RETRY_JITTER_MIN: Minimum jitter factor for retry delay randomization.
                Why 0.5: Provides 50% variance to prevent thundering herd when
                multiple workflows retry simultaneously.

        Output Limits:
            MAX_STEP_OUTPUT_SIZE: Maximum items in step output list/dict
                before warning. Why 10000: Large enough for comprehensive
                test results or file lists, small enough to prevent memory
                exhaustion. Warnings appear at this threshold.
            MAX_CONTEXT_SIZE: Maximum recommended size for entire context
                (not enforced). Why 50000: Reserved for future use. Five
                times step size allows accumulation across workflow without
                unbounded growth.

        Checkpoint Behavior:
            CHECKPOINT_DIR: Default directory for checkpoint persistence.
                Why .maverick/checkpoints: Follows .git convention for tool-specific
                state. Hidden directory prevents clutter. Git-ignored by default.

        Visualization:
            ASCII_DIAGRAM_WIDTH: Default width in characters for ASCII diagrams.
                Why 60: Fits standard terminal width (80 columns) with margin for
                line numbers and editor chrome. Wide enough for readable step names.
            ASCII_DIAGRAM_BORDER_WIDTH: Width of border characters in ASCII diagrams.
                Why 2: Accounts for box-drawing corner characters (┌, ┐, └, ┘).
            ASCII_DIAGRAM_PADDING: Width of padding on each side (│ + space).
                Why 2: Provides visual breathing room. Total padding is 4 (2 * 2).

        Issue Analysis:
            DEFAULT_ISSUE_LIMIT: Default maximum number of issues to analyze.
                Why 5: Reasonable batch size for parallel analysis. Prevents
                overwhelming the agent with too many issues at once.
            DEFAULT_RECENT_COMMIT_LIMIT: Default number of recent commits to retrieve.
                Why 10: Provides sufficient context for commit message style and
                recent changes without overwhelming the generator.
    """

    # Command execution
    COMMAND_TIMEOUT: float = 30.0

    # Project structure
    PROJECT_STRUCTURE_MAX_DEPTH: int = 3

    # Retry behavior
    DEFAULT_RETRY_ATTEMPTS: int = 3
    DEFAULT_RETRY_DELAY: float = 1.0
    RETRY_BACKOFF_MAX: float = 60.0
    RETRY_JITTER_MIN: float = 0.5

    # Output limits
    MAX_STEP_OUTPUT_SIZE: int = 10000
    MAX_CONTEXT_SIZE: int = 50000

    # Checkpoint behavior
    CHECKPOINT_DIR: str = ".maverick/checkpoints"

    # Visualization
    ASCII_DIAGRAM_WIDTH: int = 60
    ASCII_DIAGRAM_BORDER_WIDTH: int = 2
    ASCII_DIAGRAM_PADDING: int = 2

    # Issue analysis
    DEFAULT_ISSUE_LIMIT: int = 5
    DEFAULT_RECENT_COMMIT_LIMIT: int = 10


# Singleton instance for convenient access throughout the codebase
DEFAULTS = DSLDefaults()
