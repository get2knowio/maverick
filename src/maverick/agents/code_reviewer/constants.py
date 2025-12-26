"""Constants for CodeReviewerAgent.

This module contains configuration constants for the code review agent,
including size limits and default values.
"""

from __future__ import annotations

#: Maximum diff lines before truncation (FR-017)
MAX_DIFF_LINES: int = 2000

#: Maximum diff files before truncation (FR-017)
MAX_DIFF_FILES: int = 50

#: Maximum tokens per review chunk (FR-021)
MAX_TOKENS_PER_CHUNK: int = 50_000

#: Default base branch for comparison
DEFAULT_BASE_BRANCH: str = "main"

#: Default token estimate when file not found in parsed diff
DEFAULT_FILE_TOKEN_ESTIMATE: int = 1000
