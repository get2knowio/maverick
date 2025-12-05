# Tech Debt Delegation Workflow

Analyze open tech debt issues and delegate up to 3 non-conflicting issues to Copilot for parallel resolution.

## Phase 1: Issue Discovery

Retrieve all open tech debt issues:

```bash
gh issue list --label tech-debt --state open --json number,title,body,labels,createdAt,url --limit 50
```

Parse the JSON output and note:
- Issue number and title
- Creation date (for prioritizing oldest issues)
- Labels (for identifying criticality and affected components)
- Issue body (for understanding scope and dependencies)

## Phase 2: Codebase Impact Analysis

Use the tech-debt-delegator agent to analyze the issues:

```
Analyze the following tech debt issues for parallel work assignment:

[PASTE ISSUE LIST JSON]

For each issue:
1. Identify the files/modules likely to be modified
2. Assess criticality based on:
   - Security implications
   - Performance impact
   - Developer productivity impact
   - Code maintainability
3. Estimate conflict potential with other issues
4. Consider age (older issues should be weighted higher)

Select <= 3 issues that:
- Can be worked on in parallel without merge conflicts
- Have minimal overlapping file changes
- Balance criticality with isolation
- Favor older issues when criticality is equal

Return a structured report with:
- Selected issues (numbered, with rationale)
- Rejected issues (with brief explanation)
- Conflict analysis (why selected issues won't conflict)
```

## Phase 3: Assignment Execution

For each selected issue, assign to Copilot:

```bash
gh issue edit <number> --add-assignee "@copilot"
```

After each assignment, confirm success:

```bash
gh issue view <number> --json assignees
```

## Phase 4: Summary Report

Generate a summary:

```markdown
## Tech Debt Delegation Summary

### Assigned to Copilot
| Issue | Title | Age | Criticality | Rationale |
|-------|-------|-----|-------------|-----------|
| #XXX  | ...   | Xd  | High/Med/Low | ... |

### Not Assigned (This Round)
| Issue | Title | Reason |
|-------|-------|--------|
| #YYY  | ...   | Conflicts with #XXX on module Z |

### Conflict Analysis
[Brief explanation of why selected issues can be worked in parallel]

### Next Steps
- Monitor Copilot PRs for the assigned issues
- Re-run this workflow after assignments complete to pick up remaining debt
```

## Execution Notes

- Maximum 3 issues per delegation run to avoid overwhelming review capacity
- Issues already assigned to someone (including Copilot) should be skipped
- If fewer than 3 non-conflicting issues exist, assign what's available
- Prefer issues with clear acceptance criteria and well-defined scope
