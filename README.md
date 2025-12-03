# Maverick

A Claude Code plugin for AI-powered development workflow automation. Maverick orchestrates multi-phase workflows including feature implementation, code review, convention updates, and PR management.

## What is Maverick?

Maverick is a [slash command](https://docs.anthropic.com/en/docs/claude-code/slash-commands) for Claude Code that automates the full development cycle:

1. **Feature Implementation** - Execute tasks from a structured task list using parallel subagents
2. **Code Review** - Run automated reviews (CodeRabbit + architecture analysis) and fix issues
3. **Convention Learning** - Update project conventions based on review findings
4. **PR Management** - Create or update pull requests with comprehensive summaries

It follows a spec-driven development model where each feature branch has a corresponding specification directory containing requirements and a task list.

## Installation

### Option 1: Copy files (recommended for most users)

```bash
# From your target project root
mkdir -p .claude/commands .claude/scripts

# Copy command and scripts
cp path/to/maverick/src/commands/fly.md .claude/commands/project:fly.md
cp path/to/maverick/src/scripts/*.sh .claude/scripts/

# Make scripts executable
chmod +x .claude/scripts/*.sh
```

### Option 2: Symlink (recommended for Maverick development)

```bash
# From your target project root
mkdir -p .claude/commands

# Symlink command and scripts directory
ln -s /absolute/path/to/maverick/src/commands/fly.md .claude/commands/project:fly.md
ln -s /absolute/path/to/maverick/src/scripts .claude/scripts
```

### Option 3: Configure permissions

Optionally merge Maverick's permission settings with your project's Claude Code configuration:

```bash
# View the recommended permissions
cat path/to/maverick/src/settings.json

# Merge with your .claude/settings.json as needed
```

The `settings.json` includes:
- Pre-approved permissions for common development tools (git, npm, cargo, go, python, etc.)
- Hook configurations for auto-approving permissions and error notifications

## Usage

### Prerequisites

Your project must have:
- A Git repository with a remote origin
- A `specs/<branch-name>/` directory containing specification files
- A `specs/<branch-name>/tasks.md` file with the task list

### Running the Workflow

In Claude Code, run:

```
/project:fly
```

Or specify a branch:

```
/project:fly feature-branch
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

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `sync-branch.sh` | Syncs branch with origin/main, validates spec directory exists. Returns JSON status. |
| `get-changed-files.sh` | Returns JSON list of files changed vs base branch with status (A/M/D/R). |
| `run-validation.sh` | Auto-detects project type (Rust/Node/Python/Go) and runs appropriate checks. Returns JSON results. |
| `manage-pr.sh` | Creates or updates a GitHub PR. Returns JSON with action and URL. |
| `notify.sh` | Sends notifications to ntfy.sh when `NTFY_TOPIC` is set. |

## Notifications

Maverick can send push notifications via [ntfy.sh](https://ntfy.sh) for workflow events:

```bash
# Set your ntfy topic
export NTFY_TOPIC=my-dev-notifications

# Optional: use a custom ntfy server
export NTFY_SERVER=ntfy.example.com
```

Events notified:
- `spec_start` - Workflow started
- `testing` - Entered validation phase
- `complete` - All tasks completed, PR created
- `error` - Errors or conflicts detected

## Project Structure

```
src/
├── commands/
│   └── fly.md              # Main workflow slash command
├── scripts/
│   ├── sync-branch.sh      # Branch sync and validation
│   ├── get-changed-files.sh # Git diff helper
│   ├── run-validation.sh   # Project validation runner
│   ├── manage-pr.sh        # GitHub PR management
│   └── notify.sh           # Push notifications
└── settings.json           # Claude Code permissions config
```

## Requirements

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR management
- Git repository with remote origin
- Optional: [CodeRabbit CLI](https://coderabbit.ai/) for enhanced code review
- Optional: [ntfy](https://ntfy.sh) for push notifications

## Dependencies

Maverick expects these slash commands to be available in your project:
- `/speckit.implement` - Task implementation command
- `/speckit.constitution` - Convention update command

These are part of the [Speckit](https://github.com/example/speckit) framework (or implement your own).

## License

MIT
