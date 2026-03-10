"""Specialized code review agents.

This package provides the parallel review-fix workflow:

- CompletenessReviewerAgent: Requirements coverage and acceptance criteria
- CorrectnessReviewerAgent: Technical quality, security, and best practices
- UnifiedReviewerAgent: Legacy combined reviewer (superseded by the parallel pair)
- SimpleFixerAgent: Fixes findings with parallel execution support

Usage:
    from maverick.agents.reviewers import (
        CompletenessReviewerAgent,
        CorrectnessReviewerAgent,
        SimpleFixerAgent,
    )

    # Run parallel reviews
    completeness = CompletenessReviewerAgent(feature_name="my-feature")
    correctness = CorrectnessReviewerAgent(feature_name="my-feature")

    # Fix findings
    fixer = SimpleFixerAgent()
    outcomes = await fixer.execute({"findings": result.all_findings})
"""

from __future__ import annotations

from maverick.agents.reviewers.completeness_reviewer import CompletenessReviewerAgent
from maverick.agents.reviewers.correctness_reviewer import CorrectnessReviewerAgent
from maverick.agents.reviewers.simple_fixer import SimpleFixerAgent

__all__ = [
    "CompletenessReviewerAgent",
    "CorrectnessReviewerAgent",
    "SimpleFixerAgent",
]
