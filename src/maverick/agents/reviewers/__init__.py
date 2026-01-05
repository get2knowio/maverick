"""Specialized code review agents.

This package provides focused review agents that each examine code from
a specific perspective:

- SpecReviewerAgent: Reviews for spec compliance and completeness
- TechnicalReviewerAgent: Reviews for technical quality and best practices
- ReviewFixerAgent: Fixes issues identified by reviewers

These agents work together in the review workflow to provide comprehensive
code review coverage with automatic issue resolution.
"""

from __future__ import annotations

from maverick.agents.reviewers.review_fixer import (
    ReviewFixerAgent,
    build_fixer_input,
    build_fixer_input_from_legacy,
)
from maverick.agents.reviewers.spec_reviewer import SpecReviewerAgent
from maverick.agents.reviewers.technical_reviewer import TechnicalReviewerAgent
from maverick.agents.reviewers.utils import parse_findings, validate_findings

__all__ = [
    "ReviewFixerAgent",
    "SpecReviewerAgent",
    "TechnicalReviewerAgent",
    "build_fixer_input",
    "build_fixer_input_from_legacy",
    "parse_findings",
    "validate_findings",
]
