# Unified Review-Fix Workflow

## Overview

Simplify the current multi-agent review architecture into a single unified reviewer
that leverages Claude's native subagent spawning, followed by an iterative fixer loop.

## Current Architecture (Complex)

```
SpecReviewer ──────┐
                   ├──► create_issue_registry() ──► IssueRegistry ──► FixerLoop
TechnicalReviewer ─┘         (dedup/merge)           (complex)
```

**Problems**:
- Two separate agent classes with overlapping concerns
- Complex consolidation logic (`create_issue_registry`, `_is_duplicate`, severity mapping)
- Heavy data models (`TrackedFinding`, `FixAttempt`, `IssueRegistry`)
- YAML fragment is 280+ lines

## Proposed Architecture (Simple)

```
UnifiedReviewer ──► FindingsList ──► FixerLoop ──► Tracker ──► CreateIssues
    (spawns          (structured)     (N passes)   (simple)    (remaining)
     subagents)
```

## Components

### 1. UnifiedReviewer Agent

Single agent with a prompt that spawns parallel expert subagents:

```python
UNIFIED_REVIEWER_PROMPT = """
Review the work on this branch by spawning two parallel subagents:

1. **Python Expert** - Reviews for:
   - Idiomatic Python and clean code principles
   - Proper type hints and async patterns
   - Pydantic usage and 3rd party library standards per CLAUDE.md

2. **Speckit Expert** - Reviews against @specs/{feature_name}/:
   - Feature completeness vs spec requirements
   - Data model compliance
   - API contracts and integration points

Combine all findings into a single list. For each finding provide:
- file: path relative to repo root
- line: line number or range (e.g., "45" or "45-67")
- issue: clear description of the problem
- severity: critical | major | minor
- category: one of [spec_gap, library_standards, clean_code, type_hints, testing, data_model]
- fix_hint: brief suggestion for how to fix (optional)

Group findings by which can be fixed independently (different files, no dependencies).
Output as JSON matching this schema:

{
  "groups": [
    {
      "description": "Independent fixes - batch 1",
      "findings": [
        {
          "id": "F001",
          "file": "src/maverick/foo.py",
          "line": "45-67",
          "issue": "Uses raw subprocess instead of CommandRunner",
          "severity": "major",
          "category": "library_standards",
          "fix_hint": "Use CommandRunner from maverick.runners.command"
        }
      ]
    }
  ]
}
"""
```

**Output Model**:

```python
@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    file: str
    line: str
    issue: str
    severity: Literal["critical", "major", "minor"]
    category: str
    fix_hint: str | None = None

@dataclass(frozen=True, slots=True)
class FindingGroup:
    description: str
    findings: tuple[Finding, ...]

@dataclass(frozen=True, slots=True)
class ReviewResult:
    groups: tuple[FindingGroup, ...]
```

### 2. Finding Tracker (Simplified)

Replace heavy `IssueRegistry` with simple tracking:

```python
@dataclass
class TrackedFinding:
    finding: Finding
    status: Literal["open", "fixed", "blocked", "deferred"]
    attempts: list[FixAttempt] = field(default_factory=list)

@dataclass
class FixAttempt:
    timestamp: datetime
    outcome: Literal["fixed", "blocked", "deferred"]
    explanation: str

class FindingTracker:
    """Simple tracker for findings across fix iterations."""

    def __init__(self, review_result: ReviewResult):
        self._findings: dict[str, TrackedFinding] = {}
        for group in review_result.groups:
            for finding in group.findings:
                self._findings[finding.id] = TrackedFinding(
                    finding=finding,
                    status="open"
                )

    def get_open_findings(self) -> list[Finding]:
        """Get findings that still need fixing."""
        return [tf.finding for tf in self._findings.values()
                if tf.status == "open"]

    def get_actionable_findings(self) -> list[Finding]:
        """Get open + deferred (for retry) findings."""
        return [tf.finding for tf in self._findings.values()
                if tf.status in ("open", "deferred")]

    def record_outcome(self, finding_id: str, outcome: str, explanation: str):
        """Record the result of a fix attempt."""
        tf = self._findings[finding_id]
        tf.attempts.append(FixAttempt(
            timestamp=datetime.now(),
            outcome=outcome,
            explanation=explanation
        ))
        if outcome == "fixed":
            tf.status = "fixed"
        elif outcome == "blocked":
            tf.status = "blocked"
        # deferred stays actionable for retry

    def get_unresolved(self) -> list[TrackedFinding]:
        """Get findings that weren't fixed (for issue creation)."""
        return [tf for tf in self._findings.values()
                if tf.status in ("blocked", "deferred")]

    def is_complete(self) -> bool:
        """Check if all findings are resolved."""
        return all(tf.status in ("fixed", "blocked")
                   for tf in self._findings.values())
```

### 3. Fixer Agent

Simplified fixer that takes a batch of findings:

```python
FIXER_PROMPT = """
You are a code fixer. For each finding in the list below, either:
1. **Fix it** - Make the necessary code changes
2. **Block it** - If truly unfixable (missing dependencies, architectural issue)
3. **Defer it** - If you need more context or hit an unexpected issue

You MUST report on EVERY finding. Do not silently skip any.

Findings to fix:
{findings_json}

After attempting fixes, output JSON:
{
  "outcomes": [
    {
      "id": "F001",
      "outcome": "fixed",
      "explanation": "Replaced subprocess.run with CommandRunner"
    },
    {
      "id": "F002",
      "outcome": "blocked",
      "explanation": "Requires GitPython which is not installed"
    }
  ]
}
"""
```

### 4. Workflow

```python
async def review_and_fix(
    feature_name: str,
    max_iterations: int = 5,
) -> ReviewFixResult:
    """Run unified review and iterative fix loop."""

    # Step 1: Run unified review
    reviewer = UnifiedReviewerAgent(feature_name=feature_name)
    review_result = await reviewer.run()

    # Step 2: Initialize tracker
    tracker = FindingTracker(review_result)

    # Step 3: Fix loop
    fixer = FixerAgent()
    iteration = 0

    while not tracker.is_complete() and iteration < max_iterations:
        iteration += 1

        # Get findings to fix this iteration
        findings = tracker.get_actionable_findings()
        if not findings:
            break

        # Run fixer
        outcomes = await fixer.fix(findings)

        # Record outcomes
        for outcome in outcomes:
            tracker.record_outcome(
                outcome.id,
                outcome.outcome,
                outcome.explanation
            )

    # Step 4: Create issues for unresolved
    unresolved = tracker.get_unresolved()
    issues_created = []
    for tf in unresolved:
        issue_url = await create_github_issue(tf)
        issues_created.append(issue_url)

    return ReviewFixResult(
        total_findings=len(tracker._findings),
        fixed=len([tf for tf in tracker._findings.values() if tf.status == "fixed"]),
        blocked=len([tf for tf in tracker._findings.values() if tf.status == "blocked"]),
        issues_created=issues_created,
    )
```

## Migration Path

### Remove
- `src/maverick/agents/reviewers/spec_reviewer.py`
- `src/maverick/agents/reviewers/technical_reviewer.py`
- `src/maverick/library/actions/review_registry.py` (most of it)
- `src/maverick/library/fragments/review-and-fix-with-registry.yaml`
- `src/maverick/models/review_registry.py` (most of it)

### Simplify
- `src/maverick/agents/reviewers/review_fixer.py` → simpler input/output
- `src/maverick/models/fixer_io.py` → simpler models

### Add
- `src/maverick/agents/reviewers/unified_reviewer.py`
- `src/maverick/models/review_models.py` (simple Finding/Tracker models)

## Key Differences

| Aspect | Current | Proposed |
|--------|---------|----------|
| Reviewer agents | 2 separate classes | 1 agent spawning subagents |
| Output format | Complex typed models | Simple JSON with Finding dataclass |
| Consolidation | Python code (dedup, merge) | Done by reviewer prompt |
| Parallelization | Workflow orchestrates | Reviewer groups, fixer handles |
| Tracking | IssueRegistry (heavy) | FindingTracker (simple dict) |
| Lines of code | ~2500+ | ~500 estimated |

## Design Decisions

1. **Fixer receives all findings** - Pass all findings (with grouping hints) to fixer, which spawns
   its own subagents to work in parallel where applicable. Reports back status for each finding.

2. **Max 2 retries for deferred** - After 2 unsuccessful attempts, treat deferred as blocked.

3. **Simple justification handling** - Trust fixer output, don't over-validate. Flag suspicious
   justifications in issue body if created.

4. **Keep file deletion handling** - Check path existence before fix attempt, auto-block if deleted.

## Fixer Subagent Strategy

The fixer prompt instructs the agent to:
1. Receive all findings with their parallelization groupings
2. Spawn subagents to work on independent batches in parallel
3. Report outcome for each finding (fixed/blocked/deferred)
4. Return consolidated results

```python
FIXER_PROMPT = """
You are a code fixer. You will receive a list of findings grouped by parallelization opportunity.

For each group of independent findings, spawn a subagent to fix them in parallel.
Wait for all subagents to complete before returning results.

For each finding, the outcome must be one of:
- **fixed**: Code changes made successfully
- **blocked**: Cannot fix (missing dependency, architectural constraint, requires human decision)
- **deferred**: Need more context or hit unexpected issue (will retry)

You MUST report on EVERY finding. Silent skipping is not allowed.

{findings_with_groups}

Output JSON with outcomes for all findings:
{{
  "outcomes": [
    {{"id": "F001", "outcome": "fixed", "explanation": "..."}},
    {{"id": "F002", "outcome": "blocked", "explanation": "..."}},
    ...
  ]
}}
"""
```

## Iteration Flow

```
Round 1: All findings → Fixer (spawns parallel subagents) → Outcomes
         Filter: keep deferred items (attempt 1)

Round 2: Deferred items → Fixer → Outcomes
         Filter: keep deferred items (attempt 2)

Round 3: Remaining deferred → Fixer → Outcomes
         Any still deferred → treat as blocked

Final:   Blocked items → Create GitHub issues
```
