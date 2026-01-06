"""Specialized code review agents.

This package provides the unified review-fix workflow:

- UnifiedReviewerAgent: Comprehensive review spawning parallel expert subagents
- SimpleFixerAgent: Fixes findings with parallel execution support

Usage:
    from maverick.agents.reviewers import UnifiedReviewerAgent, SimpleFixerAgent

    # Run unified review
    reviewer = UnifiedReviewerAgent(feature_name="my-feature")
    result = await reviewer.execute({"cwd": Path.cwd()})

    # Fix findings
    fixer = SimpleFixerAgent()
    outcomes = await fixer.execute({"findings": result.all_findings})
"""

from __future__ import annotations

from maverick.agents.reviewers.simple_fixer import SimpleFixerAgent, fix_findings
from maverick.agents.reviewers.unified_reviewer import UnifiedReviewerAgent

__all__ = [
    "UnifiedReviewerAgent",
    "SimpleFixerAgent",
    "fix_findings",
]
