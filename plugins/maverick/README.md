# Maverick

AI-powered development workflow automation for Claude Code. Maverick orchestrates multi-phase workflows including feature implementation, code review, convention updates, and PR management.

## Installation

From the maverick-plugins marketplace:

```
/plugin marketplace add get2knowio/maverick
/plugin install maverick
```

## Usage

### Prerequisites

Your project must have:
- A Git repository with a remote origin
- A `specs/<branch-name>/` directory containing specification files
- A `specs/<branch-name>/tasks.md` file with the task list

### Running the Workflow

```
/fly
```

Or specify a branch:

```
/fly feature-branch
```

### Tech Debt Refuel

Pick up and fix tech-debt issues automatically:

```
/refuel
```

Or specify a custom label:

```
/refuel bugs
```

### Task File Format

Create `specs/<branch-name>/tasks.md` with your task list:

```markdown
## Tasks

- [ ] Initialize project configuration
- [ ] Set up database schema
- [x] Configure linting rules (already done)

## Parallel Tasks

Adjacent tasks marked with "P" execute in parallel:

- [ ] P: Implement user authentication
- [ ] P: Implement session management
- [ ] P: Add rate limiting
- [ ] Integrate auth with API endpoints (runs after parallel tasks)
```

## Workflow Phases

### Part 0: Setup and Sync
- Switches to the target branch (if specified)
- Rebases onto `origin/main`
- Validates the spec directory and tasks file exist
- Sends notifications via ntfy.sh (if configured)

### Part 1: Feature Implementation
- Parses the tasks file and identifies incomplete tasks
- Spawns subagents for each task (parallel when marked with "P:")
- Each subagent invokes `/speckit.implement` with the task and spec directory
- Marks tasks complete and runs build verification

### Part 2: Code Review and Improvement
1. **Parallel Reviews**: Runs CodeRabbit review and architecture/spec compliance review simultaneously
2. **Consolidate**: Deduplicates and categorizes findings (CRITICAL/MAJOR/MINOR/STYLE)
3. **Execute Fixes**: Spawns subagents to fix issues in parallel batches
4. **Validate**: Runs the full test suite, fixing any failures (up to 5 iterations)

### Part 3: Convention Update
- Synthesizes learnings from code review
- Invokes `/speckit.constitution` to update CLAUDE.md and project conventions
- Documents recurring patterns and anti-patterns

### Part 4: PR Management
- Generates a comprehensive PR description with implementation summary
- Creates or updates the pull request via GitHub CLI
- Reports the PR URL

## Agents

| Agent | Purpose |
|-------|---------|
| `rust-code-reviewer` | Senior Rust code reviewer with expertise in safety, idioms, and architecture |
| `speckit-rust-implementer` | Implements speckit specifications systematically with full test coverage |
| `spec-compliance-reviewer` | Validates implementations against specifications and standards |
| `issue-implementer` | Implements fixes for GitHub issues (tech-debt) with full completion |

## Skills

| Skill | Purpose |
|-------|---------|
| `code-review-workflow` | Parallel CodeRabbit + architecture review, consolidates findings, executes fixes |
| `validation-workflow` | Runs format/lint/build/tests, iteratively fixes failures |

## Scripts

| Script | Purpose |
|--------|---------|
| `sync-branch.sh` | Syncs branch with origin/main, validates spec directory exists |
| `get-changed-files.sh` | Returns JSON list of files changed vs base branch |
| `run-validation.sh` | Auto-detects project type and runs appropriate checks |
| `manage-pr.sh` | Creates or updates a GitHub PR |
| `notify.sh` | Sends notifications to ntfy.sh |

## Notifications

Maverick can send push notifications via [ntfy.sh](https://ntfy.sh):

```bash
export NTFY_TOPIC=my-dev-notifications
# Optional: custom server
export NTFY_SERVER=ntfy.example.com
```

Events: `spec_start`, `review`, `testing`, `complete`, `error`

## Dependencies

Maverick expects these slash commands to be available:
- `/speckit.implement` - Task implementation command
- `/speckit.constitution` - Convention update command

## License

MIT
