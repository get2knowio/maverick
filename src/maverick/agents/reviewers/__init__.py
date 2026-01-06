"""Specialized code review agents.

This package provides focused review agents that each examine code from
a specific perspective:

Unified (preferred):
- UnifiedReviewerAgent: Comprehensive review spawning parallel expert subagents
- SimpleFixerAgent: Fixes findings with parallel execution support

Legacy:
- SpecReviewerAgent: Reviews for spec compliance and completeness
- TechnicalReviewerAgent: Reviews for technical quality and best practices
- ReviewFixerAgent: Fixes issues identified by reviewers

The unified agents provide a simpler architecture with better parallelization.
"""

from __future__ import annotations

from maverick.agents.reviewers.review_fixer import (
    ReviewFixerAgent,
    build_fixer_input,
    build_fixer_input_from_legacy,
)
from maverick.agents.reviewers.simple_fixer import SimpleFixerAgent, fix_findings
from maverick.agents.reviewers.spec_reviewer import SpecReviewerAgent
from maverick.agents.reviewers.technical_reviewer import TechnicalReviewerAgent
from maverick.agents.reviewers.unified_reviewer import UnifiedReviewerAgent
from maverick.agents.reviewers.utils import parse_findings, validate_findings

__all__ = [
    # Unified (preferred)
    "UnifiedReviewerAgent",
    "SimpleFixerAgent",
    "fix_findings",
    # Legacy
    "ReviewFixerAgent",
    "SpecReviewerAgent",
    "TechnicalReviewerAgent",
    "build_fixer_input",
    "build_fixer_input_from_legacy",
    "parse_findings",
    "validate_findings",
]
