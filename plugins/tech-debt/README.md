# Tech Debt

Technical debt analysis and delegation for Claude Code. Analyzes tech debt issues for optimal parallel assignment and delegates to Copilot for async resolution.

## Installation

From the maverick-plugins marketplace:

```
/plugin marketplace add get2knowio/maverick
/plugin install tech-debt
```

## Usage

```
/techdebt.delegate
```

This command will:
1. Retrieve all open tech debt issues from GitHub
2. Analyze each issue for conflict potential and criticality
3. Select up to 3 non-conflicting issues for parallel work
4. Assign selected issues to Copilot
5. Generate a structured summary report

## Workflow Phases

### Phase 1: Issue Discovery

Retrieves all open tech debt issues:

```bash
gh issue list --label tech-debt --state open --json number,title,body,labels,createdAt,url --limit 50
```

### Phase 2: Codebase Impact Analysis

Uses the `tech-debt-delegator` agent to analyze issues for:
- **Scope Classification**: isolated, localized, cross-cutting, or architectural
- **Criticality Factors**: Security, reliability, performance, maintainability
- **Conflict Potential**: Which issues touch the same files/modules

### Phase 3: Assignment Execution

For each selected issue:
```bash
gh issue edit <number> --add-assignee "@copilot"
```

### Phase 4: Summary Report

Generates a markdown report with:
- Assigned issues (with rationale)
- Deferred issues (with reasons)
- Conflict analysis matrix
- Recommendations for next round

## Agents

| Agent | Purpose |
|-------|---------|
| `tech-debt-delegator` | Analyzes tech debt for parallel assignment potential |

## Selection Criteria

Issues are prioritized by:
1. **Age** - Older debt accumulates more interest
2. **Criticality** - Security/reliability before aesthetics
3. **Isolation** - Easier to review, less conflict risk
4. **Definition** - Clear acceptance criteria enable faster resolution
5. **Proportionality** - Appropriate scope for async resolution

Issues are avoided if they:
- Require architectural decisions
- Have unclear requirements
- Depend on unresolved design questions
- Touch the same hot spots as other selected issues

## Output Example

```markdown
## Tech Debt Delegation Summary

### Assigned to Copilot
| Issue | Title | Age | Criticality | Rationale |
|-------|-------|-----|-------------|-----------|
| #42   | Fix deprecated API usage | 30d | Medium | Isolated to single module |

### Not Assigned (This Round)
| Issue | Title | Reason |
|-------|-------|--------|
| #38   | Refactor auth | Conflicts with #42 on shared utils |

### Conflict Analysis
Issues #42 and #45 can be worked in parallel as they touch
different modules with no shared dependencies.
```

## Requirements

- [GitHub CLI](https://cli.github.com/) (`gh`) authenticated
- Issues labeled with `tech-debt`
- Copilot available for assignment

## License

MIT
